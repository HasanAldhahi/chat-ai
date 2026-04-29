"""JSON-RPC 2.0 dispatcher.

The MCP wire protocol (in this implementation) is plain JSON-RPC 2.0
over a single HTTP POST endpoint at ``/rpc``. Two methods:

- ``initialize`` — MCP-compat handshake (returns protocolVersion)
- ``list_tools`` / ``tools/list`` — tool discovery
- ``call_tool`` / ``tools/call`` — invocation

Anything else -> ``method_not_found``. We intentionally keep this
narrow; new capabilities should be new tools, not new methods.

Why hand-rolled instead of the official MCP SDK? Three reasons:
1. Single dependency (FastAPI) — already used by the broker.
2. Tests can hit the FastAPI ``TestClient`` directly; no SDK harness.
3. The agent frameworks we ship (OpenHands etc.) have their own
   client code; they only need this server to obey the wire format.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from .errors import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    TOOL_RUNTIME_ERROR,
    ToolError,
    rpc_error,
)
from .tools import TOOLS_BY_NAME, list_descriptors


log = logging.getLogger("agentic-mcp-server")


def _envelope(req_id: Any, result: Dict[str, Any] | None = None,
              error: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Build a JSON-RPC 2.0 response envelope.

    ``id`` echoes back what the client sent (including ``None`` for
    notifications, though we don't fast-path those). Exactly one of
    ``result`` or ``error`` is set.
    """
    out: Dict[str, Any] = {"jsonrpc": "2.0", "id": req_id}
    if error is not None:
        out["error"] = error
    else:
        out["result"] = result or {}
    return out


def parse_request(payload: Any) -> Dict[str, Any]:
    """Validate the JSON-RPC 2.0 envelope; return the validated dict.

    Errors raise ``ValueError`` with the JSON-RPC code in ``args[0]``
    so the caller can build a proper error envelope around them.
    """
    if not isinstance(payload, dict):
        raise ValueError(INVALID_REQUEST, "request must be a JSON object")
    if payload.get("jsonrpc") != "2.0":
        raise ValueError(INVALID_REQUEST, "missing or wrong jsonrpc field")
    method = payload.get("method")
    if not isinstance(method, str) or not method:
        raise ValueError(INVALID_REQUEST, "method must be a non-empty string")
    params = payload.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ValueError(INVALID_PARAMS, "params must be a JSON object (this server does not accept positional params)")
    return {
        "id": payload.get("id"),
        "method": method,
        "params": params,
    }


async def dispatch(payload: Any) -> Dict[str, Any]:
    """Execute one JSON-RPC request, returning a response envelope.

    All exceptions are turned into JSON-RPC errors — this function
    must never raise, since the FastAPI handler relies on always
    getting a response dict to serialise.
    """
    try:
        req = parse_request(payload)
    except ValueError as ve:
        code, message = ve.args
        return _envelope(
            req_id=payload.get("id") if isinstance(payload, dict) else None,
            error=rpc_error(code, message),
        )

    method = req["method"]
    params = req["params"]
    req_id = req["id"]

    # MCP / Goose-compatible aliases (narrow JSON-RPC server; Task 4.1)
    if method == "initialize":
        return _envelope(
            req_id,
            result={
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "chat-ai-mcp", "version": "0.1.0"},
            },
        )

    if method in ("notifications/initialized", "initialized"):
        # JSON-RPC notifications may omit id; callers should send null id.
        return _envelope(req_id, result={})

    if method in ("tools/list", "tools.list"):
        return _envelope(req_id, result={"tools": list_descriptors()})

    if method in ("tools/call", "tools.call"):
        # Same payload shape as call_tool (`name` / `arguments`).
        return await _call_tool(req_id, params)

    if method == "list_tools":
        log.info("rpc.list_tools", extra={"request_id": req_id})
        return _envelope(req_id, result={"tools": list_descriptors()})

    if method == "call_tool":
        return await _call_tool(req_id, params)

    return _envelope(
        req_id,
        error=rpc_error(METHOD_NOT_FOUND, f"unknown method: {method!r}"),
    )


async def _call_tool(req_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    name = params.get("name")
    if not isinstance(name, str) or not name:
        return _envelope(
            req_id,
            error=rpc_error(INVALID_PARAMS, "call_tool: missing string `name`"),
        )
    arguments = params.get("arguments", {})
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        return _envelope(
            req_id,
            error=rpc_error(
                INVALID_PARAMS,
                "call_tool: `arguments` must be an object",
            ),
        )

    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        return _envelope(
            req_id,
            error=rpc_error(METHOD_NOT_FOUND, f"unknown tool: {name!r}"),
        )

    log.info(
        "rpc.call_tool",
        extra={
            "request_id": req_id,
            "tool": name,
            "argument_keys": sorted(arguments.keys()),
        },
    )

    try:
        result = await tool.fn(arguments)
    except ToolError as te:
        log.info(
            "rpc.tool_error",
            extra={"request_id": req_id, "tool": name, "tool_error": te.code},
        )
        return _envelope(req_id, error=te.to_rpc())
    except Exception as exc:  # noqa: BLE001
        log.exception("rpc.tool_crashed", extra={"tool": name})
        return _envelope(
            req_id,
            error=rpc_error(
                TOOL_RUNTIME_ERROR,
                f"tool {name!r} crashed: {type(exc).__name__}: {exc}",
            ),
        )

    return _envelope(req_id, result=result)
