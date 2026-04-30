"""US-003 Secure file analysis — the agent reads a user file via MCP
``fs_read`` and gets back its contents; reading sensitive paths like
``/etc/passwd`` is refused.

This is an end-to-end verification through the actual MCP /rpc HTTP
endpoint, mirroring what an agent runtime inside the Apptainer
container does over loopback.
"""

from __future__ import annotations

from pathlib import Path


def _rpc(client, method: str, params: dict, *, req_id: int = 1) -> dict:
    r = client.post(
        "/rpc",
        json={"jsonrpc": "2.0", "id": req_id, "method": method, "params": params},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_us003_agent_can_read_workspace_file(mcp_client, mcp_settings):
    sandbox = Path(mcp_settings.fs_read_roots[0])
    (sandbox / "notes.md").write_text("hello world\n", encoding="utf-8")

    env = _rpc(
        mcp_client,
        "tools/call",
        {"name": "fs_read", "arguments": {"path": "notes.md"}},
    )
    assert "result" in env, env
    assert env["result"]["content"] == "hello world\n"
    assert env["result"]["encoding"] == "utf-8"


def test_us003_etc_passwd_is_refused(mcp_client):
    env = _rpc(
        mcp_client,
        "tools/call",
        {"name": "fs_read", "arguments": {"path": "/etc/passwd"}},
    )
    assert "error" in env
    assert env["error"]["data"]["tool_error"] == "path_not_allowed"


def test_us003_directory_traversal_is_refused(mcp_client):
    env = _rpc(
        mcp_client,
        "tools/call",
        {
            "name": "fs_read",
            "arguments": {"path": "../../../../etc/hostname"},
        },
    )
    assert "error" in env
    assert env["error"]["data"]["tool_error"] == "path_not_allowed"


def test_us003_fs_list_only_inside_sandbox(mcp_client, mcp_settings):
    sandbox = Path(mcp_settings.fs_read_roots[0])
    (sandbox / "a.txt").write_text("a")
    (sandbox / "sub").mkdir()

    env = _rpc(
        mcp_client,
        "tools/call",
        {"name": "fs_list", "arguments": {"path": str(sandbox)}},
    )
    assert "result" in env
    names = {e["name"] for e in env["result"]["entries"]}
    assert {"a.txt", "sub"}.issubset(names)


def test_us003_write_to_workspace_then_read_back(mcp_client, mcp_settings):
    """Write/read round-trip: agent writes a file then reads it,
    mirroring "save analysis output for the user" workflows.
    """
    env = _rpc(
        mcp_client,
        "tools/call",
        {
            "name": "fs_write",
            "arguments": {"path": "report.txt", "content": "summary v1\n"},
        },
    )
    assert "result" in env, env

    env = _rpc(
        mcp_client,
        "tools/call",
        {"name": "fs_read", "arguments": {"path": "report.txt"}},
    )
    assert env["result"]["content"] == "summary v1\n"
