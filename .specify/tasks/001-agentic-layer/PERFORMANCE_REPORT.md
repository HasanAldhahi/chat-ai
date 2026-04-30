# Performance Test Report — Agentic Broker

**Branch:** `task-5.3-performance-testing` (off `task-5.2-end-to-end-testing`)
**Spec source:** `.specify/tasks/001-agentic-layer/tasks.md` § Task 5.3
**Runbook:** `agentic/docs/PERFORMANCE_TESTING.md`
**Status:** template — fill in per campaign

This document tracks load-test campaigns against the broker. One row
per run; keep history so optimisation work shows up as numerical
deltas. Pair every campaign with the resource log produced by § 2.3
of the runbook.

---

## 1. Targets (from Task 5.3 acceptance)

| # | Metric                                     | Target          |
| - | ------------------------------------------ | --------------- |
| 1 | P99 first-action latency (agent_chat)      | < 5 s           |
| 2 | P95 SSE publish→deliver latency            | < 500 ms        |
| 3 | Broker CPU at 100 concurrent users         | < 50 %          |
| 4 | Slurm queue backlog at peak                | < 10 jobs       |
| 5 | RSS growth over 30 min                     | < 100 MB        |
| 6 | Error rate (5xx outside expected paths)    | < 1 %           |

## 2. Run summary

For each campaign, append a row. Pull the percentiles from
`reports/<timestamp>_stats.csv`; CPU/RSS from the resource log; queue
backlog from cluster metrics (N/A in mock mode).

| Date (UTC) | Commit | Workers | Users | Run-time | P99 agent_chat | P95 SSE pub | CPU peak | RSS Δ | Errors | Pass? |
| ---------- | ------ | ------- | ----- | -------- | -------------- | ----------- | -------- | ----- | ------ | ----- |
| _ex._ 2026-05-04T12:00 | `abcd123` | 1 | 100 | 5 m | _x_ ms | _y_ ms | _z_ % | _w_ MB | _e_ | ☐ |

(Replace the example row with real measurements.)

## 3. Bottlenecks & fixes

For each issue identified by a campaign:

```
### B-XXX  <one-line title>
- First seen: <date> on <commit>
- Symptom: <which target was breached and by how much>
- Hypothesis: <which handler / lock / dependency>
- Profiling artefact: <path to py-spy / flamegraph / Locust CSV>
- Fix commit: <sha>
- Re-test campaign: <date> — <pass | breached>
```

## 4. Sustained-load notes (optional)

Long-haul runs (30 m+) catch slow leaks. Record:

- **Heap snapshot** (or RSS sample every 60 s).
- **Subscriber-count** for SSE rooms — stays bounded?
- **Open httpx clients / asyncio tasks** — `asyncio.all_tasks()` count.

## 5. Sign-off

- [ ] Two consecutive campaigns at 100 users meet every target row.
- [ ] No outstanding "B-" entries with severity ≥ medium.
- [ ] In-process perf suite (`pytest -m perf`) green on the same commit.
- [ ] Resource-log script archived alongside the Locust CSV.
- [ ] Sign-off recorded by SRE / platform owner.

---

**Engagement metadata** (fill in per run)

- Driver host: _________________________
- Broker host: _________________________
- vLLM endpoint: _________________________
- Worker count: _________________________
- Tuned envs (`AGENTIC_*`): _________________________
- Locust args: _________________________
