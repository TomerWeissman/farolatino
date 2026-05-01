#!/bin/bash
# FaroLatino A&R Dashboard — Mac/Linux launcher
# Double-click this file in Finder to start the dashboard.
# First run: bootstraps Python venv + dependencies (~60-90s).
# Later runs: launches in ~10s.

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo
echo "==========================================="
echo "  FaroLatino A&R Dashboard"
echo "==========================================="
echo

# 1. Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed."
    echo
    echo "   Please install Python 3.11 or later from:"
    echo "   https://www.python.org/downloads/"
    echo
    echo "   After installing, double-click this file again."
    echo
    read -p "Press Enter to close..."
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
PY_OK=$(python3 -c 'import sys; print(1 if sys.version_info >= (3,11) else 0)')
if [ "$PY_OK" != "1" ]; then
    echo "❌ Python 3.11+ required (you have $PY_VERSION)."
    echo "   Install from: https://www.python.org/downloads/"
    echo
    read -p "Press Enter to close..."
    exit 1
fi
echo "✓ Python $PY_VERSION"

# 2. Check .env file
if [ ! -f ".env" ]; then
    echo
    echo "❌ The .env file is missing."
    echo
    echo "   Drop the .env file you were sent into this folder:"
    echo "   $SCRIPT_DIR"
    echo
    echo "   Then double-click this file again."
    echo
    read -p "Press Enter to close..."
    exit 1
fi
echo "✓ .env present"

# 3. Create venv if missing
if [ ! -d "venv" ]; then
    echo
    echo "First-time setup: creating virtual environment (~30s)..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
fi

# 4. Activate venv
# shellcheck disable=SC1091
source venv/bin/activate

# 5. Install / update deps (quiet, but show progress for first install)
if ! python -c "import streamlit" 2>/dev/null; then
    echo
    echo "Installing dependencies (~60s, only on first run)..."
    pip install --upgrade pip --quiet
    pip install -r requirements.txt --quiet
    echo "✓ Dependencies installed"
else
    # Quick refresh; usually no-op
    pip install -r requirements.txt --quiet 2>/dev/null || true
fi

# 6. Open browser after Streamlit boots (3s delay)
(
    sleep 3
    open http://localhost:8501 2>/dev/null || true
) &

# 7. Launch Streamlit
echo
echo "Starting dashboard..."
echo "(Browser will open automatically. Press Ctrl+C in this window to stop.)"
echo
streamlit run streamlit_app/main.py --server.headless=true
