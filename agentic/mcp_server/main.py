"""FastAPI application factory for the MCP server.

The server exposes two endpoints:

- ``GET /health`` — liveness probe used by the broker / cluster
  health checks. Always returns 200 with a small JSON body.
- ``POST /rpc`` — single-shot JSON-RPC 2.0 endpoint. Body must be a
  JSON object; batch requests are not supported (no agent we ship
  uses them and the wire is simpler without).

We deliberately do *not* re-add the ``X-User`` auth middleware here.
The MCP server is reachable only on ``localhost`` from inside the
session container (one user per container, the agent talks to it
over loopback), so trusting the network is correct at this layer.
The broker's auth boundary is upstream.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import __version__
from .config import MCPSettings, get_settings
from .errors import PARSE_ERROR, rpc_error
from .server import dispatch


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def create_app(settings: MCPSettings | None = None) -> FastAPI:
    settings = settings or get_settings()
    _configure_logging(settings.log_level)
    log = logging.getLogger(settings.app_name)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from .skills.loader import load_skill_store, reset_skill_cache
        from .tools import TOOLS

        reset_skill_cache()
        st = load_skill_store(settings.skills_dir, reload=False)
        log.info(
            "mcp_server starting",
            extra={
                "version": __version__,
                "tool_count": len(TOOLS),
                "skill_count": len(st.docs),
                "fs_read_roots": settings.fs_read_roots,
                "fs_write_roots": settings.fs_write_roots,
            },
        )
        yield
        log.info("mcp_server stopping")

    app = FastAPI(
        title="Agentic MCP Server",
        version=__version__,
        description=(
            "JSON-RPC 2.0 MCP server. POST /rpc with "
            '{"jsonrpc":"2.0","method":"list_tools","id":1} to discover tools.'
        ),
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health() -> dict:
        from .skills.loader import load_skill_store
        from .tools import TOOLS

        st = load_skill_store(settings.skills_dir)
        return {
            "status": "healthy",
            "version": __version__,
            "tool_count": len(TOOLS),
            "skill_count": len(st.docs),
        }

    @app.post("/rpc")
    async def rpc(request: Request):
        # Reading the raw body lets us return a proper JSON-RPC parse
        # error envelope rather than FastAPI's generic 422.
        raw = await request.body()
        try:
            payload = json.loads(raw or b"null")
        except json.JSONDecodeError as exc:
            return JSONResponse(
                status_code=200,
                content={
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": rpc_error(PARSE_ERROR, f"parse error: {exc}"),
                },
            )

        envelope = await dispatch(payload)
        return JSONResponse(status_code=200, content=envelope)

    return app


# Module-level instance for ``uvicorn mcp_server.main:app``.
app = create_app()
