"""Pydantic response models for the API. Kept thin — most data flows
through as plain dicts (the run-log records, dossier output, etc.).
"""
from __future__ import annotations

from pydantic import BaseModel


class SkillSummary(BaseModel):
    slug: str
    name: str
    description: str


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
