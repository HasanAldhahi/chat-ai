#!/bin/sh
# build_all.sh — build all chat-ai agent images in dependency order.
#
# Order: base → mcp → goose
# Each image bootstraps from the previous via `Bootstrap: localimage`.
# Pass --fakeroot (workstation) or --remote (GWDG login node) as the
# first argument; it is forwarded to every build_image.sh call.
#
# Usage:
#   ./build_all.sh --fakeroot          # build all three
#   ./build_all.sh --fakeroot base mcp # build only base and mcp

set -eu

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
BUILDER_FLAG=""
FORCE=""
IMAGES="base mcp goose"

usage() {
    cat <<EOF
Usage: $(basename "$0") [--fakeroot|--remote] [--force] [image ...]

  --fakeroot    Build with fakeroot (workstation, needs /etc/subuid entry).
  --remote      Build with remote builder (GWDG login node).
  --force       Overwrite existing .sif files.
  image ...     Subset to build (default: base mcp goose).

Examples:
  ./build_all.sh --fakeroot
  ./build_all.sh --fakeroot --force
  ./build_all.sh --fakeroot base mcp
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --fakeroot) BUILDER_FLAG="--fakeroot" ;;
        --remote)   BUILDER_FLAG="--remote" ;;
        --force)    FORCE="--force" ;;
        -h|--help)  usage; exit 0 ;;
        base|mcp|goose|openhands|opencode) IMAGES="$*"; break ;;
        *) echo "unknown option: $1" >&2; usage >&2; exit 1 ;;
    esac
    shift
done

if [ -z "$BUILDER_FLAG" ] && [ "$(id -u)" -ne 0 ]; then
    echo "[fail] pass --fakeroot or --remote (or run as root)" >&2
    exit 1
fi

echo "[build_all] builder=$BUILDER_FLAG images=$IMAGES"

for img in $IMAGES; do
    dir="$SCRIPT_DIR/$img"
    if [ ! -d "$dir" ]; then
        echo "[warn] skipping unknown image dir: $dir" >&2
        continue
    fi
    echo ""
    echo "============================================================"
    echo " Building: $img"
    echo "============================================================"
    cd "$dir"
    ./build_image.sh $BUILDER_FLAG $FORCE --log
    cd "$SCRIPT_DIR"
done

echo ""
echo "[build_all] all done."
echo "[hint] copy .sif files to _out/ for use with local-exec mode:"
echo "  mkdir -p _out"
echo "  cp base/base.sif mcp/mcp.sif goose/goose.sif _out/"
