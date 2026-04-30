# Performance testing — Phase 5 / Task 5.3

This is the operator-facing runbook for the broker's load-testing
deliverables. It pairs with two artifacts:

* `agentic/perf/locustfile.py` — Locust load campaign for the broker.
* `agentic/tests/perf/` — in-process micro-benchmarks, advisory.

The per-campaign measurements go into
`.specify/tasks/001-agentic-layer/PERFORMANCE_REPORT.md` (one row per
run).

---

## 1. Targets (Task 5.3 acceptance)

| # | Metric                                     | Target               |
| - | ------------------------------------------ | -------------------- |
| 1 | P99 latency for first action (agent chat)  | < 5 s                |
| 2 | P95 SSE streaming latency (publish→deliver) | < 500 ms            |
| 3 | Broker CPU at 100 concurrent users         | < 50 %               |
| 4 | Slurm queue backlog at peak                | < 10 jobs            |
| 5 | Memory growth over a 30-min run            | < 100 MB RSS         |
| 6 | No 5xx outside expected scenarios          | error rate < 1 %     |

---

## 2. Locust campaign

### 2.1 Boot the broker (mock mode)

```bash
cd agentic
source .venv/bin/activate

AGENTIC_SLURM_MOCK_MODE=1 \
AGENTIC_VAULT_MOCK_MODE=1 \
AGENTIC_VLLM_BASE_URL=http://127.0.0.1:9999 \
AGENTIC_AUTH_RATE_PER_USER=10000 \
AGENTIC_SSE_PUBLISH_RATE_PER_SESSION=10000 \
uvicorn app.main:app --host 0.0.0.0 --port 8001 \
    --workers 1 --log-level warning &
```

Notes:

- **Worker count.** Production should match the cluster sizing; for the
  benchmark, start at `--workers 1` to attribute CPU + RSS to one
  process. Scale up only after the single-worker numbers are clean.
- **Rate limits.** The defaults (10 req/s per user, 100 msg/s per SSE
  session) intentionally throttle real workloads. A load test wants
  raw throughput, so the env vars above lift them. **Re-tune for prod
  before deploying.**
- **vLLM stub.** `AGENTIC_VLLM_BASE_URL=http://127.0.0.1:9999` points
  at a non-existent endpoint so the agent_chat task records 502s
  quickly without burning real LLM tokens. To exercise the streaming
  path, point at a real vLLM or run a tiny SSE stub.

### 2.2 Run the campaign

```bash
cd agentic/perf
pip install 'locust>=2.30,<3.0'   # one-time

mkdir -p reports
locust -f locustfile.py --host http://127.0.0.1:8001 \
    --users 100 --spawn-rate 10 --run-time 5m --headless \
    --csv "reports/$(date -u +%Y%m%dT%H%M%SZ)"
```

Output files (`*_stats.csv`, `*_failures.csv`, `*_history.csv`,
`*_stats_history.csv`) are the inputs to `PERFORMANCE_REPORT.md`.

### 2.3 Capture broker resource numbers

In a parallel terminal:

```bash
PID=$(pgrep -f 'uvicorn app.main:app' | head -1)
while kill -0 "$PID" 2>/dev/null; do
    ts=$(date -u +%H:%M:%S)
    cpu=$(ps -p "$PID" -o %cpu= | awk '{print $1}')
    rss=$(ps -p "$PID" -o rss= | awk '{print $1}')
    echo "$ts cpu=$cpu rss_kb=$rss"
    sleep 5
done | tee reports/broker_resource_$(date -u +%Y%m%dT%H%M%SZ).log
```

Grafana / Prometheus scrape is the production answer; the script above
covers a single ad-hoc campaign.

### 2.4 Reading the result

In Locust's CSV:

| Column            | Maps to                                                  |
| ----------------- | -------------------------------------------------------- |
| `99%`             | Target #1 / #2 (compare per request name)                |
| `Failure Count`   | Target #6                                                |
| `Median Response` | Sanity sieve — should be << target                       |

The campaign passes when every row in
`PERFORMANCE_REPORT.md` § "Run summary" sits under its target column.

---

## 3. In-process micro-benchmarks

Advisory; run on every push so accidental hot-path regressions surface
before they reach the load test:

```bash
pytest agentic/tests/perf/ -m perf -v
```

Coverage:

| Module                           | What it locks in                                                                                              |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `test_sse_hub_perf.py`           | publish→subscribe latency < 50 ms; broadcast-to-50 < 50 ms; 1000-msg round-trip < 2 s.                        |
| `test_mcp_dispatch_perf.py`      | `tools/list` mean < 5 ms; method-not-found < 1 ms; 200 concurrent dispatches < 1 s.                           |
| `test_auth_rate_limit_perf.py`   | `touch_and_check` mean < 50 µs; 200 users × 10 ops < 500 ms; `parse_user_header` < 10 µs.                     |
| `test_secret_cache_perf.py`      | 1 miss + 999 hits → 1 Vault call; 50 concurrent first hits collapse to 1 Vault call; cache hit < 5 µs mean.   |

These are **not** part of the default CI gate. Bounds are wide enough
that a clean machine passes by 10–100×, but they're sensitive to
contention from co-tenant work — keep them out of mandatory merge gates.

---

## 4. Bottleneck triage cheat-sheet

If a target is breached, the suspects in priority order:

| Symptom                                    | Likely cause                                  | Where to look                                         |
| ------------------------------------------ | --------------------------------------------- | ----------------------------------------------------- |
| SSE publish P95 > 500 ms                   | Lock contention in `_get_or_create_room`      | `app/services/sse_hub.py` — single asyncio.Lock       |
| Job status P95 > 1 s                       | Cache-miss flood; poll loop saturated         | `app/services/job_monitor.py::get_status` cache TTL   |
| Secrets P99 > 1 s                          | Cache stampede; per-key lock not held         | `app/services/secret_cache.py::_lock_for`             |
| Broker CPU > 50 %                          | Synchronous CPU work in a request handler     | `cProfile -o broker.prof` then snakeviz               |
| RSS climbs > 100 MB                        | Subscriber queue leak / unreaped SSE rooms    | `SseHub` reaper interval; `subscriber_count()`        |
| 5xx spike on `/api/agent/chat`             | vLLM upstream / proxy / no `AGENTIC_VLLM_BASE_URL` | Broker `vllm_stream_finished` log + 502 detail   |

Profiling the broker live:

```bash
PID=$(pgrep -f 'uvicorn app.main:app' | head -1)
py-spy record --pid "$PID" --duration 30 --output broker.svg
```

(`py-spy` does not require restarting the process — flame-graph in
`broker.svg` after 30 s.)

---

## 5. Monitoring (operator follow-up)

The acceptance criteria call for Grafana dashboards. The broker does
**not** yet expose `/metrics`; adding `prometheus_fastapi_instrumentator`
is the recommended next step but is intentionally not part of this
task because:

* It requires deploying Prometheus + Grafana to a real environment
  before the dashboard JSON can be validated.
* It changes broker dependencies and CORS surface.

Tracked in `PRODUCTION_CHECKLIST.md` § 5.3 as a follow-up. The Locust
CSV + the resource-log script above are the workaround for ad-hoc
campaigns until that lands.

---

## 6. Re-test after optimisation

Each round of changes should:

1. Re-run the Locust campaign with the same `--users / --run-time / --csv` flags.
2. Add a new row to `PERFORMANCE_REPORT.md` § "Run summary" with the
   commit hash being measured.
3. Note any tuning that moved the numbers (worker count, queue size,
   rate-limit cap) in § "Bottlenecks & fixes".

Task 5.3 stays IN PROGRESS until two consecutive campaigns at 100
users meet every target without breaking other suites (security, e2e).
