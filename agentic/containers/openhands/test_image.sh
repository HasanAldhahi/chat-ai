#!/bin/sh
# test_image.sh — runtime smoke for the chat-ai OpenHands image (Task 2.3).
#
# Exercises every Task 2.3 acceptance criterion that doesn't require a
# real vLLM endpoint or LLM token budget. The actual OpenHands→vLLM→MCP
# round-trip is exercised on the cluster with a configured vLLM service;
# this script verifies the image's *bootstrapping* layer works.
#
# Probes:
#   - openhands package importable (acceptance: OpenHands installed)
#   - openhands_runtime package importable (launcher / sse_forwarder)
#   - /etc/openhands/config.toml present and parseable as TOML
#   - launcher --version exits 0 (validates argparse wiring)
#   - launcher boots MCP and serves /health within timeout
#     (single command starts both — acceptance criterion)
#
# Usage: test_image.sh <path-to-openhands.sif>
#
# Exit code is 0 on full pass, otherwise the count of failed checks.

set -eu

if [ $# -ne 1 ]; then
    echo "usage: $(basename "$0") <path-to-openhands.sif>" >&2
    exit 1
fi

SIF="$1"

if [ ! -e "$SIF" ]; then
    echo "[fail] $SIF does not exist" >&2
    exit 1
fi

if command -v apptainer >/dev/null 2>&1; then
    APPTAINER=apptainer
elif command -v singularity >/dev/null 2>&1; then
    APPTAINER=singularity
else
    echo "[fail] apptainer/singularity not on PATH" >&2
    exit 1
fi

for tool in curl jq; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "[fail] $tool is required for this smoke test" >&2
        exit 1
    fi
done

PASS=0
FAIL=0

check() {
    LABEL="$1"; shift
    if "$@" >/dev/null 2>&1; then
        printf "[ok]   %s\n" "$LABEL"
        PASS=$((PASS + 1))
    else
        printf "[fail] %s\n" "$LABEL"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== chat-ai OpenHands image smoke test: $SIF ==="
echo

# ----- 1. python imports inside the image -----
check "openhands package importable" \
    "$APPTAINER" exec "$SIF" python3.11 -c "import openhands"

check "openhands_runtime package importable" \
    "$APPTAINER" exec "$SIF" python3.11 -c \
    "import openhands_runtime.launcher; import openhands_runtime.sse_forwarder"

check "tomli importable (config parser dep)" \
    "$APPTAINER" exec "$SIF" python3.11 -c "import tomli"

# ----- 2. config template present and valid TOML -----
check "/etc/openhands/config.toml present" \
    "$APPTAINER" exec "$SIF" test -s /etc/openhands/config.toml

check "/etc/openhands/config.toml parses as TOML" \
    "$APPTAINER" exec "$SIF" python3.11 -c \
    "import tomli; tomli.load(open('/etc/openhands/config.toml','rb'))"

# ----- 3. launcher --version exits 0 -----
check "launcher --version exits 0" \
    "$APPTAINER" exec "$SIF" python3.11 -m openhands_runtime.launcher --version

# ----- 4. mcp_server still importable from this image -----
check "mcp_server.main:app importable" \
    "$APPTAINER" exec "$SIF" python3.11 -c "from mcp_server.main import app"

# ----- 5. Single-command boot — launcher brings up MCP -----
# Pin the launcher to a synthetic OpenHands command (`/bin/cat`) so it
# doesn't actually need a vLLM endpoint or LLM tokens. Verifies that
# the launcher's MCP-up path works end-to-end inside the container.
PORT="${OPENHANDS_TEST_PORT:-18181}"
INSTANCE="openhands-smoke-$$"
WORKSPACE_DIR=$(mktemp -d)

cleanup() {
    set +e
    "$APPTAINER" instance stop "$INSTANCE" >/dev/null 2>&1 || true
    rm -rf "$WORKSPACE_DIR"
    set -e
}
trap cleanup EXIT INT TERM

APPTAINERENV_OPENHANDS_OPENHANDS_COMMAND=/bin/cat \
APPTAINERENV_OPENHANDS_BROKER_SSE_URL= \
APPTAINERENV_OPENHANDS_MCP_UVICORN_PORT="$PORT" \
APPTAINERENV_OPENHANDS_MCP_SERVER_URL="http://localhost:${PORT}" \
APPTAINERENV_OPENHANDS_OPENHANDS_MAX_RUNTIME_S=10 \
APPTAINERENV_MCP_SERVER_PORT="$PORT" \
    "$APPTAINER" instance start \
        --bind "$WORKSPACE_DIR:/workspace" \
        "$SIF" "$INSTANCE" >/dev/null 2>&1

ready=0
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
        ready=1
        break
    fi
    sleep 1
done
if [ "$ready" -eq 1 ]; then
    printf "[ok]   launcher brought MCP up on :%s\n" "$PORT"
    PASS=$((PASS + 1))
else
    printf "[fail] launcher did not bring MCP up on :%s within 20s\n" "$PORT"
    FAIL=$((FAIL + 1))
fi

# ----- 6. labels -----
echo "--- inspecting labels ---"
"$APPTAINER" inspect --labels "$SIF" 2>/dev/null | grep -E '^org\.chat-ai\.' || true

# ----- 7. size budget -----
SIZE_BYTES=$(stat -c%s "$SIF" 2>/dev/null || stat -f%z "$SIF")
LIMIT_5GB=5368709120
if [ "$SIZE_BYTES" -le "$LIMIT_5GB" ]; then
    printf "[ok]   size budget (%s bytes <= 5 GB)\n" "$SIZE_BYTES"
    PASS=$((PASS + 1))
else
    printf "[fail] size budget exceeded (%s bytes > 5 GB)\n" "$SIZE_BYTES"
    FAIL=$((FAIL + 1))
fi

echo
echo "=== summary: $PASS passed, $FAIL failed ==="

exit "$FAIL"
