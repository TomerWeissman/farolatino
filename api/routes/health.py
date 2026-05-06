"""GET /api/health — Chartmetric token + active LLM provider check.

Cached for 5 min so we don't burn Chartmetric's per-second rate limit
on every page load.
"""
from __future__ import annotations

import os
import time
from threading import Lock

from fastapi import APIRouter

from api.schemas import HealthStatus
from core.llm import detect_provider_name

router = APIRouter()

# Tiny TTL cache: chartmetric ping is 1 HTTPS roundtrip and the result
# barely changes minute-to-minute, but the @ rate limit punishes us if
# the page is reloaded a lot.
_CACHE_TTL = 300.0  # seconds
_cache: dict[str, tuple[float, HealthStatus]] = {}
_lock = Lock()


def _ping_chartmetric() -> tuple[str, str | None]:
    refresh = os.getenv("CHARTMETRIC_REFRESH_TOKEN")
    if not refresh:
        return ("missing_creds", "No CHARTMETRIC_REFRESH_TOKEN in .env")
    try:
        # Lazy import so a module-level health check doesn't trigger
        # network calls before .env is loaded.
        from mcp_server.tools.chartmetric_auth import get_access_token
        access = get_access_token()
        if access:
            return ("ok", None)
        return ("auth_failed", "Chartmetric returned an empty token")
    except ConnectionError as exc:
        msg = str(exc)
        if "401" in msg or "auth" in msg.lower():
            return ("auth_failed", "Chartmetric rejected the refresh token")
        return ("error", f"Cannot reach Chartmetric: {msg[:120]}")
    except Exception as exc:  # pragma: no cover — defensive
        return ("error", f"Unexpected error: {str(exc)[:120]}")


@router.get("/health", response_model=HealthStatus)
def get_health() -> HealthStatus:
    now = time.monotonic()
    with _lock:
        cached = _cache.get("health")
        if cached and now - cached[0] < _CACHE_TTL:
            return cached[1]

    chart_status, chart_detail = _ping_chartmetric()
    status = HealthStatus(
        chartmetric=chart_status,
        chartmetric_detail=chart_detail,
        llm_provider=detect_provider_name(),
    )
    with _lock:
        _cache["health"] = (now, status)
    return status
