import asyncio
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

import aiosmtplib
import httpx
from openai import APIError, AsyncOpenAI, DefaultAsyncHttpxClient
from pydantic import ValidationError

if TYPE_CHECKING or __package__:
    from .config import Settings, configure_logging, load_settings
    from .models import (
        RedditListing,
        RedditPost,
        RedditPostPayload,
        RedditToken,
        SummaryPost,
    )
    from .templates.email_template import generate_email_template
else:
    from config import Settings, configure_logging, load_settings
    from models import (
        RedditListing,
        RedditPost,
        RedditPostPayload,
        RedditToken,
        SummaryPost,
    )
    from templates.email_template import generate_email_template

logger = logging.getLogger(__name__)

REDDIT_AUTH_URL = "https://www.reddit.com/api/v1/access_token"
REDDIT_BASE_URL = "https://oauth.reddit.com"
REDDIT_SORTS = {"hot", "rising", "new"}
MAX_CONCURRENCY = 4
CLI_SUBREDDITS = [
    "LocalLLaMA",
    "singularity",
    "LocalLLM",
    "codex",
    "machinelearningnews",
    "AI_Agents",
]
API_SUBREDDITS = ["LocalLLaMA", "reactjs", "Python", "javascript"]


class DigestError(Exception):
    pass


class UpstreamError(DigestError):
    pass


class NoPostsError(DigestError):
    pass


class EmailDeliveryError(DigestError):
    pass


@dataclass
class DigestService:
    settings: Settings
    reddit: httpx.AsyncClient
    llm: AsyncOpenAI
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def send_digest(
        self,
        subreddits: list[str],
        posts_per_sub: int,
        batch_size: int,
        *,
        hot: bool = False,
    ) -> int:
        async with asyncio.timeout(self.settings.digest_timeout_seconds):
            posts = await fetch_multiple_subreddits(
                subreddits,
                posts_per_sub,
                reddit_client=self.reddit,
                settings=self.settings,
            )
            if not posts:
                raise NoPostsError("No posts were available for the digest")
            summary_text = await get_llm_summaries_in_batches(
                posts, batch_size, client=self.llm, model=self.settings.openai_model
            )
            source_posts = {post["permalink"]: post for post in posts}
            formatted_posts: list[SummaryPost] = []
            seen_links: set[str] = set()
            for summary in parse_summaries(summary_text):
                source = source_posts.get(summary["link"])
                if (
                    source is None
                    or summary["link"] in seen_links
                    or not summary["summary"]
                ):
                    continue
                seen_links.add(summary["link"])
                formatted_posts.append(
                    {
                        "subreddit": source["subreddit"],
                        "title": source["title"],
                        "link": source["permalink"],
                        "summary": summary["summary"],
                    }
                )
            if not formatted_posts:
                raise UpstreamError("The model returned no usable summaries")
            if len(formatted_posts) < len(posts):
                logger.warning(
                    "Digest contains %s of %s fetched posts",
                    len(formatted_posts),
                    len(posts),
                )

            html = create_condensed_html_email(
                formatted_posts, subreddits, max_display=100
            )
            title = (
                f"Reddit Digest (HOT) - {datetime.now():%Y-%m-%d}"
                if hot
                else "Reddit Digest"
            )
            plain = create_plain_text_email(
                formatted_posts, len(subreddits), title=title
            )
            subject = (
                f"🔥 Reddit Digest - HOT ({len(formatted_posts)} posts) - {datetime.now():%b %d}"
                if hot
                else f"Reddit Digest ({len(formatted_posts)} posts)"
            )
            if not await send_email(
                subject,
                html,
                plain,
                self.settings.to_email,
                self.settings.gmail_email,
                self.settings.gmail_app_password.get_secret_value(),
            ):
                raise EmailDeliveryError(
                    "Email delivery failed or its outcome is unknown"
                )
            return len(formatted_posts)


@asynccontextmanager
async def open_digest_service(settings: Settings) -> AsyncIterator[DigestService]:
    async with (
        get_reddit_client(settings) as reddit,
        get_openai_client(settings) as llm,
    ):
        yield DigestService(settings, reddit, llm)


def _shorten(value: str, max_length: int = 120) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= max_length:
        return cleaned
    return f"{cleaned[: max_length - 1]}…"


def get_openai_client(settings: Settings) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.openai_api_key.get_secret_value()
        if settings.openai_api_key
        else "",
        base_url=str(settings.openai_base_url),
        max_retries=0,
        timeout=httpx.Timeout(120.0, connect=10.0, pool=10.0),
        http_client=DefaultAsyncHttpxClient(
            limits=httpx.Limits(
                max_connections=MAX_CONCURRENCY,
                max_keepalive_connections=MAX_CONCURRENCY,
            )
        ),
    )


def get_reddit_client(settings: Settings) -> httpx.AsyncClient:
    """Create a scoped async Reddit API client."""
    return httpx.AsyncClient(
        base_url=REDDIT_BASE_URL,
        headers={"User-Agent": settings.reddit_user_agent},
        timeout=httpx.Timeout(20.0, connect=10.0),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )


async def get_reddit_access_token(
    reddit_client: httpx.AsyncClient, settings: Settings
) -> str:
    """Fetch an application-only Reddit OAuth token."""
    logger.info("Authenticating with Reddit API")
    response = await reddit_client.post(
        REDDIT_AUTH_URL,
        auth=(
            settings.client_id.get_secret_value(),
            settings.client_secret.get_secret_value(),
        ),
        data={"grant_type": "client_credentials"},
    )
    response.raise_for_status()

    access_token = RedditToken.model_validate_json(response.content).access_token
    logger.info("Reddit API authentication succeeded")
    return access_token


async def fetch_reddit_listing(
    reddit_client: httpx.AsyncClient,
    access_token: str,
    subreddit: str,
    sort_type: str,
    limit: int,
) -> list[dict[str, object]]:
    """Fetch one Reddit listing and return raw post payloads."""
    logger.info(
        "Fetching Reddit listing r/%s/%s limit=%s",
        subreddit,
        sort_type,
        limit,
    )
    response = await reddit_client.get(
        f"/r/{subreddit}/{sort_type}.json",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"limit": limit, "raw_json": 1},
    )
    response.raise_for_status()

    listing = RedditListing.model_validate_json(response.content)
    posts = [child.data for child in listing.data.children]
    logger.info(
        "Fetched %s raw Reddit threads from r/%s/%s",
        len(posts),
        subreddit,
        sort_type,
    )
    return posts


def normalize_reddit_post(post_data: dict[str, object]) -> RedditPost | None:
    """Convert Reddit API post JSON into summarizer input."""
    if post_data.get("stickied"):
        return None

    try:
        post = RedditPostPayload.model_validate(post_data)
    except ValidationError:
        logger.warning("Skipping malformed Reddit post")
        return None

    permalink = f"https://reddit.com{post.permalink}"
    url = post.url or permalink
    selftext = post.selftext if post.is_self else ""

    return {
        "title": post.title,
        "author": post.author or "[deleted]",
        "score": post.score,
        "num_comments": post.num_comments,
        "created_utc": post.created_utc,
        "subreddit": post.subreddit,
        "permalink": permalink,
        "url": url,
        "is_self": post.is_self,
        "selftext": selftext,
        "upvote_ratio": post.upvote_ratio,
        "content_type": "text" if post.is_self else "link",
        "content": selftext if post.is_self else f"External link to: {url}",
    }


async def fetch_multiple_subreddits(
    subreddit_list: list[str],
    posts_per_sub: int = 3,
    sort_type: str = "hot",
    *,
    reddit_client: httpx.AsyncClient,
    settings: Settings,
) -> list[RedditPost]:
    if not 1 <= posts_per_sub <= 100:
        raise ValueError("posts_per_sub must be between 1 and 100")
    if sort_type not in REDDIT_SORTS:
        raise ValueError("sort_type must be hot, rising, or new")
    if any(not re.fullmatch(r"[A-Za-z0-9_]+", name) for name in subreddit_list):
        raise ValueError("Invalid subreddit name")
    if not subreddit_list:
        return []

    try:
        access_token = await get_reddit_access_token(reddit_client, settings)
    except (httpx.HTTPError, ValidationError) as exc:
        logger.error("Reddit authentication failed: %s", type(exc).__name__)
        raise UpstreamError("Reddit authentication failed") from exc

    successful_listings = 0

    async def fetch_subreddit_posts(sub_name: str) -> list[RedditPost]:
        nonlocal successful_listings
        posts: list[RedditPost] = []
        seen_links: set[str] = set()
        listings = [(sort_type, posts_per_sub)]
        if sort_type == "hot":
            listings.append(("new", 3))
        for listing_sort, limit in listings:
            try:
                raw_posts = await fetch_reddit_listing(
                    reddit_client, access_token, sub_name, listing_sort, limit
                )
            except (httpx.HTTPError, ValidationError) as exc:
                logger.warning(
                    "Reddit listing failed for r/%s/%s: %s",
                    sub_name,
                    listing_sort,
                    type(exc).__name__,
                )
                continue
            successful_listings += 1
            for raw_post in raw_posts:
                post = normalize_reddit_post(raw_post)
                if post is None or post["permalink"] in seen_links:
                    continue
                seen_links.add(post["permalink"])
                posts.append(post)
                logger.info(
                    "Queued Reddit thread r/%s: %s",
                    post["subreddit"],
                    _shorten(post["title"]),
                )
        return posts

    all_posts: list[RedditPost] = []
    for offset in range(0, len(subreddit_list), MAX_CONCURRENCY):
        async with asyncio.TaskGroup() as group:
            tasks = [
                group.create_task(fetch_subreddit_posts(name))
                for name in subreddit_list[offset : offset + MAX_CONCURRENCY]
            ]
        for task in tasks:
            all_posts.extend(task.result())
    if not successful_listings:
        raise UpstreamError("All Reddit listings failed")
    logger.info("Completed Reddit fetch with %s normalized threads", len(all_posts))
    return all_posts


def create_summary_prompt_batch(
    posts_batch: list[RedditPost], batch_num: int, total_batches: int
) -> str:
    """Create a prompt for a batch of posts."""
    prompt = f"""You are creating a Reddit digest email (batch {batch_num} of {total_batches}).
Summarize these {len(posts_batch)} posts concisely. Each summary should be 1-2 sentences maximum.

Format EXACTLY as follows for parsing:

[SUBREDDIT: subreddit_name]
[TITLE: Post title here]
[LINK: permalink_url]
[SUMMARY: One sentence summary - focus on the main point only]
[END]

Posts to summarize:
"""
    for i, post in enumerate(posts_batch, 1):
        prompt += f"\nPOST {i}:\n"
        prompt += f"Subreddit: r/{post['subreddit']}\n"
        prompt += f"Title: {post['title']}\n"
        prompt += f"Score: {post['score']} | Comments: {post['num_comments']}\n"
        prompt += f"Content: {post['content'][:2000]}...\n"
        prompt += f"Link: {post['permalink']}\n"
        prompt += "-" * 30 + "\n"
    return prompt


async def get_llm_summaries_in_batches(
    posts_data: list[RedditPost],
    batch_size: int = 8,
    *,
    client: AsyncOpenAI,
    model: str,
) -> str:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if not posts_data:
        return ""
    total_batches = (len(posts_data) + batch_size - 1) // batch_size

    async def process_batch(batch: list[RedditPost], batch_num: int) -> str:
        logger.info(
            "Summarizing Reddit batch %s/%s with %s threads",
            batch_num,
            total_batches,
            len(batch),
        )
        try:
            response = await client.responses.create(
                model=model,
                input=create_summary_prompt_batch(batch, batch_num, total_batches),
                temperature=1,
                max_output_tokens=4096,
            )
        except APIError as exc:
            logger.warning(
                "LLM batch %s/%s failed: %s",
                batch_num,
                total_batches,
                type(exc).__name__,
            )
            return ""
        content = response.output_text
        if not content.strip():
            logger.warning("LLM batch %s/%s returned no text", batch_num, total_batches)
            return ""
        if not content.rstrip().endswith("[END]"):
            logger.warning(
                "Batch %s/%s output appears truncated", batch_num, total_batches
            )
        return content

    summaries: list[str] = []
    for first_batch in range(0, total_batches, MAX_CONCURRENCY):
        async with asyncio.TaskGroup() as group:
            tasks = [
                group.create_task(
                    process_batch(
                        posts_data[index * batch_size : (index + 1) * batch_size],
                        index + 1,
                    )
                )
                for index in range(
                    first_batch, min(first_batch + MAX_CONCURRENCY, total_batches)
                )
            ]
        summaries.extend(task.result() for task in tasks if task.result())
    if not summaries:
        raise UpstreamError("All summarization batches failed")
    return "\n".join(summaries)


def parse_summaries(summary_text: str) -> list[SummaryPost]:
    """Parse the LLM summary text into structured data.

    Tolerant of a missing final [END] marker so truncated model output
    does not silently drop the last thread in a batch.
    """
    posts: list[SummaryPost] = []
    pattern = re.compile(
        r"\[SUBREDDIT:\s*(?P<subreddit>.*?)\]\s*"
        r"\[TITLE:\s*(?P<title>.*?)\]\s*"
        r"\[LINK:\s*(?P<link>.*?)\]\s*"
        r"\[SUMMARY:\s*(?P<summary>.*?)(?:\]|\Z)\s*"
        r"(?:\[END\]|(?=\[SUBREDDIT:)|\Z)",
        re.DOTALL,
    )

    for match in pattern.finditer(summary_text):
        posts.append(
            {
                "subreddit": match.group("subreddit").strip(),
                "title": match.group("title").strip(),
                "link": match.group("link").strip(),
                "summary": match.group("summary").strip(),
            }
        )

    if posts:
        matched_chars = sum(m.end() - m.start() for m in pattern.finditer(summary_text))
        unparsed = len(summary_text) - matched_chars
        logger.info(
            "Parsed %s summaries from LLM output (%s chars)",
            len(posts),
            matched_chars,
        )
        if unparsed > 20:
            logger.warning(
                "Discarded %s unparsed chars from LLM summary output", unparsed
            )
    else:
        logger.warning(
            "No summaries parsed from %s chars of LLM output", len(summary_text)
        )
    return posts


def create_condensed_html_email(
    posts_data: list[SummaryPost], subreddit_list: list[str], max_display: int = 15
) -> str:
    """Create HTML email from parsed summaries."""
    return generate_email_template(posts_data, subreddit_list, max_display=max_display)


def create_plain_text_email(
    posts_data: list[SummaryPost], subreddit_count: int, title: str = "Reddit Digest"
) -> str:
    """Create a plain text digest fallback for email clients."""
    plain_text = f"{title}\n\n"
    plain_text += f"Total posts: {len(posts_data)} from {subreddit_count} subreddits\n"
    plain_text += "=" * 60 + "\n\n"

    for post in posts_data:
        plain_text += f"[r/{post['subreddit']}] {post['title']}\n"
        plain_text += f"{post['summary']}\n"
        plain_text += f"Link: {post['link']}\n\n"

    return plain_text


async def main() -> None:
    try:
        settings = load_settings()
        configure_logging(settings)
        async with open_digest_service(settings) as service:
            await service.send_digest(CLI_SUBREDDITS, 7, 8, hot=True)
    except (ValueError, DigestError, TimeoutError) as exc:
        logger.error("Digest run failed: %s", exc)
        raise SystemExit(1) from None


async def send_email(
    subject: str,
    html_body: str,
    plain_body: str,
    to_email: str,
    from_email: str,
    from_password: str,
) -> bool:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    for port, use_tls in ((465, True), (587, False)):
        smtp = aiosmtplib.SMTP(
            hostname="smtp.gmail.com",
            port=port,
            use_tls=use_tls,
            start_tls=not use_tls,
            username=from_email,
            password=from_password,
            timeout=60,
        )
        try:
            try:
                await smtp.connect()
            except (aiosmtplib.SMTPConnectError, OSError) as exc:
                logger.warning(
                    "SMTP connection failed on port %s: %s", port, type(exc).__name__
                )
                continue
            except aiosmtplib.SMTPException as exc:
                logger.error("SMTP setup failed: %s", type(exc).__name__)
                return False

            try:
                await smtp.send_message(msg)
            except (aiosmtplib.SMTPException, OSError) as exc:
                logger.error(
                    "SMTP delivery failed; no retry after submission: %s",
                    type(exc).__name__,
                )
                return False
            logger.info("Digest email accepted by Gmail SMTP on port %s", port)
            with suppress(aiosmtplib.SMTPException, OSError):
                await smtp.quit()
            return True
        finally:
            smtp.close()
    return False


if __name__ == "__main__":
    asyncio.run(main())
