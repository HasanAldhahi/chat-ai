"""Code-execution tools.

``code_exec``: launches an isolated Python subprocess with a timeout.
The subprocess inherits the container's environment and network policy
— the *outer* sandbox (Task 2.4 nsjail / Task 2.5 network filter) is
the load-bearing isolation. Inside this process we just enforce the
timeout and the stdout/stderr cap.

``code_check``: runs pyflakes against the snippet via ``-m pyflakes``.
A linter never throws on bad input — syntax errors, undefined names,
etc. become *messages*, not exceptions, which matches what an agent
expects when asking "is this code OK?".
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, List

from .. import config
from ..errors import ToolError, ToolErrorCode


def _settings():
    return config.get_settings()


def _truncate(stream: bytes, cap: int) -> tuple[str, bool]:
    if len(stream) <= cap:
        return stream.decode("utf-8", errors="replace"), False
    head = stream[:cap].decode("utf-8", errors="replace")
    return head + f"\n[...truncated, {len(stream) - cap} bytes dropped]", True


# --------------------------------------------------------------------------- #
# code_exec                                                                   #
# --------------------------------------------------------------------------- #

async def code_exec(args: Dict[str, Any]) -> Dict[str, Any]:
    code = args.get("code")
    if not isinstance(code, str):
        raise ToolError(
            code=ToolErrorCode.INVALID_PARAMS,
            message="`code` must be a string",
        )
    s = _settings()
    timeout = float(args.get("timeout_s") or s.code_exec_default_timeout_s)
    if timeout <= 0 or timeout > s.code_exec_max_timeout_s:
        raise ToolError(
            code=ToolErrorCode.INVALID_PARAMS,
            message=f"timeout_s must be in (0, {s.code_exec_max_timeout_s}]",
        )
    stdin_text = args.get("stdin", "") or ""

    proc = await asyncio.create_subprocess_exec(
        s.code_python_bin,
        "-I",  # ignore PYTHON* env vars and user site
        "-c",
        code,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    timed_out = False
    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(stdin_text.encode("utf-8")),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        timed_out = True
        proc.kill()
        # drain to completion so we don't leak transports
        try:
            stdout_b, stderr_b = await proc.communicate()
        except Exception:  # noqa: BLE001
            stdout_b, stderr_b = b"", b""

    cap = s.code_exec_max_output_bytes
    stdout, stdout_trunc = _truncate(stdout_b, cap)
    stderr, stderr_trunc = _truncate(stderr_b, cap)

    if timed_out:
        # Surface as a tool error so the agent knows to back off, but
        # still attach the captured streams so it can debug.
        raise ToolError(
            code=ToolErrorCode.EXEC_TIMEOUT,
            message=f"code_exec exceeded {timeout}s timeout",
            rpc_code=-32000,
            data={
                "stdout": stdout,
                "stderr": stderr,
                "timeout_s": timeout,
            },
        )

    return {
        "exit_code": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": stdout_trunc,
        "stderr_truncated": stderr_trunc,
        "timeout_s": timeout,
    }


# --------------------------------------------------------------------------- #
# code_check                                                                  #
# --------------------------------------------------------------------------- #

# pyflakes output looks like:  <stdin>:3:5: undefined name 'foo'
_PYFLAKES_LINE = re.compile(
    r"^<stdin>:(?P<line>\d+):(?:(?P<col>\d+):)?\s*(?P<message>.*)$"
)


async def code_check(args: Dict[str, Any]) -> Dict[str, Any]:
    code = args.get("code")
    if not isinstance(code, str):
        raise ToolError(
            code=ToolErrorCode.INVALID_PARAMS,
            message="`code` must be a string",
        )
    s = _settings()

    proc = await asyncio.create_subprocess_exec(
        s.code_python_bin,
        "-m",
        "pyflakes",
        # Do not pass ``-I`` here: isolated mode drops user/venv site-packages
        # so ``python -m pyflakes`` often fails to import pyflakes in dev images.
        # pyflakes reads stdin when no path args are given — `-` is
        # interpreted as a literal filename.
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(code.encode("utf-8")),
            timeout=s.code_exec_max_timeout_s,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise ToolError(
            code=ToolErrorCode.EXEC_TIMEOUT,
            message="code_check timed out (pyflakes hung?)",
            rpc_code=-32000,
        )

    if proc.returncode not in (0, 1):
        # pyflakes exits 0 (clean) or 1 (issues found). Anything else
        # is a real failure (e.g. pyflakes itself missing).
        raise ToolError(
            code=ToolErrorCode.EXEC_FAILED,
            message=(
                f"pyflakes exited with code {proc.returncode}: "
                f"{stderr_b.decode('utf-8', errors='replace').strip()}"
            ),
            rpc_code=-32000,
        )

    messages: List[Dict[str, Any]] = []
    for raw in stdout_b.decode("utf-8", errors="replace").splitlines():
        m = _PYFLAKES_LINE.match(raw)
        if not m:
            continue
        messages.append(
            {
                "line": int(m.group("line")),
                "column": int(m.group("col")) if m.group("col") else None,
                "message": m.group("message").strip(),
                "severity": "warning",
            }
        )

    return {
        "ok": not messages,
        "messages": messages,
    }
