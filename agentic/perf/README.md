# Load testing the agentic broker (Phase 5 / Task 5.3)

Two ways in:

* **Locust** — `locustfile.py` here. Simulates 100 concurrent users
  across the broker's main HTTP surfaces (jobs, status polling,
  secrets, SSE publish, agent chat).
* **In-process micro-benchmarks** — `agentic/tests/perf/`, run with
  `pytest -m perf`. Catches per-handler regressions in CI without
  needing a deployed stack.

## Quick start (Locust)

```bash
# 1. Install Locust into the agentic venv
cd agentic
source .venv/bin/activate
pip install 'locust>=2.30,<3.0'

# 2. Boot the broker in mock mode
AGENTIC_SLURM_MOCK_MODE=1 \
AGENTIC_VAULT_MOCK_MODE=1 \
AGENTIC_VLLM_BASE_URL=http://127.0.0.1:9999 \
AGENTIC_AUTH_RATE_PER_USER=10000 \
AGENTIC_SSE_PUBLISH_RATE_PER_SESSION=10000 \
uvicorn app.main:app --host 0.0.0.0 --port 8001 \
    --workers 1 --log-level warning &

# 3. Run the load campaign
cd perf
locust -f locustfile.py --host http://127.0.0.1:8001 \
    --users 100 --spawn-rate 10 --run-time 5m --headless \
    --csv reports/$(date -u +%Y%m%dT%H%M%SZ)
```

The CSV files (`*_stats.csv`, `*_failures.csv`, `*_history.csv`)
populate the per-campaign rows in `PERFORMANCE_REPORT.md`.

## Targets (Task 5.3 acceptance bullets)

| Metric                                 | Target          | Where to read it                         |
| -------------------------------------- | --------------- | ---------------------------------------- |
| P99 latency for first action           | < 5 s           | Locust `_stats.csv` `99%` column         |
| P95 SSE streaming latency              | < 500 ms        | `POST /api/sse/:id/events` `95%`         |
| Broker CPU at 100 concurrent users     | < 50 %          | `top -p $(pidof uvicorn)` over the run   |
| Slurm queue backlog                    | < 10 jobs       | (cluster only — N/A in mock mode)        |
| Memory growth over 30 min run          | < 100 MB        | `ps -o rss=` on the broker pid           |

## What the mix looks like

Per-user request mix per the `@task(weight)` markers in `locustfile.py`:

* **8x** GET `/api/jobs/:id/status`  — dominates a real session
* **6x** POST `/api/sse/:id/events`  — agent runtime publishes
* **3x** POST `/api/jobs`            — job submission
* **2x** GET `/api/secrets/:type`    — secret pull on session start
* **1x** POST `/api/agent/chat`      — the heavyweight vLLM-bound call
* **1x** GET `/health`               — sanity probe

## Notes

* **Mock mode** is critical for the broker side — without it Locust
  hits a real cluster and either times out or generates real Slurm
  load. Mock-mode Slurm + Vault return synthetic responses in O(µs).
* **vLLM** is the only upstream that can't be cheaply mocked here.
  Either point `AGENTIC_VLLM_BASE_URL` at a real test instance, or
  spin up a tiny SSE stub (e.g. `python -m http.server` returning a
  canned chat completion). The latency budget for this endpoint is
  dominated by the upstream, not the broker.
* **Distributed mode** for >1 worker: launch a master with
  `locust ... --master` and N workers with `--worker --master-host=…`
  per the [Locust docs](https://docs.locust.io/en/stable/running-distributed.html).

## In-process micro-benchmarks

```bash
pytest agentic/tests/perf/ -m perf -v
```

Advisory only — they assert generous per-call timing bounds that
should never trip on a healthy box but will catch obvious regressions
(e.g. accidental O(n²) work on a hot path). They are NOT part of the
default CI gate.
