#!/bin/sh
# OpenCode session entry (Task 4.3): launcher starts MCP uvicorn → OpenCode run.
#
# Broker passes APPTAINERENV_OPENCODE_* and APPTAINERENV_* (OPENAI_* for cluster LLMs).
set -eu

export PYTHONPATH="${PYTHONPATH:-}:/opt/agentic"
WORKDIR="${HOME:-/workspace}"
mkdir -p "$WORKDIR"
cd "$WORKDIR"

exec python3.11 -m opencode_runtime.launcher "$@"
