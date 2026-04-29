"""Tests for the MCP fs_* tools (Task 2.2).

Direct unit tests of the async tool callables — bypasses the JSON-RPC
envelope so we can assert on the structured return value and on the
``ToolError`` codes the dispatcher relies on. Server-level
integration is covered by ``test_mcp_server.py``.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Iterator

import pytest

import mcp_server.config as cfg
from mcp_server.errors import ToolError, ToolErrorCode
from mcp_server.tools import fs as fs_tools


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #

@pytest.fixture
def sandbox(tmp_path) -> Iterator[Path]:
    """Isolated read+write root for each test."""
    settings = cfg.MCPSettings(
        fs_read_roots=[str(tmp_path)],
        fs_write_roots=[str(tmp_path)],
        fs_max_read_bytes=1024,
        fs_max_write_bytes=512,
    )
    original = cfg.get_settings
    cfg.get_settings = lambda: settings  # type: ignore[assignment]
    try:
        yield tmp_path
    finally:
        cfg.get_settings = original


@pytest.fixture
def split_roots(tmp_path) -> Iterator[tuple[Path, Path]]:
    """Two roots: read-only home, writable workspace.

    Used to assert fs_write rejects the user-home root even though
    fs_read accepts it.
    """
    home = tmp_path / "home"
    work = tmp_path / "work"
    home.mkdir()
    work.mkdir()
    settings = cfg.MCPSettings(
        fs_read_roots=[str(home), str(work)],
        fs_write_roots=[str(work)],
    )
    original = cfg.get_settings
    cfg.get_settings = lambda: settings  # type: ignore[assignment]
    try:
        yield home, work
    finally:
        cfg.get_settings = original


# --------------------------------------------------------------------------- #
# fs_read                                                                     #
# --------------------------------------------------------------------------- #

async def test_fs_read_happy_path(sandbox):
    (sandbox / "x.txt").write_text("hello world", encoding="utf-8")
    res = await fs_tools.fs_read({"path": "x.txt"})
    assert res["content"] == "hello world"
    assert res["encoding"] == "utf-8"
    assert res["size_bytes"] == 11


async def test_fs_read_path_outside_root_rejected(sandbox):
    with pytest.raises(ToolError) as ei:
        await fs_tools.fs_read({"path": "/etc/passwd"})
    assert ei.value.code == ToolErrorCode.PATH_NOT_ALLOWED


async def test_fs_read_traversal_rejected(sandbox):
    """`..` is collapsed by resolve(); the result must still be inside root."""
    with pytest.raises(ToolError) as ei:
        await fs_tools.fs_read({"path": "../../../../etc/hostname"})
    assert ei.value.code == ToolErrorCode.PATH_NOT_ALLOWED


async def test_fs_read_symlink_escape_rejected(sandbox):
    target = "/etc/hostname"
    if not Path(target).exists():
        pytest.skip("no /etc/hostname on this host")
    link = sandbox / "escape"
    link.symlink_to(target)
    with pytest.raises(ToolError) as ei:
        await fs_tools.fs_read({"path": "escape"})
    # resolve() follows the link to /etc/... which is outside the root.
    assert ei.value.code == ToolErrorCode.PATH_NOT_ALLOWED


async def test_fs_read_missing_file(sandbox):
    with pytest.raises(ToolError) as ei:
        await fs_tools.fs_read({"path": "ghost.txt"})
    assert ei.value.code == ToolErrorCode.FILE_NOT_FOUND


async def test_fs_read_directory_rejected(sandbox):
    (sandbox / "sub").mkdir()
    with pytest.raises(ToolError) as ei:
        await fs_tools.fs_read({"path": "sub"})
    assert ei.value.code == ToolErrorCode.NOT_A_FILE


async def test_fs_read_too_large(sandbox):
    big = sandbox / "big.bin"
    big.write_bytes(b"x" * 2048)  # > fs_max_read_bytes (1024)
    with pytest.raises(ToolError) as ei:
        await fs_tools.fs_read({"path": "big.bin"})
    assert ei.value.code == ToolErrorCode.FILE_TOO_LARGE
    assert ei.value.data["size_bytes"] == 2048


async def test_fs_read_binary_falls_back_to_base64(sandbox):
    (sandbox / "img.bin").write_bytes(b"\xff\xfe\x00\x01")
    res = await fs_tools.fs_read({"path": "img.bin"})
    assert res["encoding"] == "base64"
    assert base64.b64decode(res["content"]) == b"\xff\xfe\x00\x01"


async def test_fs_read_explicit_base64_encoding(sandbox):
    (sandbox / "x.txt").write_text("hi", encoding="utf-8")
    res = await fs_tools.fs_read({"path": "x.txt", "encoding": "base64"})
    assert res["encoding"] == "base64"
    assert base64.b64decode(res["content"]) == b"hi"


async def test_fs_read_invalid_encoding(sandbox):
    with pytest.raises(ToolError) as ei:
        await fs_tools.fs_read({"path": "anything", "encoding": "ebcdic"})
    assert ei.value.code == ToolErrorCode.INVALID_PARAMS


async def test_fs_read_nul_byte_rejected(sandbox):
    with pytest.raises(ToolError) as ei:
        await fs_tools.fs_read({"path": "x\x00.txt"})
    assert ei.value.code == ToolErrorCode.INVALID_PARAMS


# --------------------------------------------------------------------------- #
# fs_write                                                                    #
# --------------------------------------------------------------------------- #

async def test_fs_write_happy_path(sandbox):
    res = await fs_tools.fs_write({"path": "out.txt", "content": "data"})
    assert res["size_bytes"] == 4
    assert (sandbox / "out.txt").read_text() == "data"


async def test_fs_write_creates_parents(sandbox):
    res = await fs_tools.fs_write(
        {"path": "nested/deep/o.txt", "content": "x"}
    )
    assert (sandbox / "nested" / "deep" / "o.txt").exists()


async def test_fs_write_too_large(sandbox):
    payload = "x" * 600  # > fs_max_write_bytes (512)
    with pytest.raises(ToolError) as ei:
        await fs_tools.fs_write({"path": "big.txt", "content": payload})
    assert ei.value.code == ToolErrorCode.WRITE_TOO_LARGE


async def test_fs_write_outside_root_rejected(sandbox):
    with pytest.raises(ToolError) as ei:
        await fs_tools.fs_write({"path": "/tmp/escape.txt", "content": "x"})
    assert ei.value.code == ToolErrorCode.PATH_NOT_ALLOWED


async def test_fs_write_to_user_home_rejected(split_roots):
    """User home is in fs_read_roots but NOT fs_write_roots."""
    home, work = split_roots
    with pytest.raises(ToolError) as ei:
        await fs_tools.fs_write({"path": str(home / "x.txt"), "content": "x"})
    assert ei.value.code == ToolErrorCode.PATH_NOT_ALLOWED


async def test_fs_write_to_workspace_ok(split_roots):
    home, work = split_roots
    res = await fs_tools.fs_write({"path": str(work / "y.txt"), "content": "x"})
    assert (work / "y.txt").read_text() == "x"


async def test_fs_write_base64_decoded(sandbox):
    payload = base64.b64encode(b"\x01\x02\x03").decode("ascii")
    await fs_tools.fs_write(
        {"path": "bin.dat", "content": payload, "encoding": "base64"}
    )
    assert (sandbox / "bin.dat").read_bytes() == b"\x01\x02\x03"


async def test_fs_write_bad_base64(sandbox):
    with pytest.raises(ToolError) as ei:
        await fs_tools.fs_write(
            {"path": "x.dat", "content": "!!!notb64!!!", "encoding": "base64"}
        )
    assert ei.value.code == ToolErrorCode.INVALID_PARAMS


async def test_fs_write_directory_target_rejected(sandbox):
    (sandbox / "d").mkdir()
    with pytest.raises(ToolError) as ei:
        await fs_tools.fs_write({"path": "d", "content": "x"})
    assert ei.value.code == ToolErrorCode.NOT_A_FILE


# --------------------------------------------------------------------------- #
# fs_list                                                                     #
# --------------------------------------------------------------------------- #

async def test_fs_list_happy_path(sandbox):
    (sandbox / "a.txt").write_text("a")
    (sandbox / "b.txt").write_text("bb")
    (sandbox / "sub").mkdir()
    res = await fs_tools.fs_list({"path": str(sandbox)})
    names = {e["name"]: e for e in res["entries"]}
    assert {"a.txt", "b.txt", "sub"}.issubset(names)
    # Directory should sort first (kind tie-break).
    assert res["entries"][0]["type"] == "dir"
    assert res["truncated"] is False
    assert names["a.txt"]["size_bytes"] == 1


async def test_fs_list_not_a_directory(sandbox):
    (sandbox / "a.txt").write_text("a")
    with pytest.raises(ToolError) as ei:
        await fs_tools.fs_list({"path": "a.txt"})
    assert ei.value.code == ToolErrorCode.NOT_A_DIRECTORY


async def test_fs_list_outside_root_rejected(sandbox):
    with pytest.raises(ToolError) as ei:
        await fs_tools.fs_list({"path": "/etc"})
    assert ei.value.code == ToolErrorCode.PATH_NOT_ALLOWED


async def test_fs_list_truncates_when_over_cap():
    """Exercise the cap directly with a tiny limit."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        for i in range(5):
            Path(td, f"f{i}.txt").write_text("x")
        settings = cfg.MCPSettings(
            fs_read_roots=[td], fs_write_roots=[td], fs_max_list_entries=2
        )
        original = cfg.get_settings
        cfg.get_settings = lambda: settings  # type: ignore[assignment]
        try:
            res = await fs_tools.fs_list({"path": td})
        finally:
            cfg.get_settings = original
    assert len(res["entries"]) == 2
    assert res["truncated"] is True
