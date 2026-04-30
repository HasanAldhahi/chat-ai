"""US-002 Web search & summarization — the agent invokes the MCP
``web_search`` tool, gets a structured result list, and forwards it to
the user. Without a real LLM in this suite we drive the MCP RPC layer
directly (the agent runtime would do the same JSON-RPC call).
"""

from __future__ import annotations


def _rpc(client, method: str, params: dict, *, req_id: int = 1) -> dict:
    r = client.post(
        "/rpc",
        json={"jsonrpc": "2.0", "id": req_id, "method": method, "params": params},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_us002_list_tools_advertises_web_search(mcp_client):
    env = _rpc(mcp_client, "tools/list", {})
    assert "result" in env, env
    names = {t["name"] for t in env["result"]["tools"]}
    assert "web_search" in names
    assert "web_browse" in names


def test_us002_web_search_returns_url_list(mcp_client):
    env = _rpc(
        mcp_client,
        "tools/call",
        {
            "name": "web_search",
            "arguments": {"query": "quantum computing", "num_results": 3},
        },
    )
    assert "result" in env, env
    res = env["result"]
    assert res["query"] == "quantum computing"
    assert res["provider"] == "stub"
    assert len(res["results"]) == 3
    for entry in res["results"]:
        # Acceptance: output contains URL + snippet so the agent can
        # build a summary from the result list.
        assert entry["url"].startswith("https://")
        assert "title" in entry
        assert "snippet" in entry


def test_us002_web_search_rejects_empty_query(mcp_client):
    env = _rpc(
        mcp_client,
        "tools/call",
        {"name": "web_search", "arguments": {"query": "  "}},
    )
    assert "error" in env
    assert env["error"]["data"]["tool_error"] == "invalid_params"


def test_us002_web_search_caps_num_results(mcp_client):
    env = _rpc(
        mcp_client,
        "tools/call",
        {"name": "web_search", "arguments": {"query": "x", "num_results": 999}},
    )
    assert "error" in env
    assert env["error"]["data"]["tool_error"] == "invalid_params"
