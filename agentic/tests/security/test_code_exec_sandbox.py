"""code_exec sandbox regressions (Task 5.1: "code_exec({code: 'import os;
os.system(\"rm -rf /\")'}) timeout error" / "30 second timeout"). The
outer Apptainer + nsjail layer is the load-bearing isolation; here we
verify the inner timeout enforcement works because that's the last
backstop if a user-submitted snippet decides to spin forever.
"""

from __future__ import annotations

import pytest

import mcp_server.config as mcp_cfg
from mcp_server.errors import ToolError, ToolErrorCode
from mcp_server.tools import code as code_tool


@pytest.fixture
def short_timeout(monkeypatch):
    settings = mcp_cfg.MCPSettings(
        code_exec_default_timeout_s=0.3,
        code_exec_max_timeout_s=0.5,
        code_exec_max_output_bytes=4096,
    )
    monkeypatch.setattr(mcp_cfg, "get_settings", lambda: settings)
    yield


async def test_code_exec_kills_an_infinite_loop(short_timeout):
    with pytest.raises(ToolError) as ei:
        await code_tool.code_exec({"code": "while True:\n    pass\n"})
    assert ei.value.code == ToolErrorCode.EXEC_TIMEOUT


async def test_code_exec_rejects_oversize_timeout(short_timeout):
    with pytest.raises(ToolError) as ei:
        await code_tool.code_exec({"code": "print('x')", "timeout_s": 60})
    assert ei.value.code == ToolErrorCode.INVALID_PARAMS


async def test_code_exec_rejects_negative_timeout(short_timeout):
    with pytest.raises(ToolError) as ei:
        await code_tool.code_exec({"code": "print('x')", "timeout_s": -1})
    assert ei.value.code == ToolErrorCode.INVALID_PARAMS


async def test_code_exec_isolated_mode_blocks_user_site(short_timeout):
    """``-I`` flag should also drop ``PYTHON*`` env vars. The inner
    sandbox cannot replace the outer one, but ``python -I`` is the
    minimum hardening we promise inside the broker.
    """
    res = await code_tool.code_exec(
        {"code": "import sys; print(sys.flags.isolated)"}
    )
    assert res["exit_code"] == 0
    assert res["stdout"].strip() == "1", res
