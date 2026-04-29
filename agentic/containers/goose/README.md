# Goose agent image (Task 4.1)

Apptainer recipe for the **[AAIF Goose](https://github.com/aaif-goose/goose)** CLI alongside the MCP server stack inherited from [`../mcp/`](../mcp/).

## Prerequisites

Built [`../base/base.sif`](../base/) and [`../mcp/mcp.sif`](../mcp/) first (`build_image.sh` in each).

## Build

```bash
cd agentic/containers/goose
chmod +x build_image.sh entrypoint.sh test_image.sh
./build_image.sh --fakeroot
# -> goose.sif, goose.sif.meta.json
```

Outgoing HTTPS needed during `%post` to download the Goose release tarball (GitHub).

## Smoke test

```bash
./test_image.sh ./goose.sif
```

Cluster integration (broker → Slurm → `apptainer run goose.sif …`, MCP + vLLM round-trip) mirrors OpenHands documented in [`../openhands/README.md`](../openhands/).

## Runtime env (broker-supplied)

| Variable | Typical |
|----------|---------|
| `MCP_SERVER_URL` | `http://localhost:{port}` inside container |
| `LLM_*` / OpenAI-compat | Broker injects cluster vLLM URL |
| `HTTPS_PROXY` / `HTTP_PROXY` | GWW-Cache |

Full **launcher** parity (`openhands_runtime.launcher`: boot MCP → wait `/health` → agent → SSE toward broker) is tracked as follow-up work on Task 4.1; entrypoint defaults to `goose --help` unless argv is supplied.
