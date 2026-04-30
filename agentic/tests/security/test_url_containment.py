"""URL / network containment regressions (Task 5.1: "Internal network access
attempts blocked", "Proxy bypass attempts fail", "Access to http://10.0.0.1
fails", etc.).

The MCP ``web_browse`` tool's first-pass URL filter is responsible for
rejecting attempts to address internal infrastructure directly. Egress
proxy / NetworkPolicy is the second line of defence at runtime, but at
the application layer ``validate_url`` is the load-bearing gate.
"""

from __future__ import annotations

import pytest

from mcp_server.errors import ToolError, ToolErrorCode
from mcp_server.security import validate_url
from mcp_server.tools import web as web_tools


# --------------------------------------------------------------------------- #
# Private / loopback / link-local / reserved IP literals must be blocked.    #
# --------------------------------------------------------------------------- #


BLOCKED_IP_URLS = [
    # RFC1918 ranges called out explicitly in the spec.
    "http://10.0.0.1/",
    "http://10.255.255.254/",
    "http://172.16.0.1/",
    "http://172.31.255.254/",
    "http://192.168.0.1/",
    "http://192.168.255.254/",
    # Loopback.
    "http://127.0.0.1/",
    "http://127.1.2.3/",
    # Link-local + multicast + reserved.
    "http://169.254.169.254/latest/meta-data/",  # cloud metadata service
    "http://224.0.0.1/",
    "http://0.0.0.0/",
    # IPv6 loopback / link-local / unique-local.
    "http://[::1]/",
    "http://[fe80::1]/",
    "http://[fc00::1]/",
]


@pytest.mark.parametrize("url", BLOCKED_IP_URLS)
def test_validate_url_blocks_private_ip_literals(mcp_sandbox, url):
    with pytest.raises(ToolError) as ei:
        validate_url(url)
    assert ei.value.code == ToolErrorCode.URL_BLOCKED, url


# --------------------------------------------------------------------------- #
# Hostname blocklist (Task 2.5) — internal.gwdg.de + suffixes.                #
# --------------------------------------------------------------------------- #


BLOCKED_HOSTS = [
    "http://internal.gwdg.de/",
    "https://foo.internal.gwdg.de/path",
    "http://api.internal/",
    "http://service.local/",
]


@pytest.mark.parametrize("url", BLOCKED_HOSTS)
def test_validate_url_blocks_internal_hostnames(mcp_sandbox, url):
    with pytest.raises(ToolError) as ei:
        validate_url(url)
    assert ei.value.code == ToolErrorCode.URL_BLOCKED, url


# --------------------------------------------------------------------------- #
# Non-http(s) schemes must be rejected.                                       #
# --------------------------------------------------------------------------- #


REJECTED_SCHEMES = [
    "file:///etc/passwd",
    "ftp://example.com/",
    "gopher://example.com/",
    "javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    # No scheme at all.
    "example.com",
    "//example.com",
]


@pytest.mark.parametrize("url", REJECTED_SCHEMES)
def test_validate_url_rejects_non_http_schemes(mcp_sandbox, url):
    with pytest.raises(ToolError) as ei:
        validate_url(url)
    assert ei.value.code in (
        ToolErrorCode.SCHEME_NOT_ALLOWED,
        ToolErrorCode.URL_INVALID,
    ), url


# --------------------------------------------------------------------------- #
# End-to-end: the web_browse tool surfaces the same block.                    #
# --------------------------------------------------------------------------- #


async def test_web_browse_propagates_block(mcp_sandbox):
    with pytest.raises(ToolError) as ei:
        await web_tools.web_browse({"url": "http://10.0.0.1/"})
    assert ei.value.code == ToolErrorCode.URL_BLOCKED


async def test_web_browse_blocks_hostname_blocklist(mcp_sandbox):
    with pytest.raises(ToolError) as ei:
        await web_tools.web_browse({"url": "https://internal.gwdg.de/secret"})
    assert ei.value.code == ToolErrorCode.URL_BLOCKED


# --------------------------------------------------------------------------- #
# Empty / non-string input is rejected, not silently passed.                  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("bad", ["", "   ", None, 42, []])
def test_validate_url_rejects_bad_input_types(mcp_sandbox, bad):
    with pytest.raises(ToolError):
        validate_url(bad)  # type: ignore[arg-type]
