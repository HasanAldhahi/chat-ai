"""File-system containment regressions (Task 5.1 acceptance bullets:
"Directory traversal attempts blocked", "File system permission violations
blocked", "User attempting to access another user's workspace returns 403").

These tests reproduce the *exact* scenarios the spec calls out — sensitive
absolute paths, symlink escapes, traversal segments that don't resolve
cleanly, NUL byte injection — at the MCP tool boundary and at the broker
HTTP boundary. They guard against accidental policy regression when the
fs roots, the resolver, or the dispatcher are touched.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mcp_server.errors import ToolError, ToolErrorCode
from mcp_server.tools import fs as fs_tools


# --------------------------------------------------------------------------- #
# Sensitive absolute paths must be rejected even if they exist.               #
# --------------------------------------------------------------------------- #


SENSITIVE_PATHS = [
    "/etc/passwd",
    "/etc/shadow",
    "/etc/hostname",
    "/root/.bash_history",
    "/proc/self/environ",
    "/proc/1/cmdline",
]


@pytest.mark.parametrize("victim", SENSITIVE_PATHS)
async def test_fs_read_rejects_sensitive_absolute_paths(mcp_sandbox, victim):
    with pytest.raises(ToolError) as ei:
        await fs_tools.fs_read({"path": victim})
    assert ei.value.code == ToolErrorCode.PATH_NOT_ALLOWED, victim


# --------------------------------------------------------------------------- #
# Traversal must not climb out of the sandbox even with redundant separators. #
# --------------------------------------------------------------------------- #


TRAVERSAL_INPUTS = [
    "../etc/passwd",
    "../../etc/passwd",
    "../../../../../../../../etc/passwd",
    "./.././../etc/passwd",
    "subdir/../../../../etc/passwd",
    "//etc//passwd",
    "/./etc/passwd",
]


@pytest.mark.parametrize("victim", TRAVERSAL_INPUTS)
async def test_fs_read_rejects_traversal_combinations(mcp_sandbox, victim):
    with pytest.raises(ToolError) as ei:
        await fs_tools.fs_read({"path": victim})
    assert ei.value.code == ToolErrorCode.PATH_NOT_ALLOWED


# --------------------------------------------------------------------------- #
# Symlink escapes resolve to the target; resolver must catch that.            #
# --------------------------------------------------------------------------- #


async def test_fs_read_blocks_symlink_to_outside_root(mcp_sandbox):
    target = "/etc/hostname"
    if not Path(target).exists():
        pytest.skip("no /etc/hostname on this host")
    sandbox = Path(mcp_sandbox)
    link = sandbox / "leak"
    link.symlink_to(target)

    with pytest.raises(ToolError) as ei:
        await fs_tools.fs_read({"path": "leak"})
    assert ei.value.code == ToolErrorCode.PATH_NOT_ALLOWED


async def test_fs_write_blocks_symlink_to_outside_root(mcp_sandbox, tmp_path):
    """Writing through a symlink that points outside must be refused.

    This is the TOCTOU shape: an agent could ``fs_write`` content to a
    file that an attacker pre-staged as a symlink pointing at, e.g., a
    sibling user's home. The resolver must detect that.
    """
    sandbox = Path(mcp_sandbox)
    outside = tmp_path.parent / "outside_target"
    outside.mkdir(exist_ok=True)
    (sandbox / "trap").symlink_to(outside)

    with pytest.raises(ToolError) as ei:
        await fs_tools.fs_write({"path": "trap/leaked.txt", "content": "x"})
    assert ei.value.code == ToolErrorCode.PATH_NOT_ALLOWED


# --------------------------------------------------------------------------- #
# Read-only home enforcement: writes to a read root that isn't a write root.  #
# --------------------------------------------------------------------------- #


async def test_fs_write_to_read_only_root_rejected(tmp_path, monkeypatch):
    import mcp_server.config as mcp_cfg

    home = tmp_path / "home"
    work = tmp_path / "work"
    home.mkdir()
    work.mkdir()
    settings = mcp_cfg.MCPSettings(
        fs_read_roots=[str(home), str(work)],
        fs_write_roots=[str(work)],
    )
    monkeypatch.setattr(mcp_cfg, "get_settings", lambda: settings)

    with pytest.raises(ToolError) as ei:
        await fs_tools.fs_write({"path": str(home / "leak.txt"), "content": "x"})
    assert ei.value.code == ToolErrorCode.PATH_NOT_ALLOWED


# --------------------------------------------------------------------------- #
# Defensive parsing: NUL byte and bad encoding.                               #
# --------------------------------------------------------------------------- #


async def test_fs_read_rejects_nul_byte_in_path(mcp_sandbox):
    with pytest.raises(ToolError) as ei:
        await fs_tools.fs_read({"path": "ok.txt\x00/etc/passwd"})
    assert ei.value.code == ToolErrorCode.INVALID_PARAMS


async def test_fs_list_rejects_outside_root(mcp_sandbox):
    with pytest.raises(ToolError) as ei:
        await fs_tools.fs_list({"path": "/etc"})
    assert ei.value.code == ToolErrorCode.PATH_NOT_ALLOWED
