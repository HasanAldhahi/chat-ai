# Goose agent image (Task 4.1)

Apptainer recipe for **[AAIF Goose](https://github.com/aaif-goose/goose)** plus [**`goose_runtime/`](../../goose_runtime/)**: MCP server bootstrap, Goose headless **`run --no-session`**, and SSE forwarding toward the broker (same envelope as OpenHands).

## Prerequisites

Build [`../base/base.sif`](../base/), then [`../mcp/mcp.sif`](../mcp/).

## Build

```bash
cd agentic/containers/goose
chmod +x build_image.sh entrypoint.sh test_image.sh
./build_image.sh --fakeroot
```

## Default run inside Slurm/container

Runs:

```bash
python3.11 -m goose_runtime.launcher
```

Broker injects **`GOOSE_*`**, **`APPTAINERENV_HTTPS_PROXY`**, vLLM/LLM env, **`HOME=/workspace`** (bind mount).

## Smoke test

After `goose.sif` exists:

```bash
./test_image.sh ./goose.sif
```

Broker integration exercises vLLM + real Goose headless prompts on the cluster; local smoke skips LLM credentials when **`GOOSE_DEV_COMMAND_OVERRIDE=/bin/true`**.
