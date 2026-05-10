"""Pure-Python helpers used by the FastAPI app (api/).

Lives in core/ rather than api/ because nothing here depends on FastAPI
(or any web framework) — they're plain subprocess + file-I/O helpers
that can be exercised in headless tests or scripts without spinning up
a server.
"""

# Hardcoded fallback — used when no code overlay is active (fresh
# install, source mode without an overlay, etc.). Read by:
#   - packaging/setup_py2app.py — sets CFBundleVersion + CFBundleShortVersionString
#   - core/updater.py — compares against GitHub Releases tags
#   - api/routes/updates.py — returned to the UI's "Check for updates"
_BUNDLED_VERSION = "0.4.3"


def _resolve_version() -> str:
    """Pick the running version.

    Prefers the user code overlay's manifest.json (~/Library/.../FaroAI/
    code/manifest.json) if it exists and parses. That keeps
    ``core.__version__`` in sync with whatever code is actually
    executing — important because Python loads ``core/__init__.py``
    BEFORE ``core/__main__.py`` runs the overlay hook, so the bundled
    package metadata can't otherwise reflect a patch update. The
    overlay's Python modules (api.*, mcp_server.*, etc.) load
    correctly from the overlay; only this package's metadata needs the
    manifest fallback.

    Falls back to ``_BUNDLED_VERSION`` if anything goes wrong — better
    to under-report than to crash at import.
    """
    try:
        import json
        import os
        import platform
        from pathlib import Path

        override = os.environ.get("FAROAI_CONFIG_DIR")
        if override:
            cfg = Path(override).expanduser().resolve()
        elif platform.system() == "Darwin":
            cfg = Path.home() / "Library" / "Application Support" / "FaroAI"
        elif platform.system() == "Windows":
            base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
            cfg = Path(base) / "FaroAI"
        else:
            base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
            cfg = Path(base) / "faroai"

        manifest = cfg / "code" / "manifest.json"
        if manifest.is_file():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            v = data.get("version")
            if isinstance(v, str) and v:
                return v
    except Exception:
        pass
    return _BUNDLED_VERSION


__version__ = _resolve_version()
