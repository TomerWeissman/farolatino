"""Pick the active LLM provider based on env, expose its capabilities.

Detection precedence (first match wins):

  1. ``LLM_PROVIDER`` — explicit override (``"anthropic"``, ``"openai"``,
     ``"gemini"``). Lets a user paste both an Anthropic and an OpenAI
     key but force-pick one of them for a comparison run.
  2. ``ANTHROPIC_API_KEY`` (``sk-ant-`` prefix)
  3. ``OPENAI_API_KEY`` (``sk-`` / ``sk-proj-``)
  4. ``GEMINI_API_KEY`` (``AIza``)

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


def _classify_explicit(name: str) -> str | None:
    """Validate a `LLM_PROVIDER` override; ignore unknowns silently."""
    name = name.strip().lower()
    if name in KNOWN_PROVIDERS:
        return name
    return None


def detect_provider_name() -> str:
    """Return ``"anthropic" | "openai" | "gemini" | "none"``.

    Side-effect-free; safe to call from health/connections endpoints.
    """
    explicit = os.getenv("LLM_PROVIDER")
    if explicit and (picked := _classify_explicit(explicit)):
        # Only honor the override if the *matching* key is also set —
        # otherwise the chat would error on every turn with no way for
        # the user to notice from the sidebar.
        env_var = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}[picked]
        if os.getenv(env_var):
            return picked
        log.warning("LLM_PROVIDER=%s but %s is not set; falling through", picked, env_var)

    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
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

    if name == "anthropic":
        from core.llm.anthropic_provider import AnthropicProvider
        _provider_instance = AnthropicProvider()
    elif name == "openai":
        from core.llm.openai_provider import OpenAIProvider
        _provider_instance = OpenAIProvider()
    elif name == "gemini":
        from core.llm.gemini_provider import GeminiProvider
        _provider_instance = GeminiProvider()
    else:
        raise NoLLMProviderError(f"Unknown provider: {name}")

    _provider_instance_name = name
    return _provider_instance
