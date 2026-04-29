#!/bin/sh
# build_image.sh — build the chat-ai OpenCode (sst/opencode) Apptainer image (Task 4.3).
#
# Bootstraps from ../mcp/mcp.sif (Task 2.2). POSIX sh.
#
# Exit codes: same as openhands/build_image.sh

set -eu

set +e
SCRIPT_DIR=$(cd "$(dirname "$0")" 2>/dev/null && pwd)
set -e
DEF="${SCRIPT_DIR}/Apptainer.def"
PARENT_SIF="${SCRIPT_DIR}/../mcp/mcp.sif"

OUTPUT="${SCRIPT_DIR}/opencode.sif"
FORCE=""
BUILDER_FLAG=""
SANDBOX=""
LOG_FILE=""

usage() {
    cat <<EOF
Usage: $(basename "$0") [options]

Builds the OpenCode agent image (Task 4.3) from ../mcp/mcp.sif.

Options match openhands/build_image.sh: --fakeroot, --remote, --force,
--sandbox, --output PATH, --log, -h/--help.

Note: build base.sif and mcp.sif first.
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --fakeroot)   BUILDER_FLAG="--fakeroot" ;;
        --remote)     BUILDER_FLAG="--remote" ;;
        --force)      FORCE="--force" ;;
        --sandbox)    SANDBOX="--sandbox" ;;
        --output)     shift; [ $# -gt 0 ] || { echo "missing arg for --output" >&2; exit 1; }; OUTPUT="$1" ;;
        --output=*)   OUTPUT="${1#--output=}" ;;
        --log)        LOG_FILE="auto" ;;
        -h|--help)    usage; exit 0 ;;
        *)            echo "unknown option: $1" >&2; usage >&2; exit 1 ;;
    esac
    shift
done

if command -v apptainer >/dev/null 2>&1; then
    APPTAINER=apptainer
elif command -v singularity >/dev/null 2>&1; then
    APPTAINER=singularity
    echo "[warn] using singularity fallback" >&2
else
    echo "[fail] apptainer/singularity not on PATH" >&2
    exit 2
fi

if [ ! -f "$DEF" ]; then
    echo "[fail] recipe not found: $DEF" >&2
    exit 1
fi

if [ ! -f "$PARENT_SIF" ]; then
    echo "[fail] parent image not found: $PARENT_SIF — build mcp first." >&2
    exit 1
fi

OUTPUT_DIR=$(dirname "$OUTPUT")
if [ ! -d "$OUTPUT_DIR" ]; then
    echo "[fail] output directory missing: $OUTPUT_DIR" >&2
    exit 1
fi
if [ ! -w "$OUTPUT_DIR" ]; then
    echo "[fail] output directory not writable: $OUTPUT_DIR" >&2
    exit 1
fi
if [ -e "$OUTPUT" ] && [ -z "$FORCE" ]; then
    echo "[fail] $OUTPUT exists; use --force" >&2
    exit 1
fi

if [ -z "$BUILDER_FLAG" ] && [ "$(id -u)" -ne 0 ]; then
    echo "[fail] specify --fakeroot or --remote (or run as root)." >&2
    exit 1
fi

GIT_SHA=$(git -C "$SCRIPT_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)
BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)

if [ -n "$LOG_FILE" ]; then
    LOG_FILE="${OUTPUT}.log"
    echo "[info] logging to $LOG_FILE"
fi

echo "[info] output: $OUTPUT"

export APPTAINERENV_BUILD_SHA="$GIT_SHA"
export APPTAINERENV_BUILD_DATE="$BUILD_DATE"
export SINGULARITYENV_BUILD_SHA="$GIT_SHA"
export SINGULARITYENV_BUILD_DATE="$BUILD_DATE"

set +e
if [ -n "$LOG_FILE" ]; then
    RC_FILE=$(mktemp)
    ( "$APPTAINER" build $FORCE $BUILDER_FLAG $SANDBOX "$OUTPUT" "$DEF" 2>&1; echo $? > "$RC_FILE" ) | tee "$LOG_FILE"
    BUILD_RC=$(cat "$RC_FILE")
    rm -f "$RC_FILE"
else
    "$APPTAINER" build $FORCE $BUILDER_FLAG $SANDBOX "$OUTPUT" "$DEF"
    BUILD_RC=$?
fi
set -e

if [ "$BUILD_RC" -ne 0 ]; then
    echo "[fail] apptainer build exited $BUILD_RC" >&2
    exit 3
fi

if [ -n "$SANDBOX" ]; then
    echo "[ok] sandbox: $OUTPUT"
    exit 0
fi

"$APPTAINER" inspect --labels "$OUTPUT" || true
SIZE_BYTES=$(stat -c%s "$OUTPUT" 2>/dev/null || stat -f%z "$OUTPUT")
LIMIT_5GB=5368709120
if [ "$SIZE_BYTES" -gt "$LIMIT_5GB" ]; then
    echo "[fail] image exceeds 5 GB" >&2
    exit 4
fi

META="${OUTPUT}.meta.json"
cat > "$META" <<EOF
{
  "image": "opencode",
  "task": "4.3",
  "version": "0.1.0",
  "parent": "mcp",
  "git_sha": "${GIT_SHA}",
  "build_date": "${BUILD_DATE}",
  "size_bytes": ${SIZE_BYTES},
  "path": "${OUTPUT}"
}
EOF
echo "[ok] $OUTPUT"
exit 0
