"""Shared fixtures for the Phase 5 / Task 5.1 security regression suite.

Every test in this package is marked ``security`` so operators can run
the gate in CI with ``pytest -m security`` without pulling in unrelated
suites.
"""

from __future__ import annotations

from typing import Dict, Iterator

import pytest

import mcp_server.config as mcp_cfg


def pytest_collection_modifyitems(config, items):  # noqa: D401
    """Tag every test in this package with ``@pytest.mark.security``.

    The marker is applied by file path so individual modules don't have to
    repeat it. It also lets the suite be invoked as a single gate.
    """
    sec_marker = pytest.mark.security
    for item in items:
        if "/tests/security/" in str(item.fspath).replace("\\", "/"):
            item.add_marker(sec_marker)


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    """Default valid auth headers used by HTTP-level security tests."""
    return {
        "Authorization": "Bearer test-token",
        "X-User": "alice@gwdg",
        "Content-Type": "application/json",
    }


@pytest.fixture
def mcp_sandbox(tmp_path) -> Iterator[str]:
    """MCP fs roots locked to a temp dir; web blocklist with GWDG defaults.

    Yields the sandbox path so tests can write fixture files into it and
    then refer to them by relative or absolute path.
    """
    settings = mcp_cfg.MCPSettings(
        fs_read_roots=[str(tmp_path)],
        fs_write_roots=[str(tmp_path)],
        fs_max_read_bytes=1024,
        fs_max_write_bytes=512,
        web_search_provider="stub",
        web_blocked_host_suffixes=["internal.gwdg.de", ".internal", ".local"],
        web_max_response_bytes=1024,
    )
    original = mcp_cfg.get_settings
    mcp_cfg.get_settings = lambda: settings  # type: ignore[assignment]
    try:
        yield str(tmp_path)
    finally:
        mcp_cfg.get_settings = original
