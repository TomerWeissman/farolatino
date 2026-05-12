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
from core.agent_runner import (
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
    state: dict = {"error": None, "session_id": None}
    # Map tool_use_id → tool_name so we can recognise an evaluate_artist
    # tool_result when it lands on the next user event. Used only to
    # decide whether to emit an evaluate_pill event — the LLM still
    # sees the full result.
    tool_use_index: dict[str, str] = {}

    def _push(item) -> None:
        """Thread-safe enqueue from the worker thread."""
        loop.call_soon_threadsafe(queue.put_nowait, item)

    def _parse_tool_result_content(tool_result_block: dict) -> dict | None:
        """Provider adapters serialize tool_result content as either a
        JSON string or a list of text blocks. Normalize and parse, or
        return None if the result isn't a dict we can read."""
        content = tool_result_block.get("content")
        if isinstance(content, list):
            content = "".join(
                (b.get("text") or "") for b in content if isinstance(b, dict)
            )
        if not isinstance(content, str):
            return None
        try:
            parsed = json.loads(content)
        except (ValueError, TypeError):
            return None
        return parsed if isinstance(parsed, dict) else None

    def _maybe_emit_evaluate_pill(tool_result_block: dict) -> None:
        """When the just-completed tool was evaluate_artist, parse the
        result and emit a compact pill event so the chat renders a card
        linking to /evaluate instead of the LLM pasting the dossier wall.
        Silently does nothing if the result is missing fields, errored,
        or was a disambiguation prompt."""
        tool_use_id = tool_result_block.get("tool_use_id")
        if not tool_use_id:
            return
        if tool_use_index.get(tool_use_id) != "mcp__farolatino__evaluate_artist":
            return
        parsed = _parse_tool_result_content(tool_result_block)
        if parsed is None:
            return
        if parsed.get("error") or parsed.get("needs_disambiguation"):
            return
        dossier = parsed.get("dossier") or {}
        identity = dossier.get("identity") or {}
        score = dossier.get("prospect_score") or {}
        cm_id = parsed.get("cm_id") or identity.get("cm_id")
        artist = identity.get("name")
        if not (cm_id and artist):
            return
        _push(_build_event("evaluate_pill", {
            "artist": artist,
            "cm_id": cm_id,
            "image": identity.get("image"),
            "tier": score.get("tier"),
            "score": score.get("overall"),
        }))

    def _maybe_emit_compare_pill(tool_result_block: dict) -> None:
        """When the just-completed tool was compare_artists, parse the
        result and emit a compact two-photo pill event. Skipped on
        partial results (either side errored or needs disambiguation)
        — the chat surfaces the LLM's prose follow-up in those cases."""
        tool_use_id = tool_result_block.get("tool_use_id")
        if not tool_use_id:
            return
        if tool_use_index.get(tool_use_id) != "mcp__farolatino__compare_artists":
            return
        parsed = _parse_tool_result_content(tool_result_block)
        if parsed is None:
            return
        if (
            parsed.get("error")
            or parsed.get("needs_disambiguation_a")
            or parsed.get("needs_disambiguation_b")
        ):
            return
        comp = parsed.get("comparison") or {}
        cm_id_a = parsed.get("cm_id_a")
        cm_id_b = parsed.get("cm_id_b")
        if not (cm_id_a and cm_id_b and comp.get("name_a") and comp.get("name_b")):
            return
        _push(_build_event("compare_pill", {
            "artist_a": comp["name_a"],
            "artist_b": comp["name_b"],
            "cm_id_a": cm_id_a,
            "cm_id_b": cm_id_b,
            "image_a": comp.get("image_a"),
            "image_b": comp.get("image_b"),
            "tier_a": comp.get("tier_a"),
            "tier_b": comp.get("tier_b"),
            "score_a": comp.get("score_a"),
            "score_b": comp.get("score_b"),
        }))

    def _on_event(event: dict) -> None:
        """Forwarded into RunLogger (telemetry) AND used to surface
        tool_use events to the client BEFORE the corresponding text
        chunk arrives — gives the UI a chance to update the status pill.
        Also captures the session_id from the system/init event so the
        frontend can pass it back as resume_session_id on follow-up turns.
        And: emits a synthetic evaluate_pill event when a successful
        evaluate_artist tool_result lands."""
        logger.record_event(event)
        etype = event.get("type")
        if etype == "system" and event.get("subtype") == "init":
            sid = event.get("session_id")
            if sid:
                state["session_id"] = sid
            return
        if etype == "user":
            # Tool results come back on synthetic user messages.
            for block in (event.get("message") or {}).get("content") or []:
                if block.get("type") == "tool_result":
                    _maybe_emit_evaluate_pill(block)
                    _maybe_emit_compare_pill(block)
            return
        if etype != "assistant":
            return
        for block in (event.get("message") or {}).get("content") or []:
            if block.get("type") == "tool_use":
                name = block.get("name", "tool")
                tid = block.get("id")
                if tid:
                    tool_use_index[tid] = name
                _push(_build_event("tool_use", {
                    "name": name,
                    "label": humanize_tool(name),
                    "input": block.get("input") or {},
                }))

    def _worker() -> None:
        try:
            for chunk in run_claude_streaming(
                prompt,
                on_event=_on_event,
                resume_session_id=req.resume_session_id,
                messages=[m.model_dump() for m in (req.messages or [])],
            ):
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
            payload: dict = {"message": str(exc)}
            if exc.hint:
                payload["hint"] = exc.hint
            if exc.fix_url:
                payload["fix_url"] = exc.fix_url
            if exc.raw:
                payload["raw"] = exc.raw
            _push(_build_event("error", payload))
        except Exception as exc:  # pragma: no cover — defensive
            log.exception("chat worker crashed")
            state["error"] = f"unexpected: {exc!r}"
            _push(_build_event("error", {
                "message": "Unexpected server error",
                "hint": "Check the server logs for the stack trace.",
                "raw": state["error"],
            }))
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
                "session_id": state["session_id"],  # for frontend to stash + resume on next turn
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
