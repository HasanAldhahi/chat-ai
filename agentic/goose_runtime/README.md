# goose_runtime

Task **4.1** orchestration for the Goose CLI in Chat AI Apptainer images.

| Module | Purpose |
|--------|---------|
| `launcher` | MCP `uvicorn` → `/health` → Goose `run --no-session` + broker SSE ingest |
| `mcp_stdio_bridge` | MCP extension shim: stdin JSON-RPC ↔ `POST …/rpc` |
| `goose_yaml` | Writes Goose `extensions.chat-ai-mcp` pointing at the bridge |

Env prefix **`GOOSE_`** (see `config.py`). For smoke builds without invoking the real Goose binary, use **`GOOSE_DEV_COMMAND_OVERRIDE=/bin/true`**.
