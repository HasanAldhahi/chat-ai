"""US-005 Real-time streaming — publish via the SSE HTTP endpoint and
verify the broker hub forwards a wire-format frame with the requested
event/data preserved.

We exercise the hub directly for the streaming consumer side, because
``httpx``'s ``ASGITransport`` (used by FastAPI ``TestClient``) buffers
full responses and would deadlock on a long-lived ``text/event-stream``
endpoint. The HTTP publish path is exercised through the TestClient.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import List

import pytest

from app.config import Settings
from app.models.sse import SseEventName, SsePublishRequest
from app.services.sse_hub import SseHub


@pytest.mark.asyncio
async def test_us005_publish_then_subscribe_delivers_frame():
    settings = Settings(
        sse_heartbeat_interval_s=10.0,
        sse_subscriber_queue_size=64,
        sse_publish_rate_per_session=100,
        sse_session_idle_timeout_s=300.0,
        sse_reaper_interval_s=60.0,
    )
    hub = SseHub(settings)
    await hub.start()
    try:
        timestamp = "2026-04-30T12:00:00Z"
        # Subscriber attaches first so the publish is delivered, not dropped.
        gen = hub.subscribe("sess-stream", user_id="alice@gwdg")
        # Drain the connection comment so the next chunk is the frame.
        first = await gen.__anext__()
        assert b": connected" in first

        await hub.publish(
            "sess-stream",
            SsePublishRequest(
                event=SseEventName.ACTION,
                data={
                    "type": "web_search",
                    "message": "Searching for quantum computing",
                    "timestamp": timestamp,
                },
            ),
            user_id="alice@gwdg",
        )

        chunk = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
        text = chunk.decode("utf-8")
        assert "event: action" in text
        assert "data:" in text
        # The data line carries our payload verbatim.
        data_line = next(
            line for line in text.splitlines() if line.startswith("data:")
        )
        payload = json.loads(data_line[len("data:"):].strip())
        assert payload["type"] == "web_search"
        assert payload["timestamp"] == timestamp

        # Close the generator so the unsubscribe finally-block runs.
        await gen.aclose()
    finally:
        await hub.aclose()


@pytest.mark.asyncio
async def test_us005_three_event_kinds_round_trip():
    """Action / result / error frames all reach the subscriber."""
    settings = Settings(
        sse_heartbeat_interval_s=10.0,
        sse_subscriber_queue_size=64,
        sse_publish_rate_per_session=100,
    )
    hub = SseHub(settings)
    await hub.start()
    try:
        gen = hub.subscribe("sess-kinds", user_id="alice@gwdg")
        first = await gen.__anext__()
        assert b": connected" in first

        kinds: List[SseEventName] = [
            SseEventName.ACTION,
            SseEventName.RESULT,
            SseEventName.ERROR,
        ]
        for kind in kinds:
            await hub.publish(
                "sess-kinds",
                SsePublishRequest(event=kind, data={"k": kind.value}),
                user_id="alice@gwdg",
            )

        seen: List[str] = []
        for _ in kinds:
            chunk = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
            text = chunk.decode("utf-8")
            event_line = next(
                line for line in text.splitlines() if line.startswith("event:")
            )
            seen.append(event_line.split(":", 1)[1].strip())

        assert seen == [k.value for k in kinds]
        await gen.aclose()
    finally:
        await hub.aclose()


def test_us005_publish_rate_limit_returns_429(make_broker_client, auth_headers):
    """Sustained per-session publish above the cap surfaces as 429 with
    a Retry-After header — matches Task 1.6 acceptance and the FR-006
    streaming contract.
    """
    client = make_broker_client(sse_publish_rate_per_session=2)
    with client as c:
        for _ in range(2):
            r = c.post(
                "/api/sse/sess-rl/events",
                json={"event": "action", "data": {}},
                headers=auth_headers("alice@gwdg"),
            )
            assert r.status_code == 200
        r = c.post(
            "/api/sse/sess-rl/events",
            json={"event": "action", "data": {}},
            headers=auth_headers("alice@gwdg"),
        )
        assert r.status_code == 429
        assert r.headers.get("retry-after") == "1"


def test_us005_publish_known_event_kinds_return_200(broker_client, auth_headers):
    """The four spec-defined event kinds (action / result / error /
    message) must round-trip through the publish endpoint without 422.
    """
    for kind in ("action", "result", "error", "message"):
        r = broker_client.post(
            "/api/sse/sess-kinds-http/events",
            json={"event": kind, "data": {"timestamp": "2026-04-30T12:00:00Z"}},
            headers=auth_headers("alice@gwdg"),
        )
        assert r.status_code == 200, (kind, r.text)
