"""Write ~/.config/goose/config.yaml pointing MCP stdio bridge at POST /rpc."""

from __future__ import annotations

import json
from pathlib import Path


def chat_ai_extensions_block(mcp_rpc_url: str) -> str:
    """Return YAML fragment for Goose ``extensions.chat-ai-mcp``."""
    escaped = json.dumps(mcp_rpc_url)
    return f"""extensions:
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
    """Persist config under ``{home}/.config/goose/config.yaml``."""

    cfg = home / ".config" / "goose"
    cfg.mkdir(parents=True, exist_ok=True)
    out = cfg / "config.yaml"
    out.write_text(chat_ai_extensions_block(rpc_url), encoding="utf-8")
    return out

