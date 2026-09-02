@echo off
setlocal
if not exist .venv (
  py -3 -m venv .venv
)
call .venv\Scripts\activate
python -m pip install -r requirements.txt
if not exist .env copy .env.example .env

rem Keep local demo deterministic even if .env targets an intranet deployment.
set GATEWAY_HOST=127.0.0.1
set GATEWAY_PORT=18088
set PUBLIC_BASE_URL=http://127.0.0.1:18088
set UPSTREAM_BASE_URL=http://127.0.0.1:9090
set CORS_ALLOW_ORIGINS=*

start "Mock FLV Upstream" cmd /k "call .venv\Scripts\activate && python -m uvicorn scripts.mock_upstream:app --host 127.0.0.1 --port 9090"
timeout /t 2 >nul
python -m app.server
