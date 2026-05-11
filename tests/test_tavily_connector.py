"""Tests for the Tavily web-search connector."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from core.connectors import get_connector
from core.connectors.tavily import TavilyConnector, web_search


@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)


@pytest.fixture
def good_key(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-fake-1234567890")


@pytest.fixture
def bad_prefix(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "not-a-tavily-key")


def test_connector_registered():
    """Importing core.connectors registers Tavily under slug 'tavily'."""
    conn = get_connector("tavily")
    assert conn is not None
    assert conn.slug == "tavily"
    assert "TAVILY_API_KEY" in conn.env_vars


def test_status_missing_creds(no_key):
    info = TavilyConnector().status()
    assert info.status == "missing_creds"
    assert "tavily.com" in (info.detail or "").lower()


def test_status_ok_with_prefix(good_key):
    info = TavilyConnector().status()
    assert info.status == "ok"


def test_status_auth_failed_on_bad_prefix(bad_prefix):
    info = TavilyConnector().status()
    assert info.status == "auth_failed"
    assert "tvly-" in (info.detail or "")


def test_web_search_returns_error_without_key(no_key):
    out = web_search("anything")
    assert "error" in out
    assert "TAVILY_API_KEY" in out["error"]


def test_web_search_happy_path(good_key):
    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "results": [
            {"title": "T1", "url": "https://example.com/1", "content": "snippet 1"},
            {"title": "T2", "url": "https://example.com/2", "content": "snippet 2"},
        ]
    }
    with patch("core.connectors.tavily.httpx.post", return_value=fake_response) as post:
        out = web_search("bad bunny new label", max_results=3)
    # Verify request shape
    args, kwargs = post.call_args
    assert args[0] == "https://api.tavily.com/search"
    sent = kwargs.get("json") or {}
    assert sent.get("query") == "bad bunny new label"
    assert sent.get("max_results") == 3
    assert sent.get("api_key") == "tvly-fake-1234567890"
    # Verify result shape
    assert out["query"] == "bad bunny new label"
    assert len(out["results"]) == 2
    assert out["results"][0]["url"] == "https://example.com/1"
    assert out["results"][0]["title"] == "T1"


def test_web_search_max_results_capped(good_key):
    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 200
    fake_response.json.return_value = {"results": []}
    with patch("core.connectors.tavily.httpx.post", return_value=fake_response) as post:
        web_search("query", max_results=999)
    sent = post.call_args.kwargs["json"]
    assert sent["max_results"] == 10  # capped at 10


def test_web_search_max_results_zero_falls_back_to_default(good_key):
    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 200
    fake_response.json.return_value = {"results": []}
    with patch("core.connectors.tavily.httpx.post", return_value=fake_response) as post:
        web_search("query", max_results=0)
    sent = post.call_args.kwargs["json"]
    # 0 is falsy → treated as "use default", not as "zero results"
    assert sent["max_results"] == 5


def test_web_search_max_results_negative_floored_to_one(good_key):
    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 200
    fake_response.json.return_value = {"results": []}
    with patch("core.connectors.tavily.httpx.post", return_value=fake_response) as post:
        web_search("query", max_results=-3)
    sent = post.call_args.kwargs["json"]
    assert sent["max_results"] == 1  # negative floored at 1


def test_web_search_auth_failure(good_key):
    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 401
    fake_response.text = "Unauthorized"
    with patch("core.connectors.tavily.httpx.post", return_value=fake_response):
        out = web_search("query")
    assert "error" in out
    assert "auth" in out["error"].lower()


def test_web_search_quota_exhausted(good_key):
    fake_response = MagicMock(spec=httpx.Response)
    fake_response.status_code = 429
    fake_response.text = "rate-limited"
    with patch("core.connectors.tavily.httpx.post", return_value=fake_response):
        out = web_search("query")
    assert "error" in out
    assert "quota" in out["error"].lower()


def test_web_search_network_error(good_key):
    with patch(
        "core.connectors.tavily.httpx.post",
        side_effect=httpx.ConnectError("nope"),
    ):
        out = web_search("query")
    assert "error" in out
    assert "network" in out["error"].lower()


def test_web_search_in_dispatch_registry():
    """The bare 'web_search' name routes to the Tavily callable."""
    from core.llm.tool_dispatch import get_callable
    fn = get_callable("web_search")
    assert fn is not None
    assert fn is web_search
