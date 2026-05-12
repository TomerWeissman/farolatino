"""Single source of truth for attaching `web_search` tools across providers.

v0.5.1 had three near-identical blocks of "if web_search == 'native':
tools = list(tools) + [...]" — one per provider, each in a slightly
different shape. v0.5.2 collapses them here so per-provider drift can't
cause a "web_search works on one provider but not another" bug.

Caller passes the existing tools list (already includes the
Tavily-backed local `web_search` tool when mode is "tavily"). This
helper returns a NEW list with the right native-search tool appended
when mode is "native". Logging is INFO so the run log shows which
search backend was chosen per request — helps diagnose "the LLM
didn't search the web" without instrumenting each provider.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Hosted web_search tool shapes per provider. None means the caller
# already has a local `web_search` MCP tool in the list (the Tavily
# path) — nothing more to attach.
_ANTHROPIC_NATIVE_TOOL: dict = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 5,
}

_OPENAI_NATIVE_TOOL: dict = {
    "type": "web_search",
}


def attach_for_anthropic(tools: list[dict], mode: str) -> list[dict]:
    """Return ``tools`` with Anthropic's hosted web_search appended on native mode."""
    if mode == "native":
        log.info("web_search backend: anthropic native (web_search_20250305)")
        return list(tools) + [_ANTHROPIC_NATIVE_TOOL]
    if mode == "tavily":
        log.info("web_search backend: tavily (in-process)")
    elif mode == "off":
        log.info("web_search backend: off (not advertised to model)")
    return tools


def attach_for_openai(tools: list[dict], mode: str) -> list[dict]:
    """Return ``tools`` with OpenAI's hosted web_search appended on native mode."""
    if mode == "native":
        log.info("web_search backend: openai native (web_search)")
        return list(tools) + [_OPENAI_NATIVE_TOOL]
    if mode == "tavily":
        log.info("web_search backend: tavily (in-process)")
    elif mode == "off":
        log.info("web_search backend: off (not advertised to model)")
    return tools


def attach_for_gemini_grounding(mode: str) -> bool:
    """Return True when the Gemini provider should attach the
    ``google_search`` grounding tool.

    Gemini's tool surface is different from Anthropic/OpenAI — grounding
    is added via a separate ``Tool(google_search=...)`` instead of a
    tool-list entry, so we just return a flag instead of mutating a
    list.
    """
    if mode == "native":
        log.info("web_search backend: gemini grounding (google_search)")
        return True
    if mode == "tavily":
        log.info("web_search backend: tavily (in-process)")
    elif mode == "off":
        log.info("web_search backend: off (not advertised to model)")
    return False
