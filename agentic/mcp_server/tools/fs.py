"""File-system tools.

All paths flow through :func:`mcp_server.security.resolve_safe_path`,
which is the *one* place the containment policy is enforced. If you
add a new fs tool, do **not** open paths directly — always go through
that helper.
"""

from __future__ import annotations

import asyncio
import base64
import os
from typing import Any, Dict, List

from .. import config
from ..errors import ToolError, ToolErrorCode
from ..security import resolve_safe_path


def _settings():
    # Resolve through the module so tests can monkeypatch
    # ``mcp_server.config.get_settings`` and have it stick.
    return config.get_settings()


# --------------------------------------------------------------------------- #
# fs_read                                                                     #
# --------------------------------------------------------------------------- #

async def fs_read(args: Dict[str, Any]) -> Dict[str, Any]:
    path_arg = args.get("path")
    encoding = args.get("encoding", "utf-8")
    if encoding not in ("utf-8", "base64"):
        raise ToolError(
            code=ToolErrorCode.INVALID_PARAMS,
            message="encoding must be 'utf-8' or 'base64'",
        )
    s = _settings()
    resolved = resolve_safe_path(path_arg, s.fs_read_roots, must_exist=True)
    if not resolved.is_file():
        raise ToolError(
            code=ToolErrorCode.NOT_A_FILE,
            message=f"{path_arg} is not a regular file",
        )

    size = resolved.stat().st_size
    if size > s.fs_max_read_bytes:
        raise ToolError(
            code=ToolErrorCode.FILE_TOO_LARGE,
            message=(
                f"file is {size} bytes; max read is {s.fs_max_read_bytes}"
            ),
            data={"size_bytes": size, "limit_bytes": s.fs_max_read_bytes},
        )

    raw = await asyncio.to_thread(resolved.read_bytes)
    if encoding == "utf-8":
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            # Fall back transparently — the agent can request base64
            # explicitly if it wants raw bytes.
            content = base64.b64encode(raw).decode("ascii")
            encoding = "base64"
    else:
        content = base64.b64encode(raw).decode("ascii")

    return {
        "path": str(resolved),
        "content": content,
        "encoding": encoding,
        "size_bytes": size,
    }


# --------------------------------------------------------------------------- #
# fs_write                                                                    #
# --------------------------------------------------------------------------- #

async def fs_write(args: Dict[str, Any]) -> Dict[str, Any]:
    path_arg = args.get("path")
    content = args.get("content")
    encoding = args.get("encoding", "utf-8")
    create_parents = bool(args.get("create_parents", True))

    if not isinstance(content, str):
        raise ToolError(
            code=ToolErrorCode.INVALID_PARAMS,
            message="`content` must be a string (use base64 encoding for binary)",
        )
    if encoding not in ("utf-8", "base64"):
        raise ToolError(
            code=ToolErrorCode.INVALID_PARAMS,
            message="encoding must be 'utf-8' or 'base64'",
        )

    s = _settings()
    # First validate the user-provided path against the *write* roots
    # (stricter than read roots — user's home is read-only by default).
    resolved = resolve_safe_path(path_arg, s.fs_write_roots)

    if encoding == "base64":
        try:
            data = base64.b64decode(content, validate=True)
        except Exception as exc:  # noqa: BLE001
            raise ToolError(
                code=ToolErrorCode.INVALID_PARAMS,
                message=f"invalid base64: {exc}",
            ) from exc
    else:
        data = content.encode("utf-8")

    if len(data) > s.fs_max_write_bytes:
        raise ToolError(
            code=ToolErrorCode.WRITE_TOO_LARGE,
            message=(
                f"payload is {len(data)} bytes; max write is "
                f"{s.fs_max_write_bytes}"
            ),
            data={
                "size_bytes": len(data),
                "limit_bytes": s.fs_max_write_bytes,
            },
        )

    if create_parents:
        await asyncio.to_thread(
            lambda: resolved.parent.mkdir(parents=True, exist_ok=True)
        )

    if resolved.exists() and resolved.is_dir():
        raise ToolError(
            code=ToolErrorCode.NOT_A_FILE,
            message=f"{resolved} is an existing directory",
        )

    await asyncio.to_thread(resolved.write_bytes, data)

    return {
        "path": str(resolved),
        "size_bytes": len(data),
        "encoding": encoding,
    }


# --------------------------------------------------------------------------- #
# fs_list                                                                     #
# --------------------------------------------------------------------------- #

def _entry_kind(p) -> str:
    if p.is_symlink():
        return "symlink"
    if p.is_dir():
        return "dir"
    if p.is_file():
        return "file"
    return "other"


async def fs_list(args: Dict[str, Any]) -> Dict[str, Any]:
    path_arg = args.get("path")
    s = _settings()
    resolved = resolve_safe_path(path_arg, s.fs_read_roots, must_exist=True)
    if not resolved.is_dir():
        raise ToolError(
            code=ToolErrorCode.NOT_A_DIRECTORY,
            message=f"{path_arg} is not a directory",
        )

    def _scan() -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        with os.scandir(resolved) as it:
            for entry in it:
                if len(out) >= s.fs_max_list_entries:
                    break
                try:
                    st = entry.stat(follow_symlinks=False)
                    size = st.st_size if entry.is_file(follow_symlinks=False) else None
                except OSError:
                    size = None
                out.append(
                    {
                        "name": entry.name,
                        "type": _entry_kind(entry),
                        "size_bytes": size,
                    }
                )
        out.sort(key=lambda e: (e["type"] != "dir", e["name"]))
        return out

    entries = await asyncio.to_thread(_scan)
    truncated = len(entries) >= s.fs_max_list_entries
    return {
        "path": str(resolved),
        "entries": entries,
        "truncated": truncated,
    }
