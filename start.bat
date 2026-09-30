@echo off
title Antigravity Proxy
echo Starting Antigravity Proxy Setup...

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in your system PATH.
    echo Please install Python 3.10+ and try again.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo [INFO] Creating virtual environment...
    python -m venv .venv
)

echo [INFO] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [INFO] Installing/Updating dependencies...
pip install -q fastapi uvicorn httpx sse-starlette pydantic

echo [INFO] Launching Proxy UI...
python ui.py

pause
