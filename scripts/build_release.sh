#!/bin/bash
# Build a release zip for distribution.
#
# Output: dist/farolatino-<version>.zip
#
# Usage:
#   ./scripts/build_release.sh                    # picks version from latest git tag, falling back to "dev"
#   ./scripts/build_release.sh v0.1.0             # use a specific version label
#
# Excludes: venv/, .git/, data/cache/, data/internal/, web/node_modules/,
# web/.next/, .pytest_cache/, build/, dist/, *.pyc, .DS_Store, .env.
# Includes: web/out/ (the prebuilt frontend so end-users don't need Node).

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
cd "$PROJECT_ROOT"

VERSION="${1:-$(git describe --tags --abbrev=0 2>/dev/null || echo dev)}"
NAME="farolatino-${VERSION}"
DIST_DIR="$PROJECT_ROOT/dist"
STAGE_DIR="$DIST_DIR/$NAME"

# Sanity: make sure the prebuilt frontend exists. Without it the launcher
# warns and the dashboard 404s.
if [ ! -f "web/out/index.html" ]; then
    echo "❌ web/out/index.html is missing. Run scripts/build_web.sh first."
    exit 1
fi

echo "Building release: $NAME"
rm -rf "$DIST_DIR"
mkdir -p "$STAGE_DIR"

# rsync the project into the staging dir, excluding everything the user
# doesn't need / shouldn't get (credentials, caches, dev artifacts).
rsync -a \
    --exclude='venv/' \
    --exclude='venv_*/' \
    --exclude='.git/' \
    --exclude='.github/' \
    --exclude='.pytest_cache/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='data/cache/' \
    --exclude='data/internal/' \
    --exclude='web/node_modules/' \
    --exclude='web/.next/' \
    --exclude='*.egg-info/' \
    --exclude='.DS_Store' \
    --exclude='dist/' \
    --exclude='build/' \
    --exclude='.env' \
    --exclude='.pip_install.log' \
    --exclude='.mcp.json' \
    --exclude='communications/' \
    --exclude='docs/' \
    --exclude='TOP 10*.7z' \
    --exclude='TOP 10*.7z.tmp' \
    --exclude='TOP 10*.csv' \
    --exclude='*.csv' \
    --exclude='*.tar.gz' \
    --exclude='/tmp/' \
    "$PROJECT_ROOT/" "$STAGE_DIR/"

# Sanity checks on the staged tree
[ -f "$STAGE_DIR/start.command" ] || { echo "❌ start.command missing from stage"; exit 1; }
[ -f "$STAGE_DIR/start.bat" ]      || { echo "❌ start.bat missing from stage"; exit 1; }
[ -f "$STAGE_DIR/web/out/index.html" ] || { echo "❌ web/out/ missing from stage"; exit 1; }
[ -f "$STAGE_DIR/INSTALL.md" ]     || { echo "❌ INSTALL.md missing from stage"; exit 1; }

# Make sure start.command is executable in the zip
chmod +x "$STAGE_DIR/start.command" 2>/dev/null || true

# Zip from inside dist/ so the archive's top-level entry is the named folder.
cd "$DIST_DIR"
zip -r -q "${NAME}.zip" "$NAME"
cd "$PROJECT_ROOT"

SIZE=$(du -h "$DIST_DIR/${NAME}.zip" | awk '{print $1}')
echo
echo "✓ $DIST_DIR/${NAME}.zip ($SIZE)"
echo
echo "Next: upload to GitHub Releases, or push a matching git tag to trigger CI."
