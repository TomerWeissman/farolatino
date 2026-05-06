"""GET /api/connections — live status of every external API the dashboard uses.

Returns one row per connector: name, status (one of `ok` / `missing_creds`
/ `auth_failed` / `quota_required` / `network_error` / `unknown`), a
human-readable detail string, and the env var names that drive it.

V2: walks the connector registry in ``core/connectors/`` instead of
hardcoding three provider checks. Adding a new data source is one
file in ``core/connectors/<name>.py``; this route picks it up
automatically. The LLM provider row stays separate (different concept,
own auth abstraction) and is appended last so it always shows at the
bottom of the Connections page.

Cached for 60s — the page can re-poll without burning daily quotas.
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

    from core.connectors import list_connectors
    rows: list[ConnectionStatus] = []
    for connector in list_connectors():
        info = _safe_status(connector)
        rows.append(
            ConnectionStatus(
                name=connector.name,
                status=info.status,
                detail=info.detail,
                env_vars=connector.env_vars,
                docs_url=connector.docs_url,
            )
        )
    rows.append(_check_llm_provider())

    with _cache_lock:
        _cache["all"] = (now, rows)
    return rows


def _safe_status(connector) -> "ConnectionStatusInfo":  # noqa: F821
    """Defense-in-depth wrapper: a buggy connector shouldn't break the
    whole Connections page. Catch + report as 'unknown'."""
    from core.connectors import ConnectionStatusInfo
    try:
        return connector.status()
    except Exception as exc:
        return ConnectionStatusInfo(
            status="unknown",
            detail=f"connector raised: {type(exc).__name__}: {str(exc)[:200]}",
        )


# ─── LLM provider (kept separate from data connectors) ──────────────────

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
    """Single 'AI Model' row — auto-detects provider from the LLM_API_KEY
    prefix. Not a connector because the LLM is conceptually different
    (the brain, not a data source) and uses a different auth abstraction
    in ``core/llm/``.
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
