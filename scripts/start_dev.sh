#!/bin/bash
# Developer mode: run FastAPI + Next.js dev servers side-by-side.
#
# - FastAPI (uvicorn --reload) on :8000
# - Next.js dev server (npm run dev) on :3000, with /api/* proxied to :8000
#
# Open http://localhost:3000 — hot-reloads on file changes in either side.
#
# This is for active development. End users run start.command (single
# uvicorn process serving the pre-built static frontend on :8501).
#
# Stop with Ctrl+C — both processes are killed.

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

cd "$ROOT"

# Activate venv if it exists; otherwise the current shell needs deps installed.
if [ -d "venv" ]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
fi

if ! command -v npm &> /dev/null; then
    echo "❌ npm is not installed. Install Node 18+ from https://nodejs.org/"
    exit 1
fi

if [ ! -d "web/node_modules" ]; then
    echo "Installing frontend deps (one-time)..."
    (cd web && npm install --silent)
fi

# Start FastAPI in the background; the Next.js dev server in the foreground.
# Trapping SIGINT/SIGTERM kills both cleanly.
trap 'kill $UVPID 2>/dev/null; exit 0' INT TERM

uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload --log-level warning &
UVPID=$!

echo "→ FastAPI on http://127.0.0.1:8000 (PID $UVPID)"
echo "→ Next.js dev server starting on http://127.0.0.1:3000 ..."
echo "  Open http://localhost:3000 in your browser."
echo

(cd web && npm run dev)

kill $UVPID 2>/dev/null || true
