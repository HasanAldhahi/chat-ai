"""MCP dispatcher: MCP-style method aliases (Task 4.1 / Goose compatibility)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mcp_server.main import create_app


@pytest.fixture(scope="module")
def client():
    app = create_app()
    yield TestClient(app)


def test_initialize(client: TestClient):
    r = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    assert "result" in body
    assert body["result"].get("protocolVersion")


def test_tools_list_alias_matches_list_tools(client: TestClient):
    mcp = [
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "list_tools", "params": {}},
    ]
    for req in mcp:
        r = client.post("/rpc", json=req)
        assert r.status_code == 200, r.text
        res = r.json()["result"]
        assert "tools" in res
        ids = [t.get("name") or t.get("id") for t in res["tools"]]
        assert len(ids) >= 1
