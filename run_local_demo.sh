#!/usr/bin/env bash
set -euo pipefail
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
python -m uvicorn scripts.mock_upstream:app --host 127.0.0.1 --port 9090 &
UPSTREAM_PID=$!
trap 'kill "$UPSTREAM_PID" 2>/dev/null || true' EXIT
python -m uvicorn app.main:app --host 127.0.0.1 --port 8088 --reload
