# AI Agent Guidelines for Reddit AI Digest

## Build and Run Commands

### Main Application

```bash
uv run --locked -m src.raid
uv run --locked src/raid.py
```

### FastAPI Development Server

```bash
uv run --locked uvicorn src.app:app --reload --host 127.0.0.1 --port 8000
```

### Package Management

```bash
uv sync --locked     # Install dependencies
uv add <package>     # Add new dependency
uv add --dev <package>  # Add dev dependency
```

### Testing

```bash
uv run pytest                          # Run all tests
uv run pytest tests/                   # Run all tests in directory
uv run pytest tests/test_module.py     # Single test file
uv run pytest tests/test_module.py::test_name  # Specific test
uv run pytest -v                       # Verbose output
```

### Linting & Formatting

```bash
uv run --locked ruff format src tests         # Format code
uv run --locked ruff check src tests          # Lint
uv run --locked ruff check src tests --fix    # Lint with fixes
```

### Type Checking

```bash
uv run --locked mypy                  # Strict type check
```

## Code Style Guidelines

### Imports

Order: standard library → third-party → local (grouped, alphabetically)

```python
import asyncio
from collections import defaultdict
from datetime import datetime
import os
import time
from typing import Any, Dict, List

import aiosmtplib
import httpx
from dotenv import load_dotenv
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from openai import AsyncOpenAI

from src.templates.email_template import generate_email_template
```

### Type Hints

Always use type hints for function signatures.

### Naming Conventions

- Functions/variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private: `_leading_underscore`
- Filenames: `snake_case.py`

### Async/Await Patterns

Async-first - all I/O must be async.

### Error Handling

Use try/except for operations that may fail:

```python
try:
    response = await client.chat.completions.create(...)
    content = response.choices[0].message.content
    if content is None:
        raise ValueError("Received None response")
    return content
except Exception as e:
    print(f"Error: {e}")
    return ""
```

### Strings

Use f-strings and double quotes.

### Environment Variables

Load at module top, never hardcode secrets.

## Architecture Patterns

### Batch Processing

```python
tasks = [fetch_subreddit(name) for name in subreddits]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

### Resource Cleanup

```python
async with get_reddit_client(settings) as reddit:
    # use reddit
```

## Project Structure

```
src/
├── __init__.py
├── raid.py              # Main application logic
├── app.py               # FastAPI endpoints
├── config.py            # Validated environment settings
├── models.py            # Provider validation and digest types
└── templates/
    ├── __init__.py
    └── email_template.py
tests/
.env                     # Environment variables (never commit)
```

## Key Dependencies

- **httpx**: Async Reddit API HTTP client
- **openai**: OpenAI API (AsyncOpenAI)
- **fastapi**: Web framework
- **aiosmtplib**: Async SMTP
- **uvicorn**: ASGI server
- **python-dotenv**: Environment vars
- **pydantic-settings**: Validated configuration

## Development Notes

- Python 3.12+ required
- LLM summarization in batches (CLI: 8, API: 10), with at most 4 active batches
- HTTP delivery uses POST /digest with DIGEST_API_TOKEN bearer authentication
- Gmail SMTP for email delivery
- All API keys via environment variables
- Never commit .env or secrets
