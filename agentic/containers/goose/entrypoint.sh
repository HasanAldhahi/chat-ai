#!/bin/sh
# entrypoint.sh — Goose image default run (Task 4.1).
# Broker may override argv; default is goose --help (non-interactive sanity).
#
# POSIX sh.

set -eu

WORKSPACE="${GOOSE_WORKSPACE:-/workspace}"
mkdir -p "$WORKSPACE"
cd "$WORKSPACE"

if [ "$#" -gt 0 ]; then
  exec goose "$@"
fi

exec goose --help
