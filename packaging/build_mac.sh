#!/usr/bin/env bash
# Build FaroAI.app from source.
#
# Usage:
#   ./packaging/build_mac.sh         # full build, cleans dist/ first
#   ./packaging/build_mac.sh --dirty  # incremental build, skips clean
#
# Output: dist/FaroAI.app — drag to /Applications to install.
#
# The build runs in a parallel Python 3.12 venv (venv-py312/) because
# py2app's vendored Python framework currently maxes at 3.13 and the
# main dev venv is on 3.14. The build venv is created on first run and
# kept around for incremental builds.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BUILD_VENV="venv-py312"
DIRTY=false
[[ "${1:-}" == "--dirty" ]] && DIRTY=true

# 1. Build venv (Python 3.12). Created idempotently so subsequent
#    builds skip the install step.
if [ ! -d "$BUILD_VENV" ]; then
    echo "==> Creating $BUILD_VENV (one-time setup, ~30s)…"
    python3.12 -m venv "$BUILD_VENV"
    "$BUILD_VENV/bin/pip" install --quiet --upgrade pip
    "$BUILD_VENV/bin/pip" install --quiet -r requirements.txt
    "$BUILD_VENV/bin/pip" install --quiet py2app
fi

source "$BUILD_VENV/bin/activate"

# 2. Frontend must be built first — the bundled .app references
#    web/out/ from Contents/Resources. Skip if --dirty + already built.
if [ ! -d "web/out" ] || [ "$DIRTY" = false ]; then
    echo "==> Building frontend (web/out)…"
    (cd web && npm run build)
fi

# 3. Clean previous build artifacts unless --dirty.
if [ "$DIRTY" = false ]; then
    echo "==> Cleaning build/ + dist/…"
    rm -rf build dist
fi

# 4. Run py2app.
echo "==> Running py2app (~60-180s on first build)…"
python packaging/setup_py2app.py py2app --no-strip 2>&1 | tail -20

# 5. Post-build: copy namespace packages py2app's old find_module
#    can't enumerate. The Gemini SDK lives under `google.*` (PEP 420
#    namespace package); py2app's `includes` mode pulls individual
#    module files but not the full package tree, so we copy the
#    venv's google/ + grpc/ directories into the bundle's site-packages
#    after py2app finishes. Same trick for any future namespace dep.
APP_LIB="dist/FaroAI.app/Contents/Resources/lib/python3.12"
VENV_LIB="$BUILD_VENV/lib/python3.12/site-packages"
if [ -d "dist/FaroAI.app" ]; then
    echo "==> Copying namespace packages (google, grpc) into the bundle…"
    for pkg in google grpc; do
        if [ -d "$VENV_LIB/$pkg" ] && [ ! -d "$APP_LIB/$pkg" ]; then
            cp -R "$VENV_LIB/$pkg" "$APP_LIB/$pkg"
        fi
    done
    # Also copy any *.dist-info dirs Python's package discovery uses
    # to find google.genai's metadata. Without these, `google.genai`
    # imports fine but introspection (e.g. version checks) breaks.
    for di in "$VENV_LIB"/google_*-*.dist-info "$VENV_LIB"/grpcio-*.dist-info; do
        [ -d "$di" ] && cp -R "$di" "$APP_LIB/"
    done
fi

# 6. Wrap the .app in a .dmg installer for distribution.
#    Uses macOS's built-in hdiutil so no extra tools needed (vs.
#    create-dmg which requires Homebrew). Plain layout — the user
#    drags FaroAI.app onto /Applications inside the mounted disk image.
#    Skip with SKIP_DMG=1 ./packaging/build_mac.sh during dev.
if [ -d "dist/FaroAI.app" ] && [ -z "${SKIP_DMG:-}" ]; then
    # Read _BUNDLED_VERSION (the literal fallback). Runtime __version__
    # is a function call now, so we grep the constant the function falls
    # back to — same value, parseable from the source file.
    VERSION=$(python -c "import re; print(re.search(r'_BUNDLED_VERSION\s*=\s*[\"\'](.*)[\"\']', open('core/__init__.py').read()).group(1))")
    DMG="dist/FaroAI-v${VERSION}.dmg"
    # Use ASCII dots — macOS's bundled bash 3.2 parses the Unicode
    # ellipsis (…) as part of the adjacent variable name, hitting
    # "unbound variable" under set -u. Other ellipses in this script
    # are fine because no $VAR reference sits immediately to their left.
    echo "==> Building ${DMG} ..."
    rm -f "$DMG"
    hdiutil create \
        -volname "FaroAI" \
        -srcfolder dist/FaroAI.app \
        -ov \
        -format UDZO \
        "$DMG" > /dev/null
fi

# 7. Report.
if [ -d "dist/FaroAI.app" ]; then
    SIZE=$(du -sh dist/FaroAI.app | cut -f1)
    echo
    echo "==> Built dist/FaroAI.app ($SIZE)"
    if [ -f "$DMG" ]; then
        DMG_SIZE=$(du -sh "$DMG" | cut -f1)
        echo "==> Built $DMG ($DMG_SIZE) — drag-to-install installer for distribution"
    fi
    echo "    Test:    open dist/FaroAI.app"
    echo "    Install: cp -R dist/FaroAI.app /Applications/"
    echo "    First-launch warning is expected (unsigned)."
    echo "    Right-click → Open → confirm Gatekeeper dialog once."
else
    echo "==> BUILD FAILED — dist/FaroAI.app not produced"
    exit 1
fi
