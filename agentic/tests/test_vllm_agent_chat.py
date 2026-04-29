"""Tests for vLLM client and agent chat bridge (Tasks 2.6 + 3.1)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
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


def test_agent_chat_rejects_non_agent_model() -> None:
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
    assert r.status_code == 400


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
            "model": "Agent - OpenHands",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        },
    )
    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == "agent-reply"
    assert calls.get("ok")


def test_agent_chat_stream_passthrough(monkeypatch: Any) -> None:
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
            "model": "Agent - OpenHands",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    )
    assert r.status_code == 200
    assert b"data:" in r.content
