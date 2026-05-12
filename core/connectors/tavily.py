"""Tavily connector — web search for free-form chat and follow-ups.

Tavily is an LLM-friendly search API: one POST returns ranked results
with title/url/content snippets, suited for grounding a model answer.
Free tier is 1K searches/month, plenty for the FaroLatino team to
start with. When this key is set, the agent runner routes the
``web_search`` tool to ``tavily.web_search`` (in-process) instead of
falling back to each LLM provider's native hosted search.

Status probe is intentionally **format-only** (env var present + key
prefix). A real probe call would burn a search quota every 60s the
Connections page is open — over the free tier in a few hours. Real
auth/quota failures surface at first call time as a structured error
returned to the model from ``web_search``.
"""
from __future__ import annotations

import logging
import os
from typing import Callable

import httpx

from core.connectors import ConnectionStatusInfo, register

log = logging.getLogger(__name__)

_TAVILY_API_URL = "https://api.tavily.com/search"
_TAVILY_TIMEOUT_S = 15.0
_TAVILY_KEY_PREFIX = "tvly-"


class TavilyConnector:
    name = "Tavily Web Search"
    slug = "tavily"
    env_vars = ["TAVILY_API_KEY"]
    docs_url = "https://tavily.com/"

    def status(self) -> ConnectionStatusInfo:
        key = os.getenv("TAVILY_API_KEY")
        if not key:
            return ConnectionStatusInfo(
                status="missing_creds",
                detail=(
                    "Optional. Add for consistent web search across all LLM providers "
                    "(1K free searches/month at tavily.com). Without it, web search "
                    "falls back to your LLM's native search."
                ),
            )
        # Format check only — a real /search probe burns a search per
        # status poll, which would blow through the free tier.
        if not key.startswith(_TAVILY_KEY_PREFIX):
            return ConnectionStatusInfo(
                status="auth_failed",
                detail=f"TAVILY_API_KEY does not look like a Tavily key (expected '{_TAVILY_KEY_PREFIX}…' prefix)",
            )
        return ConnectionStatusInfo(
            status="ok",
            detail="Key set; web search routes through Tavily.",
        )

    def reset_cache(self) -> None:
        # No in-memory state — the env var is read fresh on every search.
        return None

    def tools(self) -> dict[str, Callable]:
        # Dispatch happens via core.llm.tool_dispatch._REGISTRY (same
        # pattern as the chartmetric connector). This forward-compat
        # hook returns {} for now.
        return {}


def web_search(query: str, max_results: int = 5) -> dict:
    """Search the public web for current information.

    Use this when the user asks about anything requiring up-to-date
    public information that the in-house datasets (Chartmetric,
    Spotify, YouTube, FaroLatino internal) don't cover: press coverage,
    label/management changes, tour announcements, social context, news.

    Args:
        query: The search query. Be specific — include the artist name
            plus the topic (e.g. "Bad Bunny new label 2026", not just
            "Bad Bunny").
        max_results: How many top results to return. Default 5, capped
            at 10 to keep the response budget tight.
    """
    import time
    started = time.monotonic()
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        log.info("tavily skipped: no TAVILY_API_KEY set")
        return _error_payload("permanent", "TAVILY_API_KEY not set; web search unavailable.")

    capped = max(1, min(int(max_results or 5), 10))
    # search_depth="advanced" pulls richer page content into the result
    # snippets (Tavily charges 2 credits/query vs 1 on "basic"). v0.5.2:
    # the basic depth was returning thin snippets that left the model
    # saying "I couldn't find detailed information" on legitimate
    # results. include_answer=True gives the model a pre-synthesized
    # one-line summary alongside the raw snippets — useful grounding.
    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": capped,
        "include_answer": True,
        "search_depth": "advanced",
    }
    try:
        resp = httpx.post(_TAVILY_API_URL, json=payload, timeout=_TAVILY_TIMEOUT_S)
    except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError) as exc:
        log.warning("tavily transient error: %s", exc)
        return _error_payload(
            "recoverable",
            f"network error: {type(exc).__name__}: {exc}",
            hint="Transient network/timeout — try the same search again, or use a different approach.",
        )
    except httpx.HTTPError as exc:
        log.warning("tavily request failed: %s", exc)
        return _error_payload(
            "permanent",
            f"network error: {type(exc).__name__}: {exc}",
        )

    elapsed_ms = int((time.monotonic() - started) * 1000)
    if resp.status_code in (401, 403):
        log.warning("tavily auth failed (%s) in %dms", resp.status_code, elapsed_ms)
        return _error_payload(
            "permanent",
            "Tavily auth failed — check TAVILY_API_KEY in Connections.",
            hint="The Tavily key is invalid or revoked. The user must fix it in the Connections page; don't retry until they do.",
        )
    if resp.status_code == 429:
        log.warning("tavily rate limited (429) in %dms", elapsed_ms)
        return _error_payload(
            "recoverable",
            "Tavily quota exhausted — wait or upgrade your plan.",
            hint="Rate-limited. Don't retry immediately on the same query; tell the user the limit hit.",
        )
    if 500 <= resp.status_code < 600:
        log.warning("tavily 5xx (%s) in %dms", resp.status_code, elapsed_ms)
        return _error_payload(
            "recoverable",
            f"Tavily HTTP {resp.status_code}: {resp.text[:200]}",
            hint="Transient server error — try the same search again in a moment, or proceed without web data.",
        )
    if resp.status_code >= 400:
        log.warning("tavily 4xx (%s) in %dms", resp.status_code, elapsed_ms)
        return _error_payload(
            "permanent",
            f"Tavily HTTP {resp.status_code}: {resp.text[:200]}",
        )

    try:
        data = resp.json()
    except ValueError:
        log.warning("tavily returned non-JSON in %dms", elapsed_ms)
        return _error_payload("permanent", "Tavily returned non-JSON response")

    results = [
        {
            "title": r.get("title") or "",
            "url": r.get("url") or "",
            "content": r.get("content") or "",
        }
        for r in (data.get("results") or [])
    ]
    log.info(
        "tavily ok query=%r n_results=%d in %dms",
        query[:80], len(results), elapsed_ms,
    )
    out: dict = {"query": query, "results": results}
    # When include_answer=True, Tavily pre-synthesizes a one-line answer
    # from the result snippets. Pass it through verbatim so the model
    # has a strong starting point — but ALWAYS keep the per-result
    # snippets too so the model can cite specific URLs.
    answer = data.get("answer")
    if isinstance(answer, str) and answer.strip():
        out["answer"] = answer.strip()
    return out


def _error_payload(
    category: str,  # "recoverable" | "permanent"
    message: str,
    *,
    hint: str | None = None,
) -> dict:
    """Structure Tavily error returns so the model can distinguish
    'try again / try differently' from 'give up and tell the user'.

    The provider serialises this dict as the tool_result content; the
    model sees both ``error`` and the ``error_category`` + ``hint``
    fields and can act accordingly. v0.5.2: distinct categories so a
    single Tavily failure doesn't make the model give up on web search
    entirely (the v0.5.1 bug).
    """
    out: dict = {"error": message, "error_category": category}
    if hint:
        out["hint"] = hint
    return out


register(TavilyConnector())
