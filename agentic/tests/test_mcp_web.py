"""Tests for the MCP web_* tools (Task 2.2).

Network is mocked at the httpx layer with ``MockTransport`` — same
pattern the broker tests use. The web tools build their own
``httpx.AsyncClient`` so the mock has to be installed by patching
the ``_client`` factory in ``mcp_server.tools.web``.
"""

from __future__ import annotations

from typing import Callable, Iterator

import httpx
import pytest

import mcp_server.config as cfg
from mcp_server.errors import ToolError, ToolErrorCode
from mcp_server.tools import web as web_tools


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _install_mock_transport(monkeypatch, handler: Callable[[httpx.Request], httpx.Response]):
    transport = httpx.MockTransport(handler)

    async def fake_client(timeout_s: float):
        return httpx.AsyncClient(transport=transport, timeout=timeout_s)

    monkeypatch.setattr(web_tools, "_client", fake_client)


@pytest.fixture
def stub_settings(monkeypatch) -> Iterator[None]:
    settings = cfg.MCPSettings(
        web_search_provider="stub",
        web_search_api_key="",
        web_max_response_bytes=1024,
    )
    original = cfg.get_settings
    cfg.get_settings = lambda: settings  # type: ignore[assignment]
    try:
        yield
    finally:
        cfg.get_settings = original


@pytest.fixture
def serpapi_settings(monkeypatch) -> Iterator[None]:
    settings = cfg.MCPSettings(
        web_search_provider="serpapi",
        web_search_api_key="key-abc",
        web_search_endpoint="https://serpapi.test/search.json",
        web_max_response_bytes=1024,
    )
    original = cfg.get_settings
    cfg.get_settings = lambda: settings  # type: ignore[assignment]
    try:
        yield
    finally:
        cfg.get_settings = original


# --------------------------------------------------------------------------- #
# web_search                                                                  #
# --------------------------------------------------------------------------- #

async def test_web_search_stub_returns_deterministic_results(stub_settings):
    res = await web_tools.web_search({"query": "lhc", "num_results": 3})
    assert res["provider"] == "stub"
    assert len(res["results"]) == 3
    assert all("lhc" in r["title"] for r in res["results"])


async def test_web_search_rejects_empty_query(stub_settings):
    with pytest.raises(ToolError) as ei:
        await web_tools.web_search({"query": "  "})
    assert ei.value.code == ToolErrorCode.INVALID_PARAMS


async def test_web_search_num_results_bounds(stub_settings):
    with pytest.raises(ToolError):
        await web_tools.web_search({"query": "x", "num_results": 0})
    with pytest.raises(ToolError):
        await web_tools.web_search({"query": "x", "num_results": 51})


async def test_web_search_serpapi_translates_response(serpapi_settings, monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "organic_results": [
                    {"title": "T1", "link": "https://a.example", "snippet": "S1"},
                    {"title": "T2", "link": "https://b.example", "snippet": "S2"},
                ]
            },
        )

    _install_mock_transport(monkeypatch, handler)
    res = await web_tools.web_search({"query": "quantum", "num_results": 5})
    assert res["provider"] == "serpapi"
    assert len(res["results"]) == 2
    assert res["results"][0] == {
        "title": "T1",
        "url": "https://a.example",
        "snippet": "S1",
    }
    # API key is forwarded but never echoed back in the result body.
    assert "api_key=key-abc" in captured["url"]


async def test_web_search_serpapi_no_api_key_errors(monkeypatch):
    settings = cfg.MCPSettings(web_search_provider="serpapi", web_search_api_key="")
    original = cfg.get_settings
    cfg.get_settings = lambda: settings  # type: ignore[assignment]
    try:
        with pytest.raises(ToolError) as ei:
            await web_tools.web_search({"query": "x"})
    finally:
        cfg.get_settings = original
    assert ei.value.code == ToolErrorCode.SEARCH_PROVIDER_UNAVAILABLE


async def test_web_search_serpapi_http_error(serpapi_settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream down")

    _install_mock_transport(monkeypatch, handler)
    with pytest.raises(ToolError) as ei:
        await web_tools.web_search({"query": "x"})
    assert ei.value.code == ToolErrorCode.NETWORK_ERROR


# --------------------------------------------------------------------------- #
# web_browse                                                                  #
# --------------------------------------------------------------------------- #

async def test_web_browse_happy_path(stub_settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="<html>hi</html>",
            headers={"content-type": "text/html; charset=utf-8"},
        )

    _install_mock_transport(monkeypatch, handler)
    res = await web_tools.web_browse({"url": "https://example.com"})
    assert res["status_code"] == 200
    assert "hi" in res["text"]
    assert "text/html" in res["content_type"]
    assert res["truncated"] is False


async def test_web_browse_truncates_large_response(stub_settings, monkeypatch):
    big_body = "x" * 5000

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=big_body)

    _install_mock_transport(monkeypatch, handler)
    res = await web_tools.web_browse({"url": "https://example.com"})
    assert res["truncated"] is True
    assert len(res["text"]) <= 1024


async def test_web_browse_blocks_loopback_ip(stub_settings):
    with pytest.raises(ToolError) as ei:
        await web_tools.web_browse({"url": "http://127.0.0.1/"})
    assert ei.value.code == ToolErrorCode.URL_BLOCKED


async def test_web_browse_blocks_private_ip(stub_settings):
    with pytest.raises(ToolError) as ei:
        await web_tools.web_browse({"url": "http://10.0.0.1/admin"})
    assert ei.value.code == ToolErrorCode.URL_BLOCKED


async def test_web_browse_blocks_link_local(stub_settings):
    with pytest.raises(ToolError) as ei:
        await web_tools.web_browse({"url": "http://169.254.169.254/latest"})
    assert ei.value.code == ToolErrorCode.URL_BLOCKED


async def test_web_browse_blocks_ipv6_loopback(stub_settings):
    with pytest.raises(ToolError) as ei:
        await web_tools.web_browse({"url": "http://[::1]/"})
    assert ei.value.code == ToolErrorCode.URL_BLOCKED


async def test_web_browse_rejects_non_http_scheme(stub_settings):
    with pytest.raises(ToolError) as ei:
        await web_tools.web_browse({"url": "file:///etc/passwd"})
    assert ei.value.code == ToolErrorCode.SCHEME_NOT_ALLOWED


async def test_web_browse_rejects_empty_url(stub_settings):
    with pytest.raises(ToolError) as ei:
        await web_tools.web_browse({"url": ""})
    assert ei.value.code == ToolErrorCode.URL_INVALID


async def test_web_browse_network_error(stub_settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    _install_mock_transport(monkeypatch, handler)
    with pytest.raises(ToolError) as ei:
        await web_tools.web_browse({"url": "https://example.com"})
    assert ei.value.code == ToolErrorCode.NETWORK_ERROR
