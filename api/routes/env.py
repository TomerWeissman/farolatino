"""GET / PUT /api/env — view + edit credentials in the project's .env.

Lets the user manage API keys from the Connections page without
dropping into a code editor. Returns masked previews on read; accepts
plain values on write. Writes go through dotenv.set_key (atomic, comment-
preserving) and update the running process's os.environ so subsequent
API calls and subprocesses see the new value immediately.

Whitelist-only: we expose ONLY the keys the dashboard actually uses,
so writing a typo'd key here can't accidentally pollute the rest of
the .env. Keys outside the whitelist are rejected with 400.

Single-tenant local app: this endpoint runs on localhost only and
manages credentials the user owns. We still mask values on read so
secrets don't leak into screenshots / DevTools logs.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv, set_key
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.paths import credentials_path


def _env_path() -> Path:
    """V2: writes go to ~/Library/Application Support/FaroAI/credentials.env
    (or the platform equivalent). Wrapped in a function so tests can
    swap the location via ``FAROAI_CONFIG_DIR`` mid-run without
    re-importing the module.
    """
    return credentials_path()


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Keys the dashboard surfaces. Order is the order the UI groups them.
EXPOSED_VARS: list[str] = [
    # LLM provider — single field, auto-sniffs Anthropic / OpenAI /
    # Gemini from the key's prefix. One key in, one model out.
    "LLM_API_KEY",
    # Chartmetric
    "CHARTMETRIC_REFRESH_TOKEN",
    # Spotify
    "SPOTIFY_CLIENT_ID",
    "SPOTIFY_CLIENT_SECRET",
    # YouTube
    "YOUTUBE_API_KEY",
    "YOUTUBE_CLIENT_ID",
    "YOUTUBE_CLIENT_SECRET",
    "YOUTUBE_REFRESH_TOKEN",
    # Alerts (used by route_alert + the email/whatsapp adapters)
    "ALERT_FROM_EMAIL",
    "ALERT_TO_EMAILS",
    "ALERT_WHATSAPP_NUMBERS",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_WHATSAPP_FROM",
]

router = APIRouter()


class EnvVar(BaseModel):
    name: str
    populated: bool
    preview: str | None  # masked first/last few chars; None when empty
    length: int          # actual char count of the underlying value


class EnvBundle(BaseModel):
    vars: list[EnvVar]


class EnvUpdate(BaseModel):
    updates: dict[str, str]


def _mask(value: str) -> str | None:
    """Display-safe preview. Empty → None; <12 chars → all dots; else
    first 4 + dots + last 4. Never reveals the middle."""
    if not value:
        return None
    if len(value) < 12:
        return "•" * len(value)
    return f"{value[:4]}{'•' * 4}{value[-4:]}"


def _snapshot() -> EnvBundle:
    return EnvBundle(vars=[
        EnvVar(
            name=k,
            populated=bool(os.getenv(k)),
            preview=_mask(os.getenv(k, "")),
            length=len(os.getenv(k, "")),
        )
        for k in EXPOSED_VARS
    ])


@router.get("/env", response_model=EnvBundle)
def get_env() -> EnvBundle:
    return _snapshot()


@router.put("/env", response_model=EnvBundle)
def put_env(payload: EnvUpdate) -> EnvBundle:
    # Reject anything not in the whitelist.
    bad = [k for k in payload.updates if k not in EXPOSED_VARS]
    if bad:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot edit unknown env var(s): {', '.join(bad)}",
        )

    # Reject impossibly long values (defense vs accidental paste of an
    # entire file).
    for k, v in payload.updates.items():
        if len(v) > 4000:
            raise HTTPException(
                status_code=413,
                detail=f"{k} > 4000 chars; refusing (paste error?)",
            )

    # Make sure the .env exists — dotenv's set_key will refuse to write
    # to a path that doesn't resolve, so create an empty file if needed.
    env_path = _env_path()
    env_path.touch(exist_ok=True)

    # set_key handles quoting, atomic write, and preserves the rest of
    # the file (other keys, comments, blank lines).
    for k, v in payload.updates.items():
        set_key(str(env_path), k, v)
        os.environ[k] = v

    # Reload from disk so any module that reads via os.getenv (without
    # caching) picks up the change. override=True overwrites whatever
    # was already in os.environ.
    load_dotenv(env_path, override=True)

    # Clear caches that hold credentials in memory.
    _invalidate_caches()

    return _snapshot()


def _invalidate_caches() -> None:
    """Clear in-memory token caches + the connections-status cache so
    the next call exercises the new credentials."""
    # Connections + health caches — bypassed via the existing ?t= query
    # param too, but clearing here means the next call without cache-
    # busting also sees fresh state. Without clearing health, a user
    # who pastes an OPENAI_API_KEY would still see llm_provider="none"
    # in the sidebar pill for up to 5 minutes (the health TTL).
    from api.routes.connections import _cache as conn_cache
    conn_cache.clear()
    from api.routes.health import _cache as health_cache
    health_cache.clear()

    # Drop the cached LLM provider instance so a key swap takes effect
    # without restarting the process. Without this, a user who pastes
    # a new ANTHROPIC_API_KEY would still see the old client until the
    # next uvicorn restart.
    from core.llm import reset_provider_cache
    reset_provider_cache()

    # Connector token caches — walk the registry so adding a new
    # connector with its own cache doesn't require editing this list.
    from core.connectors import reset_all_caches
    reset_all_caches()
