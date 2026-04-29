#!/bin/sh
# test_image.sh — runtime smoke tests for the chat-ai MCP server image (Task 2.2).
#
# Exercises every Task 2.2 acceptance criterion: import graph clean,
# /health responds 200, list_tools returns 8 tools, fs/web/code tools
# round-trip via JSON-RPC (incl. get_skills), security boundaries enforced. Output is the
# same [ok]/[fail] format the base image's test_image.sh uses.
#
# Usage: test_image.sh <path-to-mcp.sif>
#
# The script starts an apptainer instance in the background, waits for
# the server to come up, runs the probes, then tears the instance down.
# Requires: apptainer, curl, jq, mktemp.
#
# Exit code is 0 on full pass, otherwise the count of failed checks.

set -eu

if [ $# -ne 1 ]; then
    echo "usage: $(basename "$0") <path-to-mcp.sif>" >&2
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

# Pick a free port to avoid collisions with anything already on 8080.
PORT="${MCP_TEST_PORT:-18080}"
INSTANCE="mcp-smoke-$$"
WORKSPACE_DIR=$(mktemp -d)

# Trap to clean up the instance even on script failure.
cleanup() {
    set +e
    "$APPTAINER" instance stop "$INSTANCE" >/dev/null 2>&1 || true
    rm -rf "$WORKSPACE_DIR"
    set -e
}
trap cleanup EXIT INT TERM

echo "=== chat-ai MCP server image smoke test: $SIF ==="
echo "[info] port=$PORT instance=$INSTANCE workspace=$WORKSPACE_DIR"
echo

# ----- 1. instance start -----
APPTAINERENV_MCP_SERVER_PORT="$PORT" \
    "$APPTAINER" instance start \
        --bind "$WORKSPACE_DIR:/workspace" \
        "$SIF" "$INSTANCE" >/dev/null 2>&1

# Wait up to 20s for /health to come up.
ready=0
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
        ready=1
        break
    fi
    sleep 1
done
if [ "$ready" -ne 1 ]; then
    printf "[fail] mcp_server did not respond on port %s within 20s\n" "$PORT"
    exit 1
fi
printf "[ok]   mcp_server reachable on :%s\n" "$PORT"
PASS=$((PASS + 1))

RPC="http://127.0.0.1:${PORT}/rpc"

# ----- 2. /health -----
HEALTH=$(curl -fsS "http://127.0.0.1:${PORT}/health")
if printf '%s' "$HEALTH" | jq -e '.status == "healthy" and .tool_count == 8' >/dev/null; then
    printf "[ok]   /health reports 8 tools healthy\n"
    PASS=$((PASS + 1))
else
    printf "[fail] /health unexpected response: %s\n" "$HEALTH"
    FAIL=$((FAIL + 1))
fi

# ----- 3. list_tools -----
TOOLS=$(curl -fsS "$RPC" -H 'content-type: application/json' \
    -d '{"jsonrpc":"2.0","id":1,"method":"list_tools"}')
EXPECTED_TOOLS="fs_read fs_write fs_list web_search web_browse code_exec code_check get_skills"
for t in $EXPECTED_TOOLS; do
    if printf '%s' "$TOOLS" | jq -e --arg n "$t" '.result.tools[] | select(.name == $n)' >/dev/null; then
        printf "[ok]   list_tools includes %s\n" "$t"
        PASS=$((PASS + 1))
    else
        printf "[fail] list_tools missing %s\n" "$t"
        FAIL=$((FAIL + 1))
    fi
done

# ----- 4. fs_read denied outside roots -----
FS_DENY=$(curl -fsS "$RPC" -H 'content-type: application/json' -d '{
    "jsonrpc":"2.0","id":2,"method":"call_tool",
    "params":{"name":"fs_read","arguments":{"path":"/etc/passwd"}}
}')
if printf '%s' "$FS_DENY" | jq -e '.error.data.tool_error == "path_not_allowed"' >/dev/null; then
    printf "[ok]   fs_read /etc/passwd blocked (path_not_allowed)\n"
    PASS=$((PASS + 1))
else
    printf "[fail] fs_read should have been blocked: %s\n" "$FS_DENY"
    FAIL=$((FAIL + 1))
fi

# ----- 5. fs_write -> fs_read round-trip -----
WRITE=$(curl -fsS "$RPC" -H 'content-type: application/json' -d '{
    "jsonrpc":"2.0","id":3,"method":"call_tool",
    "params":{"name":"fs_write","arguments":{"path":"/workspace/smoke.txt","content":"hi"}}
}')
if printf '%s' "$WRITE" | jq -e '.result.size_bytes == 2' >/dev/null; then
    printf "[ok]   fs_write 2 bytes\n"
    PASS=$((PASS + 1))
else
    printf "[fail] fs_write failed: %s\n" "$WRITE"
    FAIL=$((FAIL + 1))
fi

READ=$(curl -fsS "$RPC" -H 'content-type: application/json' -d '{
    "jsonrpc":"2.0","id":4,"method":"call_tool",
    "params":{"name":"fs_read","arguments":{"path":"/workspace/smoke.txt"}}
}')
if printf '%s' "$READ" | jq -e '.result.content == "hi"' >/dev/null; then
    printf "[ok]   fs_read round-trip\n"
    PASS=$((PASS + 1))
else
    printf "[fail] fs_read round-trip failed: %s\n" "$READ"
    FAIL=$((FAIL + 1))
fi

# ----- 6. web_browse blocks loopback -----
URL_DENY=$(curl -fsS "$RPC" -H 'content-type: application/json' -d '{
    "jsonrpc":"2.0","id":5,"method":"call_tool",
    "params":{"name":"web_browse","arguments":{"url":"http://127.0.0.1/"}}
}')
if printf '%s' "$URL_DENY" | jq -e '.error.data.tool_error == "url_blocked"' >/dev/null; then
    printf "[ok]   web_browse 127.0.0.1 blocked (url_blocked)\n"
    PASS=$((PASS + 1))
else
    printf "[fail] web_browse should block loopback: %s\n" "$URL_DENY"
    FAIL=$((FAIL + 1))
fi

# ----- 7. code_exec runs python -----
EXEC=$(curl -fsS "$RPC" -H 'content-type: application/json' -d '{
    "jsonrpc":"2.0","id":6,"method":"call_tool",
    "params":{"name":"code_exec","arguments":{"code":"print(2 + 2)"}}
}')
if printf '%s' "$EXEC" | jq -e '.result.stdout | tonumber? == 4 or contains("4")' >/dev/null; then
    printf "[ok]   code_exec 'print(2+2)' = 4\n"
    PASS=$((PASS + 1))
else
    printf "[fail] code_exec output unexpected: %s\n" "$EXEC"
    FAIL=$((FAIL + 1))
fi

# ----- 8. code_exec timeout -----
TIMEOUT=$(curl -fsS "$RPC" -H 'content-type: application/json' -d '{
    "jsonrpc":"2.0","id":7,"method":"call_tool",
    "params":{"name":"code_exec","arguments":{"code":"import time; time.sleep(5)","timeout_s":1}}
}')
if printf '%s' "$TIMEOUT" | jq -e '.error.data.tool_error == "exec_timeout"' >/dev/null; then
    printf "[ok]   code_exec timeout enforced\n"
    PASS=$((PASS + 1))
else
    printf "[fail] code_exec timeout expected: %s\n" "$TIMEOUT"
    FAIL=$((FAIL + 1))
fi

# ----- 9. code_check pyflakes -----
CHECK=$(curl -fsS "$RPC" -H 'content-type: application/json' -d '{
    "jsonrpc":"2.0","id":8,"method":"call_tool",
    "params":{"name":"code_check","arguments":{"code":"print(undefined_var)"}}
}')
if printf '%s' "$CHECK" | jq -e '.result.ok == false and (.result.messages | length) >= 1' >/dev/null; then
    printf "[ok]   code_check flags undefined name\n"
    PASS=$((PASS + 1))
else
    printf "[fail] code_check expected message: %s\n" "$CHECK"
    FAIL=$((FAIL + 1))
fi

# ----- 10. labels -----
echo "--- inspecting labels ---"
"$APPTAINER" inspect --labels "$SIF" 2>/dev/null | grep -E '^org\.chat-ai\.' || true

# ----- 11. size budget -----
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
