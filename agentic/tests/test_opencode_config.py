"""Tests for Task 4.3 OpenCode config writer."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencode_runtime.config import OpenCodeSettings, reset_settings_cache
from opencode_runtime.opencode_json import build_opencode_config_dict, write_opencode_config


@pytest.fixture(autouse=True)
def _clear_settings():
    reset_settings_cache()
    yield
    reset_settings_cache()


def test_build_opencode_config_has_mcp_stdio_bridge():
    s = OpenCodeSettings(
        home_dir="/w",
        mcp_server_url="http://127.0.0.1:8080",
        opencode_model="openai/x",
        session_prompt="hi",
    )
    d = build_opencode_config_dict(s)
    assert d["model"] == "openai/x"
    chat = d["mcp"]["chat-ai"]
    assert chat["type"] == "local"
    assert "opencode_runtime.mcp_stdio_gateway" in " ".join(chat["command"])
    assert chat["environment"]["CHAT_AI_MCP_RPC_URL"] == "http://127.0.0.1:8080/rpc"


def test_write_roundtrip(tmp_path: Path):
    s = OpenCodeSettings()
    dest = write_opencode_config(home=tmp_path, settings=s)
    assert dest.samefile(tmp_path / ".config" / "opencode" / "opencode.json")
    txt = dest.read_text(encoding="utf-8")
    assert "chat-ai" in txt
    assert "CHAT_AI_MCP_RPC_URL" in txt
