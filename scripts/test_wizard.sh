#!/bin/bash
# Self-test the V1 setup wizard in an isolated copy of the project.
#
# Creates a fresh project snapshot at $1 (default ~/Desktop/farolatino_wizard_test/),
# excluding venv/, data/cache/, data/internal/, .git/, and other dev artifacts.
# This lets you verify the start.command flow exactly as a non-technical
# tester would experience it, without touching your real venv or cached data.
#
# Usage:
#   ./scripts/test_wizard.sh                                # default destination
#   ./scripts/test_wizard.sh ~/tmp/test1                    # custom path
#   ./scripts/test_wizard.sh --force                        # overwrite existing
#   ./scripts/test_wizard.sh --cleanup ~/Desktop/farolatino_wizard_test
#
# After running, open the destination folder in Finder and double-click start.command.

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

DEFAULT_DEST="$HOME/Desktop/farolatino_wizard_test"
FORCE=0
CLEANUP=""

# Parse args
DEST=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --force) FORCE=1; shift ;;
        --cleanup)
            CLEANUP="$2"
            if [ -z "$CLEANUP" ]; then
                echo "Error: --cleanup requires a path."
                exit 1
            fi
            shift 2 ;;
        -h|--help)
            sed -n '1,/^set -e/p' "$0" | sed 's/^# \?//'
            exit 0 ;;
        *)
            DEST="$1"; shift ;;
    esac
done

# Cleanup mode
if [ -n "$CLEANUP" ]; then
    if [ ! -d "$CLEANUP" ]; then
        echo "Nothing to clean up at: $CLEANUP"
        exit 0
    fi
    if [ "$CLEANUP" = "/" ] || [ "$CLEANUP" = "$HOME" ] || [ "$CLEANUP" = "$PROJECT_ROOT" ]; then
        echo "Refusing to delete: $CLEANUP"
        exit 1
    fi
    echo "Removing $CLEANUP ..."
    rm -rf "$CLEANUP"
    echo "Done."
    exit 0
fi

DEST="${DEST:-$DEFAULT_DEST}"

# Refuse to overwrite project itself
if [ "$DEST" = "$PROJECT_ROOT" ]; then
    echo "❌ Refusing to use the project directory as the test destination."
    exit 1
fi

# Existing destination check
if [ -e "$DEST" ]; then
    if [ "$FORCE" -ne 1 ]; then
        echo "❌ Destination already exists: $DEST"
        echo "   Pass --force to overwrite, or --cleanup $DEST to delete it first."
        exit 1
    fi
    echo "Removing existing $DEST ..."
    rm -rf "$DEST"
fi

mkdir -p "$DEST"
echo "Copying project snapshot to: $DEST"

# Copy with exclusions. rsync handles trailing-slash semantics: copy CONTENTS of project root.
rsync -a \
    --exclude='venv/' \
    --exclude='venv_*/' \
    --exclude='.git/' \
    --exclude='.pytest_cache/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='data/cache/' \
    --exclude='data/internal/' \
    --exclude='.streamlit/' \
    --exclude='streamlit_app/.streamlit/' \
    --exclude='TOP 10*.7z' \
    --exclude='TOP 10*.7z.tmp' \
    --exclude='*.egg-info/' \
    --exclude='.DS_Store' \
    --exclude='dist/' \
    --exclude='build/' \
    --exclude='communications/' \
    "$PROJECT_ROOT/" "$DEST/"

# Sanity check: did .env make it (it must, otherwise the test is meaningless)
if [ ! -f "$DEST/.env" ]; then
    echo
    echo "⚠️  Warning: $DEST/.env is missing. Tester won't have credentials."
    echo "   If you intended to include it, check the rsync exclusions above."
fi

# Sanity check: launcher made it
if [ ! -f "$DEST/start.command" ]; then
    echo "❌ start.command was not copied. Aborting."
    exit 1
fi
chmod +x "$DEST/start.command" 2>/dev/null || true

echo
echo "✓ Snapshot ready at: $DEST"
echo
echo "Next step:"
echo "  1. Open the folder in Finder:"
echo "       open \"$DEST\""
echo "  2. Double-click start.command"
echo "  3. Watch Terminal: it should create venv (~30s), install deps (~60s),"
echo "     and open the dashboard in your browser."
echo
echo "When you're done testing:"
echo "  ./scripts/test_wizard.sh --cleanup \"$DEST\""
echo
