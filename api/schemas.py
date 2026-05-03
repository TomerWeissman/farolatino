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
    claude_binary: bool


class PersonaPayload(BaseModel):
    content: str


class ChatRequest(BaseModel):
    prompt: str


class RunSummary(BaseModel):
    run_id: str
    started_at: str
    duration_s: float
    prompt: str
    status: str
    cost_usd: float | None = None
    tool_calls: list[str] = []
    summary: str
