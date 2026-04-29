#!/bin/sh
# test_image.sh — smoke test for Goose Apptainer image (Task 4.1).

set -eu

if [ $# -ne 1 ]; then
    echo "usage: $(basename "$0") <goose.sif>" >&2
    exit 1
fi

SIF="$1"
if [ ! -e "$SIF" ]; then
    echo "[fail] missing $SIF" >&2
    exit 1
fi

if command -v apptainer >/dev/null 2>&1; then
    APPTAINER=apptainer
elif command -v singularity >/dev/null 2>&1; then
    APPTAINER=singularity
else
    echo "[fail] apptainer/singularity required" >&2
    exit 1
fi

PASS=0
FAIL=0
check() {
    LABEL="$1"
    shift
    if "$@"; then
        printf "[ok]   %s\n" "$LABEL"
        PASS=$((PASS + 1))
    else
        printf "[fail] %s\n" "$LABEL"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== goose image smoke test: $SIF ==="

check "goose --version exits 0" \
    "$APPTAINER" exec "$SIF" goose --version

check "entrypoint executable" \
    "$APPTAINER" exec "$SIF" test -x /opt/agentic/entrypoint.sh

check "mcp_server importable (parent)" \
    "$APPTAINER" exec "$SIF" python3.11 -c "from mcp_server.main import app"

check "/etc/chat-ai-image-info present" \
    "$APPTAINER" exec "$SIF" grep -q "^image=goose\$" /etc/chat-ai-image-info

SIZE_BYTES=$(stat -c%s "$SIF" 2>/dev/null || stat -f%z "$SIF")
LIMIT_5GB=5368709120
if [ "$SIZE_BYTES" -le "$LIMIT_5GB" ]; then
    printf "[ok]   size <= 5 GB (%s bytes)\n" "$SIZE_BYTES"
    PASS=$((PASS + 1))
else
    printf "[fail] size exceeds 5 GB\n"
    FAIL=$((FAIL + 1))
fi

echo "=== summary: $PASS ok, $FAIL failed ==="
exit "$FAIL"
