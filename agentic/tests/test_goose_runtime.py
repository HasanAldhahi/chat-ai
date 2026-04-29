"""Tests for goose_runtime YAML writer (Task 4.1)."""

from __future__ import annotations

from pathlib import Path

from goose_runtime.goose_yaml import chat_ai_extensions_block, write_goose_config


def test_extensions_block_contains_bridge():
    blk = chat_ai_extensions_block("http://127.0.0.1:8080/rpc")
    assert "goose_runtime.mcp_stdio_bridge" in blk
    assert "CHAT_AI_MCP_HTTP_URL" in blk
    assert "http://127.0.0.1:8080/rpc" in blk


def test_write_roundtrip(tmp_path: Path):
    p = write_goose_config(home=tmp_path, rpc_url="http://x/rpc")
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "chat-ai-mcp:" in text
