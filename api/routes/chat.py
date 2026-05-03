"""POST /api/chat — SSE-streaming chat endpoint.

Wraps `core.claude_runner.run_claude_streaming` (a blocking subprocess
generator) and emits structured SSE events to the browser:

  event: tool_use   data: {"name": ..., "label": ..., "input": {...}}
  event: thinking   data: {"delta": "..."}
  event: text       data: {"delta": "..."}
  event: result     data: {"run_id": ..., "status": ..., "duration_s": ..., "cost_usd": ...}
  event: error      data: {"message": "..."}

The generator runs in a worker thread; an asyncio.Queue bridges the
threads. The queue is sentinel-terminated so the SSE coroutine exits
cleanly when claude --print does.
"""
from __future__ import annotations

import asyncio
import json
import logging
from threading import Thread

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from api.schemas import ChatRequest
from core.claude_runner import (
    THINKING_PREFIX,
    ClaudeRunnerError,
    run_claude_streaming,
)
from core.humanize import humanize_tool
from core.run_log import RunLogger

router = APIRouter()
log = logging.getLogger(__name__)

# Sentinel pushed onto the queue to signal "stream is done".
_DONE = object()


def _build_event(event_type: str, payload: dict) -> dict:
    """sse-starlette expects {event, data} dicts. Data is JSON-encoded once
    here so the client can `JSON.parse(event.data)` directly."""
    return {"event": event_type, "data": json.dumps(payload)}


@router.post("/chat")
async def post_chat(req: ChatRequest):
    """Streaming chat. Returns text/event-stream."""
    prompt = (req.prompt or "").strip()
    if not prompt:
        # 204-style empty response would also work, but SSE clients tend
        # to handle "stream that immediately closes" better than HTTP 400.
        async def _empty():
            yield _build_event("error", {"message": "empty prompt"})
        return EventSourceResponse(_empty())

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    logger = RunLogger(prompt=prompt)

    # State carried across the worker thread → SSE generator boundary.
    accumulated_text: list[str] = []
    thinking_blocks: list[str] = []
    state: dict = {"error": None}

    def _push(item) -> None:
        """Thread-safe enqueue from the worker thread."""
        loop.call_soon_threadsafe(queue.put_nowait, item)

    def _on_event(event: dict) -> None:
        """Forwarded into RunLogger (telemetry) AND used to surface
        tool_use events to the client BEFORE the corresponding text
        chunk arrives — gives the UI a chance to update the status pill."""
        logger.record_event(event)
        if event.get("type") != "assistant":
            return
        for block in (event.get("message") or {}).get("content") or []:
            if block.get("type") == "tool_use":
                name = block.get("name", "tool")
                _push(_build_event("tool_use", {
                    "name": name,
                    "label": humanize_tool(name),
                    "input": block.get("input") or {},
                }))

    def _worker() -> None:
        try:
            for chunk in run_claude_streaming(prompt, on_event=_on_event):
                if chunk.startswith(THINKING_PREFIX):
                    delta = chunk[len(THINKING_PREFIX):]
                    thinking_blocks.append(delta)
                    _push(_build_event("thinking", {"delta": delta}))
                else:
                    # Strip the auto-generated "_using `tool`..._" markers —
                    # the UI renders tool_use events explicitly, so the
                    # marker is noise.
                    cleaned = _strip_using_markers(chunk)
                    if cleaned:
                        accumulated_text.append(cleaned)
                        _push(_build_event("text", {"delta": cleaned}))
        except ClaudeRunnerError as exc:
            state["error"] = str(exc)
            _push(_build_event("error", {"message": str(exc)}))
        except Exception as exc:  # pragma: no cover — defensive
            log.exception("chat worker crashed")
            state["error"] = f"unexpected: {exc!r}"
            _push(_build_event("error", {"message": state["error"]}))
        finally:
            _push(_DONE)

    Thread(target=_worker, daemon=True).start()

    async def _emit():
        try:
            while True:
                item = await queue.get()
                if item is _DONE:
                    break
                yield item
            # Final result event after stream-end so the client can show
            # cost/duration and link to the run-log entry.
            record = logger.finalize(
                response_text="".join(accumulated_text),
                error=state["error"],
                thinking_blocks=thinking_blocks,
            )
            yield _build_event("result", {
                "run_id": record.run_id,
                "status": record.status,
                "duration_s": record.duration_s,
                "cost_usd": record.cost_usd,
                "tool_calls": record.tool_calls,
                "thinking_block_count": len(record.thinking_blocks),
            })
        except asyncio.CancelledError:
            # Client disconnected mid-stream. The watchdog in
            # claude_runner kills the subprocess + descendants, but the
            # logger never reaches finalize() — log that, swallow the
            # exception so uvicorn doesn't 500.
            log.info("chat client disconnected mid-stream (run_id=%s)", logger.run_id)
            raise

    # `ping` makes sse-starlette emit a `: ping\n\n` comment every N seconds.
    # Chromium-based browsers buffer SSE responses until the wire-level
    # buffer hits a threshold (~1KB) — for a slow @evaluate run that
    # produces tiny tool_use events, the user's chat would silently sit on
    # "Thinking…" for the full duration even though events are queued. The
    # heartbeat keeps bytes flowing so the browser flushes early events.
    return EventSourceResponse(_emit(), ping=2)


def _strip_using_markers(chunk: str) -> str:
    """Remove the `_using `<tool>`..._` markers the runner inserts inline.

    The structured tool_use event already conveys this info; rendering it
    twice would clutter the assistant prose."""
    import re
    return re.sub(r"\n*_using `[^`]+`\.\.\._\n*", "", chunk)
