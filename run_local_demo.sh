#!/usr/bin/env bash
set -euo pipefail

[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
[ -f .env ] || cp .env.example .env

export GATEWAY_HOST=127.0.0.1
export GATEWAY_PORT=18088
export PUBLIC_BASE_URL=http://127.0.0.1:18088
export UPSTREAM_BASE_URL=http://127.0.0.1:9090
export CORS_ALLOW_ORIGINS='*'

python -m uvicorn scripts.mock_upstream:app --host 127.0.0.1 --port 9090 &
UPSTREAM_PID=$!
trap 'kill "$UPSTREAM_PID" 2>/dev/null || true' EXIT

python -m app.server
