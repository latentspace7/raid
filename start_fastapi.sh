#!/usr/bin/env bash
set -e

. .venv/bin/activate

# Start FastAPI server using uvicorn
uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload