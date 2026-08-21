@echo off
setlocal
if not exist .venv (
  py -3 -m venv .venv
)
call .venv\Scripts\activate
python -m pip install -r requirements.txt
if not exist .env copy .env.example .env
start "Mock FLV Upstream" cmd /k "call .venv\Scripts\activate && python -m uvicorn scripts.mock_upstream:app --host 127.0.0.1 --port 9090"
timeout /t 2 >nul
python -m uvicorn app.main:app --host 127.0.0.1 --port 8088 --reload
