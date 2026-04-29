# OpenCode (`sst/opencode`) agent image — Task 4.3

Derives from `../mcp/mcp.sif`. Installs the [OpenCode](https://opencode.ai/docs/) CLI (`anomalyco/opencode` release tarball), the Python `mcp` package, and `agentic/opencode_runtime/`:

| Component | Role |
|-----------|------|
| `uvicorn mcp_server.main:app` | HTTP JSON-RPC on `:${MCP_SERVER_PORT:-8080}` (`/rpc`, `/health`) |
| `opencode_runtime.mcp_stdio_gateway` | Stdio MCP server spawned by OpenCode as a **local** MCP (`type: local`); proxies `tools/list` and `tools/call` to `POST /rpc` |
| `opencode_runtime.launcher` | Starts MCP, waits `/health`, writes `~/.config/opencode/opencode.json`, runs `opencode run …`, forwards stdout to the broker SSE (same pattern as Goose / OpenHands) |

## Build order

```bash
cd ../base && ./build_image.sh --fakeroot   # Task 2.1
cd ../mcp  && ./build_image.sh --fakeroot   # Task 2.2
./build_image.sh --fakeroot                  # yields ./opencode.sif
```

## Runtime env (broker / Slurm typical)

OpenCode pulls the coding model via `provider/options` (`openai` block with `OPENAI_API_KEY` / `OPENAI_BASE_URL`). Per-session MCP remains loopback-only.

| Variable | Meaning |
|---------|---------|
| `OPENCODE_SESSION_ID`, `OPENCODE_USER_ID` | Session + user (launcher pass-through for SSE forwarder if set by broker naming) |
| `OPENCODE_BROKER_SSE_URL` | Broker SSE ingest (optional) |
| `OPENCODE_SESSION_PROMPT` | Headless prompt for `opencode run` |
| `OPENCODE_MODEL` | `provider/model` (written into generated config unless you override entirely) |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL` | Point at cluster vLLM or OpenAI-compat endpoint |
| `OPENCODE_DEV_COMMAND_OVERRIDE` | e.g. `/bin/true` for smoke tests without contacting an LLM |
| proxy env | Respect cluster `HTTPS_PROXY`, `HTTP_PROXY`, `NO_PROXY` (inherited by child processes) |

## Smoke

Without a GPU / API key Dev:

```bash
APPTAINERENV_OPENCODE_DEV_COMMAND_OVERRIDE=/bin/true \
    apptainer run opencode.sif
```

Structured checks after `./build_image.sh`:

```bash
./test_image.sh ./opencode.sif
```

## Acceptance

Implementation follows the Task 4.3 spec: OpenCode installs in-container, MCP comes up on loopback; OpenCode is configured via `opencode.json` to attach the chat-ai MCP through the stdio bridge; launcher wiring matches other agent images.

Cluster E2E (real LLM + tool rounds) stays an operator checklist — not replaced by pytest.
