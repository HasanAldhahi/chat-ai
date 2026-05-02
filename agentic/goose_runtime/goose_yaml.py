"""Write ~/.config/goose/config.yaml pointing MCP stdio bridge at POST /rpc."""

from __future__ import annotations

import json
from pathlib import Path


def chat_ai_extensions_block(mcp_rpc_url: str) -> str:
    """Return YAML config for goose: platform extensions + bundled MCP + chat-ai-mcp."""
    escaped = json.dumps(mcp_rpc_url)
    return f"""extensions:
  # --- Platform extensions (built into the goose binary) -------------------
  developer:
    enabled: true
    type: platform
    name: developer
    description: Write and edit files, and execute shell commands
    display_name: Developer
    bundled: true
    available_tools: []
  analyze:
    enabled: true
    type: platform
    name: analyze
    description: 'Analyze code structure with tree-sitter: directory overviews, file details, symbol call graphs'
    display_name: Analyze
    bundled: true
    available_tools: []
  todo:
    enabled: true
    type: platform
    name: todo
    description: Enable a todo list for goose so it can keep track of what it is doing
    display_name: Todo
    bundled: true
    available_tools: []
  summarize:
    enabled: true
    type: platform
    name: summarize
    description: Load files/directories and get an LLM summary in a single call
    display_name: Summarize
    bundled: true
    available_tools: []

  # --- Bundled MCP servers (goose mcp <name>) ------------------------------
  memory:
    enabled: true
    type: stdio
    name: memory
    display_name: Memory
    description: Persistent key-value memory across agent turns
    cmd: goose
    args:
      - mcp
      - memory
    timeout: 300
    envs: {{}}
  computercontroller:
    enabled: true
    type: stdio
    name: computercontroller
    display_name: Computer Controller
    description: Read and write PDF, DOCX, XLSX files; automate desktop interactions
    cmd: goose
    args:
      - mcp
      - computercontroller
    timeout: 300
    envs: {{}}

  # --- Chat AI MCP (stdio → HTTP bridge to broker's /rpc) ------------------
  chat-ai-mcp:
    name: "Chat AI MCP (stdio→HTTP)"
    enabled: true
    type: stdio
    timeout: 900
    cmd: python3.11
    args:
      - -m
      - goose_runtime.mcp_stdio_bridge
    envs:
      CHAT_AI_MCP_HTTP_URL: {escaped}
"""


def write_goose_config(*, home: Path, rpc_url: str) -> Path:
    """Persist config under ``{{home}}/.config/goose/config.yaml``."""

    cfg = home / ".config" / "goose"
    cfg.mkdir(parents=True, exist_ok=True)
    out = cfg / "config.yaml"
    out.write_text(chat_ai_extensions_block(rpc_url), encoding="utf-8")
    return out
