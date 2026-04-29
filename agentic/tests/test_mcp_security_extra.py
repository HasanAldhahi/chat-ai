"""Task 2.5: hostname blocklist and configurable Slurm proxy defaults."""

from __future__ import annotations

import logging

import httpx
import pytest

import mcp_server.config as cfg
from app.clients.slurm import SlurmClient
from app.config import Settings
from app.models.job import JobSubmissionRequest
from mcp_server.errors import ToolError, ToolErrorCode
from mcp_server.security import hostname_blocked
from mcp_server.tools import web as web_tools


@pytest.fixture
def mcp_stub_settings(monkeypatch):
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


def test_hostname_blocked_exact_and_subdomain():
    patterns = ["internal.gwdg.de", ".internal"]
    assert hostname_blocked("internal.gwdg.de", patterns)
    assert hostname_blocked("foo.internal.gwdg.de", patterns)
    assert hostname_blocked("x.internal", patterns)
    assert hostname_blocked("internal", patterns)
    assert not hostname_blocked("example.com", patterns)
    assert not hostname_blocked("www.gwdg.de", patterns)


@pytest.fixture
def empty_blocklist_settings(monkeypatch):
    settings = cfg.MCPSettings(
        web_search_provider="stub",
        web_blocked_host_suffixes=[],
        web_max_response_bytes=1024,
    )
    orig = cfg.get_settings
    cfg.get_settings = lambda: settings  # type: ignore[assignment]
    try:
        yield
    finally:
        cfg.get_settings = orig


async def test_web_browse_allows_internal_host_when_blocklist_empty(
    empty_blocklist_settings, monkeypatch
):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    transport = httpx.MockTransport(handler)

    async def fake_client(timeout_s: float):
        return httpx.AsyncClient(transport=transport, timeout=timeout_s)

    monkeypatch.setattr(web_tools, "_client", fake_client)
    res = await web_tools.web_browse({"url": "http://internal.gwdg.de/"})
    assert res["status_code"] == 200


async def test_web_browse_blocks_internal_gwdg_hostname(mcp_stub_settings):
    with pytest.raises(ToolError) as ei:
        await web_tools.web_browse({"url": "https://internal.gwdg.de/path"})
    assert ei.value.code == ToolErrorCode.URL_BLOCKED


async def test_web_browse_blocks_private_class_b_and_c(mcp_stub_settings):
    for url in ("http://172.16.0.1/", "http://192.168.0.1/"):
        with pytest.raises(ToolError) as ei:
            await web_tools.web_browse({"url": url})
        assert ei.value.code == ToolErrorCode.URL_BLOCKED


async def test_web_browse_blocked_ip_emits_log(caplog, mcp_stub_settings):
    caplog.set_level(logging.WARNING, logger="mcp_server.security")
    with pytest.raises(ToolError):
        await web_tools.web_browse({"url": "http://10.0.0.1/"})
    assert any(
        getattr(r, "msg", None) == "mcp_url_blocked" or "mcp_url_blocked" in r.getMessage()
        for r in caplog.records
    )


def test_slurm_payload_respects_cluster_proxy_settings():
    s = Settings(
        cluster_http_proxy="http://proxy.example:8888",
        cluster_https_proxy="http://proxy.example:8888",
        cluster_no_proxy="localhost,api.internal",
    )
    transport = httpx.MockTransport(lambda r: httpx.Response(404))
    http = httpx.AsyncClient(transport=transport, base_url="http://slurm.test")
    client = SlurmClient(s, http_client=http)
    payload = client._build_payload(
        JobSubmissionRequest(session_id="s1", container_image="/x.sif")
    )
    env = {
        p.split("=", 1)[0]: p.split("=", 1)[1]
        for p in payload["job"]["environment"]
    }
    assert env["HTTP_PROXY"] == "http://proxy.example:8888"
    assert env["HTTPS_PROXY"] == "http://proxy.example:8888"
    assert env["NO_PROXY"] == "localhost,api.internal"