"""Error model for the MCP server.

Two layers:

1. ``ToolError`` — raised by tool implementations. Carries a stable
   string ``code`` so the agent (and tests) can branch on it without
   parsing English.
2. ``rpc_error`` — converts a ``ToolError`` (or any exception) into the
   wire-level JSON-RPC 2.0 error object.

The JSON-RPC numeric codes follow the spec:

- ``-32700`` parse error
- ``-32600`` invalid request
- ``-32601`` method not found
- ``-32602`` invalid params
- ``-32603`` internal error
- ``-32000`` server-defined: tool runtime failure (e.g. file not found,
  HTTP 500 from upstream). Distinguished from ``-32602`` so that
  *callable but failing* is reported differently from *bad input*.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


# JSON-RPC error codes -------------------------------------------------------
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
TOOL_RUNTIME_ERROR = -32000


# Stable string codes used by ToolError. Keep narrow; the agent
# branches on these.
class ToolErrorCode:
    INVALID_PARAMS = "invalid_params"
    PATH_NOT_ALLOWED = "path_not_allowed"
    PATH_TRAVERSAL = "path_traversal"
    SYMLINK_REJECTED = "symlink_rejected"
    FILE_NOT_FOUND = "file_not_found"
    NOT_A_FILE = "not_a_file"
    NOT_A_DIRECTORY = "not_a_directory"
    FILE_TOO_LARGE = "file_too_large"
    WRITE_TOO_LARGE = "write_too_large"
    READ_ONLY_ROOT = "read_only_root"
    URL_INVALID = "url_invalid"
    URL_BLOCKED = "url_blocked"
    SCHEME_NOT_ALLOWED = "scheme_not_allowed"
    SEARCH_PROVIDER_UNAVAILABLE = "search_provider_unavailable"
    NETWORK_ERROR = "network_error"
    RESPONSE_TOO_LARGE = "response_too_large"
    EXEC_TIMEOUT = "exec_timeout"
    EXEC_FAILED = "exec_failed"


@dataclass
class ToolError(Exception):
    """Raised inside tool implementations.

    ``code`` is the stable string from :class:`ToolErrorCode`.
    ``rpc_code`` is the JSON-RPC numeric code we'll return to the
    client; defaults to ``INVALID_PARAMS`` because most tool errors
    are caused by bad input.
    """

    code: str
    message: str
    rpc_code: int = INVALID_PARAMS
    data: Dict[str, Any] | None = None

    def __post_init__(self) -> None:  # noqa: D401 - keeps Exception happy
        super().__init__(self.message)

    def to_rpc(self) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "code": self.rpc_code,
            "message": self.message,
            "data": {"tool_error": self.code},
        }
        if self.data:
            body["data"].update(self.data)
        return body


def rpc_error(code: int, message: str, data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    body: Dict[str, Any] = {"code": code, "message": message}
    if data:
        body["data"] = data
    return body
