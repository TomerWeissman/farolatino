"""Tests for the web-search mode resolver in core.agent_runner.

Verifies the decision matrix:
  - profile.web_search_mode == 'off'        → 'off'
  - mode 'on' + healthy Tavily              → 'tavily'
  - mode 'on' + unhealthy/missing Tavily    → 'native'
  - mode 'on' + OpenAI unsupported model    → 'off'
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from core.agent_runner import (
    _DEFAULT_TOOL_NAMES,
    _resolve_skill_profile,
    _resolve_web_search_mode,
)
from core.connectors import ConnectionStatusInfo


def _no_tavily(slug):
    return None


def _ok_tavily(slug):
    class _F:
        def status(self):
            return ConnectionStatusInfo(status="ok", detail="x")
    return _F() if slug == "tavily" else None


def _bad_tavily(slug):
    class _F:
        def status(self):
            return ConnectionStatusInfo(status="auth_failed", detail="x")
    return _F() if slug == "tavily" else None


def test_off_profile_returns_off():
    profile = {"web_search_mode": "off"}
    with patch("core.connectors.get_connector", _ok_tavily):
        assert _resolve_web_search_mode(profile, "anthropic") == "off"


def test_default_profile_with_tavily_returns_tavily():
    profile = _resolve_skill_profile("tell me about bad bunny")
    assert profile["web_search_mode"] == "on"
    with patch("core.connectors.get_connector", _ok_tavily):
        assert _resolve_web_search_mode(profile, "anthropic") == "tavily"


def test_default_profile_without_tavily_returns_native():
    profile = _resolve_skill_profile("tell me about bad bunny")
    with patch("core.connectors.get_connector", _no_tavily):
        assert _resolve_web_search_mode(profile, "anthropic") == "native"


def test_default_profile_with_unhealthy_tavily_returns_native():
    profile = _resolve_skill_profile("tell me about bad bunny")
    with patch("core.connectors.get_connector", _bad_tavily):
        assert _resolve_web_search_mode(profile, "gemini") == "native"


def test_evaluate_skill_returns_off():
    profile = _resolve_skill_profile("@evaluate Bad Bunny")
    assert profile["web_search_mode"] == "off"
    with patch("core.connectors.get_connector", _ok_tavily):
        assert _resolve_web_search_mode(profile, "anthropic") == "off"


def test_similar_skill_returns_off():
    profile = _resolve_skill_profile("@similar Bad Bunny")
    assert profile["web_search_mode"] == "off"
    with patch("core.connectors.get_connector", _ok_tavily):
        assert _resolve_web_search_mode(profile, "anthropic") == "off"


def test_openai_unsupported_model_returns_off_when_no_tavily(monkeypatch):
    profile = _resolve_skill_profile("tell me about an artist")
    monkeypatch.setenv("FAROAI_OPENAI_MODEL", "gpt-3.5-turbo")
    with patch("core.connectors.get_connector", _no_tavily):
        assert _resolve_web_search_mode(profile, "openai") == "off"


def test_openai_supported_model_returns_native_when_no_tavily(monkeypatch):
    profile = _resolve_skill_profile("tell me about an artist")
    monkeypatch.setenv("FAROAI_OPENAI_MODEL", "gpt-4o")
    with patch("core.connectors.get_connector", _no_tavily):
        assert _resolve_web_search_mode(profile, "openai") == "native"


def test_openai_unsupported_model_still_uses_tavily_when_available(monkeypatch):
    profile = _resolve_skill_profile("tell me about an artist")
    monkeypatch.setenv("FAROAI_OPENAI_MODEL", "gpt-3.5-turbo")
    with patch("core.connectors.get_connector", _ok_tavily):
        assert _resolve_web_search_mode(profile, "openai") == "tavily"


def test_web_search_in_default_allowlist():
    assert "web_search" in _DEFAULT_TOOL_NAMES


def test_evaluate_profile_excludes_web_search():
    profile = _resolve_skill_profile("@evaluate x")
    assert "web_search" not in profile["tools"]


def test_similar_profile_excludes_web_search():
    profile = _resolve_skill_profile("@similar x")
    assert "web_search" not in profile["tools"]
