"""YouTube Data API v3 authentication — OAuth refresh-token flow.

We use OAuth (not just an API key) because the .env is wired with
client_id + client_secret + refresh_token from Google Cloud Console.
This unlocks both public read endpoints AND any private channel data
the granted scopes allow (analytics, etc.).

Token lifecycle:
1. Refresh token (permanent, in .env)
2. Access token (1 hour, refreshed on demand)

Tokens are cached at module level with a 5-minute expiry buffer so
multiple tool calls in a row don't trigger redundant refreshes.

If only YOUTUBE_API_KEY is populated and no OAuth, we fall back to
the API key (read-only, public data, simpler) — both work for the
tools we expose right now.
"""
from __future__ import annotations

import os
import threading
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

API_BASE = "https://www.googleapis.com/youtube/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"

_access_token: str | None = None
_token_expires_at: float = 0.0
_token_lock = threading.Lock()
_EXPIRY_BUFFER_SECONDS = 300


class YouTubeAuthError(RuntimeError):
    """No usable credentials in .env (neither OAuth triple nor API key)."""


def _have_oauth() -> bool:
    return all(
        os.getenv(k) for k in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")
    )


def _refresh_token() -> None:
    """Exchange the refresh token for a fresh access token."""
    global _access_token, _token_expires_at

    if not _have_oauth():
        raise YouTubeAuthError(
            "OAuth credentials missing — set YOUTUBE_CLIENT_ID, "
            "YOUTUBE_CLIENT_SECRET, and YOUTUBE_REFRESH_TOKEN in .env "
            "(or YOUTUBE_API_KEY for read-only public access)."
        )

    try:
        r = httpx.post(
            TOKEN_URL,
            data={
                "client_id": os.getenv("YOUTUBE_CLIENT_ID"),
                "client_secret": os.getenv("YOUTUBE_CLIENT_SECRET"),
                "refresh_token": os.getenv("YOUTUBE_REFRESH_TOKEN"),
                "grant_type": "refresh_token",
            },
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise ConnectionError(f"Cannot reach YouTube token endpoint: {exc}") from exc

    if r.status_code != 200:
        raise YouTubeAuthError(
            f"YouTube rejected refresh-token exchange ({r.status_code}): {r.text[:200]}"
        )
    data = r.json()
    _access_token = data["access_token"]
    _token_expires_at = time.time() + data.get("expires_in", 3600) - _EXPIRY_BUFFER_SECONDS


def get_access_token() -> str:
    """Return a valid OAuth access token, refreshing if needed."""
    with _token_lock:
        if _access_token is None or time.time() >= _token_expires_at:
            _refresh_token()
        assert _access_token is not None
        return _access_token


def api_get(path: str, params: dict | None = None) -> dict:
    """GET https://www.googleapis.com/youtube/v3{path}.

    Prefers OAuth (Bearer header) when configured; falls back to
    `key=<API_KEY>` if only the API key is set. Both work for the
    public read endpoints our tools currently use.
    """
    full_params = dict(params or {})
    headers: dict[str, str] = {}

    if _have_oauth():
        headers["Authorization"] = f"Bearer {get_access_token()}"
    elif os.getenv("YOUTUBE_API_KEY"):
        full_params["key"] = os.getenv("YOUTUBE_API_KEY")
    else:
        raise YouTubeAuthError(
            "No YouTube credentials in .env — set either OAuth triple "
            "or YOUTUBE_API_KEY."
        )

    try:
        r = httpx.get(f"{API_BASE}{path}", headers=headers, params=full_params, timeout=15.0)
    except httpx.HTTPError as exc:
        raise ConnectionError(f"YouTube request failed: {exc}") from exc
    if r.status_code == 401 and _have_oauth():
        # Force refresh + retry once.
        with _token_lock:
            _refresh_token()
        headers["Authorization"] = f"Bearer {_access_token}"
        r = httpx.get(f"{API_BASE}{path}", headers=headers, params=full_params, timeout=15.0)
    if r.status_code >= 400:
        raise ConnectionError(f"YouTube {r.status_code} on {path}: {r.text[:300]}")
    return r.json()
