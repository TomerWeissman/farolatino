"""In-app code-only updates from GitHub Releases.

Every release tag pushed to the repo triggers GitHub Actions to
publish two artifacts:
  - ``FaroAI-vX.Y.Z.dmg``        — full bundle (~400 MB), one-time
                                    install or major version bump.
  - ``faroai-code-vX.Y.Z.zip``   — ~5 MB, this module's target.

The "Check for updates" button on the Connections page calls
``check_for_update()``; if a newer code zip is available, the user
clicks "Update" and ``apply_update()`` downloads the zip, verifies
its SHA256 against a checksum embedded in the GitHub release notes,
extracts it to ``~/Library/Application Support/FaroAI/code/``, and
restarts the app. The next launch picks up the new code via the
overlay hook in ``core/__main__.py``.

Why this is separate from the LLM provider's updater (n/a — it
doesn't have one): code updates are a UI-driven user action, not an
automatic background process. We never silently pull code from the
internet.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from core import __version__ as CURRENT_VERSION
from core.paths import app_config_dir

log = logging.getLogger(__name__)


def _append_update_log(line: str) -> None:
    """Append a diagnostic line to <config>/logs/update.log.

    Mirrors the format used by ``core/__init__.py:_log_version_resolution``
    so all updater telemetry lands in one file. Never raises — logging
    must never break a release check.
    """
    try:
        from datetime import datetime

        log_dir = app_config_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "update.log").open("a", encoding="utf-8").write(
            f"{datetime.now().isoformat(timespec='seconds')} {line}\n"
        )
    except Exception:
        pass


# Where we look for releases. Hardcoded to the FaroLatino repo since
# this is single-tenant — change this only when forking.
GITHUB_OWNER = "TomerWeissman"
GITHUB_REPO = "farolatino"
GITHUB_API_BASE = "https://api.github.com"
GITHUB_LATEST_URL = f"{GITHUB_API_BASE}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

# Asset filename pattern. Must match what GitHub Actions publishes.
CODE_ASSET_PATTERN = re.compile(r"^faroai-code-v(\d+\.\d+\.\d+)\.zip$")


@dataclass
class UpdateInfo:
    """Result of ``check_for_update()`` — passed to the UI."""

    current_version: str
    latest_version: str
    update_available: bool
    download_url: str | None
    expected_sha256: str | None
    release_notes: str | None


class UpdateError(RuntimeError):
    """Anything that goes wrong during check / download / verify / apply.
    Caller surfaces ``str(exc)`` to the user."""


def check_for_update(timeout: float = 10.0) -> UpdateInfo:
    """Hit GitHub Releases API; compare latest tag to ``__version__``.

    Returns an ``UpdateInfo`` with ``update_available`` set. Idempotent
    + side-effect-free; safe to call from a route handler. Errors
    (no network, rate-limit, repo missing) raise ``UpdateError``.
    """
    try:
        # Anonymous GitHub API: 60 req/hr/IP. Plenty for a manual
        # "Check for updates" flow; we don't poll.
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(GITHUB_LATEST_URL, headers={"Accept": "application/vnd.github+json"})
        if resp.status_code == 404:
            raise UpdateError("No releases published yet (404 from GitHub).")
        if resp.status_code == 403:
            raise UpdateError("GitHub API rate-limited. Try again in an hour.")
        if resp.status_code != 200:
            raise UpdateError(f"GitHub returned HTTP {resp.status_code}.")
    except httpx.HTTPError as exc:
        raise UpdateError(f"Couldn't reach GitHub: {exc}") from exc

    payload = resp.json()
    latest_tag = (payload.get("tag_name") or "").lstrip("v")
    if not latest_tag:
        raise UpdateError("Latest release has no tag_name.")

    # Find the code-only asset in the release.
    code_asset = None
    for asset in payload.get("assets") or []:
        if CODE_ASSET_PATTERN.match(asset.get("name", "")):
            code_asset = asset
            break

    asset_name = code_asset.get("name") if code_asset else None
    update_available = _is_newer(latest_tag, CURRENT_VERSION)
    _append_update_log(
        f"check_for_update current={CURRENT_VERSION} latest={latest_tag} "
        f"update_available={update_available} asset={asset_name!r}"
    )

    if code_asset is None:
        # Release exists but no code zip published — full reinstall path.
        return UpdateInfo(
            current_version=CURRENT_VERSION,
            latest_version=latest_tag,
            update_available=update_available,
            download_url=None,
            expected_sha256=None,
            release_notes=payload.get("body"),
        )

    # Convention: the SHA256 lives in the release body as
    # ``faroai-code-vX.Y.Z.zip: <sha256>``. Easier than uploading a
    # separate checksum file. Parsed leniently.
    sha = _extract_sha256(payload.get("body") or "", code_asset["name"])

    return UpdateInfo(
        current_version=CURRENT_VERSION,
        latest_version=latest_tag,
        update_available=update_available,
        download_url=code_asset.get("browser_download_url"),
        expected_sha256=sha,
        release_notes=payload.get("body"),
    )


def apply_update(info: UpdateInfo, *, restart: bool = True) -> None:
    """Download the code zip, verify its SHA256, extract to the user
    ``code/`` overlay, and (optionally) restart the app.

    Raises ``UpdateError`` on any failure. The overlay is only updated
    after successful verification — partial downloads can't corrupt
    the running install.
    """
    if not info.update_available:
        raise UpdateError("Already up to date.")
    if not info.download_url:
        raise UpdateError(
            "This update requires a new installer (no code-only zip published)."
        )

    log.info("downloading %s -> staging", info.download_url)
    zip_bytes = _download(info.download_url)

    if info.expected_sha256:
        actual = hashlib.sha256(zip_bytes).hexdigest()
        if actual.lower() != info.expected_sha256.lower():
            raise UpdateError(
                f"SHA256 mismatch (expected {info.expected_sha256[:8]}…, "
                f"got {actual[:8]}…). Aborting; install untouched."
            )

    # Extract to a temp dir first; only swap into place if extraction
    # succeeds. Atomic-ish — if the extract fails halfway, the live
    # overlay isn't corrupted.
    with tempfile.TemporaryDirectory(prefix="faroai-update-") as staging:
        staging_path = Path(staging)
        try:
            # io.BytesIO is already a fully file-like object — no need
            # for a custom adapter (and Python 3.14's zipfile requires
            # ``seekable()`` which our old wrapper didn't implement).
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                # Reject path-traversal attempts. zipfile's default
                # extractall is unsafe against zip-slip attacks.
                _safe_extract(zf, staging_path)
        except zipfile.BadZipFile as exc:
            raise UpdateError(f"Downloaded file is not a valid zip: {exc}") from exc

        # Manifest required — the overlay hook in __main__ refuses to
        # load a code dir without one. Reject zips that lack it OR
        # that ship a version that disagrees with the release tag (a
        # mismatch leaves __version__ permanently stale, which is the
        # root cause of the "keeps prompting to update" loop).
        manifest_path = staging_path / "manifest.json"
        if not manifest_path.is_file():
            raise UpdateError("Update zip is missing manifest.json.")
        try:
            manifest_data = json.loads(manifest_path.read_text())
        except Exception as exc:
            raise UpdateError(f"manifest.json is not valid JSON: {exc}") from exc

        manifest_version = (manifest_data.get("version") or "").strip().lstrip("v") if isinstance(manifest_data, dict) else ""
        expected_version = info.latest_version.lstrip("v")
        if manifest_version != expected_version:
            _append_update_log(
                f"apply_update aborted: manifest_version={manifest_version!r} "
                f"!= release_tag={expected_version!r}"
            )
            raise UpdateError(
                f"Update aborted: zip manifest says v{manifest_version or '?'} "
                f"but the release tag is v{expected_version}. The downloaded "
                f"build is mislabeled — refusing to swap it in."
            )

        # Replace the live overlay. We keep the previous version under
        # ``code.bak`` so a botched update can be rolled back manually
        # by the user (rename code.bak -> code).
        target = app_config_dir() / "code"
        backup = app_config_dir() / "code.bak"
        if backup.exists():
            shutil.rmtree(backup)
        if target.exists():
            target.rename(backup)
        shutil.copytree(staging_path, target)
        _append_update_log(
            f"apply_update success: installed v{manifest_version} at {target}"
        )

    if restart:
        _restart_app()


# ─── Helpers ────────────────────────────────────────────────────────────


_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")


def _parse_version(s: str) -> tuple[int, int, int] | None:
    """Lenient semver parser. Returns ``None`` if the string doesn't
    look like X.Y.Z (with optional ``v`` prefix or trailing junk)."""
    if not s:
        return None
    m = _VERSION_RE.match(s.lstrip("v"))
    if not m:
        return None
    return tuple(int(g) for g in m.groups())  # type: ignore[return-value]


def _is_newer(candidate: str, current: str) -> bool:
    a = _parse_version(candidate)
    b = _parse_version(current)
    if a is None or b is None:
        return False
    return a > b


def _extract_sha256(body: str, asset_name: str) -> str | None:
    """Pull a hex sha256 out of the release notes for the named asset.

    We accept any of these formats so release-note authoring stays
    friendly:
        faroai-code-v0.2.1.zip: a1b2c3...
        sha256: a1b2c3... (faroai-code-v0.2.1.zip)
        - faroai-code-v0.2.1.zip — sha256: a1b2c3...
    """
    if not body:
        return None
    asset_pattern = re.escape(asset_name)
    # Look for a 64-hex-char chunk on the same line as the asset name.
    line_re = re.compile(
        rf"({asset_pattern}.*?|.*?{asset_pattern}.*)",
        re.IGNORECASE,
    )
    for line in body.splitlines():
        if not line_re.search(line):
            continue
        m = re.search(r"\b([a-f0-9]{64})\b", line, re.IGNORECASE)
        if m:
            return m.group(1).lower()
    return None


def _download(url: str, timeout: float = 60.0) -> bytes:
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url)
        if resp.status_code != 200:
            raise UpdateError(f"Download HTTP {resp.status_code}.")
        return resp.content
    except httpx.HTTPError as exc:
        raise UpdateError(f"Download failed: {exc}") from exc


def _safe_extract(zf: zipfile.ZipFile, target: Path) -> None:
    """Extract a zip without falling for zip-slip path traversal.

    Default zipfile.extractall is vulnerable: a malicious zip can
    contain entries with paths like ``../../etc/passwd`` and
    overwrite arbitrary files. We resolve every entry's destination
    and refuse anything that escapes the target directory.
    """
    target = target.resolve()
    for member in zf.infolist():
        # Reject absolute paths + parent-dir escapes.
        dest = (target / member.filename).resolve()
        if not str(dest).startswith(str(target)):
            raise UpdateError(f"Refusing zip entry outside target: {member.filename}")
    zf.extractall(target)


def _restart_app() -> None:
    """Re-exec the current Python interpreter with the same argv.

    For source-mode this re-runs ``python -m core``. For the bundled
    .app, sys.executable is the .app's Python framework, so re-exec
    relaunches the bundle. The OS keeps the .app's main process
    handle alive across the exec.
    """
    log.info("restarting %s %s", sys.executable, sys.argv)
    os.execv(sys.executable, [sys.executable] + sys.argv)
