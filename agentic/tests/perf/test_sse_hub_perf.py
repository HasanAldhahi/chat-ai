"""SSE hub micro-benchmarks (Task 5.3 acceptance: SSE streaming latency
< 500 ms; broker stays cheap under broadcast).

These run entirely in-process so they measure the broker code path
without TCP / ASGI overhead — the network leg is whatever Locust
records under load. Bounds are wide so a busy CI runner will still
pass; what we want to catch is an accidental O(n²) on broadcast or a
forgotten ``await`` that adds an event-loop hop per subscriber.
"""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from app.config import Settings
from app.models.sse import SseEventName, SsePublishRequest
from app.services.sse_hub import SseHub


@pytest.mark.asyncio
async def test_publish_to_subscribe_latency_under_50_ms():
    """One publish → one consumer must hop within tens of ms in-process.

    The acceptance criterion is 500 ms wall-clock under network load;
    50 ms in-process is a generous tripwire. If we ever blow past it
    on a developer machine it almost certainly means a regression
    (e.g. someone added a synchronous I/O call to the publish path).
    """
    settings = Settings(
        sse_heartbeat_interval_s=10.0,
        sse_publish_rate_per_session=1000,
    )
    hub = SseHub(settings)
    await hub.start()
    try:
        gen = hub.subscribe("perf-1", user_id="alice@gwdg")
        first = await gen.__anext__()
        assert b": connected" in first

        t0 = time.perf_counter()
        await hub.publish(
            "perf-1",
            SsePublishRequest(
                event=SseEventName.ACTION,
                data={"type": "tick", "n": 0},
            ),
            user_id="alice@gwdg",
        )
        chunk = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        assert b"event: action" in chunk
        # 50 ms is ~25x the typical observed in-process timing.
        assert elapsed_ms < 50.0, f"publish→subscribe latency {elapsed_ms:.2f} ms"
        await gen.aclose()
    finally:
        await hub.aclose()


@pytest.mark.asyncio
async def test_broadcast_to_50_subscribers_under_50_ms():
    """50 subscribers receive one frame; assert no message loss and the
    publisher returns quickly. Catches an accidental sync loop.
    """
    settings = Settings(
        sse_heartbeat_interval_s=10.0,
        sse_publish_rate_per_session=1000,
        sse_subscriber_queue_size=64,
    )
    hub = SseHub(settings)
    await hub.start()
    try:
        gens = []
        for _ in range(50):
            g = hub.subscribe("fanout", user_id="alice@gwdg")
            await g.__anext__()  # drain `: connected`
            gens.append(g)

        t0 = time.perf_counter()
        delivered = await hub.publish(
            "fanout",
            SsePublishRequest(event=SseEventName.RESULT, data={"x": 1}),
            user_id="alice@gwdg",
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        assert delivered == 50
        assert elapsed_ms < 50.0, (
            f"broadcast to 50 subs took {elapsed_ms:.2f} ms"
        )

        # And every subscriber actually sees the frame.
        for g in gens:
            chunk = await asyncio.wait_for(g.__anext__(), timeout=1.0)
            assert b"event: result" in chunk
        for g in gens:
            await g.aclose()
    finally:
        await hub.aclose()


@pytest.mark.asyncio
async def test_publish_throughput_1000_messages_under_2_s():
    """Sustain 1000 publishes to one subscriber and read them all.

    The default per-session rate limit is 100/s — bump it for the test.
    Wall-clock bound is generous (2 s for 1000 frames in-process is
    deeply pessimistic; observed times are typically ~50–200 ms).
    """
    settings = Settings(
        sse_heartbeat_interval_s=10.0,
        sse_publish_rate_per_session=10_000,
        sse_subscriber_queue_size=2048,
    )
    hub = SseHub(settings)
    await hub.start()
    try:
        gen = hub.subscribe("hot", user_id="alice@gwdg")
        await gen.__anext__()  # drain `: connected`

        t0 = time.perf_counter()
        for i in range(1000):
            await hub.publish(
                "hot",
                SsePublishRequest(
                    event=SseEventName.ACTION,
                    data={"i": i},
                ),
                user_id="alice@gwdg",
            )
        # Drain all frames so we know they actually delivered.
        seen = 0
        while seen < 1000:
            chunk = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
            if b"event: action" in chunk:
                seen += 1
        elapsed_s = time.perf_counter() - t0

        assert seen == 1000
        assert elapsed_s < 2.0, (
            f"1000-msg round-trip took {elapsed_s:.2f}s (>2s budget)"
        )
        await gen.aclose()
    finally:
        await hub.aclose()
