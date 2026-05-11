"""Provider-agnostic event protocol shared by every LLM adapter.

The chat endpoint consumes an iterator of `AgentEvent`s; the agent
runner translates them to SSE on the wire. Keeping this dataclass
provider-blind is what lets us swap Anthropic → OpenAI → Gemini in
Phase 2 with no changes to `api/routes/chat.py` or the frontend.

Event kinds (mirrors the V1 stream-json shape closely enough that
`web/lib/streams.tsx` is unchanged):

- ``text``       — visible assistant prose. ``content`` is the delta.
- ``thinking``   — extended-thinking delta (Anthropic only). Routed to the
                   collapsible Reasoning panel via THINKING_PREFIX in
                   ``core.agent_runner``.
- ``tool_use``   — model wants to call a tool. ``tool_name`` + ``tool_input``
                   set; ``tool_use_id`` is the provider's correlation id.
- ``tool_result``— tool finished. ``tool_use_id`` matches the tool_use; the
                   resulting dict is JSON-serialised into ``content``.
- ``result``     — terminal event with ``cost_usd`` / ``input_tokens`` /
                   ``output_tokens`` totals. Emitted exactly once.
- ``error``      — fatal error, agent loop aborts. ``content`` is the
                   message shown to the user.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Protocol


@dataclass
class AgentEvent:
    """One step in the agent loop. All fields optional except ``type``.

    Designed to be a near-superset of the Claude Code stream-json events
    we previously consumed, so `core.agent_runner` can serialise it back
    into the legacy on-event shape that `core.run_log.RunLogger` already
    knows how to record.
    """

    type: str  # "text" | "thinking" | "tool_use" | "tool_result" | "result" | "error"
    content: str = ""
    tool_name: str | None = None
    tool_input: dict | None = None
    tool_use_id: str | None = None
    cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    extra: dict = field(default_factory=dict)


class LLMProvider(Protocol):
    """Streaming provider contract. Implementations own the agent loop:
    the runner just iterates events out and forwards them.
    """

    name: str  # "anthropic" | "openai" | "gemini"

    def run(
        self,
        *,
        messages: list[dict],
        tools: list[dict],
        system: str,
        web_search: str = "off",
    ) -> Iterator[AgentEvent]:
        """Drive a full multi-turn agent loop until the model stops.

        Args:
            messages: prior conversation as `{role, content}` dicts. The
                last item is always the new user message. Earlier items
                replay context lost when we dropped `--resume <id>`.
            tools: provider-formatted tool schemas (Anthropic flavor in
                Phase 1; emitted by `core.llm.tool_schemas`).
            system: full system prompt (FAROAI.md persona + today's date).
            web_search: web-search mode resolved upstream in the agent
                runner. One of:
                  - ``"off"``: do nothing.
                  - ``"tavily"``: ``web_search`` is already in ``tools``;
                    the model dispatches it in-process via ``tool_dispatch``.
                  - ``"native"``: append the provider's hosted web-search
                    tool (Brave / Bing / Google grounding); results are
                    executed server-side by the provider.
                Adapters that don't support native search treat anything
                other than ``"tavily"`` as a no-op.

        Yields:
            `AgentEvent` instances in the order the model produces them.
            Implementations MUST yield exactly one ``result`` event at
            the end (success or error path).
        """
        ...
