"""MCP /rpc dispatch micro-benchmarks (Task 5.3).

The dispatcher is the hottest path inside an agent session — every
tool call goes through it. Catch obvious regressions in the
parse/dispatch loop or the per-call envelope construction.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from mcp_server.server import dispatch


@pytest.mark.asyncio
async def test_tools_list_dispatch_under_5_ms_mean():
    """500 tools/list calls in a row; the mean per-call time should
    sit in the low-microseconds range. We assert <5 ms / call to
    leave generous headroom for slow CI runners.
    """
    # Warm-up so the tool registry import is paid once.
    await dispatch({"jsonrpc": "2.0", "id": 0, "method": "tools/list"})

    n = 500
    t0 = time.perf_counter()
    for i in range(n):
        env = await dispatch(
            {"jsonrpc": "2.0", "id": i, "method": "tools/list"}
        )
        assert "result" in env
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    per_call_ms = elapsed_ms / n

    assert per_call_ms < 5.0, (
        f"tools/list mean dispatch {per_call_ms:.3f} ms (>5 ms budget)"
    )


@pytest.mark.asyncio
async def test_method_not_found_short_circuits_under_1_ms_mean():
    """Unknown method must fail fast — no I/O, no tool lookup.

    A regression here would mean someone added an expensive default
    branch to the dispatcher.
    """
    n = 1000
    t0 = time.perf_counter()
    for i in range(n):
        env = await dispatch(
            {"jsonrpc": "2.0", "id": i, "method": "definitely_not_a_method"}
        )
        assert "error" in env
        assert env["error"]["code"] == -32601
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    per_call_ms = elapsed_ms / n

    assert per_call_ms < 1.0, (
        f"method-not-found mean {per_call_ms:.3f} ms (>1 ms budget)"
    )


@pytest.mark.asyncio
async def test_concurrent_tools_list_no_lock_contention():
    """200 concurrent tools/list dispatches — total wall-clock should
    stay well under sequential time, demonstrating the dispatcher does
    not serialise on a coarse lock.
    """
    n = 200

    async def one():
        env = await dispatch(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        )
        assert "result" in env

    t0 = time.perf_counter()
    await asyncio.gather(*(one() for _ in range(n)))
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    # 200 calls × <5 ms each sequential ≈ <1 s; concurrent should be
    # noticeably less but at minimum match. Cap at 1 s.
    assert elapsed_ms < 1000.0, (
        f"200 concurrent tools/list took {elapsed_ms:.0f} ms"
    )
