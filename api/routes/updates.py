"""GET /api/updates/check, POST /api/updates/apply.

Frontend calls these from the "Check for updates" button on the
Connections page. ``check`` is idempotent + cheap (one GitHub Releases
API call); ``apply`` triggers the download + verify + extract + restart
flow in ``core.updater``.

This is single-tenant for FaroLatino — there's no auth on these
endpoints because the app already only listens on 127.0.0.1.
"""
from __future__ import annotations

import logging
from threading import Thread

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core import __version__
from core.updater import UpdateError, UpdateInfo, apply_update, check_for_update

router = APIRouter()
log = logging.getLogger(__name__)


class CheckResponse(BaseModel):
    current_version: str
    latest_version: str
    update_available: bool
    can_apply_in_app: bool  # True iff a code-only zip exists (vs full reinstall)
    download_url: str | None
    release_notes: str | None
    error: str | None = None


class ApplyResponse(BaseModel):
    started: bool
    message: str


@router.get("/version", response_model=dict)
def get_version() -> dict:
    """Trivial endpoint the UI calls on launch to render the running
    version next to the 'Check for updates' button."""
    return {"version": __version__}


@router.get("/updates/check", response_model=CheckResponse)
def check_updates() -> CheckResponse:
    """Check GitHub for a newer release. Returns enough info for the
    UI to show 'You're up to date' or 'v0.2.1 available — Update'."""
    try:
        info: UpdateInfo = check_for_update()
    except UpdateError as exc:
        return CheckResponse(
            current_version=__version__,
            latest_version=__version__,
            update_available=False,
            can_apply_in_app=False,
            download_url=None,
            release_notes=None,
            error=str(exc),
        )
    return CheckResponse(
        current_version=info.current_version,
        latest_version=info.latest_version,
        update_available=info.update_available,
        can_apply_in_app=info.update_available and info.download_url is not None,
        download_url=info.download_url,
        release_notes=info.release_notes,
    )


@router.post("/updates/apply", response_model=ApplyResponse)
def apply_updates() -> ApplyResponse:
    """Apply the latest code-only update.

    Runs the download + verify + extract + restart flow. The restart
    happens inside ``apply_update`` via ``os.execv``, so this handler
    won't return — uvicorn dies with the parent process and the new
    one starts. The frontend will see a stream-end and reconnect.
    """
    try:
        info = check_for_update()
    except UpdateError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not info.update_available:
        return ApplyResponse(started=False, message="Already up to date.")
    if not info.download_url:
        raise HTTPException(
            status_code=409,
            detail=(
                "This update needs a new installer download — full bundle "
                "changes (Python or SDK version) can't be applied in-app. "
                "Download the latest .dmg from the Releases page."
            ),
        )

    # Run the apply in a daemon thread — gives the HTTP response a
    # chance to flush before the os.execv() blows the process away.
    # Without this, the UI sees the connection drop before getting the
    # 200 OK, and the user can't tell whether the update started.
    def _do_apply() -> None:
        try:
            apply_update(info, restart=True)
        except UpdateError as exc:
            log.error("apply_update failed: %s", exc)
        except Exception:
            log.exception("apply_update crashed")

    Thread(target=_do_apply, name="faroai-updater", daemon=True).start()
    return ApplyResponse(
        started=True,
        message=f"Downloading v{info.latest_version}… app will restart shortly.",
    )
