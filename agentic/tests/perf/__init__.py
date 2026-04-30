"""Phase 5 / Task 5.3 in-process micro-benchmark suite (advisory).

These tests assert generous per-operation timing budgets that catch
*obvious* regressions on the broker / MCP hot paths (SSE publish,
RPC dispatch, auth check, secret cache). They are NOT a substitute
for the Locust campaign in ``agentic/perf/`` — that's where real
100-user load shape is exercised.

Run as:

    pytest agentic/tests/perf/ -m perf -v

Bounds are deliberately wide (a slow CI runner should still pass);
the goal is to flag accidental O(n²) work or a forgotten ``await
asyncio.sleep`` in a hot path, not to gate on absolute throughput.
"""
