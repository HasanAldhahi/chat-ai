"""US-001 Agent selection — selecting an agent model in the dropdown
routes the request through the broker's agent path (not the standard
chat path).

The user-facing routing decision is enforced by the broker on
``POST /api/agent/chat``: ``model`` must contain the substring "agent"
(case-insensitive) — see ``app.routers.agent_chat``. This test exercises
the same handler the Node proxy forwards to.
"""

from __future__ import annotations

from typing import Any


def test_us001_agent_model_routes_to_broker(broker_client, auth_headers, monkeypatch):
    """An "Agent - OpenHands" request reaches vLLM via the broker.

    We patch ``vllm_client.chat_completion_json`` so the test does not
    depend on a running vLLM. Success is the broker accepting the
    request (200) and forwarding it; the body is a plain JSON echo of
    the patched return value.
    """
    captured: dict = {}

    async def fake_json(settings: Any, **kwargs: Any) -> dict:
        captured["agent_model"] = kwargs.get("agent_model")
        captured["messages"] = kwargs.get("messages")
        return {
            "id": "stub-1",
            "choices": [{"message": {"role": "assistant", "content": "hi"}}],
        }

    monkeypatch.setattr(
        "app.routers.agent_chat.vllm_client.chat_completion_json", fake_json
    )

    r = broker_client.post(
        "/api/agent/chat",
        headers=auth_headers("alice@gwdg"),
        json={
            "model": "Agent - OpenHands",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["choices"][0]["message"]["content"] == "hi"
    assert captured["agent_model"] == "Agent - OpenHands"
    assert captured["messages"][0]["content"] == "hi"


def test_us001_non_agent_model_rejected_by_broker(broker_client, auth_headers):
    """A non-agent model on the agent endpoint is a misroute — broker
    must reject with 400 so the Node proxy's agent-detection logic
    cannot accidentally forward standard chat traffic here.
    """
    r = broker_client.post(
        "/api/agent/chat",
        headers=auth_headers(),
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        },
    )
    assert r.status_code == 400


def test_us001_agent_endpoint_requires_x_user(broker_client):
    """No X-User → 401 from auth middleware before vLLM is ever called."""
    r = broker_client.post(
        "/api/agent/chat",
        json={
            "model": "Agent - OpenHands",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        },
    )
    assert r.status_code == 401


def test_us001_empty_messages_returns_422(broker_client, auth_headers):
    """The dropdown can choose an agent, but sending an empty thread is
    not a valid agent request — the broker surfaces 422 (input invalid)
    rather than letting vLLM see it.
    """
    r = broker_client.post(
        "/api/agent/chat",
        headers=auth_headers(),
        json={
            "model": "Agent - OpenHands",
            "messages": [],
            "stream": False,
        },
    )
    assert r.status_code == 422
