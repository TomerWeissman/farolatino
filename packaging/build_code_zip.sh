#!/usr/bin/env bash
# Build the code-only update zip for the in-app updater.
#
# Produces dist/faroai-code-vX.Y.Z.zip — a small archive containing
# everything the user code overlay needs to shadow the bundled
# install. core/__main__._wire_user_code_overlay reads manifest.json,
# prepends code/ to sys.path, and the rest of the codebase loads
# from there. api/main._resolve_web_out picks code/web/out/ if
# present, falling back to the bundle.
#
# Usage:
#   ./packaging/build_code_zip.sh v0.4.1
#
# Run from the project root. CI invokes this from the build-codezip
# job after `npm run build` has populated web/out/.
set -euo pipefail

TAG="${1:?tag required, e.g. v0.4.1}"
VERSION="${TAG#v}"
OUT_DIR="dist"
ZIP_NAME="faroai-code-${TAG}.zip"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$OUT_DIR"

# Each path corresponds to a layer category in core/overlay.py or to
# a Python module tree the user-code overlay shadows via sys.path.
# rsync --relative preserves the path structure inside STAGE so the
# zip's tree mirrors the project's tree.
for path in api core mcp_server web/out FAROAI.md FAROAI.es.md config; do
  if [ -e "$path" ]; then
    rsync -a \
      --exclude='__pycache__' \
      --exclude='*.pyc' \
      --exclude='.DS_Store' \
      --relative "$path" "$STAGE/"
  else
    echo "warning: $path not found, skipping" >&2
  fi
done

# Manifest at the zip root — required by both
# core/__main__._wire_user_code_overlay (must contain "version") and
# core/updater.apply_update (must exist + parse as JSON).
cat > "$STAGE/manifest.json" <<EOF
{
  "version": "${VERSION}",
  "built_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "git_sha": "${GITHUB_SHA:-$(git rev-parse HEAD 2>/dev/null || echo unknown)}"
}
EOF

# Zip from inside the staging dir so paths in the archive are
# relative to the overlay root (no leading "stage/" prefix).
( cd "$STAGE" && zip -rq "${ZIP_NAME}" . )
mv "$STAGE/${ZIP_NAME}" "$OUT_DIR/${ZIP_NAME}"

echo "Built $OUT_DIR/${ZIP_NAME}"
ls -lh "$OUT_DIR/${ZIP_NAME}"
