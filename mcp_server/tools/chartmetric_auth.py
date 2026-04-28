"""Chartmetric API authentication — token management with auto-refresh.

The Chartmetric API uses a two-token system:
1. Refresh token (permanent, stored in .env)
2. Access token (expires in 1 hour, obtained from refresh token)

This module manages the access token lifecycle so other tools
can just call get_access_token() without worrying about expiry.
"""

import os
import threading
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

API_BASE = "https://api.chartmetric.com"

# Module-level token state
_access_token: str | None = None
_token_expires_at: float = 0.0

# Leave a 5-minute buffer before expiry to avoid mid-request failures
_EXPIRY_BUFFER_SECONDS = 300

# Chartmetric hard rate limit is 1 req/s. Keep a small buffer under the ceiling
# to avoid the edge of the window tripping a 429.
_MIN_REQUEST_INTERVAL = 1.05
_last_request_at: float = 0.0
_rate_lock = threading.Lock()


def _throttle() -> None:
    """Block until at least _MIN_REQUEST_INTERVAL seconds have passed since the
    last outbound Chartmetric request. Serialized across threads via _rate_lock.
    """
    global _last_request_at
    with _rate_lock:
        now = time.monotonic()
        wait = _MIN_REQUEST_INTERVAL - (now - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()


def _refresh_token() -> None:
    """Exchange the refresh token for a new access token."""
    global _access_token, _token_expires_at

    refresh_token = os.getenv("CHARTMETRIC_REFRESH_TOKEN")
    if not refresh_token:
        raise ValueError(
            "CHARTMETRIC_REFRESH_TOKEN not set in .env — "
            "get your refresh token from Chartmetric and add it to .env"
        )

    response = httpx.post(
        f"{API_BASE}/api/token",
        json={"refreshtoken": refresh_token},
        timeout=30.0,
    )

    if response.status_code != 200:
        raise ConnectionError(
            f"Chartmetric auth failed (HTTP {response.status_code}): "
            f"{response.text}"
        )

    data = response.json()
    _access_token = data["token"]
    expires_in = data.get("expires_in", 3600)
    _token_expires_at = time.time() + expires_in - _EXPIRY_BUFFER_SECONDS


def get_access_token() -> str:
    """Return a valid access token, refreshing if needed."""
    if _access_token is None or time.time() >= _token_expires_at:
        _refresh_token()
    return _access_token


def api_get(path: str, params: dict | None = None) -> dict:
    """Make an authenticated GET request to the Chartmetric API.

    Args:
        path: API path (e.g., "/api/artist/12345")
        params: Optional query parameters

    Returns:
        Parsed JSON response

    Raises:
        ConnectionError: On non-200 responses
    """
    token = get_access_token()
    _throttle()
    response = httpx.get(
        f"{API_BASE}{path}",
        params=params,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )

    # Handle token expiry mid-session (401 = expired token)
    if response.status_code == 401:
        _refresh_token()
        token = get_access_token()
        _throttle()
        response = httpx.get(
            f"{API_BASE}{path}",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )

    if response.status_code != 200:
        raise ConnectionError(
            f"Chartmetric API error (HTTP {response.status_code}) "
            f"on {path}: {response.text[:500]}"
        )

    return response.json()
