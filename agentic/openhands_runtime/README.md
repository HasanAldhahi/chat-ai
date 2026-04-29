# OpenHands runtime adapter (Task 2.3)

Per-session orchestration layer that lives inside the Task 2.3
Apptainer container. Three modules:

| Module                | Purpose                                                 |
|-----------------------|---------------------------------------------------------|
| `config.py`           | `OPENHANDS_*` settings (session id, MCP/vLLM URLs, …)   |
| `sse_forwarder.py`    | OpenHands stdout → broker SSE; bounded queue, drop-on-overflow |
| `launcher.py`         | Boot sequence: uvicorn(MCP) → /health → OpenHands → forwarder |

Plus `openhands_config.toml` — the OpenHands V1 config template
the launcher hands to the OpenHands subprocess.

## Boot sequence

```
launcher
  └─ spawn uvicorn mcp_server.main:app --port 8080
  └─ poll http://localhost:8080/health (timeout 20 s)
  └─ spawn `openhands --config /etc/openhands/config.toml`
       env: MCP_SERVER_URL, LLM_API_URL, LLM_MODEL, LLM_PARSER,
            HTTP_PROXY, HTTPS_PROXY, OPENHANDS_SESSION_ID, …
  └─ tail OpenHands stdout
       per line: translate to {action,result,error,message}
                 POST {broker_sse_url}/api/sse/{session_id}/events
  └─ on OpenHands exit (or 30 min hard cap):
       teardown OpenHands, drain forwarder, teardown MCP, exit
```

## Run locally (no apptainer)

```bash
cd agentic
python3.11 -m openhands_runtime.launcher
```

The launcher will:

- Start uvicorn on port 8080 (the MCP server module is in this same
  venv; see `agentic/mcp_server/`).
- Wait for `/health` (configured timeout: 20 s).
- Try to spawn `openhands` from PATH. Out of the box that will fail
  (OpenHands isn't a dev-VM dep) — set `OPENHANDS_OPENHANDS_COMMAND`
  to a placeholder for dry-runs:

  ```bash
  OPENHANDS_OPENHANDS_COMMAND=/bin/cat \
  OPENHANDS_BROKER_SSE_URL= \
    python3.11 -m openhands_runtime.launcher
  ```

  (`/bin/cat` keeps the launcher alive until you EOF; broker URL
  empty disables SSE forwarding.)

## Configuration

Env vars (prefix `OPENHANDS_`):

| Variable                              | Default                                | Purpose                                          |
|---------------------------------------|----------------------------------------|--------------------------------------------------|
| `OPENHANDS_SESSION_ID`                | `dev-session`                          | Routes SSE messages to the right room            |
| `OPENHANDS_USER_ID`                   | empty                                  | Forwarded as `X-User` to the broker              |
| `OPENHANDS_MCP_SERVER_URL`            | `http://localhost:8080`                | Where MCP listens                                |
| `OPENHANDS_MCP_UVICORN_PORT`          | `8080`                                 | Port the launcher binds uvicorn to               |
| `OPENHANDS_MCP_HEALTH_TIMEOUT_S`      | `20`                                   | How long to wait for MCP /health                 |
| `OPENHANDS_LLM_API_URL`               | `http://vllm.local/v1/completions`     | OpenAI-compatible vLLM endpoint                  |
| `OPENHANDS_LLM_MODEL`                 | `qwen3-30b`                            | Model id                                         |
| `OPENHANDS_LLM_PARSER`                | `hermes`                               | vLLM tool-call parser flag                       |
| `OPENHANDS_BROKER_SSE_URL`            | empty                                  | Broker base URL for event forwarding (empty ⇒ off)|
| `OPENHANDS_SSE_MAX_INFLIGHT`          | `32`                                   | Bounded queue depth                              |
| `OPENHANDS_OPENHANDS_COMMAND`         | `openhands`                            | Executable name / path                           |
| `OPENHANDS_OPENHANDS_CONFIG_PATH`     | `/etc/openhands/config.toml`           | Inside-container TOML config                     |
| `OPENHANDS_OPENHANDS_WORKSPACE`       | `/workspace`                           | OpenHands working directory                      |
| `OPENHANDS_OPENHANDS_MAX_RUNTIME_S`   | `1800` (30 min)                        | Hard cap before launcher kills OpenHands         |
| `OPENHANDS_HTTPS_PROXY`               | empty                                  | Plumbed back into OpenHands' env                 |

The broker injects per-session values via `APPTAINERENV_*` at submit
time (see `agentic/app/clients/slurm.py` for how that maps onto
slurmrestd job specs).

## Event translation

OpenHands V1 emits structured JSON lines on stdout. The forwarder
maps them onto the broker's SSE vocabulary:

| OpenHands `type`        | SSE event   |
|-------------------------|-------------|
| `action`                | `action`    |
| `observation` / `result` / `tool_result` | `result` |
| `message` / `agent_message` | `message` |
| `error` / `exception`   | `error`     |
| anything else           | `message`   |
| non-JSON line           | `message` (data.text = raw line) |

The unknown-shape fall-through is *intentional* — better to forward
a slightly misclassified event than drop it because OpenHands V1.next
added a new field.

## Tests

```bash
cd agentic
pytest -q tests/test_openhands_runtime.py
pytest -q tests/test_apptainer_openhands.py
```

`test_openhands_runtime.py` covers:

- `translate_openhands_line` — every mapping branch + fall-throughs
- `wait_for_health` — ready, slow, never-ready
- `build_openhands_env` / `build_openhands_argv` — env injection,
  proxy plumbing, extra args parsing
- `forward_stream` — happy path, broker 5xx, queue overflow,
  empty `broker_sse_url` short-circuit

`test_apptainer_openhands.py` is the static recipe parse — same
pattern as `test_apptainer_base.py` and `test_apptainer_mcp.py`.
