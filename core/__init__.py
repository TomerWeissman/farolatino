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
_BUNDLED_VERSION = "0.5.4"


import re as _re

# semver pattern used for sanity-checking values pulled from an
# overlay manifest. A corrupt or partially-written manifest (e.g.
# write interrupted mid-update) must NOT be allowed to register as
# the running version — otherwise we'd silently keep prompting the
# user to "update" forever.
_SEMVER_RE = _re.compile(r"^\d+\.\d+\.\d+")


def _config_dir_for_version() -> "Path":  # type: ignore[name-defined]
    """Resolve the per-user config dir without importing core.paths.

    core/__init__.py runs at import time, before the overlay hook in
    core/__main__.py has swapped in the user overlay's sys.path entry.
    Importing core.paths here would (a) be a circular-ish dependency
    and (b) potentially pin to the bundled module before the overlay
    takes effect. We replicate just the per-OS resolution rules.
    """
    import os
    import platform
    from pathlib import Path

    override = os.environ.get("FAROAI_CONFIG_DIR")
    if override:
        return Path(override).expanduser().resolve()
    sysname = platform.system()
    if sysname == "Darwin":
        return Path.home() / "Library" / "Application Support" / "FaroAI"
    if sysname == "Windows":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "FaroAI"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "faroai"


def _resolve_version() -> str:
    """Pick the running version.

    Prefers the user code overlay's manifest.json if it exists, parses,
    AND contains a valid semver. Any of: missing file, malformed JSON,
    missing version key, or non-semver value → fall back to bundled.
    A corrupt manifest used to leak through as the running version,
    which then never matched GitHub's latest tag → infinite update loop.

    Telemetry: on first call we append a single line to the update log
    so a field-deployed app can be debugged from the user's machine
    without rebuilding.
    """
    import json

    chosen = _BUNDLED_VERSION
    branch = "bundled (no overlay)"
    manifest_path = None

    try:
        cfg = _config_dir_for_version()
        manifest_path = cfg / "code" / "manifest.json"
        if manifest_path.is_file():
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as exc:
                branch = f"bundled (manifest unreadable: {exc.__class__.__name__})"
            else:
                v = data.get("version") if isinstance(data, dict) else None
                if not isinstance(v, str) or not _SEMVER_RE.match(v.strip()):
                    branch = f"bundled (manifest version invalid: {v!r})"
                else:
                    chosen = v.strip()
                    branch = "overlay manifest"
        else:
            branch = "bundled (manifest absent)"
    except Exception as exc:
        branch = f"bundled (resolver exception: {exc.__class__.__name__})"

    _log_version_resolution(manifest_path, chosen, branch)
    return chosen


def _log_version_resolution(manifest_path, chosen: str, branch: str) -> None:
    """One-shot diagnostic line per process startup.

    Written to ``<config>/logs/update.log`` so when a user reports
    "it keeps telling me to update", we can ask them to send that
    file and see exactly which branch fired.
    """
    try:
        from datetime import datetime

        cfg = _config_dir_for_version()
        log_dir = cfg / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "update.log"
        line = (
            f"{datetime.now().isoformat(timespec='seconds')} "
            f"version_resolve bundled={_BUNDLED_VERSION} "
            f"chosen={chosen} branch=\"{branch}\" "
            f"manifest={manifest_path}\n"
        )
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        # Logging must never crash import.
        pass


__version__ = _resolve_version()
