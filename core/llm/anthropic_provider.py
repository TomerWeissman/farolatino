"""Anthropic adapter for the V2 agent loop.

Replaces the V1 `claude --print` subprocess with an in-process call to
``Anthropic().messages.stream(...)``. Owns the agent loop:

    create stream → text/thinking/tool_use deltas → if stop_reason ==
    tool_use, dispatch every tool_use block via
    ``core.llm.tool_dispatch.dispatch``, append tool_use + tool_result
    blocks to messages, restart stream → repeat until stop_reason in
    {end_turn, stop_sequence, max_tokens}.

Streaming events are translated 1:1 into ``AgentEvent`` so the
runner-and-everything-above-it never has to know which provider drove
the loop.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Iterator

import anthropic

from core.llm.base import AgentEvent
from core.llm.tool_dispatch import dispatch as dispatch_tool

log = logging.getLogger(__name__)

# V1 default that worked well with @evaluate runs (Sonnet-class).
# Picked so the upgrade path is invisible to existing users — same model
# Claude Code routes to by default. Override with FAROAI_ANTHROPIC_MODEL
# during local testing.
_DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
_DEFAULT_MAX_TOKENS = 8000

# Hard cap on agent-loop iterations. Mirrors V1's `--max-turns` safety
# net so a runaway tool_use cascade can't burn the budget. Eight turns
# fits @evaluate (avg 2-4 tool calls) with margin.
_MAX_AGENT_ITERATIONS = 16


class AnthropicProvider:
    """Implementation of `LLMProvider` for the Messages API."""

    name = "anthropic"

    def __init__(self) -> None:
        self._client = anthropic.Anthropic()
        self._model = os.getenv("FAROAI_ANTHROPIC_MODEL", _DEFAULT_MODEL)

    def run(
        self,
        *,
        messages: list[dict],
        tools: list[dict],
        system: str,
        thinking_budget: int = 0,
    ) -> Iterator[AgentEvent]:
        """Drive the Anthropic agent loop. Yields `AgentEvent`s.

        ``messages`` is mutated in-place: tool_use + tool_result blocks
        are appended after each round so the next stream call has the
        full context. The caller doesn't need (and shouldn't rely on)
        the post-call state.
        """
        total_input = 0
        total_output = 0
        total_cache_read = 0
        total_cache_creation = 0

        # Extended-thinking budget. Off for tool-call-heavy composite
        # skills (matches V1's `--max-thinking-tokens 0`); on for
        # free-form prompts. Caller passes the per-skill profile value.
        thinking_param = (
            {"type": "enabled", "budget_tokens": thinking_budget}
            if thinking_budget > 0
            else {"type": "disabled"}
        )

        for iteration in range(_MAX_AGENT_ITERATIONS):
            # Per-iteration state — reset every loop.
            assistant_blocks: list[dict] = []
            current_text = ""
            current_thinking = ""
            current_signature: str | None = None
            current_tool_use: dict | None = None
            current_tool_json = ""
            stop_reason: str | None = None

            try:
                stream_ctx = self._client.messages.stream(
                    model=self._model,
                    max_tokens=_DEFAULT_MAX_TOKENS,
                    system=system,
                    messages=messages,
                    tools=tools,
                    thinking=thinking_param,
                )
            except anthropic.AuthenticationError as exc:
                yield AgentEvent(
                    type="error",
                    content=(
                        "Anthropic authentication failed. "
                        "Check the ANTHROPIC_API_KEY in Connections. "
                        f"({exc})"
                    ),
                )
                yield AgentEvent(type="result", content="error")
                return
            except anthropic.APIError as exc:
                yield AgentEvent(type="error", content=f"Anthropic API error: {exc}")
                yield AgentEvent(type="result", content="error")
                return

            with stream_ctx as stream:
                try:
                    for raw in stream:
                        evt = _process_raw_event(
                            raw,
                            assistant_blocks=assistant_blocks,
                            state={
                                "current_text": current_text,
                                "current_thinking": current_thinking,
                                "current_signature": current_signature,
                                "current_tool_use": current_tool_use,
                                "current_tool_json": current_tool_json,
                            },
                        )
                        # Re-hoist mutable state from the helper.
                        current_text = evt["state"]["current_text"]
                        current_thinking = evt["state"]["current_thinking"]
                        current_signature = evt["state"]["current_signature"]
                        current_tool_use = evt["state"]["current_tool_use"]
                        current_tool_json = evt["state"]["current_tool_json"]
                        for ev in evt["events"]:
                            yield ev
                except anthropic.APIError as exc:
                    yield AgentEvent(type="error", content=f"Anthropic streaming error: {exc}")
                    yield AgentEvent(type="result", content="error")
                    return

                final_message = stream.get_final_message()

            stop_reason = final_message.stop_reason
            usage = final_message.usage
            if usage:
                total_input += usage.input_tokens or 0
                total_output += usage.output_tokens or 0
                total_cache_read += getattr(usage, "cache_read_input_tokens", 0) or 0
                total_cache_creation += getattr(usage, "cache_creation_input_tokens", 0) or 0

            # Promote SDK content blocks (authoritative; full text + correctly
            # ordered tool_use blocks) into the messages history. Don't trust
            # our partial accumulation — the SDK already gave us the joined-up
            # version via stream.get_final_message().
            assistant_msg_content = [_block_to_dict(b) for b in final_message.content]
            messages.append({"role": "assistant", "content": assistant_msg_content})

            if stop_reason != "tool_use":
                break

            # Run every tool_use block from this turn, build a single
            # user message with all tool_result blocks, append it.
            tool_results: list[dict] = []
            for block in final_message.content:
                if block.type != "tool_use":
                    continue
                tool_input = block.input if isinstance(block.input, dict) else {}
                output = dispatch_tool(block.name, tool_input)
                serialised = _safe_json(output)
                yield AgentEvent(
                    type="tool_result",
                    content=serialised,
                    tool_use_id=block.id,
                    tool_name=block.name,
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": serialised,
                    }
                )

            messages.append({"role": "user", "content": tool_results})
        else:
            yield AgentEvent(
                type="error",
                content=(
                    f"Agent loop hit the {_MAX_AGENT_ITERATIONS}-iteration safety cap. "
                    "Last response truncated."
                ),
            )

        # Pricing for Sonnet 4.5 — input $3/Mtok, output $15/Mtok, cache
        # reads $0.30/Mtok, cache creation $3.75/Mtok. Approximate; the
        # billed amount is whatever Anthropic charges, this is just for
        # the cost ribbon and run-log telemetry.
        cost = (
            total_input * 3.0 / 1_000_000
            + total_output * 15.0 / 1_000_000
            + total_cache_read * 0.30 / 1_000_000
            + total_cache_creation * 3.75 / 1_000_000
        )
        yield AgentEvent(
            type="result",
            content="ok",
            cost_usd=round(cost, 6),
            input_tokens=total_input,
            output_tokens=total_output,
            extra={
                "cache_read_input_tokens": total_cache_read,
                "cache_creation_input_tokens": total_cache_creation,
                "model": self._model,
            },
        )


def _process_raw_event(
    raw,
    *,
    assistant_blocks: list[dict],
    state: dict,
) -> dict:
    """Translate one raw SDK event to zero-or-more `AgentEvent`s.

    Returns a dict with ``events`` (list to yield) and ``state`` (the
    updated mutable accumulator state). Kept as a free function so the
    agent loop reads top-to-bottom.
    """
    events: list[AgentEvent] = []
    etype = getattr(raw, "type", None)

    if etype == "content_block_start":
        block = raw.content_block
        btype = getattr(block, "type", None)
        if btype == "tool_use":
            state["current_tool_use"] = {
                "id": block.id,
                "name": block.name,
            }
            state["current_tool_json"] = ""
            events.append(
                AgentEvent(
                    type="tool_use",
                    tool_name=block.name,
                    tool_use_id=block.id,
                    tool_input={},
                )
            )
        elif btype == "thinking":
            state["current_thinking"] = ""
            state["current_signature"] = None
        elif btype == "text":
            state["current_text"] = ""

    elif etype == "content_block_delta":
        delta = raw.delta
        dtype = getattr(delta, "type", None)
        if dtype == "text_delta":
            state["current_text"] += delta.text
            events.append(AgentEvent(type="text", content=delta.text))
        elif dtype == "thinking_delta":
            state["current_thinking"] += delta.thinking
            events.append(AgentEvent(type="thinking", content=delta.thinking))
        elif dtype == "signature_delta":
            state["current_signature"] = (state.get("current_signature") or "") + delta.signature
        elif dtype == "input_json_delta":
            state["current_tool_json"] += delta.partial_json

    elif etype == "content_block_stop":
        # Finalize the in-flight block (no event needed; tool_use input
        # is consumed from the SDK's joined final message after the
        # stream closes).
        state["current_tool_use"] = None
        state["current_tool_json"] = ""

    return {"events": events, "state": state}


def _block_to_dict(block) -> dict:
    """Round-trip an SDK content block back to the JSON shape the
    Messages API accepts as input. The SDK exposes ``.model_dump()``
    on every block — using it preserves provider-internal fields
    (e.g. signed thinking blocks) the next request might require.
    """
    if hasattr(block, "model_dump"):
        return block.model_dump(exclude_none=True)
    return dict(block)  # pragma: no cover — defensive


def _safe_json(value) -> str:
    """JSON-serialise tool output for tool_result content blocks."""
    try:
        return json.dumps(value, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return json.dumps({"error": "tool returned non-serialisable value"})
