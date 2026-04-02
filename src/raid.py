import asyncio
from collections import defaultdict
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
import logging
import os
import re
import socket
import time
from typing import Any, Dict, List

import aiosmtplib
import asyncpraw
from dotenv import load_dotenv
from openai import AsyncOpenAI

from templates.email_template import generate_email_template

load_dotenv()

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

# OpenAI API client
client = AsyncOpenAI(
    api_key=os.getenv("OPEN_AI_TOKEN"),
)


async def get_reddit_client():
    """Create an async Reddit client using asyncpraw."""
    logger.debug("Creating Reddit client")
    return asyncpraw.Reddit(
        client_id=os.getenv("CLIENT_ID"),
        client_secret=os.getenv("CLIENT_SECRET"),
        user_agent="news",
    )


async def fetch_multiple_subreddits(
    subreddit_list: List[str], posts_per_sub: int = 3, sort_type: str = "hot"
) -> List[Dict[str, Any]]:
    """Fetch posts from multiple subreddits asynchronously."""
    logger.info(
        "Starting subreddit fetch for %s subreddits with sort=%s posts_per_sub=%s",
        len(subreddit_list),
        sort_type,
        posts_per_sub,
    )
    reddit = await get_reddit_client()

    async def fetch_subreddit_posts(sub_name: str) -> List[Dict[str, Any]]:
        posts = []
        track_ids = []
        logger.info("Fetching %s posts from r/%s", sort_type, sub_name)
        try:
            subreddit = await reddit.subreddit(sub_name)

            # Fetch posts based on sort_type
            if sort_type == "hot":
                post_generator = subreddit.hot(limit=posts_per_sub)
            elif sort_type == "rising":
                post_generator = subreddit.rising(limit=posts_per_sub)
            else:
                post_generator = subreddit.hot(limit=posts_per_sub)

            async for post in post_generator:
                if not post.stickied and post.name not in track_ids:
                    post_info = {
                        "title": post.title,
                        "author": str(post.author) if post.author else "[deleted]",
                        "score": post.score,
                        "num_comments": post.num_comments,
                        "created_utc": post.created_utc,
                        "subreddit": str(post.subreddit),
                        "permalink": f"https://reddit.com{post.permalink}",
                        "url": post.url,
                        "is_self": post.is_self,
                        "selftext": post.selftext if post.is_self else "",
                        "upvote_ratio": post.upvote_ratio,
                    }
                    if post.is_self:
                        post_info["content_type"] = "text"
                        post_info["content"] = post.selftext
                    else:
                        post_info["content_type"] = "link"
                        post_info["content"] = f"External link to: {post.url}"
                    posts.append(post_info)
                    track_ids.append(post.name)

            # New posts (only for hot sort type to maintain existing behavior)
            if sort_type == "hot":
                async for post in subreddit.new(limit=3):
                    if not post.stickied and post.name not in track_ids:
                        post_info = {
                            "title": post.title,
                            "author": str(post.author) if post.author else "[deleted]",
                            "score": post.score,
                            "num_comments": post.num_comments,
                            "created_utc": post.created_utc,
                            "subreddit": str(post.subreddit),
                            "permalink": f"https://reddit.com{post.permalink}",
                            "url": post.url,
                            "is_self": post.is_self,
                            "selftext": post.selftext if post.is_self else "",
                            "upvote_ratio": post.upvote_ratio,
                        }
                        if post.is_self:
                            post_info["content_type"] = "text"
                            post_info["content"] = post.selftext
                        else:
                            post_info["content_type"] = "link"
                            post_info["content"] = f"External link to: {post.url}"
                        posts.append(post_info)
                        track_ids.append(post.name)

            logger.info(
                "Fetched %s unique posts from r/%s",
                len(posts),
                sub_name,
            )
        except Exception as e:
            logger.exception("Reddit fetch failed for r/%s: %s", sub_name, e)
        return posts

    tasks = [fetch_subreddit_posts(name) for name in subreddit_list]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_posts = []
    for result in results:
        if isinstance(result, list):
            all_posts.extend(result)
        elif isinstance(result, Exception):
            logger.error("Concurrent subreddit fetch task failed: %s", result)

    await reddit.close()
    logger.info("Completed subreddit fetch with %s total posts", len(all_posts))
    return all_posts


def create_summary_prompt_batch(
    posts_batch: List[Dict[str, Any]], batch_num: int, total_batches: int
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
        prompt += f"Content: {post['content'][:500]}...\n"
        prompt += f"Link: {post['permalink']}\n"
        prompt += "-" * 30 + "\n"
    return prompt


async def get_llm_summaries_in_batches(
    posts_data: List[Dict[str, Any]], batch_size: int = 15
) -> str:
    """Process posts in batches asynchronously using OpenAI compatible API."""
    total_batches = (len(posts_data) + batch_size - 1) // batch_size if posts_data else 0
    logger.info(
        "Starting LLM summarization for %s posts in %s batches with batch_size=%s",
        len(posts_data),
        total_batches,
        batch_size,
    )

    async def process_batch(
        batch: List[Dict[str, Any]], batch_num: int, total_batches: int
    ) -> str:
        start_time = time.time()
        prompt = create_summary_prompt_batch(batch, batch_num, total_batches)
        logger.info(
            "Processing batch %s/%s with %s posts and prompt_length=%s",
            batch_num,
            total_batches,
            len(batch),
            len(prompt),
        )
        try:
            response = await client.chat.completions.create(
                model="gpt-5-nano-2025-08-07",
                messages=[{"role": "user", "content": prompt}],
                temperature=1,
            )

            content = response.choices[0].message.content
            if content is None:
                raise ValueError("Received None as response content")
            elapsed = time.time() - start_time
            logger.info("Batch %s/%s completed in %.1fs", batch_num, total_batches, elapsed)
            return content
        except Exception as e:
            logger.exception(
                "LLM batch %s/%s failed after %.1fs: %s",
                batch_num,
                total_batches,
                time.time() - start_time,
                e,
            )
            return ""

    tasks = []
    for i in range(0, len(posts_data), batch_size):
        batch = posts_data[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        tasks.append(process_batch(batch, batch_num, total_batches))

    all_summaries = await asyncio.gather(*tasks, return_exceptions=True)

    valid_summaries = []
    for summary in all_summaries:
        if isinstance(summary, str) and summary.strip():
            valid_summaries.append(summary)
        elif isinstance(summary, Exception):
            logger.error("Summarization task raised outside process_batch: %s", summary)

    logger.info(
        "Completed summarization with %s successful batches out of %s",
        len(valid_summaries),
        total_batches,
    )
    return "\n".join(valid_summaries)


def parse_summaries(summary_text: str) -> List[Dict[str, str]]:
    """Parse the LLM summary text into structured data."""
    posts = []
    pattern = re.compile(
        r"\[SUBREDDIT:\s*(?P<subreddit>.*?)\]\s*"
        r"\[TITLE:\s*(?P<title>.*?)\]\s*"
        r"\[LINK:\s*(?P<link>.*?)\]\s*"
        r"\[SUMMARY:\s*(?P<summary>.*?)\]\s*"
        r"\[END\]",
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
    return posts


def create_condensed_html_email(
    posts_data: List[Dict[str, str]], subreddit_list: List[str], max_display: int = 15
) -> str:
    """Create HTML email from parsed summaries."""
    posts_by_sub = defaultdict(list)
    for post in posts_data:
        posts_by_sub[post["subreddit"]].append(post)

    sorted_subs = sorted(posts_by_sub.items(), key=lambda x: len(x[1]), reverse=True)

    html = generate_email_template(posts_data, subreddit_list)

    html += """
        <h3 style="margin: 20px 20px 10px 20px; font-size: 18px;">📑 All Posts by Subreddit</h3>
    """

    posts_shown = 0
    for subreddit, posts in sorted_subs:
        if posts_shown >= max_display and len(posts_data) > max_display:
            remaining = len(posts_data) - posts_shown
            html += f"""
                <div class="view-more">
                    <p>📄 {remaining} more posts not shown to keep email readable</p>
                    <a href="https://reddit.com/r/{"+".join(subreddit_list)}" target="_blank">View all on Reddit →</a>
                </div>
            """
            break

        html += f"""
            <div class="subreddit-section">
                <div class="subreddit-header">
                    <span class="subreddit-name">r/{subreddit}</span>
                    <span class="post-count">{len(posts)} posts</span>
                </div>
                <div class="posts-list">
        """

        remaining_slots = max_display - posts_shown
        if remaining_slots <= 0:
            break

        for post in posts[:remaining_slots]:
            safe_link = escape(post["link"], quote=True)
            safe_title = escape(post["title"])
            safe_summary = escape(post["summary"])
            html += f"""
                <div class="post-item">
                    <div class="post-title">
                        <a href="{safe_link}" target="_blank">{safe_title}</a>
                    </div>
                    <div class="post-summary">{safe_summary}</div>
                </div>
            """
            posts_shown += 1

        html += """
                </div>
            </div>
        """

    html += """
        <div class="footer">
            <p>This digest was automatically generated using Reddit API and OpenAI LLM</p>
            <p style="margin-top: 10px;">
                <a href="https://reddit.com">Visit Reddit</a> •
            </p>
        </div>
    </div>
</body>
</html>
    """

    return html


async def main() -> None:
    subreddit_list = [
        "LocalLLaMA",
        "AI_Agents",                
        "artificial",
        "Rag",
        "aiagents",        
        "AIDeveloperNews"
    ]

    posts_per_subreddit = 10

    to_email = os.getenv("TO_EMAIL", "your-email@gmail.com")
    from_email = os.getenv("GMAIL_EMAIL")
    from_password = os.getenv("GMAIL_APP_PASSWORD")

    if not from_email or not from_password:
        logger.error("Email credentials not found in environment")
        return

    # Process HOT posts
    logger.info("Starting digest run for subreddits=%s", ",".join(subreddit_list))

    fetch_start = time.time()
    hot_posts = await fetch_multiple_subreddits(
        subreddit_list, posts_per_sub=posts_per_subreddit, sort_type="hot"
    )
    fetch_time = time.time() - fetch_start

    if hot_posts:
        logger.info("Fetched %s hot posts in %.1fs", len(hot_posts), fetch_time)
        logger.info("Starting summarization for hot posts")

        summary_start = time.time()
        summary_text = await get_llm_summaries_in_batches(hot_posts, batch_size=15)
        summary_time = time.time() - summary_start
        logger.info("Summaries completed in %.1fs", summary_time)

        formatted_posts = parse_summaries(summary_text)
        logger.info("Parsed %s formatted posts from model output", len(formatted_posts))

        html_email = create_condensed_html_email(
            formatted_posts, subreddit_list, max_display=100
        )

        plain_text = f"Reddit Digest (HOT) - {datetime.now().strftime('%Y-%m-%d')}\n\n"
        plain_text += f"Total posts: {len(formatted_posts)} from {len(subreddit_list)} subreddits\n"
        plain_text += "=" * 60 + "\n\n"

        for post in formatted_posts:
            plain_text += f"[r/{post['subreddit']}] {post['title']}\n"
            plain_text += f"{post['summary']}\n"
            plain_text += f"Link: {post['link']}\n\n"

        subject = f"🔥 Reddit Digest - HOT ({len(formatted_posts)} posts) - {datetime.now().strftime('%b %d')}"

        await send_email(
            subject, html_email, plain_text, to_email, from_email, from_password
        )
    else:
        logger.warning("No hot posts were fetched")


async def send_email(
    subject: str,
    html_body: str,
    plain_body: str,
    to_email: str,
    from_email: str,
    from_password: str,
) -> bool:
    """Send email via Gmail SMTP asynchronously."""
    try:
        logger.info(
            "Starting SMTP send to %s with subject=%s html_bytes=%s plain_bytes=%s",
            to_email,
            subject,
            len(html_body.encode("utf-8")),
            len(plain_body.encode("utf-8")),
        )
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email

        part1 = MIMEText(plain_body, "plain")
        part2 = MIMEText(html_body, "html")
        msg.attach(part1)
        msg.attach(part2)

        # Resolve to IPv4 explicitly — IPv6 is unreliable under WSL2
        smtp_ipv4 = socket.getaddrinfo(
            "smtp.gmail.com", None, socket.AF_INET
        )[0][4][0]
        logger.info("Resolved smtp.gmail.com to %s (IPv4)", smtp_ipv4)

        smtp_attempts = [
            {"port": 465, "use_tls": True, "start_tls": False, "label": "implicit TLS"},
            {"port": 587, "use_tls": False, "start_tls": True, "label": "STARTTLS"},
        ]

        last_error: Exception | None = None
        for attempt in smtp_attempts:
            connect_start = time.time()
            logger.info(
                "Trying SMTP %s on %s:%s",
                attempt["label"],
                smtp_ipv4,
                attempt["port"],
            )
            try:
                # Connect a raw IPv4 socket, then hand it to aiosmtplib
                # with hostname="smtp.gmail.com" so TLS validates correctly.
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(60)
                sock.connect((smtp_ipv4, attempt["port"]))
                sock.setblocking(False)

                smtp_client = aiosmtplib.SMTP(
                    hostname="smtp.gmail.com",
                    use_tls=attempt["use_tls"],
                    start_tls=attempt["start_tls"],
                    username=from_email,
                    password=from_password,
                    timeout=60,
                    sock=sock,
                )
                async with smtp_client:
                    await smtp_client.send_message(msg)
                logger.info(
                    "SMTP send succeeded via %s:%s in %.1fs",
                    smtp_ipv4,
                    attempt["port"],
                    time.time() - connect_start,
                )
                logger.info("Email sent successfully to %s", to_email)
                return True
            except Exception as e:
                last_error = e
                logger.exception(
                    "SMTP attempt failed via %s:%s after %.1fs: %s",
                    smtp_ipv4,
                    attempt["port"],
                    time.time() - connect_start,
                    e,
                )

        if last_error is not None:
            raise last_error
        raise RuntimeError("SMTP send failed without raising a concrete exception")
    except Exception as e:
        logger.exception("SMTP send failed for %s: %s", to_email, e)
        return False


if __name__ == "__main__":
    asyncio.run(main())
