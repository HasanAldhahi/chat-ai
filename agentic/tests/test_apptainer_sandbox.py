"""Static tests for Task 2.4 sandbox assets (bubblewrap wrapper).

No apptainer binary required — same pattern as ``test_apptainer_base.py``.
Operator-facing checks live in ``containers/base/test_image.sh``.
"""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SANDBOX_DIR = REPO_ROOT / "agentic" / "containers" / "sandbox"
WRAPPER_PATH = SANDBOX_DIR / "chrome-headless-sandbox.sh"
README_PATH = SANDBOX_DIR / "README.md"


def test_wrapper_exists_and_executable():
    assert WRAPPER_PATH.is_file()
    mode = WRAPPER_PATH.stat().st_mode
    assert mode & stat.S_IXUSR, "chrome-headless-sandbox.sh must be executable"


def test_wrapper_shebang_posix_sh():
    first = WRAPPER_PATH.read_text(encoding="utf-8").splitlines()[0]
    assert first == "#!/bin/sh"


def test_wrapper_sets_strict_mode():
    text = WRAPPER_PATH.read_text(encoding="utf-8")
    assert re.search(r"^\s*set\s+-eu\b", text, re.MULTILINE)


def test_wrapper_invokes_bwrap_with_security_relevant_flags():
    text = WRAPPER_PATH.read_text(encoding="utf-8")
    for token in (
        "bwrap",
        "--die-with-parent",
        "--ro-bind /usr /usr",
        "--tmpfs /tmp",
        "--tmpfs /var/tmp",
        "google-chrome-stable",
    ):
        assert token in text, f"wrapper must contain {token!r}"


def test_wrapper_documents_net_isolation_env():
    text = WRAPPER_PATH.read_text(encoding="utf-8")
    assert "CHAT_AI_BROWSER_NET_ISOLATION" in text


def test_readme_documents_path_and_task():
    text = README_PATH.read_text(encoding="utf-8")
    assert "Task 2.4" in text
    assert "/opt/chat-ai/sandbox/" in text


def test_sh_syntax_check_wrapper():
    assert os.system(f"sh -n {WRAPPER_PATH!s} >/dev/null 2>&1") == 0
