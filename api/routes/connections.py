"""GET /api/connections — live status of every external API the dashboard uses.

Returns one row per provider: name, status (one of `ok` / `missing_creds`
/ `auth_failed` / `quota_required` / `network_error`), a human-readable
detail string, and the env-var names that drive it (so the user knows
which lines in their .env to edit).

Each provider gets a tiny ping that exercises the real auth flow + a
trivial read so the result reflects reality, not just whether env
variables happen to be set. Cached for 60s — the page can re-poll
without burning daily quotas.
"""
from __future__ import annotations

import os
import time
from threading import Lock

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class ConnectionStatus(BaseModel):
    name: str
    status: str  # ok | missing_creds | auth_failed | quota_required | network_error | unknown
    detail: str | None = None
    env_vars: list[str] = []
    docs_url: str | None = None


_cache: dict[str, tuple[float, list[ConnectionStatus]]] = {}
_cache_lock = Lock()
_CACHE_TTL = 60.0


@router.get("/connections", response_model=list[ConnectionStatus])
def get_connections() -> list[ConnectionStatus]:
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get("all")
        if cached and now - cached[0] < _CACHE_TTL:
            return cached[1]

    results = [
        _check_chartmetric(),
        _check_spotify(),
        _check_youtube(),
        _check_llm_provider(),
    ]
    with _cache_lock:
        _cache["all"] = (now, results)
    return results


# ─── Provider checks ─────────────────────────────────────────────────────


def _check_chartmetric() -> ConnectionStatus:
    if not os.getenv("CHARTMETRIC_REFRESH_TOKEN"):
        return ConnectionStatus(
            name="Chartmetric",
            status="missing_creds",
            detail="CHARTMETRIC_REFRESH_TOKEN not set",
            env_vars=["CHARTMETRIC_REFRESH_TOKEN"],
            docs_url="https://chartmetric.com/api",
        )
    try:
        from mcp_server.tools.chartmetric_auth import get_access_token
        token = get_access_token()
        if not token:
            return ConnectionStatus(
                name="Chartmetric", status="auth_failed",
                detail="Token endpoint returned empty",
                env_vars=["CHARTMETRIC_REFRESH_TOKEN"],
            )
        return ConnectionStatus(
            name="Chartmetric", status="ok",
            detail="Token refresh succeeded",
            env_vars=["CHARTMETRIC_REFRESH_TOKEN"],
        )
    except ConnectionError as exc:
        msg = str(exc)
        return ConnectionStatus(
            name="Chartmetric",
            status="auth_failed" if "401" in msg or "auth" in msg.lower() else "network_error",
            detail=msg[:200],
            env_vars=["CHARTMETRIC_REFRESH_TOKEN"],
        )
    except Exception as exc:  # pragma: no cover — defensive
        return ConnectionStatus(
            name="Chartmetric", status="unknown",
            detail=f"{type(exc).__name__}: {str(exc)[:200]}",
            env_vars=["CHARTMETRIC_REFRESH_TOKEN"],
        )


def _check_spotify() -> ConnectionStatus:
    if not os.getenv("SPOTIFY_CLIENT_ID") or not os.getenv("SPOTIFY_CLIENT_SECRET"):
        return ConnectionStatus(
            name="Spotify",
            status="missing_creds",
            detail="SPOTIFY_CLIENT_ID and/or SPOTIFY_CLIENT_SECRET not set",
            env_vars=["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"],
            docs_url="https://developer.spotify.com/dashboard",
        )
    try:
        from mcp_server.tools.spotify_auth import api_get, get_access_token
        get_access_token()  # verifies client creds work
        # Now exercise an actual read — Spotify's Nov 2024 policy
        # requires the app owner to have Premium for most endpoints,
        # so a token grant alone isn't proof of usability.
        api_get("/search", params={"q": "test", "type": "artist", "limit": 1})
        return ConnectionStatus(
            name="Spotify", status="ok",
            detail="Client Credentials flow + read OK",
            env_vars=["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"],
        )
    except ConnectionError as exc:
        msg = str(exc)
        if "premium" in msg.lower() or "Active premium" in msg:
            return ConnectionStatus(
                name="Spotify",
                status="quota_required",
                detail="Spotify requires the app owner to have Premium (Nov 2024+ policy). Upgrade the developer account that owns this app.",
                env_vars=["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"],
                docs_url="https://developer.spotify.com/documentation/web-api",
            )
        return ConnectionStatus(
            name="Spotify",
            status="auth_failed" if "401" in msg or "403" in msg else "network_error",
            detail=msg[:240],
            env_vars=["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"],
        )
    except Exception as exc:  # pragma: no cover
        return ConnectionStatus(
            name="Spotify", status="unknown",
            detail=f"{type(exc).__name__}: {str(exc)[:200]}",
            env_vars=["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"],
        )


def _check_youtube() -> ConnectionStatus:
    has_oauth = all(os.getenv(k) for k in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"))
    has_api_key = bool(os.getenv("YOUTUBE_API_KEY"))
    if not has_oauth and not has_api_key:
        return ConnectionStatus(
            name="YouTube",
            status="missing_creds",
            detail="Set YOUTUBE_API_KEY for read-only access, or the OAuth triple (CLIENT_ID/CLIENT_SECRET/REFRESH_TOKEN) for authenticated access.",
            env_vars=["YOUTUBE_API_KEY", "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"],
            docs_url="https://console.cloud.google.com/apis/library/youtube.googleapis.com",
        )
    try:
        from mcp_server.tools.youtube_auth import api_get
        api_get("/search", params={"part": "snippet", "q": "test", "type": "channel", "maxResults": 1})
        return ConnectionStatus(
            name="YouTube", status="ok",
            detail="OAuth + read OK" if has_oauth else "API key + read OK",
            env_vars=["YOUTUBE_CLIENT_ID", "YOUTUBE_REFRESH_TOKEN"] if has_oauth else ["YOUTUBE_API_KEY"],
        )
    except ConnectionError as exc:
        return ConnectionStatus(
            name="YouTube", status="network_error",
            detail=str(exc)[:240],
            env_vars=["YOUTUBE_CLIENT_ID", "YOUTUBE_REFRESH_TOKEN"] if has_oauth else ["YOUTUBE_API_KEY"],
        )
    except Exception as exc:
        msg = str(exc)
        # Refresh-token expired is the most common YouTube failure
        if "expired or revoked" in msg or "invalid_grant" in msg:
            return ConnectionStatus(
                name="YouTube",
                status="auth_failed",
                detail="Refresh token expired or revoked — re-run the OAuth consent flow to mint a new refresh token.",
                env_vars=["YOUTUBE_REFRESH_TOKEN"],
                docs_url="https://developers.google.com/youtube/v3/quickstart/python",
            )
        return ConnectionStatus(
            name="YouTube", status="unknown",
            detail=f"{type(exc).__name__}: {msg[:200]}",
            env_vars=["YOUTUBE_API_KEY", "YOUTUBE_REFRESH_TOKEN"],
        )


_PROVIDER_DISPLAY = {
    "anthropic": "Anthropic (Claude)",
    "openai": "OpenAI (GPT)",
    "gemini": "Google (Gemini)",
}
_PROVIDER_DOCS = {
    "anthropic": "https://console.anthropic.com/settings/keys",
    "openai": "https://platform.openai.com/api-keys",
    "gemini": "https://aistudio.google.com/apikey",
}


def _check_llm_provider() -> ConnectionStatus:
    """Surface the LLM key as a single Connections row.

    One field, ``LLM_API_KEY``, accepts any of Anthropic / OpenAI /
    Gemini — the provider is sniffed from the key's prefix. The row's
    detail names the detected provider so the user can confirm at a
    glance which model their key routes to. We avoid a real ping (no
    paid token burn); the chat endpoint surfaces auth failures
    cleanly enough on the first turn.
    """
    from core.llm import detect_provider_name

    active = detect_provider_name()
    if active == "none":
        return ConnectionStatus(
            name="AI Model",
            status="missing_creds",
            detail=(
                "Paste an API key to enable chat. We auto-detect Anthropic "
                "(sk-ant-…), OpenAI (sk-…), or Google Gemini (AIza…)."
            ),
            env_vars=["LLM_API_KEY"],
            docs_url="https://console.anthropic.com/settings/keys",
        )
    return ConnectionStatus(
        name="AI Model",
        status="ok",
        detail=f"{_PROVIDER_DISPLAY[active]} key detected",
        env_vars=["LLM_API_KEY"],
        docs_url=_PROVIDER_DOCS[active],
    )
