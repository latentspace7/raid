from fastapi import FastAPI
from fastapi.responses import JSONResponse
from .raid import fetch_multiple_subreddits, get_llm_summaries_in_batches, parse_summaries, create_condensed_html_email, send_email
import os
from dotenv import load_dotenv
from mangum import Mangum

load_dotenv()

app = FastAPI()
handler = Mangum(app)


@app.get("/digest")
async def generate_digest():
    subreddit_list = [
        "LocalLLaMA", "reactjs", "Python", "javascript"
    ]

    posts_per_subreddit = 6

    to_email = os.getenv('TO_EMAIL', 'your-email@gmail.com')
    from_email = os.getenv('GMAIL_EMAIL')
    from_password = os.getenv('GMAIL_APP_PASSWORD')

    # Fetch posts from subreddits
    posts = await fetch_multiple_subreddits(subreddit_list, posts_per_sub=posts_per_subreddit)

    if not posts:
        return JSONResponse(content={"message": "No posts fetched!"}, status_code=400)

    # Get summaries from LLM
    summary_text = await get_llm_summaries_in_batches(posts, batch_size=10)

    # Parse summaries
    formatted_posts = parse_summaries(summary_text)

    # Create HTML email content
    html_email = create_condensed_html_email(
        formatted_posts, subreddit_list, max_display=100)

    # Create plain text version
    plain_text = f"Reddit Digest\n\n"
    plain_text += f"Total posts: {len(formatted_posts)} from {len(subreddit_list)} subreddits\n"
    plain_text += "=" * 60 + "\n\n"

    for post in formatted_posts[:15]:
        plain_text += f"[r/{post['subreddit']}] {post['title']}\n"
        plain_text += f"{post['summary']}\n"
        plain_text += f"Link: {post['link']}\n\n"

    if len(formatted_posts) > 15:
        plain_text += f"\n... and {len(formatted_posts) - 15} more posts"

    # Send email
    subject = f"Reddit Digest ({len(formatted_posts)} posts)"
    email_sent = False

    if from_email and from_password:
        email_sent = await send_email(subject, html_email, plain_text, to_email, from_email, from_password)

    if email_sent:
        return JSONResponse(content={"message": "Digest email sent successfully!"})
    else:
        return JSONResponse(content={"message": "Failed to send digest email"}, status_code=500)
