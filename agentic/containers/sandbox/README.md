# Inner sandbox utilities (Task 2.4)

Ships with the **base** Apptainer image under `/opt/chat-ai/sandbox/` (see
`containers/base/Apptainer.def`: `bubblewrap` + `chrome-headless-sandbox.sh`).

## Why bubblewrap

**Lighter** than nsjail; sufficient for **filesystem** isolation (private
`/tmp`, read-only system tree) inside the already Apptainer-wrapped workload.
**nsjail** remains an optional future swap if we need stricter cgroup limits.

## `chrome-headless-sandbox.sh`

Wrapper around `google-chrome-stable` + `bwrap`. Use this when Playwright /
browser-use launches Chrome so the renderer does not read the container’s
host-wide `/tmp` scratch.

```bash
apptainer exec --bind "$SCRATCH:/workspace" base.sif \
    /opt/chat-ai/sandbox/chrome-headless-sandbox.sh \
    --headless --disable-gpu --no-sandbox --dump-dom https://example.com
```

Set `CHAT_AI_BROWSER_NET_ISOLATION=1` only for tests that must prove no
outbound sockets (normal agent workloads need network via proxy — Task 2.5).

## Acceptance mapping

- **bubblewrap installed**: base `%post` `apt-get install bubblewrap`.
- **Browser via wrapper**: cluster operator runs `test_image.sh` (checks
  `bwrap` + wrapper + `--version`).
- **Cannot read container `/tmp`**: the sandbox mounts a **fresh** tmpfs on
  `/tmp`; files written only in the outer namespace are not visible (verified
  manually or with a follow-up integration test on a build host).
