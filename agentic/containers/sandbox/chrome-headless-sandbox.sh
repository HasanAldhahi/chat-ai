#!/bin/sh
# chrome-headless-sandbox.sh — run Chrome inside bubblewrap (Task 2.4)
#
# Isolates the browser from the container's real /tmp and /var/tmp (tmpfs
# namespaces inside the sandbox) and keeps system dirs read-only. Proxy
# (HTTP_PROXY / HTTPS_PROXY) is inherited — egress policy is Task 2.5.
#
# POSIX sh — no bashisms.
#
set -eu

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    cat <<'EOF'
Usage: chrome-headless-sandbox.sh [--] [args to google-chrome-stable...]

Runs google-chrome-stable under bubblewrap with:
  - ro-bind: /usr /bin /sbin /lib /lib64 /etc /opt/google/chrome
  - tmpfs: /tmp /var/tmp (browser does not see the container's global temp)
  - writable HOME: CHROME_SANDBOX_HOME or a fresh dir under /workspace (else /tmp)

Environment:
  CHROME_SANDBOX_HOME        Writable profile directory (created if missing).
  CHAT_AI_BROWSER_NET_ISOLATION=1
                             Adds --unshare-net to bwrap (browser cannot
                             open sockets; only for tight tests — breaks
                             normal browsing).

This helper is the integration point for Playwright / browser-use: point
CHROME_PATH or launch flags at this script instead of invoking Chrome
directly.

EOF
    exit 0
fi

if ! command -v bwrap >/dev/null 2>&1; then
    echo "chrome-headless-sandbox.sh: bwrap (bubblewrap) not found" >&2
    exit 127
fi

if ! command -v google-chrome-stable >/dev/null 2>&1; then
    echo "chrome-headless-sandbox.sh: google-chrome-stable not found" >&2
    exit 127
fi

if [ -n "${CHROME_SANDBOX_HOME:-}" ]; then
    HOME_DIR="$CHROME_SANDBOX_HOME"
else
    if [ -d /workspace ] 2>/dev/null && [ -w /workspace ] 2>/dev/null; then
        HOME_DIR=$(mktemp -d /workspace/chrome-sbox.XXXXXX)
    else
        HOME_DIR=$(mktemp -d /tmp/chrome-sbox.XXXXXX)
    fi
fi
mkdir -p "$HOME_DIR"

NET_ARGS=""
if [ "${CHAT_AI_BROWSER_NET_ISOLATION:-0}" = "1" ]; then
    NET_ARGS="--unshare-net"
fi

case "${1:-}" in
-- )
    shift
    ;;
esac

exec bwrap \
    --die-with-parent \
    --new-session \
    $NET_ARGS \
    --proc /proc \
    --dev /dev \
    --ro-bind /usr /usr \
    --ro-bind /bin /bin \
    --ro-bind /sbin /sbin \
    --ro-bind /lib /lib \
    --ro-bind /lib64 /lib64 \
    --ro-bind /etc /etc \
    --ro-bind /opt/google/chrome /opt/google/chrome \
    --tmpfs /tmp \
    --tmpfs /var/tmp \
    --bind "$HOME_DIR" "$HOME_DIR" \
    --setenv HOME "$HOME_DIR" \
    --chdir "$HOME_DIR" \
    --setenv TMPDIR /tmp \
    /usr/bin/google-chrome-stable "$@"
