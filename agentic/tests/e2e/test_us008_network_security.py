"""US-008 Network security — when the agent attempts to browse an
internal address through MCP ``web_browse``, the request is refused at
the broker boundary with ``url_blocked`` so it never reaches the GWDG
internal network.

The broker is NOT the only line of defence (egress proxy + cluster
NetworkPolicy add depth) but the application-level filter must hold
on its own — it's the contract Task 2.5 / Task 5.1 lock in.
"""

from __future__ import annotations

import pytest


def _rpc(client, method: str, params: dict, *, req_id: int = 1) -> dict:
    r = client.post(
        "/rpc",
        json={"jsonrpc": "2.0", "id": req_id, "method": method, "params": params},
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize(
    "url",
    [
        "http://10.0.0.1/",
        "http://172.16.0.1/",
        "http://192.168.0.1/",
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://internal.gwdg.de/",
        "https://foo.internal.gwdg.de/path",
        "http://service.local/",
        # Cloud-metadata service, frequent SSRF target.
        "http://169.254.169.254/latest/meta-data/",
    ],
)
def test_us008_internal_url_browse_is_blocked(mcp_client, url):
    env = _rpc(
        mcp_client,
        "tools/call",
        {"name": "web_browse", "arguments": {"url": url}},
    )
    assert "error" in env, env
    assert env["error"]["data"]["tool_error"] == "url_blocked", url


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/",
        "javascript:alert(1)",
    ],
)
def test_us008_non_http_schemes_are_blocked(mcp_client, url):
    env = _rpc(
        mcp_client,
        "tools/call",
        {"name": "web_browse", "arguments": {"url": url}},
    )
    assert "error" in env, env
    assert env["error"]["data"]["tool_error"] in ("scheme_not_allowed", "url_invalid")
