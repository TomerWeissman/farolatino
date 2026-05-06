"""Pydantic response models for the API. Kept thin — most data flows
through as plain dicts (the run-log records, dossier output, etc.).
"""
from __future__ import annotations

from pydantic import BaseModel


class SkillSummary(BaseModel):
    slug: str
    name: str
    description: str


class SkillDetail(BaseModel):
    slug: str
    name: str
    description: str
    body: str  # raw markdown (without frontmatter)
    full_markdown: str  # frontmatter + body, what gets written to disk


class SkillUpdate(BaseModel):
    """Body for PUT /api/skills/{slug}. We accept the full markdown
    (including frontmatter) so the user can edit name/description without
    a separate roundtrip."""
    full_markdown: str


class SkillCreate(BaseModel):
    slug: str
    name: str
    description: str
    body: str = ""  # optional starter body; we add a default if empty


class HealthStatus(BaseModel):
    chartmetric: str  # "ok" | "missing_creds" | "auth_failed" | "error"
    chartmetric_detail: str | None = None
    # Active LLM provider — "anthropic" | "openai" | "gemini" | "none".
    # V1 surfaced `claude_binary: bool` (whether the CLI was on PATH);
    # V2 reports the provider keyed off env so the Connections page can
    # show the right pill regardless of which SDK is in use.
    llm_provider: str


class PersonaPayload(BaseModel):
    content: str


class ChatMessage(BaseModel):
    """One prior conversation turn the frontend replays for context.

    V1 used Claude Code's `--resume <session_id>` to keep multi-turn
    state in the CLI. V2 has no CLI, so the frontend ships its
    localStorage-cached turns on every request and the backend rebuilds
    the message stack each call.
    """

    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    prompt: str
    # V1 multi-turn handle — kept for backward compat with cached
    # frontend bundles. The V2 runner ignores it; replaced by `messages`.
    resume_session_id: str | None = None
    # Prior turns the backend replays into the agent loop. Empty / absent
    # is treated as a fresh single-turn chat.
    messages: list[ChatMessage] | None = None


class RunSummary(BaseModel):
    run_id: str
    started_at: str
    duration_s: float
    prompt: str
    status: str
    cost_usd: float | None = None
    tool_calls: list[str] = []
    summary: str
