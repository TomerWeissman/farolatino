"""Pick the active LLM provider from one paste-anywhere API key.

UX: the user pastes a single key into the ``LLM_API_KEY`` field on the
Connections page. The provider is auto-detected from the key's prefix:

  - ``sk-ant-`` → Anthropic (Claude)
  - ``sk-`` / ``sk-proj-`` → OpenAI (GPT)
  - ``AIza`` → Google (Gemini)

No drop-down, no override — pick the model by pasting the matching
key. Backward compat: if ``LLM_API_KEY`` is empty but one of the
legacy V1/Phase-2 per-provider env vars (``ANTHROPIC_API_KEY``,
``OPENAI_API_KEY``, ``GEMINI_API_KEY``) is set, we fall through to it
so existing local installs keep working without a manual migration.

Capabilities (per-provider feature flags) are advisory metadata the
runner + frontend use to gate provider-specific behavior — e.g. the
Reasoning panel auto-hides when ``thinking == False``. They are NOT
part of the LLMProvider protocol so a future capability change doesn't
ripple through every adapter.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from core.llm.base import LLMProvider

log = logging.getLogger(__name__)

KNOWN_PROVIDERS = ("anthropic", "openai", "gemini")

# Legacy env vars (kept for backward compat with Phase 2 + V1 .env files).
# Read-only fallbacks; new writes always go to LLM_API_KEY.
_LEGACY_ENV: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


@dataclass(frozen=True)
class ProviderCapabilities:
    """What a provider can / can't do under our V2 wiring.

    - ``thinking``: yields extended-thinking deltas the UI surfaces in
      the Reasoning panel. Anthropic only. (OpenAI's reasoning items
      gate to o-series models; Gemini's thinking mode is gated. We
      treat both as off for now and revisit when the SDKs stabilise.)
    - ``parallel_tools``: provider runs multiple tool calls per turn
      in parallel. We disable for OpenAI (Chartmetric's 1.05 req/s
      lock would still serialise them but token cost spikes).
    """

    thinking: bool
    parallel_tools: bool


_CAPABILITIES: dict[str, ProviderCapabilities] = {
    "anthropic": ProviderCapabilities(thinking=True, parallel_tools=True),
    "openai": ProviderCapabilities(thinking=False, parallel_tools=False),
    "gemini": ProviderCapabilities(thinking=False, parallel_tools=False),
    "none": ProviderCapabilities(thinking=False, parallel_tools=False),
}


def sniff_provider(key: str | None) -> str | None:
    """Identify the provider for an API key by its prefix.

    Returns ``"anthropic" | "openai" | "gemini" | None``. Anthropic
    keys start with ``sk-ant-``; OpenAI's regular keys start with
    ``sk-`` (note: ``sk-proj-`` is also OpenAI); Gemini's API keys all
    start with ``AIza``. Whitespace is trimmed. The check has to be
    Anthropic-first since their keys *also* start with ``sk-``.
    """
    if not key:
        return None
    k = key.strip()
    if k.startswith("sk-ant-"):
        return "anthropic"
    if k.startswith("sk-"):
        return "openai"
    if k.startswith("AIza"):
        return "gemini"
    return None


def active_api_key() -> str | None:
    """Return the API key currently in play, regardless of which env
    var holds it. Caller passes this to the provider's SDK constructor
    so the SDK doesn't have to know about ``LLM_API_KEY``.

    Resolution order: ``LLM_API_KEY`` first; then legacy per-provider
    keys for backward compat with V1 / Phase 2 ``.env`` files.
    """
    key = os.getenv("LLM_API_KEY")
    if key:
        return key
    for env_var in _LEGACY_ENV.values():
        legacy = os.getenv(env_var)
        if legacy:
            return legacy
    return None


def detect_provider_name() -> str:
    """Return ``"anthropic" | "openai" | "gemini" | "none"``.

    Side-effect-free; safe to call from health/connections endpoints.
    """
    key = os.getenv("LLM_API_KEY")
    if key:
        sniffed = sniff_provider(key)
        if sniffed:
            return sniffed
        log.warning("LLM_API_KEY set but prefix unrecognised; falling through")

    # Backward compat: legacy per-provider env vars from V1 / Phase 2.
    for name, env_var in _LEGACY_ENV.items():
        if os.getenv(env_var):
            return name
    return "none"


def capabilities_for(name: str) -> ProviderCapabilities:
    return _CAPABILITIES.get(name, _CAPABILITIES["none"])


# Cached provider instance. Reset by api/routes/env.py on PUT /api/env
# so a key swap takes effect without a process restart.
_provider_instance: LLMProvider | None = None
_provider_instance_name: str | None = None


def reset_provider_cache() -> None:
    """Drop the cached provider so the next chat re-instantiates with
    the current env. Called from ``api.routes.env._invalidate_caches``
    after a key edit."""
    global _provider_instance, _provider_instance_name
    _provider_instance = None
    _provider_instance_name = None


class NoLLMProviderError(RuntimeError):
    """No usable LLM provider key found in env. Caller surfaces this
    to the chat as a clean SSE error so the user knows to paste a key
    in Connections."""


def get_provider() -> LLMProvider:
    """Build (and cache) the active provider instance.

    Each provider's constructor reads its API key from env at instance
    time; the instance is reused across chat turns until env changes
    invalidate the cache. Raises ``NoLLMProviderError`` when no key is
    set so the runner can surface a clean error to the user without
    triggering an SDK-level AttributeError.
    """
    global _provider_instance, _provider_instance_name
    name = detect_provider_name()
    if name == "none":
        raise NoLLMProviderError(
            "No LLM provider key set. Open Connections in the sidebar to "
            "paste an Anthropic, OpenAI, or Gemini API key."
        )
    if _provider_instance is not None and _provider_instance_name == name:
        return _provider_instance

    api_key = active_api_key()
    if api_key is None:
        raise NoLLMProviderError("No API key resolved for active provider")

    if name == "anthropic":
        from core.llm.anthropic_provider import AnthropicProvider
        _provider_instance = AnthropicProvider(api_key=api_key)
    elif name == "openai":
        from core.llm.openai_provider import OpenAIProvider
        _provider_instance = OpenAIProvider(api_key=api_key)
    elif name == "gemini":
        from core.llm.gemini_provider import GeminiProvider
        _provider_instance = GeminiProvider(api_key=api_key)
    else:
        raise NoLLMProviderError(f"Unknown provider: {name}")

    _provider_instance_name = name
    return _provider_instance
