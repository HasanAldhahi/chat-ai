"""OpenHands runtime adapter for the agentic layer.

Orchestrates a per-session container's life:

    launcher -> starts uvicorn (mcp_server)
             -> waits for GET /health
             -> spawns OpenHands as a subprocess, env-configured to
                speak MCP over http://localhost:8080
             -> tails OpenHands stdout, forwards structured events to
                the broker's SSE endpoint as `action` / `result` /
                `error` SSE events.

The OpenHands process itself is the LLM-driven agent — it talks to
vLLM for completions and to the MCP server for tools. This module is
the *glue* that runs both inside one Apptainer container and ships
output back to the broker.

Phase 2 / Task 2.3.
"""

from __future__ import annotations

__version__ = "0.1.0"
