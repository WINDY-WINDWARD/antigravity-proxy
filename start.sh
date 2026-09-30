#!/bin/bash
set -e

echo "Starting Antigravity Proxy Setup..."

# Detect python executable
if command -v python3 &>/dev/null; then
    PY="python3"
elif command -v python &>/dev/null; then
    PY="python"
else
    echo "[ERROR] Python is not installed or not in your system PATH."
    echo "Please install Python 3.10+ and try again."
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "[INFO] Creating virtual environment..."
    $PY -m venv .venv
fi

echo "[INFO] Activating virtual environment..."
source .venv/bin/activate

echo "[INFO] Installing/Updating dependencies..."
pip install -q fastapi uvicorn httpx sse-starlette pydantic

echo "[INFO] Launching Proxy UI..."
if ! python ui.py; then
    echo ""
    echo "[ERROR] The UI crashed or failed to start."
    echo "Note: On Linux, Tkinter is sometimes not installed by default."
    echo "If you saw a 'ModuleNotFoundError: No module named tkinter' error,"
    echo "please install it using your package manager (e.g., 'sudo apt install python3-tk')."
fi
