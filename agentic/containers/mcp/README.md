# MCP Server Apptainer Image (Task 2.2)

Per-session MCP server image. Bootstraps from the base image
(Task 2.1) and adds the `mcp_server/` Python package plus
`pyflakes` (the only non-stdlib dep that isn't already in the base).

## What's exposed

The image's runscript starts:

```
uvicorn mcp_server.main:app --host 0.0.0.0 --port ${MCP_SERVER_PORT:-8080}
```

Two HTTP endpoints:

| Endpoint   | Purpose                                                 |
|------------|---------------------------------------------------------|
| `GET /health` | Liveness probe                                       |
| `POST /rpc`   | JSON-RPC 2.0: `list_tools`, `call_tool`              |

Seven tools: `fs_read`, `fs_write`, `fs_list`, `web_search`,
`web_browse`, `code_exec`, `code_check`. Boundaries are documented in
`agentic/mcp_server/README.md`.

## Build

The MCP image **bootstraps from `../base/base.sif`** via
`Bootstrap: localimage`. Build the base first:

```bash
cd agentic/containers/base && ./build_image.sh --fakeroot
cd ../mcp                  && ./build_image.sh --fakeroot
```

On the GWDG login node use `--remote` instead of `--fakeroot` (the
remote builder doesn't need subuid mapping):

```bash
module load apptainer
apptainer remote login   # one-time
cd agentic/containers/mcp
./build_image.sh --remote
```

Other useful invocations:

```bash
./build_image.sh --fakeroot --force                  # rebuild over existing
./build_image.sh --fakeroot --output /scratch/me/mcp.sif --log
./build_image.sh --fakeroot --sandbox                # writable dir, debug
./build_image.sh --help
```

Hard size ceiling: **5 GB** (acceptance criterion). Build script exits
4 if exceeded. Expected size: ~2–2.5 GB (base contributes most of it).

## Run

```bash
apptainer run mcp.sif                    # uvicorn on :8080
apptainer instance start mcp.sif mcp     # background instance
curl localhost:8080/health
curl localhost:8080/rpc -H 'content-type: application/json' \
    -d '{"jsonrpc":"2.0","method":"list_tools","id":1}' | jq .
```

### Standard bind set (production / per-session)

The broker invokes derived agent images with these binds. The MCP
image accepts the same set:

```bash
apptainer run \
    --bind "$SLURM_TMPDIR":/workspace \
    --bind "$HOME":/home/user:ro \
    mcp.sif
```

- `/workspace` = sticky-writable scratch (1777). The agent's tool
  calls land here.
- `/home/user` = per-user home. Read-only by default; sessions that
  need write access bind it `:rw`.

### Network

Apptainer's default is host-network-shared. The MCP server listens on
all interfaces inside the container, but bind it only to the per-
session container's loopback (or to a Slurm-managed isolated network
once Task 2.5 lands). The broker plumbs the proxy via:

```bash
APPTAINERENV_HTTPS_PROXY=http://www-cache.gwdg.de:3128 \
APPTAINERENV_NO_PROXY=localhost,127.0.0.1 \
apptainer run mcp.sif
```

## Validate

```bash
./test_image.sh ./mcp.sif
```

Exercises every Task 2.2 acceptance criterion:

- /health responds 200 with `tool_count == 8` (incl. `get_skills`)
- `list_tools` returns all eight tool names
- `fs_read /etc/passwd` blocked with `path_not_allowed`
- `fs_write` then `fs_read` round-trip on `/workspace`
- `web_browse http://127.0.0.1` blocked with `url_blocked`
- `code_exec` runs Python and computes a result
- `code_exec` timeout enforced
- `code_check` flags undefined names via pyflakes
- size ≤ 5 GB

The script's exit code is the count of failed checks (0 on full pass).

## Configuration

Env vars (prefix `MCP_SERVER_`) — see `agentic/mcp_server/README.md`
for the full list. The broker plumbs the per-session ones (search
API key, proxy) via `APPTAINERENV_*`.

## Trust model

The MCP server is unauthenticated by design: it lives inside the
per-session container and is reached over localhost by exactly one
client (the agent framework). Auth is the broker's responsibility
(X-User middleware, Task 1.7). Do not expose `:8080` outside the
container.

## Push to GWDG registry

> **TBD**: registry URL not yet confirmed. Likely
> `oras://<gwdg-harbor>/chat-ai/mcp:0.1.0` or shared FS path.

```bash
apptainer push mcp.sif oras://<gwdg-registry>/chat-ai/mcp:0.1.0
```

## Forward edits (not in this image)

- **Inner sandbox (Task 2.4)** — `code_exec` would run inside nsjail /
  bubblewrap. One-line addition to `%post`, plus a sandbox policy file.
- **Network filtering (Task 2.5)** — DNS-based URL filter for
  `web_browse`. Today the egress proxy + IP-literal blocklist is the
  defence; full DNS resolution against an internal blocklist is the
  task 2.5 deliverable.
- **Streaming responses for `code_exec`** — today: capture-and-return.
  The broker's SSE hub already handles streaming if/when needed.
