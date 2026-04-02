import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .raid import (
    create_condensed_html_email,
    fetch_multiple_subreddits,
    get_llm_summaries_in_batches,
    parse_summaries,
    send_email,
)

load_dotenv()

app = FastAPI()
logger = logging.getLogger(__name__)


@app.get("/digest")
async def generate_digest():
    subreddit_list = [
        "LocalLLaMA", "reactjs", "Python", "javascript"
    ]

    posts_per_subreddit = 6

    to_email = os.getenv('TO_EMAIL', 'your-email@gmail.com')
    from_email = os.getenv('GMAIL_EMAIL')
    from_password = os.getenv('GMAIL_APP_PASSWORD')

    logger.info(
        "Received /digest request for %s subreddits with posts_per_subreddit=%s",
        len(subreddit_list),
        posts_per_subreddit,
    )

    # Fetch posts from subreddits
    posts = await fetch_multiple_subreddits(subreddit_list, posts_per_sub=posts_per_subreddit)

    if not posts:
        logger.warning("Digest generation stopped because no posts were fetched")
        return JSONResponse(content={"message": "No posts fetched!"}, status_code=400)

    # Get summaries from LLM
    summary_text = await get_llm_summaries_in_batches(posts, batch_size=10)

    # Parse summaries
    formatted_posts = parse_summaries(summary_text)
    logger.info(
        "Digest generation fetched %s posts and parsed %s formatted summaries",
        len(posts),
        len(formatted_posts),
    )

    # Create HTML email content
    html_email = create_condensed_html_email(
        formatted_posts, subreddit_list, max_display=100)

    # Create plain text version
    plain_text = f"Reddit Digest\n\n"
    plain_text += f"Total posts: {len(formatted_posts)} from {len(subreddit_list)} subreddits\n"
    plain_text += "=" * 60 + "\n\n"

    for post in formatted_posts:
        plain_text += f"[r/{post['subreddit']}] {post['title']}\n"
        plain_text += f"{post['summary']}\n"
        plain_text += f"Link: {post['link']}\n\n"

    # Send email
    subject = f"Reddit Digest ({len(formatted_posts)} posts)"
    email_sent = False

    if from_email and from_password:
        logger.info("Sending digest email for /digest request")
        email_sent = await send_email(subject, html_email, plain_text, to_email, from_email, from_password)
    else:
        logger.error("Digest email skipped because email credentials are missing")

    if email_sent:
        logger.info("Digest request completed successfully")
        return JSONResponse(content={"message": "Digest email sent successfully!"})
    else:
        logger.error("Digest request failed during email send")
        return JSONResponse(content={"message": "Failed to send digest email"}, status_code=500)
