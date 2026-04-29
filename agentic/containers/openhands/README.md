# OpenHands Apptainer Image (Task 2.3)

Per-session image that runs OpenHands V1 against the in-container
MCP server and the cluster's vLLM. Bootstraps from the Task 2.2
MCP image (which itself derives from the Task 2.1 base).

## What's added on top of `mcp.sif`

| Layer                                | Source / pin                                           |
|--------------------------------------|--------------------------------------------------------|
| OpenHands V1                         | `pip install openhands-ai==0.13.0`                     |
| `openhands_runtime/`                 | Local package (launcher, sse_forwarder, config)        |
| `/etc/openhands/config.toml`         | Template — points OpenHands at the local MCP + vLLM    |
| `/opt/agentic/entrypoint.sh`         | Thin POSIX-sh stub that execs the Python launcher      |

The runscript launches:

```
python3.11 -m openhands_runtime.launcher
```

which in turn (single command — acceptance criterion):

1. Starts uvicorn for `mcp_server.main:app` on `${MCP_SERVER_PORT:-8080}`.
2. Polls `http://localhost:8080/health` until it returns 200 (timeout 20 s).
3. Spawns OpenHands with the env that points it at the local MCP, vLLM, and per-session HTTPS proxy.
4. Tails OpenHands stdout, posting each structured line to the broker's SSE endpoint as `action`/`result`/`error`/`message`.
5. On OpenHands exit (or the 30-min hard cap), tears down both children and exits cleanly.

See `agentic/openhands_runtime/README.md` for the orchestration details.

## Build

```bash
cd agentic/containers/base      && ./build_image.sh --fakeroot
cd ../mcp                       && ./build_image.sh --fakeroot
cd ../openhands                 && ./build_image.sh --fakeroot
```

`build_image.sh` refuses to run if `../mcp/mcp.sif` is missing.

GWDG login node (`--remote` instead of `--fakeroot`):

```bash
module load apptainer
apptainer remote login   # one-time
cd agentic/containers/openhands
./build_image.sh --remote
```

Hard size ceiling: **5 GB** (acceptance criterion). Build script exits 4 if exceeded. Expected size: ~2.5–3 GB.

## Run (per-session, broker-injected)

```bash
APPTAINERENV_OPENHANDS_SESSION_ID=sess-001 \
APPTAINERENV_OPENHANDS_USER_ID=alice@gwdg \
APPTAINERENV_OPENHANDS_BROKER_SSE_URL=http://broker:8001 \
APPTAINERENV_OPENHANDS_LLM_API_URL=http://vllm.cluster/v1/completions \
APPTAINERENV_OPENHANDS_LLM_MODEL=qwen3-30b \
APPTAINERENV_HTTPS_PROXY=http://www-cache.gwdg.de:3128 \
    apptainer run \
        --bind "$SLURM_TMPDIR":/workspace \
        --bind "$HOME":/home/user:ro \
        openhands.sif
```

The broker (`agentic/app/clients/slurm.py`) sets these via the Slurm
job spec; this is what an operator-driven manual smoke looks like.

## Validate

```bash
./test_image.sh ./openhands.sif
```

Probes (no real vLLM needed):

- `import openhands` succeeds inside the image
- `import openhands_runtime.launcher` and `.sse_forwarder` succeed
- `/etc/openhands/config.toml` is parseable as TOML
- `python3.11 -m openhands_runtime.launcher --version` exits 0
- launcher boots MCP and `/health` responds 200 within 20 s
  (uses `/bin/cat` as a synthetic OpenHands command so the smoke
  doesn't depend on a real LLM endpoint)
- size ≤ 5 GB
- labels show `org.chat-ai.task=2.3` and `org.chat-ai.parent=mcp`

The script's exit code is the count of failed checks (0 on full pass).

## OpenHands V1 pin — verify before production

OpenHands V1 ships fast. The recipe pins `openhands-ai==0.13.0` (and
`tomli==2.0.1` for the TOML config). Before promoting this image to a
shared registry:

1. `apptainer inspect --labels openhands.sif` — confirms what landed.
2. Diff `/etc/openhands/config.toml` against the OpenHands V1 release
   notes for that pin — the TOML schema is not yet semver-stable.
3. Run a vLLM-backed smoke (full `OpenHands → MCP fs_read` round-trip)
   on the cluster.

If OpenHands V1 ships breaking changes to the config schema or MCP
client, fix the version in `Apptainer.def %post`, regenerate
`openhands_config.toml`, and bump `org.chat-ai.version`.

## Trust model

OpenHands runs in **OpenHands' `local` runtime mode** (no inner Docker
or Podman) — the per-session Apptainer container *is* the sandbox.
That choice matches the spec's acceptance criterion ("OpenHands runs
without Docker/Podman, uses Apptainer only") and avoids
container-in-container nesting on the cluster.

Inner-process isolation for browser / code-exec is Task 2.4
(nsjail / bubblewrap). This image is a no-op for that — Task 2.4
threads its sandbox into the Task 2.2 MCP server's `code_exec` and
`web_browse` tools, which are the only network/code surface this
image inherits.

## Push to GWDG registry

> **TBD**: registry URL not yet confirmed. Likely
> `oras://<gwdg-harbor>/chat-ai/openhands:0.1.0` or shared FS path.

```bash
apptainer push openhands.sif oras://<gwdg-registry>/chat-ai/openhands:0.1.0
```
