"""Stdio MCP server that forwards ``tools/list`` + ``tools/call`` to ``POST /rpc``.

OpenCode expects a true MCP subprocess for ``type: local``; chat-ai exposes HTTP
JSON-RPC only. This bridge exposes MCP-over-stdio to OpenCode and reuses the
broker's tool registry via loopback HTTP.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any

import httpx
import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

log = logging.getLogger("chat-ai-mcp-stdio-gateway")

_SERVER = Server("chat-ai-mcp-bridge", version="0.1.0")


def _rpc_url() -> str:
    url = os.environ.get("CHAT_AI_MCP_RPC_URL", "").strip()
    if not url:
        raise RuntimeError("CHAT_AI_MCP_RPC_URL is required")
    return url


async def _post_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(_rpc_url(), json=payload)
        r.raise_for_status()
        return r.json()


async def _rpc_result(*, req_id: int, method: str, params: dict[str, Any] | None) -> Any:
    body = await _post_envelope(
        {"jsonrpc": "2.0", "method": method, "id": req_id, "params": params or {}}
    )
    if not isinstance(body, dict):
        raise RuntimeError(f"invalid rpc response type: {type(body)}")
    if body.get("error"):
        raise RuntimeError(json.dumps(body["error"]))
    return body.get("result")


@_SERVER.list_tools()
async def _handle_list_tools() -> list[types.Tool]:
    result = await _rpc_result(req_id=1, method="list_tools", params={})
    raw_tools = result.get("tools", []) if isinstance(result, dict) else []
    out: list[types.Tool] = []
    for t in raw_tools:
        if not isinstance(t, dict):
            continue
        name = t.get("name")
        schema = t.get("input_schema") or t.get("inputSchema") or {}
        if not isinstance(name, str) or not name:
            continue
        if not isinstance(schema, dict):
            schema = {}
        out.append(
            types.Tool(
                name=name,
                description=str(t.get("description") or ""),
                inputSchema=schema,
            ),
        )
    return out


@_SERVER.call_tool()
async def _handle_call_tool(
    name: str, arguments: dict | None,
) -> list[types.TextContent]:
    arguments = dict(arguments or {})
    result = await _rpc_result(
        req_id=2,
        method="call_tool",
        params={"name": name, "arguments": arguments},
    )
    payload = json.dumps(result, indent=2, ensure_ascii=False, default=str)
    return [types.TextContent(type="text", text=payload)]


async def _async_main() -> None:
    level = getattr(
        logging,
        os.environ.get("LOG_LEVEL", "WARNING").upper(),
        logging.WARNING,
    )
    logging.basicConfig(level=level)
    init = _SERVER.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await _SERVER.run(read_stream, write_stream, init)


def main() -> None:
    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
