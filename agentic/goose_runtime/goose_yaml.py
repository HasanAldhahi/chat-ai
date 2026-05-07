"""Write ~/.config/goose/config.yaml pointing MCP stdio bridge at POST /rpc."""

from __future__ import annotations

import json
from pathlib import Path


def chat_ai_extensions_block(mcp_rpc_url: str) -> str:
    """Return YAML config for goose: minimal platform extensions + chat-ai-mcp only.

    Keeping the extension set small is intentional:
    - Fewer tools = shorter system prompt = faster LLM response (critical for
      models like Qwen3-30B that think before acting).
    - The heavy stdio servers (memory, computercontroller) each spawn a goose
      subprocess, adding ~1 s startup latency and extra context tokens.
    - developer + todo cover the core agentic use-case (code + task tracking).
    """
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
  todo:
    enabled: true
    type: platform
    name: todo
    description: Enable a todo list for goose so it can keep track of what it is doing
    display_name: Todo
    bundled: true
    available_tools: []

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
