"""GET /api/runs — recent chat-run telemetry.

Reads from `data/cache/chat_runs.jsonl` via core.run_log. The summary
endpoint trims `events` and `thinking_blocks` (those can be huge) so
the sidebar list stays small; the detail endpoint returns the whole
record so the UI can render the full event trace + reasoning.
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query

from api.schemas import RunSummary
from core.run_log import load_recent

router = APIRouter()


@router.get("/runs", response_model=list[RunSummary])
def list_runs(limit: int = Query(default=20, ge=1, le=100)) -> list[RunSummary]:
    runs = load_recent(limit=limit)
    return [
        RunSummary(
            run_id=r.run_id,
            started_at=r.started_at,
            duration_s=r.duration_s,
            prompt=r.prompt,
            status=r.status,
            cost_usd=r.cost_usd,
            tool_calls=r.tool_calls,
            summary=r.summary(),
        )
        for r in runs
    ]


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    """Full run record (events, thinking blocks, mcp_servers, …)."""
    # Pull a generous window — the JSONL grows append-only, and we need
    # to find the matching run_id which may not be in the most recent
    # 20. 500 is plenty for normal sessions; if it's not, the user has
    # bigger problems than this lookup.
    for r in load_recent(limit=500):
        if r.run_id == run_id:
            return asdict(r)
    raise HTTPException(status_code=404, detail=f"run_id {run_id} not found")
