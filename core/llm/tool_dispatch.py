"""Direct in-process tool registry + dispatcher.

V1 routed every tool call through Claude Code, which spawned an MCP
subprocess (`fastmcp run mcp_server/server.py`) and round-tripped JSON
over stdio. V2 imports the tool functions directly — same Python, no
subprocess, no JSON envelope. Each `@mcp.tool()` decorator from FastMCP
returns the original callable unchanged, so we can call it as a plain
function.

The tool *names* keep the V1 ``mcp__farolatino__`` prefix on the wire so
that:

  - The frontend status-pill mapping in ``core/humanize.py`` works
    without changes.
  - `core/run_log.py` records the same tool_call strings as V1.
  - Existing skill profiles in ``core/agent_runner.py`` are 1:1 with
    the V1 allowlist in ``core/claude_runner.py``.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

# Load mcp_server.server FIRST so the FastMCP `mcp` instance + its
# decorated tools are registered in the same import order V1 used. The
# composite_* tools import sibling tools by direct name (not through
# mcp_server.server), so importing them in tuple-form before the server
# module triggers a partial-init circular import — visible because
# alert_router.py does `from mcp_server.server import mcp` at module
# top, which re-enters mcp_server.server while it's still loading.
from mcp_server import server as _mcp_server  # noqa: F401

from mcp_server.tools import (  # noqa: E402
    alert_router,
    chartmetric_artist,
    chartmetric_discovery,
    chartmetric_search,
    composite_compare,
    composite_evaluate,
    composite_similar,
    config_manager,
    data_cache,
    dossier_generator,
    revenue_model,
    spotify_search,
    youtube_search,
)
from mcp_server.tools.scoring import engine as scoring_engine  # noqa: E402

# Tavily web search lives outside mcp_server because it's not an MCP
# tool — it's a connector-backed primitive that wraps Tavily's HTTP
# API. The agent runner only adds "web_search" to the allowlist when
# Tavily is healthy; otherwise the provider's hosted search kicks in.
from core.connectors import tavily as _tavily_connector  # noqa: E402

log = logging.getLogger(__name__)

# Public tool name → Python callable. The prefix is the V1 wire format
# Claude Code used; preserved so the rest of the stack (humanize, run
# log, frontend) sees identical strings before and after the swap.
_REGISTRY: dict[str, Callable[..., Any]] = {
    # Composite (one-call pipelines)
    "mcp__farolatino__evaluate_artist": composite_evaluate.evaluate_artist,
    "mcp__farolatino__compare_artists": composite_compare.compare_artists,
    "mcp__farolatino__find_similar_artists": composite_similar.find_similar_artists,
    # Chartmetric primitives
    "mcp__farolatino__search_artists": chartmetric_search.search_artists,
    "mcp__farolatino__search_artist_by_url": chartmetric_search.search_artist_by_url,
    "mcp__farolatino__get_artist_data": chartmetric_artist.get_artist_data,
    "mcp__farolatino__discover_artists": chartmetric_discovery.discover_artists,
    "mcp__farolatino__discover_artists_multi_country": chartmetric_discovery.discover_artists_multi_country,
    # Spotify
    "mcp__farolatino__search_spotify_artist": spotify_search.search_spotify_artist,
    "mcp__farolatino__get_spotify_artist": spotify_search.get_spotify_artist,
    # YouTube
    "mcp__farolatino__search_youtube_channel": youtube_search.search_youtube_channel,
    "mcp__farolatino__get_youtube_channel": youtube_search.get_youtube_channel,
    # Cache
    "mcp__farolatino__cache_get": data_cache.cache_get,
    "mcp__farolatino__cache_set": data_cache.cache_set,
    "mcp__farolatino__cache_clear": data_cache.cache_clear,
    # Scoring + dossier
    "mcp__farolatino__compute_prospect_score": scoring_engine.compute_prospect_score,
    "mcp__farolatino__estimate_revenue": revenue_model.estimate_revenue,
    "mcp__farolatino__generate_dossier": dossier_generator.generate_dossier,
    # Routing
    "mcp__farolatino__route_alert": alert_router.route_alert,
    # Config
    "mcp__farolatino__load_config": config_manager.load_config,
    "mcp__farolatino__get_profile": config_manager.get_profile,
    "mcp__farolatino__list_profiles": config_manager.list_profiles,
    # Web search (Tavily-backed; bare "web_search" name so the model
    # treats it as a generic capability, not an MCP-namespaced tool)
    "web_search": _tavily_connector.web_search,
}


def all_tool_names() -> list[str]:
    """Names of every tool the model is allowed to invoke."""
    return list(_REGISTRY.keys())


def get_callable(name: str) -> Callable[..., Any] | None:
    return _REGISTRY.get(name)


def dispatch(name: str, tool_input: dict | None) -> dict:
    """Call a tool by name with kwargs from the model.

    Always returns a dict so the provider can JSON-serialise it directly
    into the next ``tool_result`` content block. If the tool raises, we
    return ``{"error": "..."}`` rather than propagating — letting the
    model see the failure (and recover) is more useful than crashing
    the chat turn.
    """
    fn = _REGISTRY.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}

    kwargs = dict(tool_input or {})
    # INFO-level so the run log captures exactly what the model passed.
    # This is what diagnosed the May-6 regression where OpenAI's
    # function_call arguments were arriving stripped of required fields.
    log.info("dispatch %s args=%s", name, kwargs)
    try:
        result = fn(**kwargs)
    except TypeError as exc:
        # Surfaces "unexpected keyword argument" / "missing positional"
        # back to the model so it can self-correct.
        log.warning("tool %s rejected args %s: %s", name, list(kwargs), exc)
        return {"error": f"bad arguments: {exc}"}
    except Exception as exc:
        log.exception("tool %s raised", name)
        return {"error": f"{type(exc).__name__}: {exc}"}

    if result is None:
        # `cache_get` legitimately returns None on miss — represent that
        # as an empty dict so the JSON serialiser is happy.
        return {}
    if isinstance(result, dict):
        return result
    # Catch-all — wrap so the contract is dict in / dict out.
    try:
        return {"result": result}
    except Exception:
        return {"result": json.dumps(result, default=str)}
