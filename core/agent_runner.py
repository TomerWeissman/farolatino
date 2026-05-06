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

from core.llm import detect_provider_name, get_provider
from core.llm.base import AgentEvent
from core.llm.tool_dispatch import all_tool_names
from core.llm.tool_schemas import all_tool_specs, to_anthropic

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PERSONA_PATH = PROJECT_ROOT / "FAROAI.md"

# Sentinel prefix marking a chunk as a thinking delta. Wire-level contract
# with ``web/lib/streams.tsx``: the chat split-routes these to the
# Reasoning panel. Re-exported from this module so ``api.routes.chat``
# keeps importing it from the runner like in V1.
THINKING_PREFIX = "\x01THINK\x01"

log = logging.getLogger(__name__)


class ClaudeRunnerError(Exception):
    """Surfaced to the chat UI as a system message.

    Kept under the legacy name so the SSE error mapping in
    ``api/routes/chat.py`` (which catches ``ClaudeRunnerError``) doesn't
    need to change. The class will be renamed in Phase 9 alongside the
    ``core.claude_runner`` shim removal.
    """


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
]

_SKILL_PROFILES: dict[str, dict] = {
    "@evaluate": {
        "tools": [
            "mcp__farolatino__evaluate_artist",
            "mcp__farolatino__search_artist_by_url",
        ],
        "thinking_budget": 0,
    },
    "@similar": {
        "tools": [
            "mcp__farolatino__find_similar_artists",
            "mcp__farolatino__search_artist_by_url",
        ],
        "thinking_budget": 0,
    },
}


def _resolve_skill_profile(prompt: str) -> dict:
    """Return the per-skill profile (tool allowlist + thinking budget)."""
    head = prompt.strip().lower().split()[0] if prompt.strip() else ""
    if head in _SKILL_PROFILES:
        return _SKILL_PROFILES[head]
    return {"tools": _DEFAULT_TOOL_NAMES, "thinking_budget": 8000}


def _load_persona() -> str:
    """Re-read ``FAROAI.md`` every turn so user edits take effect immediately."""
    try:
        return PERSONA_PATH.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
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
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise ClaudeRunnerError(
            "No ANTHROPIC_API_KEY set. Open Connections in the sidebar to "
            "paste your Anthropic API key."
        )

    provider = get_provider()
    profile = _resolve_skill_profile(prompt)

    # Anthropic-flavored tool schemas, narrowed to the active skill's
    # allowlist. Same shape as V1's --allowed-tools whitelist.
    tools = to_anthropic(all_tool_specs())
    tools = _filter_tools_by_allowlist(tools, profile["tools"])

    # Carry skill thinking budget into the provider through env so the
    # provider stays Protocol-shaped. Phase 2 will widen the Protocol.
    prior_thinking = os.environ.get("FAROAI_THINKING_TOKENS")
    os.environ["FAROAI_THINKING_TOKENS"] = str(profile["thinking_budget"])

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
        try:
            for event in provider.run(messages=msg_stack, tools=tools, system=system):
                yield from _translate_event(event, on_event)
        except Exception as exc:
            log.exception("agent runner crashed")
            raise ClaudeRunnerError(f"Agent runner failed: {exc}") from exc
    finally:
        # Restore env so concurrent or subsequent runs don't inherit
        # this turn's thinking budget.
        if prior_thinking is None:
            os.environ.pop("FAROAI_THINKING_TOKENS", None)
        else:
            os.environ["FAROAI_THINKING_TOKENS"] = prior_thinking


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
        # the on_event hook above. Tool result content is implicit.
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
        # SSE `error` event with the same code path V1 used.
        raise ClaudeRunnerError(event.content or "agent error")
