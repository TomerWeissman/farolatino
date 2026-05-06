"""LLM provider abstraction.

Phase 1 ships only the Anthropic adapter. Phases 2+ add OpenAI + Gemini
behind the same `LLMProvider` interface, with auto-detection driven by
which API key is set.
"""
from __future__ import annotations

import os

from core.llm.anthropic_provider import AnthropicProvider
from core.llm.base import AgentEvent, LLMProvider

__all__ = ["AgentEvent", "LLMProvider", "get_provider", "detect_provider_name"]


def detect_provider_name() -> str:
    """Return the active provider name based on env (`anthropic` for Phase 1).

    Precedence: explicit `LLM_PROVIDER` > whichever provider key is set.
    Phase 1 only knows Anthropic; if no key is set we still return
    ``"anthropic"`` so the runner can surface a clean auth-error message
    instead of a cryptic dispatch failure.
    """
    explicit = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    if explicit:
        return explicit
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    # OpenAI / Gemini keys land here too; treated as "no Anthropic key" in
    # Phase 1, which makes /api/health return llm_provider: "none".
    return "none"


def get_provider() -> LLMProvider:
    """Return the active provider instance. Anthropic-only for Phase 1.

    Future phases dispatch on `detect_provider_name()` to pick between
    Anthropic / OpenAI / Gemini. We always instantiate Anthropic here so
    `chat` keeps working as long as `ANTHROPIC_API_KEY` is set, even if
    `LLM_PROVIDER` is set to a not-yet-supported value.
    """
    return AnthropicProvider()
