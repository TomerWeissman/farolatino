"""Gemini adapter for the V2 agent loop.

Uses ``google-genai`` (the v1 SDK; ``google.generativeai`` is the
deprecated package). Sync streaming via
``client.models.generate_content_stream(...)`` so we can yield
``AgentEvent``s without bridging an asyncio loop into the chat thread.

Multi-turn agent loop: stream → if any ``function_call`` parts appear,
dispatch each tool, append the model's response (model role) and our
``function_response`` parts (user role) to ``contents``, restart →
repeat until the model returns no more function calls.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Iterator

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from core.llm.base import AgentEvent
from core.llm.tool_dispatch import dispatch as dispatch_tool

log = logging.getLogger(__name__)

# Default model. flash variants are cheap + fast and support function
# calling. Override with FAROAI_GEMINI_MODEL.
_DEFAULT_MODEL = "gemini-2.0-flash"
_MAX_AGENT_ITERATIONS = 16

# Approx prices ($/Mtok). Override the default model + we'll fall
# back to flash pricing.
_PRICING: dict[str, tuple[float, float]] = {
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
}


class GeminiProvider:
    name = "gemini"

    def __init__(self, *, api_key: str | None = None) -> None:
        # Pass api_key explicitly — registry hands us the key from
        # LLM_API_KEY (or a legacy env-var fallback), so the SDK
        # shouldn't auto-read GEMINI_API_KEY from env on its own.
        self._client = genai.Client(api_key=api_key)
        self._model = os.getenv("FAROAI_GEMINI_MODEL", _DEFAULT_MODEL)

    def run(
        self,
        *,
        messages: list[dict],
        tools: list[dict],
        system: str,
        thinking_budget: int = 0,  # Gemini's thinking mode is gated; ignored for Phase 2
        web_search: str = "off",
    ) -> Iterator[AgentEvent]:
        # Translate our messages into Gemini's contents form.
        # Gemini uses role "user" / "model" (NOT "assistant").
        contents: list[genai_types.Content] = []
        for m in messages:
            role = m.get("role")
            content = m.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            if role == "user":
                contents.append(
                    genai_types.Content(role="user", parts=[genai_types.Part(text=content)])
                )
            elif role == "assistant":
                contents.append(
                    genai_types.Content(role="model", parts=[genai_types.Part(text=content)])
                )

        # Build the Tool wrapper from our function declarations. Gemini
        # accepts raw JSON Schema via parameters_json_schema, so we
        # don't have to translate to the SDK's Schema enum types.
        tool_wrapper = genai_types.Tool(
            function_declarations=[
                genai_types.FunctionDeclaration(
                    name=t["name"],
                    description=t.get("description") or "",
                    parameters_json_schema=t.get("parameters_json_schema") or {"type": "object"},
                )
                for t in tools
            ]
        )
        tool_list: list[genai_types.Tool] = [tool_wrapper]
        # Native Google Search grounding. Gemini 2.x supports mixing
        # google_search with function_declarations in the same request.
        # Grounding metadata (cited URLs, search queries) arrives on the
        # final chunk's candidates[0].grounding_metadata — we synthesize
        # tool_use/tool_result events post-stream so the Reasoning panel
        # renders citations consistently.
        if web_search == "native":
            try:
                tool_list.append(genai_types.Tool(google_search=genai_types.GoogleSearch()))
            except Exception:
                log.exception("failed to attach google_search grounding; continuing without")

        config = genai_types.GenerateContentConfig(
            system_instruction=system,
            tools=tool_list,
            # Force a function call when one is plausible — Gemini's
            # default is AUTO which is what we want here.
            tool_config=genai_types.ToolConfig(
                function_calling_config=genai_types.FunctionCallingConfig(mode="AUTO")
            ),
        )

        total_input = 0
        total_output = 0

        for _iteration in range(_MAX_AGENT_ITERATIONS):
            announced: set[str] = set()
            collected_parts: list[genai_types.Part] = []
            final_chunk = None
            try:
                stream = self._client.models.generate_content_stream(
                    model=self._model,
                    contents=contents,
                    config=config,
                )
                for chunk in stream:
                    final_chunk = chunk
                    candidates = getattr(chunk, "candidates", None) or []
                    if not candidates:
                        continue
                    parts = getattr(candidates[0].content, "parts", None) or []
                    for part in parts:
                        # Text deltas
                        text = getattr(part, "text", None)
                        if text:
                            yield AgentEvent(type="text", content=text)
                            collected_parts.append(part)
                            continue
                        # Tool calls
                        fc = getattr(part, "function_call", None)
                        if fc is not None:
                            # Use the function call's name as the
                            # de-dupe key — Gemini may emit the same
                            # function_call across multiple chunks
                            # while it streams.
                            key = f"{fc.name}:{id(fc)}"
                            if key not in announced:
                                announced.add(key)
                                yield AgentEvent(
                                    type="tool_use",
                                    tool_name=fc.name,
                                    tool_use_id=fc.name,  # Gemini doesn't return a stable id
                                    tool_input=dict(fc.args or {}),
                                )
                            collected_parts.append(part)
            except genai_errors.APIError as exc:
                err = _classify_error(exc)
                yield AgentEvent(type="error", content=err["title"], extra=err)
                yield AgentEvent(type="result", content="error")
                return

            usage = getattr(final_chunk, "usage_metadata", None) if final_chunk else None
            if usage is not None:
                total_input += getattr(usage, "prompt_token_count", 0) or 0
                total_output += getattr(usage, "candidates_token_count", 0) or 0

            # Surface Google Search grounding (when native web_search is
            # on) as a synthetic tool_use + tool_result pair so the
            # Reasoning panel renders the citations alongside other tool
            # calls. Metadata arrives once per response, on the final
            # chunk — not streamed.
            if web_search == "native":
                yield from _emit_grounding_events(final_chunk)

            # Persist the model's reply to contents so the next round
            # has the full conversation. Skip empty turns to keep the
            # log lean.
            if collected_parts:
                contents.append(genai_types.Content(role="model", parts=collected_parts))

            # Find tool calls in the final chunk's parts and dispatch.
            function_responses: list[genai_types.Part] = []
            for part in collected_parts:
                fc = getattr(part, "function_call", None)
                if fc is None:
                    continue
                args = dict(fc.args or {})
                output = dispatch_tool(fc.name, args)
                yield AgentEvent(
                    type="tool_result",
                    content=str(output),
                    tool_use_id=fc.name,
                    tool_name=fc.name,
                )
                function_responses.append(
                    genai_types.Part.from_function_response(
                        name=fc.name,
                        response=output if isinstance(output, dict) else {"result": output},
                    )
                )

            if not function_responses:
                break

            # User-role part list with all the function responses for
            # this round. Gemini expects them paired in one user turn.
            contents.append(genai_types.Content(role="user", parts=function_responses))
        else:
            yield AgentEvent(
                type="error",
                content=f"Agent loop hit the {_MAX_AGENT_ITERATIONS}-iteration safety cap.",
            )

        in_price, out_price = _PRICING.get(self._model, _PRICING[_DEFAULT_MODEL])
        cost = total_input * in_price / 1_000_000 + total_output * out_price / 1_000_000
        yield AgentEvent(
            type="result",
            content="ok",
            cost_usd=round(cost, 6),
            input_tokens=total_input,
            output_tokens=total_output,
            extra={"model": self._model},
        )


def _emit_grounding_events(final_chunk) -> Iterator[AgentEvent]:
    """Synthesize tool_use + tool_result AgentEvents from a Gemini
    response's grounding metadata. No-op when grounding wasn't used.

    Gemini's grounding metadata is delivered once on the final chunk;
    we transform it to look like a normal tool call (name="web_search")
    so the chat UI renders it alongside other tool dispatches.
    """
    candidates = getattr(final_chunk, "candidates", None) or []
    if not candidates:
        return
    metadata = getattr(candidates[0], "grounding_metadata", None)
    if metadata is None:
        return
    queries = list(getattr(metadata, "web_search_queries", []) or [])
    chunks = getattr(metadata, "grounding_chunks", None) or []
    sources: list[dict] = []
    for c in chunks:
        web = getattr(c, "web", None)
        if web is None:
            continue
        sources.append(
            {
                "title": getattr(web, "title", "") or "",
                "url": getattr(web, "uri", "") or "",
            }
        )
    if not queries and not sources:
        return
    tool_use_id = "gemini_grounding"
    yield AgentEvent(
        type="tool_use",
        tool_name="web_search",
        tool_use_id=tool_use_id,
        tool_input={"queries": queries},
    )
    try:
        serialised = json.dumps({"queries": queries, "sources": sources}, default=str)
    except (TypeError, ValueError):
        serialised = "{\"queries\": [], \"sources\": []}"
    yield AgentEvent(
        type="tool_result",
        content=serialised,
        tool_use_id=tool_use_id,
        tool_name="web_search",
    )


def _classify_error(exc: Exception) -> dict:
    """Map a Gemini SDK exception to a structured user-facing error."""
    raw = str(exc)
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    status = getattr(exc, "status", "") or ""

    # 401 / 403 → auth issue
    if code in (401, 403) or "API key not valid" in raw or "PERMISSION_DENIED" in status:
        return {
            "title": "Gemini API key invalid",
            "hint": "Open Connections and paste a valid Google AI Studio key (starts with AIza).",
            "fix_url": "https://aistudio.google.com/apikey",
            "raw": raw,
        }
    # 429 → quota / rate limit. Two common flavors:
    if code == 429 or "RESOURCE_EXHAUSTED" in status or "RESOURCE_EXHAUSTED" in raw:
        # The "limit: 0" pattern means the project graduated past free
        # tier — billing must be enabled on the Cloud project tied to
        # this key. Different ask than transient rate-limiting.
        if "limit: 0" in raw:
            return {
                "title": "Gemini project has no quota for this model",
                "hint": (
                    "Your Google Cloud project has 0 free-tier requests for this model. "
                    "Either enable billing on the project, or create a new key under a "
                    "different project that has free-tier enabled."
                ),
                "fix_url": "https://aistudio.google.com/apikey",
                "raw": raw,
            }
        return {
            "title": "Gemini rate-limited",
            "hint": "You've hit your per-minute / per-day request cap. Wait a moment and retry.",
            "fix_url": "https://ai.google.dev/gemini-api/docs/rate-limits",
            "raw": raw,
        }
    # 400 → bad request (model unavailable, oversized, etc.)
    if code == 400 or "INVALID_ARGUMENT" in status:
        return {
            "title": "Gemini rejected the request",
            "hint": _truncate_for_hint(raw) or "See details below.",
            "fix_url": None,
            "raw": raw,
        }
    # 503 / 504 → upstream
    if code in (500, 502, 503, 504):
        return {
            "title": "Gemini is temporarily unavailable",
            "hint": "Google reported a server-side error. Wait a moment and retry.",
            "fix_url": None,
            "raw": raw,
        }
    return {
        "title": "Gemini error",
        "hint": _truncate_for_hint(raw) or None,
        "fix_url": None,
        "raw": raw,
    }


def _truncate_for_hint(text: str, limit: int = 200) -> str:
    if not text:
        return ""
    line = text.replace("\n", " ").strip()
    if len(line) > limit:
        line = line[: limit - 1].rstrip() + "…"
    return line
