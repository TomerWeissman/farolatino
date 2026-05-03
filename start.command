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
    echo "──────────────────────────────────────────────────────────"
    echo "  Python isn't installed yet."
    echo "──────────────────────────────────────────────────────────"
    echo
    echo "  Download Python 3.11 or newer from:"
    echo "      https://www.python.org/downloads/"
    echo
    echo "  Click the big yellow 'Download Python' button, run the"
    echo "  installer, then double-click start.command again."
    echo
    read -p "  Press Enter to close..."
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
PY_OK=$(python3 -c 'import sys; print(1 if sys.version_info >= (3,11) else 0)')
if [ "$PY_OK" != "1" ]; then
    echo "──────────────────────────────────────────────────────────"
    echo "  Your Python is too old (you have $PY_VERSION, need 3.11+)."
    echo "──────────────────────────────────────────────────────────"
    echo
    echo "  Install a newer version from:"
    echo "      https://www.python.org/downloads/"
    echo
    read -p "  Press Enter to close..."
    exit 1
fi
echo "✓ Python $PY_VERSION"

# 1.5 Check Claude Code (required: chat backend invokes `claude --print`)
if ! command -v claude &> /dev/null; then
    echo "──────────────────────────────────────────────────────────"
    echo "  Claude Code isn't installed yet."
    echo "──────────────────────────────────────────────────────────"
    echo
    echo "  FaroAI uses Claude Code as its chat engine."
    echo
    echo "  1. Install it from:  https://claude.com/claude-code"
    echo "  2. Open Terminal and run once:  claude login"
    echo "  3. Double-click start.command again"
    echo
    read -p "  Press Enter to close..."
    exit 1
fi
echo "✓ Claude Code on PATH"

# 2. .env file — auto-create empty if missing. The user adds API keys
#    via the in-app Connections page once the dashboard opens; no need
#    to edit a hidden file before launch.
if [ ! -f ".env" ]; then
    echo "First-time setup: creating an empty .env (you'll add API keys in the app)..."
    touch ".env"
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
if ! python -c "import fastapi" 2>/dev/null; then
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

# 5c. Sanity-check the prebuilt frontend. We ship web/out/ in the repo so
#     end-users don't need Node. If it's missing, fall back to the API-only
#     mode (browser will land on FastAPI's docs page) and surface a hint.
if [ ! -f "$SCRIPT_DIR/web/out/index.html" ]; then
    echo "⚠️  web/out/ is missing — frontend won't be served."
    echo "    Re-clone the repo or run scripts/build_web.sh to rebuild it."
fi

# 6. Open browser once uvicorn responds (poll /api/health)
(
    for i in 1 2 3 4 5 6 7 8 9 10; do
        if curl -s -o /dev/null --max-time 1 http://127.0.0.1:8501/api/health 2>/dev/null; then
            open http://localhost:8501 2>/dev/null || true
            break
        fi
        sleep 0.5
    done
) &

# 6b. Kill any stale uvicorn from a previous failed launch. Without this,
#     a second start.command silently fails to bind :8501 (the old
#     process still owns the port) and the browser ends up talking to
#     stale code. We saw this in production: two uvicorn PIDs alive
#     simultaneously, the new one inert.
pkill -f "uvicorn api.main:app --host 127.0.0.1 --port 8501" 2>/dev/null && sleep 1 || true

# 7. Launch FastAPI (single process serves both /api/* and the static SPA
#    mounted from web/out/). Port 8501 keeps muscle memory + bookmarks
#    from the previous Streamlit setup.
echo
echo "Starting dashboard..."
echo "(Browser will open automatically. Press Ctrl+C in this window to stop.)"
echo
uvicorn api.main:app --host 127.0.0.1 --port 8501 --log-level warning
