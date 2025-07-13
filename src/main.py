import httpx
from dotenv import load_dotenv
import os
import praw
from anthropic import Anthropic
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from collections import defaultdict
from typing import List, Dict, Any
from templates.email_template import generate_email_template

load_dotenv()

reddit = praw.Reddit(
    client_id=os.getenv('CLIENT_ID'),
    client_secret=os.getenv('CLIENT_SECRET'),
    user_agent="news"
)

client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))


def fetch_multiple_subreddits(subreddit_list: List[str], posts_per_sub: int = 3) -> List[Dict[str, Any]]:
    """Fetch posts from multiple subreddits"""
    all_posts = []
    track_ids = []
    for sub_name in subreddit_list:
        print(f"Fetching from r/{sub_name}...")
        try:
            subreddit = reddit.subreddit(sub_name)

            for post in subreddit.hot(limit=posts_per_sub):

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

                    all_posts.append(post_info)
                    track_ids.append(post.name)

            for post in subreddit.new(limit=3):
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

                    all_posts.append(post_info)
                    track_ids.append(post.name)

        except Exception as e:
            print(f"Error fetching r/{sub_name}: {e}")

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


def get_llm_summaries_in_batches(posts_data: List[Dict[str, Any]], batch_size: int = 10) -> str:
    """Process posts in batches to handle large numbers"""
    all_summaries = []

    # Process in batches
    for i in range(0, len(posts_data), batch_size):
        batch = posts_data[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(posts_data) + batch_size - 1) // batch_size

        print(f"Processing batch {batch_num}/{total_batches}...")

        prompt = create_summary_prompt_batch(batch, batch_num, total_batches)

        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}]
            )
            all_summaries.append(response.content[0].text)
        except Exception as e:
            print(f"Error in batch {batch_num}: {str(e)}")

    return "\n".join(all_summaries)


# LM studio for local inference using Llama3.2-1B
# def get_llm_summaries_in_batches(posts_data: List[Dict[str, Any]], batch_size: int = 10) -> str:
#     """Process posts in batches using LM Studio's local API via httpx."""
#     all_summaries = []

#     api_url = "http://127.0.0.1:1234/v1/chat/completions"
#     headers = {"Content-Type": "application/json"}

#     with httpx.Client(timeout=60.0) as client:
#         for i in range(0, len(posts_data), batch_size):
#             batch = posts_data[i:i + batch_size]
#             batch_num = (i // batch_size) + 1
#             total_batches = (len(posts_data) + batch_size - 1) // batch_size

#             print(f"Processing batch {batch_num}/{total_batches}...")

#             prompt = create_summary_prompt_batch(
#                 batch, batch_num, total_batches)

#             payload = {
#                 "model": "meta-llama_-_llama-3.2-1b-instruct",
#                 "messages": [
#                     {"role": "system", "content": "You are a helpful assistant that summarizes user content."},
#                     {"role": "user", "content": prompt}
#                 ],
#                 "temperature": 0.0,
#                 "max_tokens": 2000,
#                 "stream": False
#             }

#             try:
#                 response = client.post(api_url, headers=headers, json=payload)
#                 response.raise_for_status()
#                 summary = response.json()["choices"][0]["message"]["content"]
#                 all_summaries.append(summary)
#             except httpx.HTTPError as e:
#                 print(f"Error in batch {batch_num}: {str(e)}")

#     return "\n".join(all_summaries)

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

# Parsing if using local inference
# def parse_summaries(summary_text: str) -> List[Dict[str, str]]:
#     """Parse the summary into structured data - fixed for actual LLM output"""
#     posts = []

#     # Split by [SUBREDDIT: pattern to get individual post blocks
#     sections = summary_text.split('[SUBREDDIT:')

#     for section in sections[1:]:  # Skip first empty section
#         try:
#             # Extract subreddit (everything up to the first ]
#             if ']' not in section:
#                 continue

#             lines = section.split('\n')
#             subreddit = lines[0].split(']')[0].strip()

#             # Find the title line
#             title = ""
#             link = ""
#             summary = ""

#             for line in lines:
#                 if line.strip().startswith('[TITLE:'):
#                     title = line.split('[TITLE:')[1].split(']')[0].strip()
#                 elif line.strip().startswith('[LINK:'):
#                     link = line.split('[LINK:')[1].split(']')[0].strip()
#                 elif line.strip().startswith('[SUMMARY:'):
#                     summary = line.split('[SUMMARY:')[1].split(']')[0].strip()

#             # Only add if we have all required fields
#             if subreddit and title and link and summary:
#                 posts.append({
#                     # Remove r/ prefix if present
#                     'subreddit': subreddit.replace('r/', ''),
#                     'title': title,
#                     'link': link,
#                     'summary': summary
#                 })
#                 print(f"✅ Parsed: {title[:50]}...")
#             else:
#                 print(
#                     f"❌ Missing fields in section: subreddit='{subreddit}', title='{title}', link='{link}', summary='{summary}'")

#         except Exception as e:
#             print(f"❌ Error parsing section: {e}")
#             print(f"Section content: {section[:200]}...")
#             continue

#     print(f"🎯 Successfully parsed {len(posts)} posts from summary text")
#     return posts


def create_condensed_html_email(posts_data: List[Dict[str, str]], subreddit_list: List[str], max_display: int = 15) -> str:
    """Create HTML email"""

    # Group posts by subreddit
    posts_by_sub = defaultdict(list)
    for post in posts_data:
        posts_by_sub[post['subreddit']].append(post)

    sorted_subs = sorted(posts_by_sub.items(),
                         key=lambda x: len(x[1]), reverse=True)

    html = generate_email_template(posts_data, subreddit_list)

    # TODO: intelligent top posts section
    # Add top posts section if many posts
    # if len(posts_data) > 10:
    #     html += """
    #         <div class="top-posts">
    #             <h3>🔥 Top Highlights</h3>
    #     """

    #     for i, post in enumerate(posts_data[:5]):
    #         html += f"""
    #             <div class="post-item">
    #                 <div class="post-title">
    #                     <a href="{post['link']}" target="_blank">{i+1}. {post['title']}</a>
    #                 </div>
    #                 <div class="post-summary">{post['summary']}</div>
    #             </div>
    #         """

    #     html += """
    #         </div>
    #     """

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


def main() -> None:

    subreddit_list = ["LocalLLaMA", "ClaudeAI", "modelcontextprotocol", "Anthropic", "GeminiAI", "OpenAI", "RooCode", "Rag", "agentdevelopmentkit", "singularity", "ArtificialInteligence", "GithubCopilot", "StableDiffusion",
                      "FastAPI", "reactjs", "Python", "technology", "javascript"]

    posts_per_subreddit = 6

    to_email = os.getenv('TO_EMAIL', 'your-email@gmail.com')
    from_email = os.getenv('GMAIL_EMAIL')
    from_password = os.getenv('GMAIL_APP_PASSWORD')

    print(f"🔍 Fetching posts from: {', '.join(subreddit_list)}")

    #
    posts = fetch_multiple_subreddits(
        subreddit_list, posts_per_sub=posts_per_subreddit)

    if not posts:
        print("❌ No posts fetched!")
        return

    print(f"✅ Fetched {len(posts)} total posts")
    print("🤖 Getting summaries...")

    summary_text = get_llm_summaries_in_batches(posts, batch_size=10)

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
        send_email(subject, html_email, plain_text,
                   to_email, from_email, from_password)
    else:
        print("❌ Email credentials not found")


def send_email(subject: str, html_body: str, plain_body: str, to_email: str, from_email: str, from_password: str) -> bool:
    """Send email via Gmail SMTP"""
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = to_email

        part1 = MIMEText(plain_body, 'plain')
        part2 = MIMEText(html_body, 'html')
        msg.attach(part1)
        msg.attach(part2)

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(from_email, from_password)
        server.send_message(msg)
        server.quit()

        print(f"✅ Email sent successfully to {to_email}")
        return True

    except Exception as e:
        print(f"❌ Error sending email: {str(e)}")
        return False


if __name__ == "__main__":
    main()
