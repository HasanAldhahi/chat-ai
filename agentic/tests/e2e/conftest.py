"""Shared fixtures for the Phase 5 / Task 5.2 E2E suite.

The principle: build the broker exactly the way ``app.main.create_app``
builds it in production, with Slurm + Vault + vLLM swapped for in-process
doubles so the suite runs without an HPC cluster. MCP server + skill
loader run unchanged — those paths execute the real handlers.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

import mcp_server.config as mcp_cfg
from app.clients.vault import VaultClient
from app.config import Settings
from app.dependencies import get_settings
from app.main import create_app
from mcp_server.main import create_app as create_mcp_app


def pytest_collection_modifyitems(config, items):  # noqa: D401
    """Tag every test in this package with ``@pytest.mark.e2e``."""
    e2e = pytest.mark.e2e
    for item in items:
        if "/tests/e2e/" in str(item.fspath).replace("\\", "/"):
            item.add_marker(e2e)


# --------------------------------------------------------------------------- #
# Broker app — Slurm + Vault in mock mode, vLLM URL set so /api/agent/chat   #
# accepts the request (the actual upstream call is mocked per test).         #
# --------------------------------------------------------------------------- #


def _broker_settings(**overrides: Any) -> Settings:
    base: Dict[str, Any] = dict(
        slurm_mock_mode=True,
        vault_mock_mode=True,
        slurm_status_poll_interval_s=10.0,
        slurm_status_cache_ttl_s=10.0,
        slurm_cancel_grace_period_s=0.0,
        auth_rate_per_user=1000,
        sse_publish_rate_per_session=1000,
        sse_heartbeat_interval_s=10.0,
        sse_session_idle_timeout_s=300.0,
        sse_reaper_interval_s=60.0,
        vllm_base_url="http://vllm.test",
        vllm_chat_path="/v1/chat/completions",
        vllm_model="qwen3-30b",
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def broker_settings() -> Settings:
    return _broker_settings()


@pytest.fixture
def broker_client(broker_settings) -> Iterator[TestClient]:
    """Wired-up FastAPI broker with mock Slurm + mock Vault."""
    app = create_app(broker_settings)
    app.dependency_overrides[get_settings] = lambda: broker_settings
    with TestClient(app) as client:
        yield client


@pytest.fixture
def make_broker_client():
    """Builder for tests that need bespoke broker settings."""

    def _build(**overrides: Any) -> TestClient:
        s = _broker_settings(**overrides)
        app = create_app(s)
        app.dependency_overrides[get_settings] = lambda: s
        return TestClient(app)

    return _build


# --------------------------------------------------------------------------- #
# Vault (real httpx.MockTransport) — used by US-006 to verify per-user path. #
# --------------------------------------------------------------------------- #


@pytest.fixture
def vault_handler():
    """Default Vault handler — return a deterministic secret payload.

    Tests that need to introspect requested URLs override this by
    using ``broker_client_with_vault`` and supplying a custom handler.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "request_id": "abc",
                "lease_duration": 1800,
                "data": {
                    "data": {"search_api_key": "sk-stub-secret"},
                    "metadata": {"version": 1},
                },
            },
        )

    return handler


@pytest.fixture
def make_broker_client_with_vault():
    """Builder that injects a real VaultClient backed by ``httpx.MockTransport``.

    Use when a test needs Vault path scoping or audit-style assertions
    (US-006). Returns ``(client, captured_calls)`` where ``captured_calls``
    is a list the wrapping handler appends to.
    """

    def _build(handler):
        s = _broker_settings(
            vault_mock_mode=False,
            vault_base_url="http://vault.test",
            vault_token="root-token",
            vault_kv_mount="kv",
            vault_max_retries=0,
            vault_retry_backoff_s=0.0,
            vault_cache_ttl_s=60.0,
        )
        captured: list = []

        def wrapped(request: httpx.Request) -> httpx.Response:
            captured.append(str(request.url))
            return handler(request)

        app = create_app(s)
        app.dependency_overrides[get_settings] = lambda: s
        transport = httpx.MockTransport(wrapped)
        http = httpx.AsyncClient(transport=transport, base_url=s.vault_base_url)
        app.state.vault_client = VaultClient(s, http_client=http)
        return TestClient(app), captured

    return _build


# --------------------------------------------------------------------------- #
# MCP app — exposes /rpc; we hammer it directly to exercise tool flows.      #
# --------------------------------------------------------------------------- #


@pytest.fixture
def mcp_settings(tmp_path) -> Iterator[mcp_cfg.MCPSettings]:
    """Sandbox MCP for the E2E suite — fs roots locked to tmp_path."""
    settings = mcp_cfg.MCPSettings(
        fs_read_roots=[str(tmp_path)],
        fs_write_roots=[str(tmp_path)],
        fs_max_read_bytes=64 * 1024,
        fs_max_write_bytes=4 * 1024,
        web_search_provider="stub",
        web_blocked_host_suffixes=["internal.gwdg.de", ".internal", ".local"],
        web_max_response_bytes=8 * 1024,
        skills_dir=str(tmp_path / "skills_void"),
    )
    original = mcp_cfg.get_settings
    mcp_cfg.get_settings = lambda: settings  # type: ignore[assignment]
    try:
        yield settings
    finally:
        mcp_cfg.get_settings = original


@pytest.fixture
def mcp_client(mcp_settings) -> Iterator[TestClient]:
    """MCP /rpc TestClient with the locked-down settings above."""
    app = create_mcp_app(mcp_settings)
    with TestClient(app) as client:
        yield client


# --------------------------------------------------------------------------- #
# Auth headers helper                                                         #
# --------------------------------------------------------------------------- #


@pytest.fixture
def auth_headers():
    def _hdr(user: str = "alice@gwdg") -> Dict[str, str]:
        return {
            "Authorization": "Bearer test-token",
            "X-User": user,
            "Content-Type": "application/json",
        }

    return _hdr
