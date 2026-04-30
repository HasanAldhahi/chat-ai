"""AuthService rate-limit micro-benchmarks (Task 5.3).

Every inbound /api/* request hits ``AuthService.touch_and_check``, so
this is one of the most contention-prone hot paths. Catch O(n²)
regressions in the sliding-window deque trim and lock contention.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from app.services.auth import AuthService


@pytest.mark.asyncio
async def test_touch_and_check_under_50_us_mean():
    """5000 sequential touches for one user — amortised cost should
    sit in the low-microseconds range.
    """
    svc = AuthService(
        validate_format=False,
        session_ttl_s=600,
        rate_per_user=10_000,
        rate_window_s=1.0,
    )
    # Warm-up.
    await svc.touch_and_check("alice", "gwdg")

    n = 5000
    t0 = time.perf_counter()
    for _ in range(n):
        await svc.touch_and_check("alice", "gwdg")
    elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
    per_call_us = elapsed_us / n

    # 50 µs per call ≈ 20k req/s sequential — pessimistic for asyncio.
    assert per_call_us < 50.0, (
        f"touch_and_check mean {per_call_us:.2f} µs (>50 µs budget)"
    )


@pytest.mark.asyncio
async def test_touch_and_check_isolated_per_user_under_concurrency():
    """200 distinct users, 50 concurrent batches. Per-user buckets must
    not stomp on each other and the total wall-clock should stay
    bounded.
    """
    svc = AuthService(
        validate_format=False,
        session_ttl_s=600,
        rate_per_user=100,
        rate_window_s=1.0,
    )

    async def hit(user_id: str, n: int):
        for _ in range(n):
            await svc.touch_and_check(user_id, "gwdg")

    t0 = time.perf_counter()
    await asyncio.gather(
        *(hit(f"u{i}", 10) for i in range(200))
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    # 200 users × 10 calls = 2000 ops. <500 ms is a generous bound.
    assert elapsed_ms < 500.0, (
        f"200×10 concurrent rate-limit ops took {elapsed_ms:.0f} ms"
    )
    assert svc.session_count() == 200


@pytest.mark.asyncio
async def test_parse_user_header_is_constant_time():
    """Header regex must run in constant time for typical input;
    assert mean < 10 µs over 10k calls.
    """
    svc = AuthService(validate_format=True)
    n = 10_000

    t0 = time.perf_counter()
    for _ in range(n):
        svc.parse_user_header("user.42@some-tenant")
    elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
    per_call_us = elapsed_us / n

    assert per_call_us < 10.0, (
        f"parse_user_header mean {per_call_us:.2f} µs (>10 µs budget)"
    )
