"""LLM provider abstraction.

Phase 2 ships Anthropic + OpenAI + Gemini behind one ``LLMProvider``
interface. The active provider is auto-detected from whichever API
key is set; ``LLM_PROVIDER`` overrides the auto-pick. See
``core.llm.provider_registry`` for the precedence rules.
"""
from __future__ import annotations

from core.llm.base import AgentEvent, LLMProvider
from core.llm.provider_registry import (
    KNOWN_PROVIDERS,
    NoLLMProviderError,
    ProviderCapabilities,
    capabilities_for,
    detect_provider_name,
    get_provider,
    reset_provider_cache,
)

__all__ = [
    "AgentEvent",
    "LLMProvider",
    "KNOWN_PROVIDERS",
    "NoLLMProviderError",
    "ProviderCapabilities",
    "capabilities_for",
    "detect_provider_name",
    "get_provider",
    "reset_provider_cache",
]
