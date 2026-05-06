"""Filesystem paths for V2.

V1 stuck everything in the project directory: ``.env``, run logs,
cached Chartmetric responses. That works for source installs but
breaks the moment the app gets bundled (`Contents/Resources/` is
read-only on macOS, the install dir is per-user on Windows, etc.).

V2 separates **app code** (lives wherever the install puts it,
read-only after install) from **user data** (lives under the OS-
standard config dir, survives upgrades, owned by the user). The
critical one is ``credentials_path()`` — paste-an-API-key has to
write somewhere durable that the bundled app can re-read on next
launch.

Directory layout (mac shown; Windows + Linux equivalent):

  ~/Library/Application Support/FaroAI/
    credentials.env          # what was previously project-root .env
    chat_runs.jsonl          # run log
    cache/                   # Chartmetric snapshots, etc.

A one-time migration copies project-root ``.env`` to
``credentials.env`` on first launch and renames the source to
``.env.legacy``. The plan calls this out as "the bundle's install
dir becomes pure code; user data is separate (survives app upgrades)".
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from platformdirs import user_config_path

# App identity — used by platformdirs to pick the right per-OS dir.
# Capitalized to match macOS Application Support convention.
_APP_NAME = "FaroAI"
_APP_AUTHOR = "FaroLatino"  # Windows folds it under <author>\<app>; mac/linux ignore it

# Project root for the legacy .env source. Resolved relative to this
# file rather than the cwd so it works regardless of where uvicorn was
# launched from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def app_config_dir() -> Path:
    """Return the per-user config dir for FaroAI, creating it if needed.

    Honors ``FAROAI_CONFIG_DIR`` first so tests can point at a tmp dir
    without polluting the real config. The plan calls this out as the
    dev-mode footgun mitigation.
    """
    override = os.environ.get("FAROAI_CONFIG_DIR")
    if override:
        path = Path(override).expanduser().resolve()
    else:
        path = user_config_path(_APP_NAME, _APP_AUTHOR, ensure_exists=False)
    path.mkdir(parents=True, exist_ok=True)
    return path


def credentials_path() -> Path:
    """Where API keys + other env vars are stored.

    Read by ``load_dotenv`` at boot; written by ``PUT /api/env`` when
    the user pastes a new key in Connections. Lives under the user
    data dir so a bundled app upgrade doesn't blow it away.
    """
    return app_config_dir() / "credentials.env"


def runs_log_path() -> Path:
    """JSONL run log. One line per chat turn (see core/run_log.py)."""
    return app_config_dir() / "chat_runs.jsonl"


def cache_dir() -> Path:
    """Per-artist Chartmetric snapshot cache lives here.

    Honors ``FAROAI_CACHE_DIR`` (legacy V1 env var still respected by
    ``data_cache.py``) so existing tests pinning a tmp cache keep working.
    """
    override = os.environ.get("FAROAI_CACHE_DIR")
    if override:
        path = Path(override).expanduser().resolve()
    else:
        path = app_config_dir() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def legacy_env_path() -> Path:
    """The V1 location of ``.env`` — project root.

    One-time migration source. Once ``migrate_legacy_env_if_present()``
    has run, this file has been renamed to ``.env.legacy`` so future
    boots don't repeatedly clobber the migrated copy.
    """
    return PROJECT_ROOT / ".env"


def legacy_env_archived_path() -> Path:
    """Where the legacy ``.env`` is moved to after migration.

    Kept (not deleted) so the user has a recovery copy in case the
    migration corrupts something — they can manually copy values back.
    """
    return PROJECT_ROOT / ".env.legacy"


def migrate_legacy_env_if_present() -> bool:
    """Copy project-root ``.env`` to ``credentials.env`` on first run.

    Idempotent: if ``credentials.env`` already exists OR if the legacy
    file isn't there, this is a no-op. Returns True iff a migration
    actually happened — caller can use the boolean to log a one-time
    notice.
    """
    src = legacy_env_path()
    dest = credentials_path()
    if dest.exists():
        return False
    if not src.exists():
        return False

    # Atomic-ish: write to dest, then rename source to .legacy.
    # shutil.copy preserves content but we don't need ownership/timestamps.
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dest)
    archived = legacy_env_archived_path()
    try:
        os.replace(src, archived)
    except OSError:
        # Source rename failed (read-only fs, etc.); leave both files
        # in place. The dest copy is what gets read going forward.
        pass
    return True


def load_credentials() -> None:
    """Migrate legacy ``.env`` (if present) and ``load_dotenv`` from the
    canonical V2 location.

    Idempotent + cheap — call from any module that needs env vars at
    import time. Centralising the migration step here means auth
    modules + api/main + scripts all observe the same one-shot
    transition without each having to remember the order of operations.
    """
    from dotenv import load_dotenv  # local import keeps top-level cheap
    migrate_legacy_env_if_present()
    load_dotenv(credentials_path())
    # Also load the legacy .env if it still exists — protects dev
    # installs where credentials.env hasn't been populated yet (e.g.
    # tests imported before api/main.py ran the migration).
    legacy = legacy_env_path()
    if legacy.exists():
        load_dotenv(legacy)


def resource_path(name: str) -> Path:
    """Resolve a packaged resource (web/out, FAROAI.md, .claude/skills/, ...).

    In source mode this is just ``PROJECT_ROOT / name``. When py2app
    bundles us in Phase 6, the resources land under
    ``Contents/Resources/`` and ``sys.frozen`` is set; we honor that
    here so api/main + agent_runner don't have to special-case the
    bundled-vs-source split.
    """
    if getattr(sys, "frozen", False):
        # py2app: resources are at Contents/Resources/<name> alongside the
        # frozen binary at Contents/MacOS/<binary>.
        bundle_resources = Path(sys.executable).resolve().parent.parent / "Resources"
        candidate = bundle_resources / name
        if candidate.exists():
            return candidate
    return PROJECT_ROOT / name
