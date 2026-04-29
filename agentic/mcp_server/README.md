# MCP Server (Task 2.2)

Per-session MCP server that runs inside the agent's Apptainer
container and exposes a small set of audited tools to the agent
framework (OpenHands, Goose, etc.).

## Wire protocol

Single endpoint, single transport: `POST /rpc` carries JSON-RPC 2.0.

```json
// list_tools
{"jsonrpc":"2.0","method":"list_tools","id":1}

// call_tool
{"jsonrpc":"2.0","method":"call_tool","id":2,
 "params":{"name":"fs_read","arguments":{"path":"/workspace/README.md"}}}
```

Responses follow the JSON-RPC 2.0 envelope. Tool errors are mapped
to JSON-RPC errors; the `data.tool_error` field carries the stable
string code (e.g. `path_not_allowed`, `file_too_large`,
`url_blocked`) the agent can branch on.

## Tools

| Name         | Purpose                                    | Boundaries (defaults)            |
|--------------|--------------------------------------------|----------------------------------|
| `fs_read`    | Read a file                                 | `/workspace`, `/home/user`; ≤10 MB |
| `fs_write`   | Write a file                                | `/workspace` only; ≤1 MB         |
| `fs_list`    | Non-recursive directory listing             | allowed roots; cap 2000 entries  |
| `web_search` | Search the web via configurable provider    | proxy; default `stub` provider   |
| `web_browse` | HTTP GET a URL                              | proxy; private IPs blocked       |
| `code_exec`  | Run a Python snippet in a subprocess        | timeout ≤30 s; 64 KiB per stream |
| `code_check` | Lint a snippet with pyflakes                | same timeout                     |

`fs_read` / `fs_list` accept `/home/user` as well, but `fs_write`
deliberately does not — user home is read-only by default. To grant
write access for a session, change `MCP_SERVER_FS_WRITE_ROOTS`.

**Network (Task 2.5):** Outbound `httpx` calls honour `HTTP_PROXY` /
`HTTPS_PROXY` / `NO_PROXY` from the environment (and optional
`MCP_SERVER_WEB_PROXY_URL`). URLs with private IP literals are rejected;
hostnames matching `MCP_SERVER_WEB_BLOCKED_HOST_SUFFIXES` (default
includes `internal.gwdg.de`, `.internal`, `.local`, `.corp`) are
rejected before connect. Blocked URLs are logged at WARNING with
`mcp_url_blocked`.

## Run locally

```bash
cd agentic
pip install -r requirements.txt
uvicorn mcp_server.main:app --port 8080
```

Then:

```bash
curl -s localhost:8080/health
curl -s localhost:8080/rpc -H 'content-type: application/json' \
    -d '{"jsonrpc":"2.0","method":"list_tools","id":1}' | jq .
```

## Run inside the container (Task 2.2 image)

```bash
cd agentic/containers/mcp
./build_image.sh --fakeroot     # or --remote on the GWDG login node
apptainer run mcp.sif           # starts uvicorn on port 8080
```

The base image (Task 2.1) is the bootstrap layer; `Apptainer.def`
copies in the `mcp_server/` package and `pip install`s `pyflakes`.

## Configuration

All knobs are environment variables, prefixed `MCP_SERVER_`. The
ones you'll typically touch:

| Variable                              | Default                                | Notes                                       |
|---------------------------------------|----------------------------------------|---------------------------------------------|
| `MCP_SERVER_PORT`                     | `8080`                                 |                                             |
| `MCP_SERVER_FS_READ_ROOTS`            | `/workspace,/home/user`                | comma-separated                             |
| `MCP_SERVER_FS_WRITE_ROOTS`           | `/workspace`                           |                                             |
| `MCP_SERVER_FS_MAX_READ_BYTES`        | `10485760`                             | acceptance: 10 MB                           |
| `MCP_SERVER_FS_MAX_WRITE_BYTES`       | `1048576`                              | acceptance: 1 MB                            |
| `MCP_SERVER_WEB_SEARCH_PROVIDER`      | `stub`                                 | `stub` or `serpapi`                         |
| `MCP_SERVER_WEB_SEARCH_API_KEY`       | empty                                  | broker plumbs from Vault                    |
| `MCP_SERVER_WEB_PROXY_URL`            | empty (uses env)                       | broker plumbs `APPTAINERENV_HTTPS_PROXY`    |
| `MCP_SERVER_CODE_EXEC_MAX_TIMEOUT_S`  | `30`                                   | acceptance: 30 s                            |

## Tests

The test suite lives under `agentic/tests/` and is purely functional:

- `test_mcp_server.py` — JSON-RPC envelope handling, list_tools, dispatch
- `test_mcp_fs.py` — fs_read/fs_write/fs_list with path traversal, symlinks
- `test_mcp_web.py` — web_search (stub + serpapi via httpx mock), web_browse, IP filter
- `test_mcp_code.py` — code_exec timeout/output cap, code_check pyflakes parsing
- `test_apptainer_mcp.py` — static recipe validation (no apptainer needed)

```bash
cd agentic
pytest -q tests/test_mcp_*.py tests/test_apptainer_mcp.py
```

## Forward edits (not in this task)

- Inner sandbox for `code_exec` (Task 2.4 nsjail / bubblewrap).
- DNS-based URL filter for `web_browse` (Task 2.5 — relies on egress
  proxy enforcement, this server only does the IP-literal first pass).
- Streaming responses for `code_exec` (today: capture-and-return; the
  broker SSE hub already handles streaming if/when needed).
