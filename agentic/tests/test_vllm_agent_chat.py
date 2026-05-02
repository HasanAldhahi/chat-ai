"""Tests for vLLM client and agent chat bridge (Tasks 2.6 + 3.1 + 6.4)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.dependencies import get_agent_orchestrator, get_local_executor
from app.main import create_app


def _app(settings: Settings) -> TestClient:
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_vllm_health_skips_auth_without_config() -> None:
    s = Settings(auth_middleware_enabled=True)
    client = _app(s)
    r = client.get("/api/vllm/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False


def test_agent_chat_requires_x_user() -> None:
    s = Settings(
        vllm_base_url="http://vllm.test",
        auth_middleware_enabled=True,
    )
    c = _app(s)
    r = c.post(
        "/api/agent/chat",
        json={
            "model": "Agent - OpenHands",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        },
    )
    assert r.status_code == 401


def test_agent_chat_non_agent_model_uses_vllm(monkeypatch: Any) -> None:
    """Non-agent models (e.g. gpt-4) are forwarded to the vLLM passthrough path."""
    async def fake_json(*_: Any, **__: Any) -> dict:
        return {"choices": [{"message": {"content": "plain-reply"}}]}

    monkeypatch.setattr("app.routers.agent_chat.vllm_client.chat_completion_json", fake_json)
    s = Settings(vllm_base_url="http://vllm.test")
    c = _app(s)
    r = c.post(
        "/api/agent/chat",
        headers={"X-User": "a@gwdg"},
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        },
    )
    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == "plain-reply"


@pytest.mark.anyio
async def test_chat_completion_json_with_injected_client() -> None:
    from app.clients import vllm as vmod

    def handler(request: httpx.Request) -> httpx.Response:
        assert "/v1/chat/completions" in str(request.url)
        return httpx.Response(200, json={"id": "1", "choices": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://vllm.x") as ac:
        s = Settings(
            vllm_base_url="http://vllm.x",
            vllm_chat_path="/v1/chat/completions",
            vllm_model="qwen",
        )
        out = await vmod.chat_completion_json(
            s,
            messages=[{"role": "user", "content": "hello"}],
            http_client=ac,
        )
        assert out["id"] == "1"


def test_agent_chat_non_stream_uses_vllm(monkeypatch: Any) -> None:
    """Non-agent model non-stream requests are forwarded to vLLM."""
    calls: dict = {}

    async def fake_json(*args: Any, **kwargs: Any) -> dict:
        calls["ok"] = True
        return {"choices": [{"message": {"content": "agent-reply"}}]}

    monkeypatch.setattr(
        "app.routers.agent_chat.vllm_client.chat_completion_json",
        fake_json,
    )
    s = Settings(vllm_base_url="http://vllm.test")
    c = _app(s)
    r = c.post(
        "/api/agent/chat",
        headers={"X-User": "u@gwdg"},
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        },
    )
    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == "agent-reply"
    assert calls.get("ok")


def test_agent_chat_stream_passthrough(monkeypatch: Any) -> None:
    """Non-agent model streaming requests are forwarded to vLLM as SSE."""
    async def fake_stream(*args: Any, **kwargs: Any):
        yield b"data: {}\n\n"

    monkeypatch.setattr(
        "app.routers.agent_chat.vllm_client.stream_chat_completion",
        fake_stream,
    )
    s = Settings(vllm_base_url="http://vllm.test")
    c = _app(s)
    r = c.post(
        "/api/agent/chat",
        headers={"X-User": "u@gwdg"},
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    )
    assert r.status_code == 200
    assert b"data:" in r.content


def test_agent_chat_agent_model_returns_202() -> None:
    """Agent models (e.g. Agent - OpenHands) return HTTP 202 with job_id/session_id."""
    s = Settings(vllm_base_url="http://vllm.test", execution_mode="local")
    app = create_app(s)
    app.dependency_overrides[get_settings] = lambda: s

    mock_orch = MagicMock()
    mock_orch.ensure_runtime = AsyncMock(
        return_value={"job_id": "local-abc", "session_id": "u-gwdg"}
    )
    app.dependency_overrides[get_agent_orchestrator] = lambda: mock_orch

    mock_exec = MagicMock()
    app.dependency_overrides[get_local_executor] = lambda: mock_exec

    c = TestClient(app)
    r = c.post(
        "/api/agent/chat",
        headers={"X-User": "u@gwdg"},
        json={
            "model": "Agent - OpenHands",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": False,
        },
    )
    assert r.status_code == 202
    body = r.json()
    assert body["job_id"] == "local-abc"
    assert "session_id" in body
    mock_orch.ensure_runtime.assert_awaited_once()


def test_agent_session_cancel_returns_200() -> None:
    """DELETE /api/agent/sessions/{id} cancels the session job (Task 6.5)."""
    s = Settings(vllm_base_url="http://vllm.test", execution_mode="local")
    app = create_app(s)
    app.dependency_overrides[get_settings] = lambda: s

    mock_orch = MagicMock()
    mock_orch.cancel_session = AsyncMock(return_value=None)
    app.dependency_overrides[get_agent_orchestrator] = lambda: mock_orch

    mock_exec = MagicMock()
    app.dependency_overrides[get_local_executor] = lambda: mock_exec

    c = TestClient(app)
    r = c.delete(
        "/api/agent/sessions/mysession",
        headers={"X-User": "u@gwdg"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "mysession"
    assert body["cancelled"] is True
    mock_orch.cancel_session.assert_awaited_once()


def test_agent_session_cancel_requires_x_user() -> None:
    """DELETE /api/agent/sessions/{id} requires X-User header (Task 6.5)."""
    s = Settings(vllm_base_url="http://vllm.test")
    c = _app(s)
    r = c.delete("/api/agent/sessions/mysession")
    assert r.status_code == 401
