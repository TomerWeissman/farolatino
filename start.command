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

# 1.5 Check Claude Code (required: chat backend invokes `claude --print`)
if ! command -v claude &> /dev/null; then
    echo
    echo "❌ Claude Code is not installed."
    echo
    echo "   Install from: https://claude.com/claude-code"
    echo "   After installing, run \`claude login\` once in a terminal."
    echo
    echo "   Then double-click this file again."
    echo
    read -p "Press Enter to close..."
    exit 1
fi
echo "✓ Claude Code on PATH"

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

# 5. Install / update deps. We capture stderr to a log file because pip's
# HTTP-cache machinery emits a benign but alarming wall of "Cache entry
# deserialization failed" warnings on some setups. We surface real errors
# via the exit code; the log is available if anything actually fails.
PIP_LOG="$SCRIPT_DIR/.pip_install.log"
if ! python -c "import streamlit" 2>/dev/null; then
    echo
    echo "Installing dependencies (~60s, only on first run)..."
    if ! { pip install --upgrade pip --quiet > "$PIP_LOG" 2>&1 \
        && pip install -r requirements.txt --quiet >> "$PIP_LOG" 2>&1; }; then
        echo
        echo "❌ Dependency install failed."
        echo "   Full log: $PIP_LOG"
        echo
        read -p "Press Enter to close..."
        exit 1
    fi
    echo "✓ Dependencies installed"
    rm -f "$PIP_LOG"
else
    # Quick refresh; usually a no-op. We skip it entirely if requirements.txt
    # hasn't changed since the venv was last refreshed (tracked via a hash
    # stamp in venv/.req_hash). On a slow network, pip's silent resolver can
    # otherwise take 60-120s with no output — looks like the launcher hung.
    REQ_HASH=$(shasum -a 256 requirements.txt 2>/dev/null | awk '{print $1}')
    STAMP_FILE="venv/.req_hash"
    PREV_HASH=$(cat "$STAMP_FILE" 2>/dev/null || echo "")
    if [ "$REQ_HASH" != "$PREV_HASH" ]; then
        echo "Refreshing dependencies (requirements changed)..."
        if pip install -r requirements.txt --quiet > "$PIP_LOG" 2>&1; then
            echo "$REQ_HASH" > "$STAMP_FILE"
            rm -f "$PIP_LOG"
            echo "✓ Dependencies refreshed"
        else
            echo "⚠️  Refresh failed — continuing with existing packages."
            echo "    Log: $PIP_LOG"
        fi
    fi
fi

# 5b. Generate .mcp.json so `claude --print` can spawn the FaroLatino
#     MCP server with this snapshot's venv. Regenerated on every launch
#     so the venv path is always current.
PY_BIN="$SCRIPT_DIR/venv/bin/python"
cat > "$SCRIPT_DIR/.mcp.json" <<EOF
{
  "mcpServers": {
    "farolatino": {
      "command": "$PY_BIN",
      "args": ["-m", "mcp_server"],
      "cwd": "$SCRIPT_DIR"
    }
  }
}
EOF
echo "✓ MCP config ready"

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
