"""OpenAI adapter for the V2 agent loop.

Uses the Responses API (``client.responses.create(stream=True, ...)``)
because it is the v1 surface for tool use + structured output on
modern models. Parallel tool calls are disabled (per plan) to keep
spend predictable and to avoid contention on Chartmetric's 1.05 req/s
lock when @evaluate fans out.

The agent loop mirrors the Anthropic adapter: stream → if any
``function_call`` items appear, dispatch each tool, append the
``function_call`` items + ``function_call_output`` items to the input,
restart → repeat until the model returns no more tool calls.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Iterator

import openai

from core.llm.base import AgentEvent
from core.llm.tool_dispatch import dispatch as dispatch_tool

log = logging.getLogger(__name__)

# Default model for v2.0. gpt-4o is widely available, supports tool
# calls + Responses API, no o-series gating quirks.
_DEFAULT_MODEL = "gpt-4o"
_MAX_AGENT_ITERATIONS = 16

# Approximate prices ($/Mtok). Used for the cost ribbon + run-log
# only — billed amount is whatever OpenAI charges. Override the
# default model via FAROAI_OPENAI_MODEL.
_PRICING: dict[str, tuple[float, float]] = {
    # (input $/Mtok, output $/Mtok)
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
}


class OpenAIProvider:
    name = "openai"

    def __init__(self, *, api_key: str | None = None) -> None:
        # Pass api_key explicitly so the SDK doesn't fall through to
        # OPENAI_API_KEY in env — the V2 single-key UX paste lands in
        # LLM_API_KEY, and the registry hands it to us here.
        self._client = openai.OpenAI(api_key=api_key)
        self._model = os.getenv("FAROAI_OPENAI_MODEL", _DEFAULT_MODEL)

    def run(
        self,
        *,
        messages: list[dict],
        tools: list[dict],
        system: str,
        thinking_budget: int = 0,  # OpenAI ignores; o-series reasoning is gated separately
    ) -> Iterator[AgentEvent]:
        # Build the initial input array. The Responses API takes either
        # a string OR an array of typed items; for multi-turn we use
        # the array form. Each prior assistant turn is collapsed into a
        # single message item — we don't replay tool_use blocks across
        # turns because the previous turn's tool results are already
        # baked into the assistant's textual reply.
        input_items: list[dict] = []
        for m in messages:
            role = m.get("role")
            content = m.get("content")
            if not isinstance(content, str):
                continue
            if role == "user":
                input_items.append({"role": "user", "content": content})
            elif role == "assistant":
                input_items.append({"role": "assistant", "content": content})

        total_input = 0
        total_output = 0

        for _iteration in range(_MAX_AGENT_ITERATIONS):
            try:
                stream = self._client.responses.create(
                    model=self._model,
                    instructions=system,
                    input=input_items,
                    tools=tools,
                    parallel_tool_calls=False,
                    stream=True,
                )
            except openai.AuthenticationError as exc:
                yield AgentEvent(
                    type="error",
                    content=(
                        "OpenAI authentication failed. "
                        "Check the OPENAI_API_KEY in Connections. "
                        f"({exc})"
                    ),
                )
                yield AgentEvent(type="result", content="error")
                return
            except openai.OpenAIError as exc:
                yield AgentEvent(type="error", content=f"OpenAI API error: {exc}")
                yield AgentEvent(type="result", content="error")
                return

            # Per-iteration scratchpad so we can correlate function_call
            # arguments deltas with their tool_use_id when they finish.
            tool_calls_in_flight: dict[str, dict] = {}
            announced: set[str] = set()
            final_response = None

            try:
                for event in stream:
                    etype = getattr(event, "type", "")
                    if etype == "response.output_text.delta":
                        delta = getattr(event, "delta", "") or ""
                        if delta:
                            yield AgentEvent(type="text", content=delta)
                    elif etype == "response.output_item.added":
                        item = getattr(event, "item", None)
                        if item is not None and getattr(item, "type", None) == "function_call":
                            tool_calls_in_flight[item.id] = {
                                "id": item.id,
                                "name": item.name,
                                "call_id": getattr(item, "call_id", item.id),
                                "arguments": "",
                            }
                            # Announce immediately so the UI status pill
                            # updates before we have the full args.
                            if item.id not in announced:
                                announced.add(item.id)
                                yield AgentEvent(
                                    type="tool_use",
                                    tool_name=item.name,
                                    tool_use_id=item.id,
                                    tool_input={},
                                )
                    elif etype == "response.function_call_arguments.delta":
                        item_id = getattr(event, "item_id", None)
                        delta = getattr(event, "delta", "") or ""
                        if item_id and item_id in tool_calls_in_flight:
                            tool_calls_in_flight[item_id]["arguments"] += delta
                    elif etype == "response.completed":
                        final_response = getattr(event, "response", None)
            except openai.OpenAIError as exc:
                yield AgentEvent(type="error", content=f"OpenAI streaming error: {exc}")
                yield AgentEvent(type="result", content="error")
                return

            usage = getattr(final_response, "usage", None) if final_response else None
            if usage is not None:
                total_input += getattr(usage, "input_tokens", 0) or 0
                total_output += getattr(usage, "output_tokens", 0) or 0

            # Append every model-emitted item to input_items so the next
            # turn's request carries forward both assistant prose and
            # the function_call records (required so OpenAI can match
            # function_call_output items by call_id).
            assistant_items: list[dict] = []
            function_calls: list[dict] = []
            if final_response is not None and getattr(final_response, "output", None):
                for item in final_response.output:
                    item_dict = (
                        item.model_dump(exclude_none=True)
                        if hasattr(item, "model_dump")
                        else dict(item)
                    )
                    assistant_items.append(item_dict)
                    if item_dict.get("type") == "function_call":
                        function_calls.append(item_dict)
            input_items.extend(assistant_items)

            if not function_calls:
                break

            # Dispatch every tool, append the corresponding function_call_output.
            for fc in function_calls:
                args_str = fc.get("arguments") or ""
                try:
                    args = json.loads(args_str) if args_str else {}
                except json.JSONDecodeError:
                    args = {}
                output = dispatch_tool(fc.get("name", ""), args)
                output_str = _safe_json(output)
                yield AgentEvent(
                    type="tool_result",
                    content=output_str,
                    tool_use_id=fc.get("id"),
                    tool_name=fc.get("name"),
                )
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": fc.get("call_id") or fc.get("id"),
                        "output": output_str,
                    }
                )
        else:
            yield AgentEvent(
                type="error",
                content=f"Agent loop hit the {_MAX_AGENT_ITERATIONS}-iteration safety cap.",
            )

        in_price, out_price = _PRICING.get(self._model, (2.50, 10.00))
        cost = total_input * in_price / 1_000_000 + total_output * out_price / 1_000_000
        yield AgentEvent(
            type="result",
            content="ok",
            cost_usd=round(cost, 6),
            input_tokens=total_input,
            output_tokens=total_output,
            extra={"model": self._model},
        )


def _safe_json(value) -> str:
    try:
        return json.dumps(value, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return json.dumps({"error": "tool returned non-serialisable value"})
