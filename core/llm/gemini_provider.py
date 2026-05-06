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

    def __init__(self) -> None:
        # The v1 client picks up GEMINI_API_KEY from env automatically.
        self._client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        self._model = os.getenv("FAROAI_GEMINI_MODEL", _DEFAULT_MODEL)

    def run(
        self,
        *,
        messages: list[dict],
        tools: list[dict],
        system: str,
        thinking_budget: int = 0,  # Gemini's thinking mode is gated; ignored for Phase 2
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

        config = genai_types.GenerateContentConfig(
            system_instruction=system,
            tools=[tool_wrapper],
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
                yield AgentEvent(type="error", content=f"Gemini API error: {exc}")
                yield AgentEvent(type="result", content="error")
                return

            usage = getattr(final_chunk, "usage_metadata", None) if final_chunk else None
            if usage is not None:
                total_input += getattr(usage, "prompt_token_count", 0) or 0
                total_output += getattr(usage, "candidates_token_count", 0) or 0

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
