"""MCP (Model Context Protocol) server for the agentic layer.

Runs inside the per-session Apptainer container alongside the agent
framework (OpenHands, Goose, etc.). Exposes a small set of audited
tools — file system, web, code — over a JSON-RPC 2.0 HTTP endpoint at
``POST /rpc``. The agent framework is the MCP *client*; this module is
the *server*.

Phase 2 / Task 2.2.
"""

from __future__ import annotations

__version__ = "0.1.0"
