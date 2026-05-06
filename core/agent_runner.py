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
    """Re-read the persona every turn via the overlay system.

    Resolution order: user/persona.md > code/FAROAI.md (latest from a
    shipped update) > bundled FAROAI.md. Returns "" silently if no
    layer has it (the runner falls back to whatever the LLM thinks
    FaroAI is from the prompt alone).
    """
    from core import overlay
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
    # Deterministic skills bypass the LLM entirely — call the tool,
    # render server-side, stream the rendered Markdown. Identical
    # output across every provider, faster, $0 LLM cost. The LLM was
    # only ever a thin wrapper for these calls in V1; V2 lifts the
    # rendering into the runner so prose framing doesn't drift between
    # Anthropic / OpenAI / Gemini.
    direct = _try_handle_skill_directly(prompt, on_event)
    if direct is not None:
        yield from direct
        return

    try:
        provider = get_provider()
    except NoLLMProviderError as exc:
        raise ClaudeRunnerError(str(exc)) from exc

    profile = _resolve_skill_profile(prompt)

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
    tools = _filter_tools_by_allowlist(tools, profile["tools"])

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


# ─── Deterministic skill handlers ───────────────────────────────────────
#
# Composite skills (@evaluate, @similar) are 1-tool-call workflows where
# the LLM was only adding prose framing on top of a deterministic tool
# output. V2 lifts the rendering server-side so the chat shows identical
# Markdown regardless of provider — same headers, same metric tables,
# same callouts, same wording. Free-form chat still flows through the
# LLM.


def _try_handle_skill_directly(prompt: str, on_event) -> Iterator[str] | None:
    """Return a chunk iterator if ``prompt`` is a deterministic skill
    we can render server-side; otherwise return ``None`` so the caller
    falls through to the LLM path.
    """
    head, _, arg = prompt.strip().partition(" ")
    head_lc = head.lower()
    if head_lc == "@evaluate":
        return _handle_evaluate(arg.strip(), on_event)
    if head_lc == "@similar":
        return _handle_similar(arg.strip(), on_event)
    return None


def _emit_synthetic_init(on_event, provider_name: str = "server-rendered") -> str:
    """Emit a synthetic system/init so RunLogger + chat.py treat the
    bypassed turn the same as an LLM-driven one (session id, mcp servers,
    provider). Returns the session id so the result event can echo it
    back to the frontend."""
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
                    "provider": provider_name,
                }
            )
        except Exception:
            pass
    return session_id


def _emit_synthetic_tool_use(on_event, name: str, tool_input: dict) -> str:
    """Emit a synthetic assistant tool_use so the UI status pill flips
    to the friendly label and RunLogger captures the tool call."""
    tool_use_id = uuid.uuid4().hex[:16]
    if on_event is not None:
        try:
            on_event(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": tool_use_id,
                                "name": name,
                                "input": tool_input,
                            }
                        ]
                    },
                }
            )
        except Exception:
            pass
    return tool_use_id


def _emit_synthetic_tool_result(on_event, tool_use_id: str, name: str, output: dict) -> None:
    if on_event is not None:
        try:
            import json as _json
            on_event(
                {
                    "type": "user",
                    "message": {
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_use_id,
                                "tool_name": name,
                                "content": _json.dumps(output, default=str),
                            }
                        ]
                    },
                }
            )
        except Exception:
            pass


def _emit_synthetic_result(on_event) -> None:
    if on_event is not None:
        try:
            on_event({"type": "result", "total_cost_usd": 0.0, "model": "server-rendered"})
        except Exception:
            pass


def _handle_evaluate(arg: str, on_event) -> Iterator[str]:
    """Server-rendered ``@evaluate`` flow. Yields the canonical Markdown
    dossier (or a disambiguation menu, or an error) — identical bytes
    regardless of which LLM provider is configured.
    """
    _emit_synthetic_init(on_event)

    if not arg:
        yield (
            "**Usage:** `@evaluate <artist name or URL>`\n\n"
            "Example: `@evaluate Bad Bunny` or `@evaluate https://open.spotify.com/artist/...`"
        )
        _emit_synthetic_result(on_event)
        return

    tool_input = {"artist": arg, "profile_name": "default"}
    tool_use_id = _emit_synthetic_tool_use(
        on_event, "mcp__farolatino__evaluate_artist", tool_input
    )
    result = dispatch_tool("mcp__farolatino__evaluate_artist", tool_input)
    _emit_synthetic_tool_result(
        on_event, tool_use_id, "mcp__farolatino__evaluate_artist", result
    )

    if "error" in result:
        yield f"⚠️ **Couldn't evaluate `{arg}`.**\n\n{result['error']}"
        _emit_synthetic_result(on_event)
        return

    if "needs_disambiguation" in result:
        yield _render_disambiguation(arg, result["needs_disambiguation"])
        _emit_synthetic_result(on_event)
        return

    # Happy path: pull the artist record (cached after evaluate_artist's
    # call) and hand both to the canonical renderer.
    cm_id = result.get("cm_id")
    artist_data: dict = {}
    if cm_id:
        try:
            artist_data = dispatch_tool(
                "mcp__farolatino__get_artist_data",
                {"cm_artist_id": cm_id, "use_cache": True},
            )
        except Exception:
            artist_data = {}

    try:
        from mcp_server.tools.dossier_renderer import render_dossier
        markdown = render_dossier(result["dossier"], artist_data or {})
    except Exception as exc:
        log.exception("dossier render failed")
        yield f"⚠️ Renderer error: {exc}"
        _emit_synthetic_result(on_event)
        return

    yield markdown
    _emit_synthetic_result(on_event)


def _handle_similar(arg: str, on_event) -> Iterator[str]:
    """Server-rendered ``@similar`` flow — same shape as ``@evaluate``,
    different tool + renderer. The body is a list of comparable artists
    rather than a single dossier.
    """
    _emit_synthetic_init(on_event)

    if not arg:
        yield (
            "**Usage:** `@similar <artist name or URL>`\n\n"
            "Example: `@similar Bad Bunny`"
        )
        _emit_synthetic_result(on_event)
        return

    tool_input = {"artist": arg}
    tool_use_id = _emit_synthetic_tool_use(
        on_event, "mcp__farolatino__find_similar_artists", tool_input
    )
    result = dispatch_tool("mcp__farolatino__find_similar_artists", tool_input)
    _emit_synthetic_tool_result(
        on_event, tool_use_id, "mcp__farolatino__find_similar_artists", result
    )

    if "error" in result:
        yield f"⚠️ **Couldn't find similar artists for `{arg}`.**\n\n{result['error']}"
        _emit_synthetic_result(on_event)
        return

    if "needs_disambiguation" in result:
        yield _render_disambiguation(arg, result["needs_disambiguation"])
        _emit_synthetic_result(on_event)
        return

    try:
        from mcp_server.tools.dossier_renderer import render_similar
        markdown = render_similar(result)
    except Exception as exc:
        log.exception("similar render failed")
        yield f"⚠️ Renderer error: {exc}"
        _emit_synthetic_result(on_event)
        return

    yield markdown
    _emit_synthetic_result(on_event)


def _render_disambiguation(query: str, candidates: list[dict]) -> str:
    """Server-rendered disambiguation menu — same bytes regardless of
    provider. Tells the user exactly which artist to specify next so
    the follow-up turn lands cleanly.
    """
    lines = [f"**Multiple artists match `{query}`.** Which one did you mean?\n"]
    for i, c in enumerate(candidates[:3], start=1):
        name = c.get("name") or "—"
        followers = c.get("sp_followers")
        listeners = c.get("sp_monthly_listeners")
        country = c.get("country_code") or "—"
        cm_id = c.get("cm_id")
        bits = []
        if listeners:
            bits.append(f"{listeners:,} monthly listeners")
        elif followers:
            bits.append(f"{followers:,} Spotify followers")
        if country and country != "—":
            bits.append(country)
        suffix = f" ({', '.join(bits)})" if bits else ""
        lines.append(f"{i}. **{name}**{suffix} — `cm_id: {cm_id}`")
    lines.append(
        "\nReply with the artist's exact name (or paste their Spotify URL) to disambiguate."
    )
    return "\n".join(lines)
