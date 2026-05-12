"""V2 in-process agent runner. Drop-in replacement for ``core.claude_runner``.

Same public surface — ``run_claude_streaming(prompt, *, on_event,
resume_session_id, ...) -> Iterator[str]`` — so ``api/routes/chat.py``
only swaps an import. Yields plain text deltas, with
``THINKING_PREFIX``-tagged thinking deltas, in the same wire format
``web/lib/streams.tsx`` already understands.

Implementation lives in ``core.llm`` and dispatches tools directly via
``core.llm.tool_dispatch``. The Claude Code CLI is no longer required —
``ANTHROPIC_API_KEY`` is the only auth.
"""
from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Iterator
from datetime import date
from pathlib import Path

from core.llm import (
    NoLLMProviderError,
    detect_provider_name,
    get_provider,
)
from core.llm.base import AgentEvent
from core.llm.tool_dispatch import all_tool_names, dispatch as dispatch_tool
from core.llm.tool_schemas import all_tool_specs, to_anthropic, to_gemini, to_openai

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PERSONA_PATH = PROJECT_ROOT / "FAROAI.md"

# Sentinel prefix marking a chunk as a thinking delta. Wire-level contract
# with ``web/lib/streams.tsx``: the chat split-routes these to the
# Reasoning panel. Re-exported from this module so ``api.routes.chat``
# keeps importing it from the runner like in V1.
THINKING_PREFIX = "\x01THINK\x01"

log = logging.getLogger(__name__)


class ClaudeRunnerError(Exception):
    """Structured chat-runner error. Surfaced to the UI as a banner.

    Carries a short human-readable ``message`` (the title shown in the
    red banner), an optional ``hint`` (one-line "how to fix"), an
    optional ``fix_url`` (rendered as a link button), and the original
    ``raw`` provider message stuffed into a collapsible "details"
    section. Providers map their SDK-specific errors to this shape via
    the per-provider ``_classify_error`` helper.

    The class keeps its V1 name so the ``except ClaudeRunnerError`` in
    ``api/routes/chat.py`` still catches it; renaming lands in Phase 9.
    """

    def __init__(
        self,
        message: str,
        *,
        hint: str | None = None,
        fix_url: str | None = None,
        raw: str | None = None,
    ) -> None:
        super().__init__(message)
        self.hint = hint
        self.fix_url = fix_url
        self.raw = raw


# --- Per-skill profiles -----------------------------------------------------
# Mirrors V1's allowlist behavior. Composite tools (e.g. @evaluate) get a
# tight tool list and zero extended-thinking so the model can't cascade
# into Bash/Agent retries (a single @evaluate run cost $0.88 / 354s on
# the unrestricted profile in V1 production).

_DEFAULT_TOOL_NAMES = [
    "mcp__farolatino__cache_clear",
    "mcp__farolatino__cache_get",
    "mcp__farolatino__cache_set",
    "mcp__farolatino__compute_prospect_score",
    "mcp__farolatino__discover_artists",
    "mcp__farolatino__discover_artists_multi_country",
    "mcp__farolatino__estimate_revenue",
    "mcp__farolatino__evaluate_artist",
    "mcp__farolatino__compare_artists",
    "mcp__farolatino__find_similar_artists",
    "mcp__farolatino__generate_dossier",
    "mcp__farolatino__get_artist_data",
    "mcp__farolatino__get_profile",
    "mcp__farolatino__list_profiles",
    "mcp__farolatino__load_config",
    "mcp__farolatino__route_alert",
    "mcp__farolatino__search_artist_by_url",
    "mcp__farolatino__search_artists",
    "mcp__farolatino__search_spotify_artist",
    "mcp__farolatino__get_spotify_artist",
    "mcp__farolatino__search_youtube_channel",
    "mcp__farolatino__get_youtube_channel",
    # Web search — conditionally retained in the allowlist by
    # _resolve_web_search_mode(). When Tavily is unhealthy or unset, the
    # provider adapter substitutes its own hosted search instead.
    "web_search",
]

_SKILL_PROFILES: dict[str, dict] = {
    "@evaluate": {
        "tools": [
            "mcp__farolatino__evaluate_artist",
            "mcp__farolatino__search_artist_by_url",
        ],
        "thinking_budget": 0,
        "web_search_mode": "off",
    },
    "@similar": {
        "tools": [
            "mcp__farolatino__find_similar_artists",
            "mcp__farolatino__search_artist_by_url",
        ],
        "thinking_budget": 0,
        "web_search_mode": "off",
    },
}


def _resolve_skill_profile(prompt: str) -> dict:
    """Return the per-skill profile (tool allowlist + thinking budget + web-search mode)."""
    head = prompt.strip().lower().split()[0] if prompt.strip() else ""
    if head in _SKILL_PROFILES:
        return _SKILL_PROFILES[head]
    return {
        "tools": _DEFAULT_TOOL_NAMES,
        "thinking_budget": 8000,
        "web_search_mode": "on",
    }


# OpenAI's hosted web_search tool is gated to specific Responses-API
# models. If the active model isn't on this list, native search is
# silently turned off (rather than emitting a 400 banner). Users on
# unsupported models can add a Tavily key to get web search anyway.
_OPENAI_NATIVE_SEARCH_MODELS = {
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
}


def _openai_model_supports_native_search() -> bool:
    model = os.getenv("FAROAI_OPENAI_MODEL", "gpt-4o")
    return model in _OPENAI_NATIVE_SEARCH_MODELS


def _resolve_web_search_mode(profile: dict, provider_name: str) -> str:
    """Return one of ``'off' | 'tavily' | 'native'`` for this request.

    Decision tree:
      1. If the active profile disables web search, return ``'off'``.
      2. If a healthy Tavily connector is registered, return ``'tavily'``
         (model dispatches the ``web_search`` tool in-process).
      3. Otherwise return ``'native'`` so the provider's hosted search
         takes over — except OpenAI on a non-supporting model, which
         degrades to ``'off'`` (no banner, just no web search).
    """
    if profile.get("web_search_mode", "off") != "on":
        return "off"
    try:
        from core.connectors import get_connector
        tavily = get_connector("tavily")
        if tavily is not None and tavily.status().status == "ok":
            return "tavily"
    except Exception:
        log.exception("tavily status probe raised; falling back to native")
    if provider_name == "openai" and not _openai_model_supports_native_search():
        return "off"
    return "native"


def _load_persona() -> str:
    """Re-read the persona every turn via the overlay system.

    Resolution order: user/persona.md > code/FAROAI.md (latest from a
    shipped update) > bundled FAROAI.md. Returns "" silently if no
    layer has it (the runner falls back to whatever the LLM thinks
    FaroAI is from the prompt alone).

    When ``preferences.language == "es"`` we try the parallel Spanish
    layer first (``persona.es.md`` / ``FAROAI.es.md``) and only fall
    back to the English persona if Spanish is missing — that keeps
    chat replies in the chosen language.
    """
    from core import overlay
    from core.preferences import get_language
    lang = get_language()
    found = None
    if lang == "es":
        found = overlay.resolve_file("persona_es")
    if found is None:
        found = overlay.resolve_file("persona")
    if found is None:
        return ""
    try:
        return found.path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _build_system_prompt() -> str:
    today = date.today().isoformat()
    persona = _load_persona()
    date_note = (
        f"Today's date is {today}. When you see release dates, compare them "
        f"to today to determine whether they are past or upcoming. Treat "
        f"dates earlier than today as already-released."
    )
    return f"{persona}\n\n---\n\n{date_note}" if persona else date_note


def _filter_tools_by_allowlist(tools: list[dict], allowed: list[str]) -> list[dict]:
    allowed_set = set(allowed)
    return [t for t in tools if t["name"] in allowed_set]


def run_claude_streaming(
    prompt: str,
    *,
    max_turns: int | None = None,  # accepted for signature compatibility, currently unused
    on_event: callable | None = None,
    resume_session_id: str | None = None,  # transitional: ignored; replaced by `messages` replay
    messages: list[dict] | None = None,
) -> Iterator[str]:
    """Drive one chat turn against the active LLM provider.

    Args:
        prompt: the user's chat message (with any `@skill` prefix).
        max_turns: legacy V1 cap, ignored — the agent loop has its own
            iteration cap inside ``AnthropicProvider``.
        on_event: callback invoked with synthetic stream-json events
            (``system``/``assistant``/``result`` shapes), so
            ``core.run_log.RunLogger`` keeps working without changes.
        resume_session_id: V1 multi-turn handle. No longer used (the
            CLI is gone); we replay ``messages`` instead. Kept for
            ChatRequest compatibility — Phase 9 will drop it.
        messages: prior turns in ``[{role, content}, ...]`` form. The
            new ``prompt`` is appended as the trailing user turn. When
            ``None`` we treat the prompt as a fresh single-turn chat —
            existing frontend behavior in V1 didn't replay either.

    Yields:
        Plain text chunks for the visible response, plus
        ``THINKING_PREFIX``-tagged chunks for thinking deltas.
    """
    # v0.5.2: the @evaluate / @similar slash bypass is retired. The
    # LLM now handles those prompts as free-form text — it calls
    # evaluate_artist / find_similar_artists itself and the chat
    # surfaces a compact pill via the evaluate_pill SSE event. This
    # removes the provider-output-divergence rationale (the canonical
    # server-rendered markdown was a thin justification once the pill
    # took over the visual representation) AND lets the LLM combine
    # the dossier with web_search results in a single reply.

    try:
        provider = get_provider()
    except NoLLMProviderError as exc:
        raise ClaudeRunnerError(str(exc)) from exc

    profile = _resolve_skill_profile(prompt)
    web_search_mode = _resolve_web_search_mode(profile, provider.name)

    # Provider-flavored tool schemas, narrowed to the active skill's
    # allowlist. Same shape as V1's --allowed-tools whitelist.
    specs = all_tool_specs()
    if provider.name == "anthropic":
        tools = to_anthropic(specs)
    elif provider.name == "openai":
        tools = to_openai(specs)
    elif provider.name == "gemini":
        tools = to_gemini(specs)
    else:  # pragma: no cover — registry only returns the three above
        raise ClaudeRunnerError(f"Unsupported provider: {provider.name}")
    # Build the per-request allowlist. ``web_search`` is in
    # _DEFAULT_TOOL_NAMES, but only stays in the allowlist when mode is
    # "tavily" — otherwise the provider adapter will substitute its own
    # hosted version (or skip web search entirely).
    allowed = list(profile["tools"])
    if web_search_mode != "tavily" and "web_search" in allowed:
        allowed = [t for t in allowed if t != "web_search"]
    tools = _filter_tools_by_allowlist(tools, allowed)

    # Build the message stack. Prior assistant/user content from the
    # frontend is replayed verbatim (`{role, content}`), then the new
    # user prompt is appended. The provider mutates this list as it
    # runs; we don't reuse it after the iterator is exhausted.
    msg_stack: list[dict] = []
    if messages:
        for m in messages:
            role = m.get("role")
            content = m.get("content")
            if role in ("user", "assistant") and isinstance(content, str) and content.strip():
                msg_stack.append({"role": role, "content": content})
    msg_stack.append({"role": "user", "content": prompt})

    system = _build_system_prompt()

    # Synthetic system/init event so RunLogger captures the run in the
    # V1 shape (mcp_servers list + session_id available to chat.py).
    session_id = uuid.uuid4().hex
    if on_event is not None:
        try:
            on_event(
                {
                    "type": "system",
                    "subtype": "init",
                    "session_id": session_id,
                    "mcp_servers": [
                        {"name": "farolatino", "status": "in_process", "tools": all_tool_names()}
                    ],
                    "provider": detect_provider_name(),
                }
            )
        except Exception:
            pass

    # Drive the provider iterator and translate `AgentEvent` → text
    # deltas (+ THINKING_PREFIX chunks) + synthetic on_event calls.
    try:
        for event in provider.run(
            messages=msg_stack,
            tools=tools,
            system=system,
            thinking_budget=profile["thinking_budget"],
            web_search=web_search_mode,
        ):
            yield from _translate_event(event, on_event)
    except ClaudeRunnerError:
        raise
    except Exception as exc:
        log.exception("agent runner crashed")
        raise ClaudeRunnerError(f"Agent runner failed: {exc}") from exc


def _translate_event(event: AgentEvent, on_event) -> Iterator[str]:
    """Map an `AgentEvent` to (a) chat text chunks, (b) RunLogger events.

    The on_event side mimics the V1 Claude Code stream-json shape so
    ``core.run_log.RunLogger.record_event`` recognises tool_use blocks
    and the final cost.
    """
    if event.type == "text":
        if event.content:
            yield event.content
        return
    if event.type == "thinking":
        if event.content:
            yield f"{THINKING_PREFIX}{event.content}"
        return
    if event.type == "tool_use":
        if on_event is not None:
            try:
                on_event(
                    {
                        "type": "assistant",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_use",
                                    "id": event.tool_use_id or "",
                                    "name": event.tool_name or "tool",
                                    "input": event.tool_input or {},
                                }
                            ]
                        },
                    }
                )
            except Exception:
                pass
        return
    if event.type == "tool_result":
        # No user-visible chunk — UI gets the tool_use status pill from
        # the corresponding tool_use event. But we DO forward the raw
        # tool output to on_event so RunLogger captures it; without this,
        # regressions like the May-6 cm_id=0 bug (tool ran "ok" but
        # returned an empty dossier) are invisible in the run trace.
        if on_event is not None:
            try:
                on_event(
                    {
                        "type": "user",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": event.tool_use_id or "",
                                    "tool_name": event.tool_name or "",
                                    "content": event.content,
                                }
                            ]
                        },
                    }
                )
            except Exception:
                pass
        return
    if event.type == "result":
        if on_event is not None:
            try:
                on_event(
                    {
                        "type": "result",
                        "total_cost_usd": event.cost_usd,
                        "input_tokens": event.input_tokens,
                        "output_tokens": event.output_tokens,
                        **event.extra,
                    }
                )
            except Exception:
                pass
        return
    if event.type == "error":
        # Surface as a ClaudeRunnerError so the chat route emits an
        # SSE `error` event with the same code path V1 used. The
        # provider may have stuffed structured fix info into
        # event.extra (hint / fix_url / raw); pass them through so the
        # UI can render a clean banner with an action link.
        extra = event.extra or {}
        raise ClaudeRunnerError(
            event.content or "agent error",
            hint=extra.get("hint"),
            fix_url=extra.get("fix_url"),
            raw=extra.get("raw"),
        )
