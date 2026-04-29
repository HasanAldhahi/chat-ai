"""Write ~/.config/opencode/opencode.json matching OpenCode MCP local plugin."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .config import OpenCodeSettings, get_settings, mcp_rpc_url


def build_opencode_config_dict(settings: OpenCodeSettings) -> Dict[str, Any]:
    rpc = mcp_rpc_url(settings)
    return {
        "$schema": "https://opencode.ai/config.json",
        "model": settings.opencode_model,
        # vLLM / OpenAI-compatible cluster endpoint (broker sets OPENAI_* in env).
        "provider": {
            "openai": {
                "options": {
                    "apiKey": "{env:OPENAI_API_KEY}",
                    "baseURL": "{env:OPENAI_BASE_URL}",
                },
            },
        },
        "mcp": {
            "chat-ai": {
                "type": "local",
                "enabled": True,
                "command": ["python3.11", "-m", "opencode_runtime.mcp_stdio_gateway"],
                "environment": {
                    "CHAT_AI_MCP_RPC_URL": rpc,
                },
            },
        },
    }


def write_opencode_config(
    *,
    home: Path,
    settings: OpenCodeSettings | None = None,
) -> Path:
    """Create ``~/.config/opencode/opencode.json``."""
    cfg = settings or get_settings()
    out_dir = home / ".config" / "opencode"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "opencode.json"
    data = build_opencode_config_dict(cfg)
    dest.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return dest
