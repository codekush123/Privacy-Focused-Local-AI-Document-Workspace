#!/usr/bin/env bash
# Starts the FastAPI backend on http://127.0.0.1:8000 (Linux / macOS / Git Bash)
set -e
cd "$(dirname "$0")/../backend"
if [ ! -d .venv ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt 2>/dev/null || .venv/Scripts/pip install -r requirements.txt
fi
PY=.venv/bin/python; [ -x "$PY" ] || PY=.venv/Scripts/python
exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
