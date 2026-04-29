"""Per-session launcher: MCP server + OpenHands + SSE forwarding.

The Apptainer image's ``%runscript`` invokes:

    python3.11 -m openhands_runtime.launcher

…which:

1. Starts ``uvicorn mcp_server.main:app`` on ``${MCP_SERVER_PORT}``
   in a child process.
2. Polls ``http://localhost:<port>/health`` until either it returns
   200 or ``mcp_health_timeout_s`` elapses.
3. Spawns OpenHands as a child process with the env that points it
   at the local MCP server, vLLM, and proxy.
4. Reads OpenHands stdout line-by-line, hands each line to
   :mod:`openhands_runtime.sse_forwarder`, which posts to the
   broker's SSE endpoint.
5. On Ctrl-C / SIGTERM / OpenHands exit / hard-cap timeout, tears
   down children and exits.

Every step is small and individually testable. The end-to-end
orchestration is exercised on the cluster (``test_image.sh``); the
unit tests cover wait-for-health, env construction, and clean
teardown.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import shlex
import signal
import sys
from typing import AsyncIterator, Dict, List, Optional

import httpx

from . import __version__, config
from .sse_forwarder import forward_stream


log = logging.getLogger("openhands-launcher")


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


# --------------------------------------------------------------------------- #
# /health probe                                                               #
# --------------------------------------------------------------------------- #

async def wait_for_health(
    url: str,
    *,
    timeout_s: float,
    interval_s: float,
    http_client: Optional[httpx.AsyncClient] = None,
) -> bool:
    """Poll ``url`` until it returns 200 or ``timeout_s`` elapses.

    Returns True on success, False on timeout. Connection errors are
    expected during startup and are silently retried.
    """
    deadline = asyncio.get_event_loop().time() + timeout_s
    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=interval_s)
    try:
        while asyncio.get_event_loop().time() < deadline:
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    return True
            except httpx.HTTPError:
                pass
            await asyncio.sleep(interval_s)
    finally:
        if owns_client:
            await client.aclose()
    return False


# --------------------------------------------------------------------------- #
# Env construction                                                            #
# --------------------------------------------------------------------------- #

def build_openhands_env(
    settings: config.OpenHandsSettings,
    *,
    base_env: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Build the env dict to hand to the OpenHands subprocess.

    Starts from ``base_env`` (or os.environ), then overlays the keys
    that bind OpenHands to *this* container's MCP server, vLLM, and
    proxy. Pulled out as a pure function so tests can assert on the
    exact env without spawning anything.
    """
    env = dict(base_env if base_env is not None else os.environ)
    env["MCP_SERVER_URL"] = settings.mcp_server_url
    env["LLM_API_URL"] = settings.llm_api_url
    env["LLM_MODEL"] = settings.llm_model
    env["LLM_PARSER"] = settings.llm_parser
    env["OPENHANDS_SESSION_ID"] = settings.session_id
    env["OPENHANDS_WORKSPACE"] = settings.openhands_workspace
    if settings.https_proxy:
        env["HTTP_PROXY"] = settings.https_proxy
        env["HTTPS_PROXY"] = settings.https_proxy
        env["NO_PROXY"] = "localhost,127.0.0.1"
    # Make the inner OpenHands process emit on unbuffered stdout so
    # we can stream its output to SSE in near-real-time.
    env["PYTHONUNBUFFERED"] = "1"
    return env


def build_openhands_argv(settings: config.OpenHandsSettings) -> List[str]:
    """Argv for the OpenHands subprocess. Pure function for testability."""
    extra = shlex.split(settings.openhands_extra_args) if settings.openhands_extra_args else []
    return [settings.openhands_command, "--config", settings.openhands_config_path, *extra]


# --------------------------------------------------------------------------- #
# Child process plumbing                                                      #
# --------------------------------------------------------------------------- #

async def _start_mcp_server(
    settings: config.OpenHandsSettings,
) -> asyncio.subprocess.Process:
    """Spawn `uvicorn mcp_server.main:app` as a child."""
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "uvicorn",
        "mcp_server.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(settings.mcp_uvicorn_port),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.STDOUT,
    )


async def _start_openhands(
    settings: config.OpenHandsSettings,
) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        *build_openhands_argv(settings),
        env=build_openhands_env(settings),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )


async def _stream_lines(
    stream: asyncio.StreamReader,
) -> AsyncIterator[str]:
    """Yield decoded lines from a child process's stdout."""
    while True:
        line = await stream.readline()
        if not line:
            return
        yield line.decode("utf-8", errors="replace")


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
        log.warning("kill_after_grace", extra={"child": name})
        try:
            proc.kill()
        except ProcessLookupError:
            return
        await proc.wait()


# --------------------------------------------------------------------------- #
# Top-level orchestrator                                                      #
# --------------------------------------------------------------------------- #

async def run(settings: Optional[config.OpenHandsSettings] = None) -> int:
    settings = settings or config.get_settings()
    _configure_logging(settings.log_level)
    log.info(
        "launcher.start",
        extra={
            "version": __version__,
            "session_id": settings.session_id,
            "mcp_server_url": settings.mcp_server_url,
            "broker_sse_url": settings.broker_sse_url or "(disabled)",
        },
    )

    mcp = await _start_mcp_server(settings)
    health_url = settings.mcp_server_url.rstrip("/") + "/health"
    healthy = await wait_for_health(
        health_url,
        timeout_s=settings.mcp_health_timeout_s,
        interval_s=settings.mcp_health_poll_interval_s,
    )
    if not healthy:
        log.error("mcp_health_timeout", extra={"timeout_s": settings.mcp_health_timeout_s})
        await _terminate(mcp, "mcp")
        return 2

    log.info("mcp.ready")

    oh = await _start_openhands(settings)

    # Wire SSE forwarding around OpenHands stdout.
    async def lines() -> AsyncIterator[str]:
        async for line in _stream_lines(oh.stdout):  # type: ignore[arg-type]
            yield line

    forward_task = asyncio.create_task(
        forward_stream(
            lines=lines(),
            broker_sse_url=settings.broker_sse_url,
            session_id=settings.session_id,
            user_id=settings.user_id,
            timeout_s=settings.sse_post_timeout_s,
            max_inflight=settings.sse_max_inflight,
        ),
        name="sse-forwarder",
    )

    # Race OpenHands' wait() against the hard runtime cap; either
    # returning ends the session.
    try:
        oh_wait = asyncio.wait_for(oh.wait(), timeout=settings.openhands_max_runtime_s)
        rc = await oh_wait
    except asyncio.TimeoutError:
        log.error(
            "openhands_runtime_cap_exceeded",
            extra={"max_runtime_s": settings.openhands_max_runtime_s},
        )
        await _terminate(oh, "openhands")
        rc = 124  # GNU `timeout` convention.

    # Drain forwarder, then tear down MCP.
    try:
        await asyncio.wait_for(forward_task, timeout=10.0)
    except asyncio.TimeoutError:
        forward_task.cancel()

    await _terminate(mcp, "mcp")

    log.info("launcher.exit", extra={"openhands_returncode": rc})
    return int(rc) if rc is not None else 1


def _install_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    def _handle(signum):
        log.warning("signal_received", extra={"signum": signum})
        for task in asyncio.all_tasks(loop):
            task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle, sig)
        except NotImplementedError:
            # Windows / weird platform — best effort.
            pass


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="openhands-launcher")
    parser.add_argument("--version", action="version", version=__version__)
    parser.parse_args(argv)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _install_signal_handlers(loop)
    try:
        return loop.run_until_complete(run())
    finally:
        loop.close()


if __name__ == "__main__":
    sys.exit(main())
