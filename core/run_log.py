"""Per-chat-submission run log for testing and debugging.

Every chat submission writes one JSON line to `data/cache/chat_runs.jsonl`
with timestamp, prompt, response text, all observed Claude Code events,
duration, and any error. The Streamlit sidebar surfaces the last N runs
with a status icon — clicking expands the full event trace.

This is for *the user testing the system*, not for shipping to end users.
The on-disk JSONL stays in `data/cache/`, which is gitignored.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = PROJECT_ROOT / "data" / "cache" / "chat_runs.jsonl"


@dataclass
class RunRecord:
    run_id: str
    started_at: str
    duration_s: float
    prompt: str
    response_text: str
    status: str  # "ok" | "error" | "no_text"
    error: str | None = None
    tool_calls: list[str] = field(default_factory=list)
    mcp_servers: list[dict] = field(default_factory=list)
    event_count: int = 0
    cost_usd: float | None = None
    events: list[dict] = field(default_factory=list)
    thinking_blocks: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """Short one-line summary for the sidebar list."""
        head = self.prompt[:40].replace("\n", " ")
        ts = self.started_at.split("T")[1][:8] if "T" in self.started_at else self.started_at
        icon = {"ok": "✓", "error": "✗", "no_text": "⚠"}.get(self.status, "?")
        return f"{icon} {ts}  {head}"


class RunLogger:
    """Collects events for one chat submission and writes the final record."""

    def __init__(self, prompt: str):
        self.run_id = uuid.uuid4().hex[:8]
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self._t0 = time.time()
        self.prompt = prompt
        self.events: list[dict] = []
        self.tool_calls: list[str] = []
        self.mcp_servers: list[dict] = []
        self.cost_usd: float | None = None

    def record_event(self, event: dict) -> None:
        """Callback for claude_runner's on_event hook."""
        self.events.append(event)
        etype = event.get("type")

        if etype == "system" and event.get("subtype") == "init":
            self.mcp_servers = event.get("mcp_servers") or []

        elif etype == "assistant":
            for block in (event.get("message") or {}).get("content") or []:
                if block.get("type") == "tool_use":
                    name = block.get("name", "tool")
                    self.tool_calls.append(name)

        elif etype == "result":
            self.cost_usd = event.get("total_cost_usd")

    def finalize(
        self,
        response_text: str,
        error: str | None = None,
        thinking_blocks: list[str] | None = None,
    ) -> RunRecord:
        if error:
            status = "error"
        elif response_text.strip():
            status = "ok"
        else:
            status = "no_text"

        record = RunRecord(
            run_id=self.run_id,
            started_at=self.started_at,
            duration_s=round(time.time() - self._t0, 2),
            prompt=self.prompt,
            response_text=response_text,
            status=status,
            error=error,
            tool_calls=self.tool_calls,
            mcp_servers=self.mcp_servers,
            event_count=len(self.events),
            cost_usd=self.cost_usd,
            events=self.events,
            thinking_blocks=list(thinking_blocks or []),
        )

        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record), default=str) + "\n")

        return record


def load_recent(limit: int = 20) -> list[RunRecord]:
    """Read the last `limit` runs from the JSONL log (newest first)."""
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    out: list[RunRecord] = []
    for line in reversed(lines[-limit:]):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            out.append(RunRecord(**data))
        except (json.JSONDecodeError, TypeError):
            continue
    return out
