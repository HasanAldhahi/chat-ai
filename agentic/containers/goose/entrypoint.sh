#!/bin/sh
# Default session entry — Goose orchestrator (Task 4.1).
#
# Broker sets APPTAINERENV_GOOSE_* and APPTAINERENV_* for MCP / SSE / HOME.
set -eu

export PYTHONPATH="${PYTHONPATH:-}:/opt/agentic"
WORKDIR="${HOME:-/workspace}"
mkdir -p "$WORKDIR"
cd "$WORKDIR"

exec python3.11 -m goose_runtime.launcher "$@"
