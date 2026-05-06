"""Spotify Web API authentication — Client Credentials flow.

We use Client Credentials (not full OAuth) because we only need
public artist data. No user context = no refresh-token dance, just
swap client_id/secret for an access token good for ~1 hour.

Tokens are cached at module level with a 5-minute expiry buffer so
multiple tool calls in a row don't trigger redundant refreshes.

Public Spotify endpoints (artist search, artist details, top tracks,
related artists) all work with this token. Private/user endpoints
(playlists, library, etc.) require full OAuth and are out of scope.
"""
from __future__ import annotations

import base64
import os
import threading
import time

import httpx

from core.paths import load_credentials  # V2: per-user config dir + legacy fallback
load_credentials()

API_BASE = "https://api.spotify.com/v1"
TOKEN_URL = "https://accounts.spotify.com/api/token"

_access_token: str | None = None
_token_expires_at: float = 0.0
_token_lock = threading.Lock()
_EXPIRY_BUFFER_SECONDS = 300


class SpotifyAuthError(RuntimeError):
    """SPOTIFY_CLIENT_ID/SECRET missing, or Spotify rejected our credentials."""


def _refresh_token() -> None:
    """Exchange client_id + client_secret for an access_token."""
    global _access_token, _token_expires_at

    cid = os.getenv("SPOTIFY_CLIENT_ID")
    secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not cid or not secret:
        raise SpotifyAuthError(
            "SPOTIFY_CLIENT_ID and/or SPOTIFY_CLIENT_SECRET not set in .env. "
            "Get them from https://developer.spotify.com/dashboard."
        )

    creds = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    try:
        r = httpx.post(
            TOKEN_URL,
            headers={
                "Authorization": f"Basic {creds}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise ConnectionError(f"Cannot reach Spotify token endpoint: {exc}") from exc

    if r.status_code != 200:
        raise SpotifyAuthError(
            f"Spotify rejected client credentials ({r.status_code}): {r.text[:200]}"
        )
    data = r.json()
    _access_token = data["access_token"]
    _token_expires_at = time.time() + data.get("expires_in", 3600) - _EXPIRY_BUFFER_SECONDS


def get_access_token() -> str:
    """Return a valid access token, refreshing if needed."""
    with _token_lock:
        if _access_token is None or time.time() >= _token_expires_at:
            _refresh_token()
        assert _access_token is not None
        return _access_token


def api_get(path: str, params: dict | None = None) -> dict:
    """GET https://api.spotify.com/v1{path}. Auto-handles auth."""
    token = get_access_token()
    try:
        r = httpx.get(
            f"{API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        raise ConnectionError(f"Spotify request failed: {exc}") from exc
    if r.status_code == 401:
        # Token expired or revoked — force refresh and retry once.
        with _token_lock:
            _refresh_token()
        token = _access_token
        r = httpx.get(
            f"{API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=15.0,
        )
    if r.status_code >= 400:
        raise ConnectionError(f"Spotify {r.status_code} on {path}: {r.text[:200]}")
    return r.json()
