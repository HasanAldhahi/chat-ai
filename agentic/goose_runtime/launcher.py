"""Launch MCP uvicorn → wait /health → run Goose CLI with broker SSE ingest."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import shlex
import signal
import sys
from pathlib import Path
from typing import AsyncIterator, List, Optional

from openhands_runtime.launcher import wait_for_health
from openhands_runtime.sse_forwarder import forward_stream

from . import __version__
from . import config as cfg_module
from .goose_yaml import write_goose_config

log = logging.getLogger("goose-runtime-launcher")


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


async def _start_mcp(port: int) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "uvicorn",
        "mcp_server.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(port),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.STDOUT,
    )


async def _stream_lines(reader: asyncio.StreamReader) -> AsyncIterator[str]:
    while True:
        line = await reader.readline()
        if not line:
            return
        yield line.decode("utf-8", errors="replace")


def _build_goose_argv(settings: cfg_module.GooseSettings) -> List[str]:
    if settings.dev_command_override.strip():
        return shlex.split(settings.dev_command_override)
    return [settings.goose_cli, *shlex.split(settings.goose_run_extra), "-t", settings.session_prompt]


def _build_goose_env(settings: cfg_module.GooseSettings) -> dict:
    env = dict(os.environ)
    py_path = env.get("PYTHONPATH", "")
    extra_py = "/opt/agentic"
    env["PYTHONPATH"] = (
        f"{extra_py}:{py_path}".rstrip(":")
        if py_path and extra_py not in py_path
        else (py_path or extra_py)
    )
    env.setdefault("HOME", settings.home_dir)
    env.setdefault(
        "XDG_CONFIG_HOME", str(Path(settings.home_dir) / ".config")
    )
    env["GOOSE_MODE"] = settings.goose_mode
    env["GOOSE_CONTEXT_STRATEGY"] = settings.goose_context_strategy
    env["GOOSE_DISABLE_SESSION_NAMING"] = "true"
    if settings.llm_provider:
        env.setdefault("GOOSE_PROVIDER", settings.llm_provider)
    return env


async def _terminate(proc: asyncio.subprocess.Process, name: str, grace_s: float = 5.0) -> None:
    if proc.returncode is not None:
        return
    log.info("terminating", extra={"child": name})
    try:
        proc.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=grace_s)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            return
        await proc.wait()


async def run(settings: Optional[cfg_module.GooseSettings] = None) -> int:
    settings = settings or cfg_module.get_settings()
    _configure_logging(settings.log_level)
    log.info(
        "goose.launcher.start",
        extra={
            "version": __version__,
            "session_id": settings.session_id,
            "broker_sse": settings.broker_sse_url or "(off)",
        },
    )

    port = settings.mcp_uvicorn_port
    rpc_url = settings.mcp_server_url.rstrip("/") + "/rpc"
    cfg_path = write_goose_config(home=Path(settings.home_dir), rpc_url=rpc_url)
    log.info("goose.config.written", extra={"path": str(cfg_path)})

    os.environ.setdefault("MCP_SERVER_AGENT_FRAMEWORK", "goose")

    health_url = f"http://127.0.0.1:{port}/health"

    mcp = await _start_mcp(port)
    ok = await wait_for_health(
        health_url,
        timeout_s=settings.mcp_health_timeout_s,
        interval_s=settings.mcp_health_poll_interval_s,
    )
    if not ok:
        log.error(
            "mcp_health_timeout",
            extra={"timeout_s": settings.mcp_health_timeout_s},
        )
        await _terminate(mcp, "mcp")
        return 2

    log.info("mcp.ready")

    argv = _build_goose_argv(settings)
    proc = await asyncio.create_subprocess_exec(
        *argv,
        env=_build_goose_env(settings),
        cwd=settings.home_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    async def goose_lines() -> AsyncIterator[str]:
        async for ln in _stream_lines(proc.stdout):  # type: ignore[arg-type]
            yield ln

    forward_task = asyncio.create_task(
        forward_stream(
            lines=goose_lines(),
            broker_sse_url=settings.broker_sse_url,
            session_id=settings.session_id,
            user_id=settings.user_id,
            timeout_s=settings.sse_post_timeout_s,
            max_inflight=settings.sse_max_inflight,
        ),
        name="goose-sse-forward",
    )

    rc = 1
    try:
        rc_val = await asyncio.wait_for(
            proc.wait(), timeout=settings.goose_max_runtime_s,
        )
        rc = int(rc_val) if rc_val is not None else 1
    except asyncio.TimeoutError:
        log.error("goose_runtime_cap", extra={"s": settings.goose_max_runtime_s})
        await _terminate(proc, "goose")
        rc = 124
    finally:
        try:
            await asyncio.wait_for(forward_task, timeout=30.0)
        except asyncio.TimeoutError:
            forward_task.cancel()

    await _terminate(mcp, "mcp")

    log.info("goose.launcher.done", extra={"goose_rc": rc})
    return rc


def _signals(loop: asyncio.AbstractEventLoop) -> None:
    def _h(signum):
        log.warning("signal", extra={"n": signum})
        for t in asyncio.all_tasks(loop):
            t.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _h, sig)
        except NotImplementedError:
            pass


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="goose-runtime-launcher")
    p.add_argument("--version", action="version", version=__version__)
    p.parse_args(argv)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _signals(loop)
    try:
        return loop.run_until_complete(run())
    finally:
        loop.close()


if __name__ == "__main__":
    sys.exit(main())
