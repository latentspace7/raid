# AI Agent Guidelines for Reddit AI Digest

## Build and Run Commands

### Main Application
```bash
python src/raid.py
uv run src/raid.py
```

### FastAPI Development Server
```bash
./start_fastapi.sh
uv run uvicorn src.app:app --reload --host 0.0.0.0 --port 8000
```

### Package Management
```bash
uv sync              # Install dependencies
uv add <package>     # Add new dependency
uv add --dev <package>  # Add dev dependency
```

### Testing
```bash
uv add --dev pytest pytest-asyncio

uv run pytest                          # Run all tests
uv run pytest tests/                   # Run all tests in directory
uv run pytest tests/test_module.py     # Single test file
uv run pytest tests/test_module.py::test_name  # Specific test
uv run pytest -v                       # Verbose output
uv run pytest --cov=src                # With coverage
```

### Linting & Formatting
```bash
uv add --dev ruff

uv run ruff format src/                # Format code
uv run ruff check src/                 # Lint with auto-fix
uv run ruff check src/ --fix           # Lint with fixes
```

### Type Checking
```bash
uv add --dev mypy

uv run mypy src/                       # Type check
uv run mypy src/ --ignore-missing-imports  # Skip missing stubs
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
import asyncpraw
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
reddit = await get_reddit_client()
try:
    # use reddit
finally:
    await reddit.close()
```

## Project Structure
```
src/
├── __init__.py
├── raid.py              # Main application logic
├── app.py               # FastAPI endpoints
└── templates/
    ├── __init__.py
    └── email_template.py
tests/
.env                     # Environment variables (never commit)
```

## Key Dependencies
- **asyncpraw**: Async Reddit API
- **openai**: OpenAI API (AsyncOpenAI)
- **fastapi**: Web framework
- **aiosmtplib**: Async SMTP
- **uvicorn**: ASGI server
- **python-dotenv**: Environment vars

## Development Notes
- Python 3.12+ required
- LLM summarization in batches (default: 15)
- Gmail SMTP for email delivery
- All API keys via environment variables
- Never commit .env or secrets
