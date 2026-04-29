#!/bin/sh
# entrypoint.sh — runscript glue for the chat-ai OpenHands image (Task 2.3).
#
# Kept thin: the actual orchestration is in Python
# (`openhands_runtime.launcher`) where it can be unit-tested. This
# script is just a 5-line bootstrap that ensures /workspace exists,
# changes into it, and execs the launcher under python3.11.
#
# POSIX sh.

set -eu

WORKSPACE="${OPENHANDS_OPENHANDS_WORKSPACE:-/workspace}"

# /workspace is normally bind-mounted by the broker. Create it as a
# fallback so a user running `apptainer run openhands.sif` without
# any --bind doesn't trip on a missing directory.
mkdir -p "$WORKSPACE"
cd "$WORKSPACE"

exec python3.11 -m openhands_runtime.launcher "$@"
