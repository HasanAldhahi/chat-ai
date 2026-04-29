"""Tests for the MCP code_* tools (Task 2.2).

These actually fork a Python subprocess — pyflakes / cpython are
already in-venv (see ``agentic/requirements.txt`` dev deps) and the
launches are bounded by a tight timeout, so the suite stays fast.

We use ``sys.executable`` for the subprocess so the test passes on
hosts where ``python3.11`` isn't on ``$PATH`` (the dev VM runs
agentic under a 3.11 venv but the test runner inherits from the
ambient interpreter).
"""

from __future__ import annotations

import sys
from typing import Iterator

import pytest

import mcp_server.config as cfg
from mcp_server.errors import ToolError, ToolErrorCode
from mcp_server.tools import code as code_tools


@pytest.fixture
def code_settings(monkeypatch) -> Iterator[None]:
    settings = cfg.MCPSettings(
        code_python_bin=sys.executable,
        code_exec_default_timeout_s=2.0,
        code_exec_max_timeout_s=3.0,
        code_exec_max_output_bytes=2048,
    )
    original = cfg.get_settings
    cfg.get_settings = lambda: settings  # type: ignore[assignment]
    try:
        yield
    finally:
        cfg.get_settings = original


# --------------------------------------------------------------------------- #
# code_exec                                                                   #
# --------------------------------------------------------------------------- #

async def test_code_exec_prints_to_stdout(code_settings):
    res = await code_tools.code_exec({"code": "print('hi')"})
    assert res["exit_code"] == 0
    assert "hi" in res["stdout"]
    assert res["stderr"] == ""
    assert res["stdout_truncated"] is False


async def test_code_exec_nonzero_exit(code_settings):
    res = await code_tools.code_exec(
        {"code": "import sys; sys.exit(7)"}
    )
    assert res["exit_code"] == 7


async def test_code_exec_writes_to_stderr(code_settings):
    res = await code_tools.code_exec(
        {"code": "import sys; sys.stderr.write('boom')"}
    )
    assert "boom" in res["stderr"]


async def test_code_exec_timeout(code_settings):
    with pytest.raises(ToolError) as ei:
        await code_tools.code_exec(
            {"code": "import time; time.sleep(5)", "timeout_s": 0.5}
        )
    assert ei.value.code == ToolErrorCode.EXEC_TIMEOUT
    assert ei.value.data["timeout_s"] == 0.5


async def test_code_exec_truncates_huge_stdout(code_settings):
    res = await code_tools.code_exec(
        {"code": "import sys; sys.stdout.write('x' * 10000)"}
    )
    assert res["stdout_truncated"] is True
    assert "truncated" in res["stdout"]


async def test_code_exec_invalid_timeout(code_settings):
    with pytest.raises(ToolError) as ei:
        await code_tools.code_exec({"code": "pass", "timeout_s": 999})
    assert ei.value.code == ToolErrorCode.INVALID_PARAMS


async def test_code_exec_stdin_is_piped(code_settings):
    res = await code_tools.code_exec(
        {"code": "import sys; print(sys.stdin.read().upper())", "stdin": "abc"}
    )
    assert "ABC" in res["stdout"]


async def test_code_exec_rejects_non_string_code(code_settings):
    with pytest.raises(ToolError) as ei:
        await code_tools.code_exec({"code": 123})  # type: ignore[arg-type]
    assert ei.value.code == ToolErrorCode.INVALID_PARAMS


# --------------------------------------------------------------------------- #
# code_check                                                                  #
# --------------------------------------------------------------------------- #

async def test_code_check_clean_snippet(code_settings):
    res = await code_tools.code_check({"code": "x = 1\nprint(x)\n"})
    assert res["ok"] is True
    assert res["messages"] == []


async def test_code_check_undefined_name(code_settings):
    res = await code_tools.code_check({"code": "print(does_not_exist)\n"})
    assert res["ok"] is False
    assert any("does_not_exist" in m["message"] for m in res["messages"])
    # Line numbers should be parsed.
    assert all(isinstance(m["line"], int) for m in res["messages"])


async def test_code_check_syntax_error(code_settings):
    """pyflakes reports a syntax error as a message, not a crash."""
    res = await code_tools.code_check({"code": "def broken(:\n"})
    # Either ok=False with a message, or ok=True if pyflakes shrugs;
    # what we *don't* want is a crash. Empty messages list is also OK
    # because pyflakes prints syntax errors on stderr (which we don't
    # parse). The contract: never raise, always return a dict.
    assert isinstance(res["ok"], bool)
    assert isinstance(res["messages"], list)


async def test_code_check_rejects_non_string(code_settings):
    with pytest.raises(ToolError) as ei:
        await code_tools.code_check({"code": None})  # type: ignore[arg-type]
    assert ei.value.code == ToolErrorCode.INVALID_PARAMS
