"""US-009 Session cleanup — when a client disconnects (or a session
goes idle past the configured TTL), the broker reclaims its room.
This guards against unbounded growth in the SSE registry and against
zombie subscriptions occupying queue slots.

Also covers session-TTL expiry on the auth side: a long-idle user is
forced to re-authenticate (401) on next request rather than silently
inheriting an old rate-limit budget.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from app.config import Settings
from app.models.sse import SseEventName, SsePublishRequest
from app.services.sse_hub import SseHub


@pytest.mark.asyncio
async def test_us009_idle_room_is_reaped():
    """Configure a tiny idle timeout + reaper interval, publish once,
    wait, and verify the room count returns to zero.
    """
    settings = Settings(
        sse_publish_rate_per_session=100,
        sse_session_idle_timeout_s=0.05,
        sse_reaper_interval_s=0.05,
    )
    hub = SseHub(settings)
    await hub.start()
    try:
        await hub.publish(
            "sess-idle",
            SsePublishRequest(event=SseEventName.ACTION, data={}),
            user_id="alice@gwdg",
        )
        assert hub.session_count() == 1

        # Give the reaper a couple of cycles to evict the idle room.
        deadline = time.monotonic() + 2.0
        while hub.session_count() > 0 and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        assert hub.session_count() == 0, "reaper failed to clean up idle room"
    finally:
        await hub.aclose()


@pytest.mark.asyncio
async def test_us009_subscriber_disconnect_releases_queue():
    """The subscribe generator's ``finally`` block must drop the queue
    so the room's subscriber list is empty after disconnect, even if
    the room itself remains open for other subscribers.
    """
    settings = Settings(
        sse_publish_rate_per_session=10,
        sse_subscriber_queue_size=4,
    )
    hub = SseHub(settings)
    await hub.start()
    try:
        gen = hub.subscribe("sess-leave", user_id="alice@gwdg")
        first = await gen.__anext__()
        assert b": connected" in first
        assert hub.subscriber_count("sess-leave") == 1

        await gen.aclose()  # simulate the browser tab closing
        assert hub.subscriber_count("sess-leave") == 0
    finally:
        await hub.aclose()


def test_us009_auth_session_ttl_forces_relogin(make_broker_client, auth_headers):
    """Set a sub-second auth TTL, send one request, sleep past it, send
    another — the second should surface as 401 with an ``expired``
    detail string.
    """
    client = make_broker_client(auth_session_ttl_s=0.05, auth_rate_per_user=100)
    with client as c:
        r = c.get(
            "/api/secrets/search_api_key",
            headers=auth_headers("alice@gwdg"),
        )
        assert r.status_code == 200
        time.sleep(0.1)
        r = c.get(
            "/api/secrets/search_api_key",
            headers=auth_headers("alice@gwdg"),
        )
        assert r.status_code == 401
        assert "expired" in r.json()["detail"].lower()
