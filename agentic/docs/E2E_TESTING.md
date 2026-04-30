# End-to-End Testing — Phase 5 / Task 5.2

This document is the operator-facing artifact for Task 5.2. It records
*what is tested where* and *what still requires a deployed stack* so a
future engineer can tell at a glance which acceptance bullet still
needs work.

Two layers of E2E coverage are planned:

1. **Backend integration suite** — `agentic/tests/e2e/`, runs in-process
   under FastAPI `TestClient` with mocked Slurm / Vault / vLLM. **Landed
   in Task 5.2.**
2. **Browser-driven UI suite** — Playwright against a running stack
   (broker + Node proxy + React dev server). **Scoped here as a
   follow-up.**

---

## 1. Backend integration suite (in this repo)

Run as a CI gate:

```bash
cd agentic
source .venv/bin/activate
pytest tests/e2e -m e2e
```

| User story | File                                          | Surface exercised                                                                                                                                                                                                                  |
| ---------- | --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| US-001     | `test_us001_agent_selection.py`               | `POST /api/agent/chat` with `model="Agent - …"` → broker accepts; non-agent model → 400; missing X-User → 401; empty messages → 422.                                                                                                |
| US-002     | `test_us002_web_search.py`                    | MCP `/rpc` `tools/list` advertises `web_search`/`web_browse`; `tools/call web_search` returns URL+title+snippet list (stub provider); empty query / oversize `num_results` → `invalid_params`.                                      |
| US-003     | `test_us003_secure_file_analysis.py`          | MCP `tools/call fs_read` round-trips a workspace file; `/etc/passwd` and traversal blocked; `fs_list` only inside sandbox; `fs_write` + `fs_read` round-trip.                                                                       |
| US-004     | `test_us004_workspace_isolation.py`           | Bob ↛ Alice on job status / cancel / SSE publish / SSE subscribe (all 403); Alice can still read her own.                                                                                                                          |
| US-005     | `test_us005_real_time_streaming.py`           | SseHub publish → subscribe delivers wire-format frame with `event:` + `data:` and the publisher-supplied timestamp; action/result/error round-trip; 429 rate-limit + Retry-After; all four event kinds accepted by HTTP publish.    |
| US-006     | `test_us006_secret_injection.py`              | `/api/secrets/{type}` returns the user's secret; per-user Vault path scoping confirmed at the captured-URL level; missing X-User blocks before any Vault round-trip; unknown `secret_type` → 422.                                  |
| US-007     | `test_us007_agent_swappability.py`            | Six different agent labels (OpenHands / Goose / opencode / smolagents + lower/spaced variants) all route through the broker; switching agents inside one session works.                                                            |
| US-008     | `test_us008_network_security.py`              | `web_browse` to RFC1918 / loopback / IPv6 ULA / cloud-metadata IPs and `internal.gwdg.de` suffixes blocked with `url_blocked`; non-http(s) schemes blocked.                                                                          |
| US-009     | `test_us009_session_cleanup.py`               | Idle SSE room reaped after `sse_session_idle_timeout_s` elapses; subscriber disconnect releases queue; auth session TTL forces re-login (401 with `expired`).                                                                       |

What is **NOT** in the in-process suite (by design):

- Real browser navigation and rendering.
- Cluster Slurm submission, real Apptainer container start, real vLLM
  generation. The broker has mock modes for the first two; vLLM is
  mocked per-test via `monkeypatch`.
- Cross-process timing / network failures. Use Task 5.3 (perf) for
  load-shaped regressions.

---

## 2. Browser-driven UI suite (follow-up)

Playwright is the recommended driver for the React side. Setup is
non-trivial: it pulls down browser binaries (~200 MB) and needs a
running broker + Node + Vite stack to be meaningful. This is intentionally
deferred so Task 5.2's CI gate stays self-contained.

When you pick this up:

1. **Install** in `front/`:

   ```bash
   cd front
   npm install --save-dev @playwright/test
   npx playwright install --with-deps chromium
   ```

2. **Stack start-up** (compose into one script):

   - `agentic`: `uvicorn app.main:app --port 8001` with mock modes
     and a vLLM stub (point `AGENTIC_VLLM_BASE_URL` at a fixture
     server, or run a tiny mock under `python -m agentic.tests.fixtures.vllm_stub`).
   - `back`: `node service.mjs` with `AGENTIC_BROKER_URL=http://127.0.0.1:8001`.
   - `front`: `npm run dev` (Vite — proxies `/api` and `/models` to
     the Node backend per `front/vite.config.js`).

3. **Coverage targets** (one Playwright spec per UI scenario):

   - **US-001**: model dropdown shows the four agent rows in the
     "Agents" group; selecting one persists in localStorage.
   - **US-002**: send a prompt with an agent selected; assert the chat
     pane shows the assistant turn populated from the broker.
   - **US-005**: agent SSE activity feed shows action / result / error
     items with timestamps and tool icons; "Show more" expands long
     output.
   - **US-007**: switch from OpenHands to Goose mid-conversation;
     assert the conversation is reset (per Task 4.5 wrapper logic) and
     the new agent label is sent.
   - **US-008** (UI surface): trigger an agent error response; the
     error chat alert offers "Retry" and the friendly error copy
     matches `agenticErrors.js`.

4. **CI integration**: run Playwright in a separate GitHub Actions
   matrix entry that boots the stack via Docker Compose. Keep total
   wall-clock under 10 minutes (Task 5.2 acceptance criterion).

Until then, the unit-level Vitest coverage in `front/src/__tests__`
already locks in the front-side helpers (agent SSE parser, model
dropdown, error mapping). The pieces *not* yet exercised are the
visual rendering of the SSE feed and the cross-stack data flow — which
is exactly what Playwright is being kept in reserve for.

---

## 3. CI gate

Suggested job (GitHub Actions sketch):

```yaml
- name: Backend E2E
  run: |
    cd agentic
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    pytest tests/security tests/e2e -m "security or e2e" --maxfail=1
```

Failing this job blocks PR merge — that's the policy needed by Task 5.2
acceptance ("Failing tests block PR merge"). The Playwright job is
added later as a separate matrix entry once § 2 is implemented.
