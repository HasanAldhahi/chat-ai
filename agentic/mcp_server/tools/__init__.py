"""Tool registry for the MCP server.

A *tool* is a small async callable plus a JSON-schema-ish descriptor.
The dispatcher in :mod:`mcp_server.server` looks up tools by name from
:data:`TOOLS` and invokes them with the caller-supplied ``arguments``.

Adding a tool is three steps:
1. Implement the callable in one of the ``tools/*.py`` modules.
2. Build a :class:`Tool` for it (name, description, input schema,
   callable).
3. Append it to :data:`TOOLS` below.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List

from . import code as code_tools
from . import fs as fs_tools
from . import web as web_tools


ToolFn = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    fn: ToolFn

    def descriptor(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


TOOLS: List[Tool] = [
    Tool(
        name="fs_read",
        description=(
            "Read a UTF-8 text file from /workspace or /home/user. "
            "Rejects symlinks that escape, paths outside allowed roots, "
            "and files larger than the configured cap (default 10 MB)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or workspace-relative path."},
                "encoding": {
                    "type": "string",
                    "enum": ["utf-8", "base64"],
                    "default": "utf-8",
                },
            },
            "required": ["path"],
        },
        fn=fs_tools.fs_read,
    ),
    Tool(
        name="fs_write",
        description=(
            "Write content to a path under /workspace. User home is "
            "read-only by default. Files capped at 1 MB."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "encoding": {"type": "string", "enum": ["utf-8", "base64"], "default": "utf-8"},
                "create_parents": {"type": "boolean", "default": True},
            },
            "required": ["path", "content"],
        },
        fn=fs_tools.fs_write,
    ),
    Tool(
        name="fs_list",
        description=(
            "List entries (non-recursive) of a directory under an allowed "
            "root. Caps at 2 000 entries per call."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
        },
        fn=fs_tools.fs_list,
    ),
    Tool(
        name="web_search",
        description=(
            "Search the public web using DuckDuckGo (default, no API key "
            "required). Returns title, URL, and snippet for each result."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "num_results": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
            },
            "required": ["query"],
        },
        fn=web_tools.web_search,
    ),
    Tool(
        name="web_browse",
        description=(
            "GET an http(s) URL via the per-session proxy and return the "
            "decoded body. Refuses private / loopback / link-local IPs; "
            "DNS-based filtering is enforced by the egress proxy."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "max_bytes": {"type": "integer", "minimum": 1024},
            },
            "required": ["url"],
        },
        fn=web_tools.web_browse,
    ),
    Tool(
        name="code_exec",
        description=(
            "Run a Python snippet in an isolated subprocess with a timeout "
            "(default 10 s, max 30 s). Captures stdout / stderr (truncated "
            "at 64 KiB per stream)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "timeout_s": {"type": "number", "minimum": 0.1, "maximum": 30},
                "stdin": {"type": "string", "default": ""},
            },
            "required": ["code"],
        },
        fn=code_tools.code_exec,
    ),
    Tool(
        name="code_check",
        description=(
            "Lint a Python snippet with pyflakes. Returns a list of "
            "messages with line / column / message; never fails because "
            "of the snippet itself."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "code": {"type": "string"},
            },
            "required": ["code"],
        },
        fn=code_tools.code_check,
    ),
]


TOOLS_BY_NAME: Dict[str, Tool] = {t.name: t for t in TOOLS}


def list_descriptors() -> List[Dict[str, Any]]:
    return [t.descriptor() for t in TOOLS]
