"""US-007 Agent swappability — the same chat request must succeed
against any of the supported agent labels (OpenHands, Goose, opencode,
smolagents). The broker accepts the request as long as the model
contains the substring "agent" (case-insensitive); the *upstream*
runtime selection is per-session and orchestrated by the
agent runtime image.
"""

from __future__ import annotations

from typing import Any

import pytest


AGENT_MODELS = [
    "Agent - OpenHands",
    "Agent - Goose",
    "Agent - opencode",
    "Agent - smolagents",
    # Lowercase / spaced variants the front-end may emit.
    "agent-openhands",
    "agent_goose",
]


@pytest.mark.parametrize("model", AGENT_MODELS)
def test_us007_each_agent_label_is_routed(broker_client, auth_headers, monkeypatch, model):
    seen: dict = {}

    async def fake_json(settings: Any, **kwargs: Any) -> dict:
        seen.setdefault("agent_models", []).append(kwargs.get("agent_model"))
        return {"choices": [{"message": {"content": f"hello from {model}"}}]}

    monkeypatch.setattr(
        "app.routers.agent_chat.vllm_client.chat_completion_json", fake_json
    )

    r = broker_client.post(
        "/api/agent/chat",
        headers=auth_headers("alice@gwdg"),
        json={
            "model": model,
            "messages": [{"role": "user", "content": "swap-test"}],
            "stream": False,
        },
    )
    assert r.status_code == 200, (model, r.text)
    assert seen["agent_models"][-1] == model


def test_us007_switching_agents_in_one_session_works(broker_client, auth_headers, monkeypatch):
    """User picks OpenHands, sends a turn, switches to Goose, sends
    another turn — both succeed and the broker forwards each request
    with the agent label intact.
    """
    seen: list = []

    async def fake_json(settings: Any, **kwargs: Any) -> dict:
        seen.append(kwargs.get("agent_model"))
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(
        "app.routers.agent_chat.vllm_client.chat_completion_json", fake_json
    )

    for model in ("Agent - OpenHands", "Agent - Goose", "Agent - opencode"):
        r = broker_client.post(
            "/api/agent/chat",
            headers=auth_headers("alice@gwdg"),
            json={
                "model": model,
                "messages": [{"role": "user", "content": "k"}],
                "stream": False,
            },
        )
        assert r.status_code == 200, (model, r.text)

    assert seen == ["Agent - OpenHands", "Agent - Goose", "Agent - opencode"]
