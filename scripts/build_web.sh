#!/bin/bash
# Build the Next.js frontend → web/out/.
#
# Run this whenever you change anything in web/ before committing. The
# resulting web/out/ is committed to git so end-users running start.command
# don't need Node installed.
#
#   ./scripts/build_web.sh
#   git add web/out/
#   git commit -m "..."

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
WEB_DIR="$( cd "$SCRIPT_DIR/.." && pwd )/web"

if ! command -v npm &> /dev/null; then
    echo "❌ npm is not installed. Install Node 18+ from https://nodejs.org/"
    exit 1
fi

cd "$WEB_DIR"

if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies (one-time, ~60s)..."
    npm install --silent
fi

echo "Building Next.js static export..."
npm run build

if [ ! -f "out/index.html" ]; then
    echo "❌ Build did not produce out/index.html — check the npm output above."
    exit 1
fi

echo
echo "✓ Built. Commit web/out/ to ship the new frontend to testers:"
echo "    git add web/out/"
echo "    git commit -m 'Rebuild web/out/'"
