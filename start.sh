#!/bin/bash
# Install playwright browser if not already
playwright install chromium 2>/dev/null || true
# Start the API server
uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}
