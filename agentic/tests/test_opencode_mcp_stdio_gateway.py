"""Unit tests for opencode MCP stdio → HTTP `/rpc` bridge."""

from __future__ import annotations

import json

import pytest

from opencode_runtime import mcp_stdio_gateway as gw


@pytest.mark.asyncio
async def test_list_tools_maps_descriptors(monkeypatch):
    async def fake_post(payload: dict) -> dict:
        assert payload["method"] == "list_tools"
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": [
                    {
                        "name": "fs_read",
                        "description": "read",
                        "input_schema": {"type": "object"},
                    },
                ],
            },
        }

    monkeypatch.setattr(gw, "_post_envelope", fake_post)
    monkeypatch.delenv("CHAT_AI_MCP_RPC_URL", raising=False)

    tools = await gw._handle_list_tools()
    assert len(tools) == 1
    assert tools[0].name == "fs_read"
    assert tools[0].inputSchema == {"type": "object"}


@pytest.mark.asyncio
async def test_call_tool_json_payload(monkeypatch):
    calls = []

    async def fake_post(payload: dict) -> dict:
        calls.append(payload)
        return {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"ok": True, "answer": 7},
        }

    monkeypatch.setattr(gw, "_post_envelope", fake_post)

    texts = await gw._handle_call_tool("dummy", {"a": "b"})
    assert len(texts) == 1
    assert json.loads(texts[0].text)["answer"] == 7
    assert calls[0]["method"] == "call_tool"
