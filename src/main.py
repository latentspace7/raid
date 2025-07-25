from dotenv import load_dotenv
import os
import asyncpraw
from anthropic import AsyncAnthropic
from datetime import datetime
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from collections import defaultdict
from typing import List, Dict, Any
import asyncio
from templates.email_template import generate_email_template

load_dotenv()


async def get_reddit_client():
    return asyncpraw.Reddit(
        client_id=os.getenv('CLIENT_ID'),
        client_secret=os.getenv('CLIENT_SECRET'),
        user_agent="news"
    )

client = AsyncAnthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))


async def fetch_multiple_subreddits(subreddit_list: List[str], posts_per_sub: int = 3) -> List[Dict[str, Any]]:
    """Fetch posts from multiple subreddits asynchronously"""
    reddit = await get_reddit_client()

    async def fetch_subreddit_posts(sub_name: str) -> List[Dict[str, Any]]:
        """Fetch posts from a single subreddit"""
        posts = []
        track_ids = []

        print(f"Fetching from r/{sub_name}...")
        try:
            subreddit = await reddit.subreddit(sub_name)

            # Fetch hot posts
            async for post in subreddit.hot(limit=posts_per_sub):
                if not post.stickied and post.name not in track_ids:
                    post_info = {
                        'title': post.title,
                        'author': str(post.author) if post.author else '[deleted]',
                        'score': post.score,
                        'num_comments': post.num_comments,
                        'created_utc': post.created_utc,
                        'subreddit': str(post.subreddit),
                        'permalink': f"https://reddit.com{post.permalink}",
                        'url': post.url,
                        'is_self': post.is_self,
                        'selftext': post.selftext if post.is_self else '',
                        'upvote_ratio': post.upvote_ratio
                    }

                    if post.is_self:
                        post_info['content_type'] = 'text'
                        post_info['content'] = post.selftext
                    else:
                        post_info['content_type'] = 'link'
                        post_info['content'] = f"External link to: {post.url}"

                    posts.append(post_info)
                    track_ids.append(post.name)

            # Fetch new posts
            async for post in subreddit.new(limit=3):
                if not post.stickied and post.name not in track_ids:
                    post_info = {
                        'title': post.title,
                        'author': str(post.author) if post.author else '[deleted]',
                        'score': post.score,
                        'num_comments': post.num_comments,
                        'created_utc': post.created_utc,
                        'subreddit': str(post.subreddit),
                        'permalink': f"https://reddit.com{post.permalink}",
                        'url': post.url,
                        'is_self': post.is_self,
                        'selftext': post.selftext if post.is_self else '',
                        'upvote_ratio': post.upvote_ratio
                    }

                    if post.is_self:
                        post_info['content_type'] = 'text'
                        post_info['content'] = post.selftext
                    else:
                        post_info['content_type'] = 'link'
                        post_info['content'] = f"External link to: {post.url}"

                    posts.append(post_info)
                    track_ids.append(post.name)

        except Exception as e:
            print(f"Error fetching r/{sub_name}: {e}")

        return posts

    # Fetch all subreddits concurrently
    tasks = [fetch_subreddit_posts(sub_name) for sub_name in subreddit_list]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Flatten results and filter out exceptions
    all_posts = []
    for result in results:
        if isinstance(result, list):
            all_posts.extend(result)
        elif isinstance(result, Exception):
            print(f"Error in concurrent fetch: {result}")

    await reddit.close()
    return all_posts


def create_summary_prompt_batch(posts_batch: List[Dict[str, Any]], batch_num: int, total_batches: int) -> str:
    """Create a prompt for a batch of posts"""
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

# If running with the Anthropic SDK


async def get_llm_summaries_in_batches(posts_data: List[Dict[str, Any]], batch_size: int = 10) -> str:
    """Process posts in batches asynchronously to handle large numbers"""

    async def process_batch(batch: List[Dict[str, Any]], batch_num: int, total_batches: int) -> str:
        """Process a single batch of posts"""
        print(f"Processing batch {batch_num}/{total_batches}...")
        prompt = create_summary_prompt_batch(batch, batch_num, total_batches)

        try:
            response = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        except Exception as e:
            print(f"Error in batch {batch_num}: {str(e)}")
            return ""

    # Create tasks for all batches
    tasks = []
    for i in range(0, len(posts_data), batch_size):
        batch = posts_data[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(posts_data) + batch_size - 1) // batch_size
        tasks.append(process_batch(batch, batch_num, total_batches))

    # Process all batches concurrently
    all_summaries = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out exceptions and empty strings
    valid_summaries = []
    for summary in all_summaries:
        if isinstance(summary, str) and summary.strip():
            valid_summaries.append(summary)
        elif isinstance(summary, Exception):
            print(f"Batch processing error: {summary}")

    return "\n".join(valid_summaries)


# If running with the Anthropic SDK
def parse_summaries(summary_text: str) -> List[Dict[str, str]]:
    """Parse the summary into structured data"""
    posts = []

    for post_section in summary_text.split('[END]'):
        if '[SUBREDDIT:' in post_section:
            try:
                subreddit = post_section.split(
                    '[SUBREDDIT:')[1].split(']')[0].strip()
                title = post_section.split('[TITLE:')[1].split(']')[0].strip()
                link = post_section.split('[LINK:')[1].split(']')[0].strip()
                summary = post_section.split(
                    '[SUMMARY:')[1].split(']')[0].strip()

                posts.append({
                    'subreddit': subreddit,
                    'title': title,
                    'link': link,
                    'summary': summary
                })
            except:
                continue

    return posts


def create_condensed_html_email(posts_data: List[Dict[str, str]], subreddit_list: List[str], max_display: int = 15) -> str:
    """Create HTML email"""

    # Group posts by subreddit
    posts_by_sub = defaultdict(list)
    for post in posts_data:
        posts_by_sub[post['subreddit']].append(post)

    sorted_subs = sorted(posts_by_sub.items(),
                         key=lambda x: len(x[1]), reverse=True)

    html = generate_email_template(posts_data, subreddit_list)

    # Add posts by subreddit
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
                <a href="https://reddit.com/r/{'+'.join(subreddit_list)}" target="_blank">View all on Reddit →</a>
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

        for post in posts[:5]:
            html += f"""
                    <div class="post-item">
                        <div class="post-title">
                            <a href="{post['link']}" target="_blank">{post['title']}</a>
                        </div>
                        <div class="post-summary">{post['summary']}</div>
                    </div>
            """
            posts_shown += 1

        html += """
                </div>
            </div>
        """

    # Footer
    html += """
            <div class="footer">
                <p>This digest was automatically generated using Reddit API and Claude AI</p>
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

    subreddit_list = ["LocalLLaMA", "reactjs", "Python", "javascript"]

    posts_per_subreddit = 6

    to_email = os.getenv('TO_EMAIL', 'your-email@gmail.com')
    from_email = os.getenv('GMAIL_EMAIL')
    from_password = os.getenv('GMAIL_APP_PASSWORD')

    print(f"🔍 Fetching posts from: {', '.join(subreddit_list)}")

    #
    posts = await fetch_multiple_subreddits(
        subreddit_list, posts_per_sub=posts_per_subreddit)

    if not posts:
        print("❌ No posts fetched!")
        return

    print(f"✅ Fetched {len(posts)} total posts")
    print("🤖 Getting summaries...")

    summary_text = await get_llm_summaries_in_batches(posts, batch_size=10)

    formatted_posts = parse_summaries(summary_text)

    html_email = create_condensed_html_email(
        formatted_posts, subreddit_list, max_display=100)

    plain_text = f"Reddit Digest - {datetime.now().strftime('%Y-%m-%d')}\n\n"
    plain_text += f"Total posts: {len(formatted_posts)} from {len(subreddit_list)} subreddits\n"
    plain_text += "=" * 60 + "\n\n"

    for post in formatted_posts[:15]:
        plain_text += f"[r/{post['subreddit']}] {post['title']}\n"
        plain_text += f"{post['summary']}\n"
        plain_text += f"Link: {post['link']}\n\n"

    if len(formatted_posts) > 15:
        plain_text += f"\n... and {len(formatted_posts) - 15} more posts"

    subject = f"📊 Reddit Digest ({len(formatted_posts)} posts) - {datetime.now().strftime('%b %d')}"

    if from_email and from_password:
        await send_email(subject, html_email, plain_text,
                         to_email, from_email, from_password)
    else:
        print("❌ Email credentials not found")


async def send_email(subject: str, html_body: str, plain_body: str, to_email: str, from_email: str, from_password: str) -> bool:
    """Send email via Gmail SMTP asynchronously"""
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = to_email

        part1 = MIMEText(plain_body, 'plain')
        part2 = MIMEText(html_body, 'html')
        msg.attach(part1)
        msg.attach(part2)

        await aiosmtplib.send(
            msg,
            hostname='smtp.gmail.com',
            port=587,
            start_tls=True,
            username=from_email,
            password=from_password,
        )

        print(f"✅ Email sent successfully to {to_email}")
        return True

    except Exception as e:
        print(f"❌ Error sending email: {str(e)}")
        return False


if __name__ == "__main__":
    asyncio.run(main())
