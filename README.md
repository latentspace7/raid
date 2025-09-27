# 📰 Reddit AI Digest

A Python application that automatically fetches posts from multiple subreddits of your choosing, generates AI-powered summaries using any OpenAI-compatible model (currently using GPT-120B OSS with Hugging Face inference providers), and sends beautifully formatted email digests to your email.

## ✨ Features

- 🔍 **Multi-Subreddit Fetching**: Collects posts from multiple subreddits simultaneously
- 🤖 **AI-Powered Summaries**: Uses any OpenAI-compatible model to create concise, intelligent summaries
- 📧 **Email Delivery**: Sends HTML and plain text email digests via Gmail SMTP
- 🎨 **Beautiful HTML Templates**: Modern, responsive email design
- ⚡ **Asynchronous Processing**: Efficiently handles large numbers of posts with async/await
- 🚀 **Concurrent Operations**: Fetches subreddits and processes AI summaries in parallel
- 📊 **Smart Organization**: Groups posts by subreddit with statistics

## 🚀 Quick Start

### Prerequisites

- Python 3.12 or higher
- [uv](https://docs.astral.sh/uv/) package manager (recommended) or pip
- Reddit API credentials
- OpenAI-compatible API key (currently using GPT-120B OSS with Hugging Face inference providers)
- Gmail account with app password setup

### Installation

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd reddit_news
   ```

2. **Install dependencies**
   
   Using uv (recommended):
   ```bash
   uv sync
   ```
   
   Using pip:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   
   Create a `.env` file in the project root:
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` with your credentials:
   ```env
   # Reddit API credentials (get from https://www.reddit.com/prefs/apps)
   CLIENT_ID=your_reddit_client_id
   CLIENT_SECRET=your_reddit_client_secret
   
   
   # Gmail credentials
   GMAIL_EMAIL=your_email@gmail.com
   GMAIL_APP_PASSWORD=your_gmail_app_password
   TO_EMAIL=recipient@gmail.com
   ```

### Running the Application

```bash
# Using uv
uv run src/main.py

# Using Python directly
python src/main.py
```

> **Note**: The application now runs fully asynchronously for improved performance and concurrent processing of Reddit posts and AI summaries.

## 🔧 Configuration

### Customizing Subreddits

Edit the `subreddit_list` in `src/main.py`:

```python
subreddit_list = [
    "technology", "programming", "LocalLLaMA",    
    # Add your favorite subreddits here
]
```

### Adjusting Post Limits

Change the number of posts fetched per subreddit:

```python
posts_per_subreddit = 6  # Adjust this value
```

### Email Display Options

Modify the maximum posts shown in email:

```python
html_email = create_condensed_html_email(
    formatted_posts, subreddit_list, max_display=100  # Adjust this
)
```

## 🔑 Setting Up API Credentials

### Reddit API

1. Go to [Reddit App Preferences](https://www.reddit.com/prefs/apps)
2. Click "Create App" or "Create Another App"
3. Choose "script" as the app type
4. Note down your `client_id` and `client_secret`

### OpenAI API

1. Visit [OpenAI Console](https://platform.openai.com/)
2. Sign up/login and navigate to API keys
3. Create a new API key
4. Ensure your API key has sufficient credits for API usage

### Gmail App Password

1. Enable 2-factor authentication on your Gmail account
2. Go to [Google App Passwords](https://myaccount.google.com/apppasswords)
3. Generate an app password for "Mail"
4. Use this password (not your regular Gmail password)

## 🎯 How It Works

1. **Fetch Posts**: The app connects to Reddit API and concurrently fetches recent posts from multiple subreddits using async operations
2. **AI Processing**: Posts are sent to the OpenAI-compatible model in parallel batches for intelligent summarization using async API calls
3. **Email Generation**: Creates both HTML and plain text versions of the digest
4. **Delivery**: Sends the formatted email via Gmail SMTP using async email delivery

## 🛠️ Customization

### Custom Email Templates

Modify `src/templates/email_template.py` to customize the email appearance:

- Change colors, fonts, and layout
- Add your branding or logo
- Modify the CSS styles

### Async Architecture

The application uses modern async/await patterns for concurency:

- **Concurrent Subreddit Fetching**: All subreddits are fetched simultaneously using `asyncio.gather()`
- **Parallel AI Processing**: OpenAI-compatible model requests are batched and processed concurrently
- **Async Email Delivery**: Non-blocking email sending using `aiosmtplib`
- **Efficient Resource Usage**: Proper connection management and cleanup

### Adding Features

## 🐛 Troubleshooting

### Common Issues

**Email not sending:**
- Verify Gmail app password is correct
- Check 2FA is enabled on Gmail account
- Ensure "Less secure app access" is not blocking the connection

**Reddit API errors:**
- Verify Reddit credentials are correct
- Check rate limits (Reddit API has usage limits)
- Ensure subreddit names are spelled correctly


### Debug Mode

Add debug prints to troubleshoot:

```python
# Add this for more verbose output
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 📋 Requirements

The application requires the following Python packages:

- `transformers>=4.28.0` - Hugging Face Transformers library for OpenAI models
- `transformers>=4.28.0` - Hugging Face Transformers library for OpenAI models
- `asyncpraw>=7.8.1` - Async Reddit API wrapper
- `aiosmtplib>=3.0.0` - Async SMTP email client
- `python-dotenv>=1.1.0` - Environment variable management

## 📋 TODO

- ✅ `async batches` - ~~Make code async with Anthropic's async class~~ (Completed)
- `templates` - Refactor to move to another module
- `LLMs` - Add support for more LLMs (Gemini, OpenAI)
- `performance` - Add connection pooling and rate limiting optimizations

---

**Made with ❤️ using Reddit API and OpenAI-compatible models**
