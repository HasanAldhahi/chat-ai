"""Tests for the MCP JSON-RPC dispatcher and FastAPI surface (Task 2.2).

Hits the FastAPI app via ``TestClient`` end-to-end. The only mocking
done at this layer is overriding the settings cache so we can pin
deterministic boundaries (read roots, write roots) inside ``tmp_path``.
"""

from __future__ import annotations

import json
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

import mcp_server.config as cfg
from mcp_server.main import create_app


@pytest.fixture
def workspace(tmp_path) -> Iterator[str]:
    """Pin both read and write roots to a per-test tmp_path.

    Ensures every fs_* call lands in an ephemeral directory rather
    than the real /workspace, and resets pydantic's settings cache
    around each test.
    """
    settings = cfg.MCPSettings(
        fs_read_roots=[str(tmp_path)],
        fs_write_roots=[str(tmp_path)],
        web_search_provider="stub",
    )
    original_get_settings = cfg.get_settings
    cfg.get_settings = lambda: settings  # type: ignore[assignment]
    try:
        yield str(tmp_path)
    finally:
        cfg.get_settings = original_get_settings


@pytest.fixture
def client(workspace: str) -> TestClient:
    return TestClient(create_app(cfg.get_settings()))


def _rpc(client: TestClient, payload):
    return client.post("/rpc", json=payload)


# --------------------------------------------------------------------------- #
# Health                                                                      #
# --------------------------------------------------------------------------- #

def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert body["tool_count"] == 8
    assert "skill_count" in body
    assert isinstance(body["skill_count"], int)


# --------------------------------------------------------------------------- #
# Envelope handling                                                           #
# --------------------------------------------------------------------------- #

def test_rpc_parse_error_returns_envelope(client):
    r = client.post("/rpc", content=b"{not valid json")
    assert r.status_code == 200
    body = r.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] is None
    assert body["error"]["code"] == -32700  # PARSE_ERROR


def test_rpc_invalid_request_no_jsonrpc_field(client):
    r = _rpc(client, {"method": "list_tools", "id": 1})
    body = r.json()
    assert body["error"]["code"] == -32600
    assert "jsonrpc" in body["error"]["message"].lower()


def test_rpc_invalid_request_missing_method(client):
    r = _rpc(client, {"jsonrpc": "2.0", "id": 1})
    body = r.json()
    assert body["error"]["code"] == -32600


def test_rpc_method_not_found(client):
    r = _rpc(client, {"jsonrpc": "2.0", "id": "x", "method": "explode"})
    body = r.json()
    assert body["error"]["code"] == -32601
    assert body["id"] == "x"


def test_rpc_params_must_be_object(client):
    r = _rpc(
        client,
        {"jsonrpc": "2.0", "id": 1, "method": "list_tools", "params": [1, 2]},
    )
    body = r.json()
    assert body["error"]["code"] == -32602


def test_rpc_id_echoed_back(client):
    for req_id in ("alpha", 7, None):
        r = _rpc(
            client,
            {"jsonrpc": "2.0", "id": req_id, "method": "list_tools"},
        )
        assert r.json()["id"] == req_id


# --------------------------------------------------------------------------- #
# list_tools                                                                  #
# --------------------------------------------------------------------------- #

EXPECTED_TOOLS = {
    "fs_read",
    "fs_write",
    "fs_list",
    "web_search",
    "web_browse",
    "code_exec",
    "code_check",
    "get_skills",
}


def test_list_tools_returns_eight_tools(client):
    r = _rpc(client, {"jsonrpc": "2.0", "id": 1, "method": "list_tools"})
    tools = r.json()["result"]["tools"]
    assert {t["name"] for t in tools} == EXPECTED_TOOLS


def test_list_tools_descriptors_have_schema(client):
    r = _rpc(client, {"jsonrpc": "2.0", "id": 1, "method": "list_tools"})
    for t in r.json()["result"]["tools"]:
        assert isinstance(t["description"], str) and t["description"]
        schema = t["input_schema"]
        assert schema["type"] == "object"
        assert "properties" in schema


# --------------------------------------------------------------------------- #
# call_tool dispatch                                                          #
# --------------------------------------------------------------------------- #

def test_call_tool_unknown_name(client):
    r = _rpc(
        client,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "call_tool",
            "params": {"name": "no_such_tool"},
        },
    )
    body = r.json()
    assert body["error"]["code"] == -32601
    assert "no_such_tool" in body["error"]["message"]


def test_call_tool_missing_name(client):
    r = _rpc(
        client,
        {"jsonrpc": "2.0", "id": 1, "method": "call_tool", "params": {}},
    )
    body = r.json()
    assert body["error"]["code"] == -32602


def test_call_tool_arguments_must_be_object(client):
    r = _rpc(
        client,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "call_tool",
            "params": {"name": "fs_list", "arguments": "/workspace"},
        },
    )
    body = r.json()
    assert body["error"]["code"] == -32602


def test_call_tool_propagates_tool_error_code(client, workspace):
    r = _rpc(
        client,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "call_tool",
            "params": {"name": "fs_read", "arguments": {"path": "/etc/passwd"}},
        },
    )
    body = r.json()
    err = body["error"]
    assert err["code"] == -32602
    # Stable code so the agent can branch on it
    assert err["data"]["tool_error"] == "path_not_allowed"


def test_call_tool_happy_path_writes_then_reads(client, workspace):
    write = _rpc(
        client,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "call_tool",
            "params": {
                "name": "fs_write",
                "arguments": {"path": "hello.txt", "content": "hi"},
            },
        },
    ).json()
    assert "result" in write, write
    assert write["result"]["size_bytes"] == 2

    read = _rpc(
        client,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "call_tool",
            "params": {
                "name": "fs_read",
                "arguments": {"path": "hello.txt"},
            },
        },
    ).json()
    assert read["result"]["content"] == "hi"
    assert read["result"]["encoding"] == "utf-8"
