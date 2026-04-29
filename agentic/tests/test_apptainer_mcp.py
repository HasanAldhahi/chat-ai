"""Tests for Task 2.2: MCP Server Apptainer image.

Same pattern as ``test_apptainer_base.py`` — parse the recipe and
shell scripts as text and assert structure / required content. No
apptainer binary needed; fast; runs anywhere pytest does.

The acceptance criteria that genuinely require a built ``.sif``
(``apptainer run mcp.sif`` -> uvicorn -> /health -> 200) are
covered by ``agentic/containers/mcp/test_image.sh`` which the
cluster operator runs after building.
"""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTAINERS_DIR = REPO_ROOT / "agentic" / "containers"
MCP_DIR = CONTAINERS_DIR / "mcp"
DEF_PATH = MCP_DIR / "Apptainer.def"
BUILD_SCRIPT_PATH = MCP_DIR / "build_image.sh"
TEST_SCRIPT_PATH = MCP_DIR / "test_image.sh"
MCP_README_PATH = MCP_DIR / "README.md"
INDEX_README_PATH = CONTAINERS_DIR / "README.md"
PACKAGE_DIR = REPO_ROOT / "agentic" / "mcp_server"
PACKAGE_README_PATH = PACKAGE_DIR / "README.md"
REQUIREMENTS_PATH = REPO_ROOT / "agentic" / "requirements.txt"


@pytest.fixture(scope="module")
def def_text() -> str:
    return DEF_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def build_script_text() -> str:
    return BUILD_SCRIPT_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def test_script_text() -> str:
    return TEST_SCRIPT_PATH.read_text(encoding="utf-8")


def _section(text: str, header: str) -> str:
    pattern = re.compile(
        rf"^{re.escape(header)}\b.*?(?=^%[a-z]+\b|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    m = pattern.search(text)
    return m.group(0) if m else ""


# --------------------------------------------------------------------------- #
# Layout                                                                      #
# --------------------------------------------------------------------------- #

def test_required_files_exist():
    for p in (
        DEF_PATH,
        BUILD_SCRIPT_PATH,
        TEST_SCRIPT_PATH,
        MCP_README_PATH,
        PACKAGE_README_PATH,
    ):
        assert p.is_file(), f"missing required file: {p}"


def test_def_size_sane():
    size = DEF_PATH.stat().st_size
    assert 1_000 < size < 50_000, (
        f"Apptainer.def is {size} bytes (expected ~1-50 KB)"
    )


def test_mcp_server_package_layout():
    # Spot-check the package the recipe ships into the image.
    for child in (
        "__init__.py",
        "main.py",
        "server.py",
        "config.py",
        "errors.py",
        "security.py",
        "tools/__init__.py",
        "tools/fs.py",
        "tools/web.py",
        "tools/code.py",
    ):
        assert (PACKAGE_DIR / child).is_file(), f"missing mcp_server/{child}"


# --------------------------------------------------------------------------- #
# Apptainer.def — header                                                      #
# --------------------------------------------------------------------------- #

def test_def_bootstrap_is_localimage(def_text: str):
    assert re.search(r"^Bootstrap:\s*localimage\b", def_text, re.MULTILINE), (
        "Apptainer.def must declare `Bootstrap: localimage` to derive from base"
    )


def test_def_from_points_at_base_sif(def_text: str):
    assert re.search(r"^From:\s*\.\./base/base\.sif\b", def_text, re.MULTILINE), (
        "Apptainer.def must declare `From: ../base/base.sif` (Task 2.1 image)"
    )


# --------------------------------------------------------------------------- #
# %files — must copy the package + requirements                              #
# --------------------------------------------------------------------------- #

def test_def_files_copies_mcp_server(def_text: str):
    files = _section(def_text, "%files")
    assert files, "Apptainer.def has no %files section"
    assert "mcp_server" in files, "%files must copy the mcp_server package"
    assert "requirements.txt" in files, (
        "%files must copy requirements.txt so %post can pip install"
    )


# --------------------------------------------------------------------------- #
# %post — installs deps and validates imports                                #
# --------------------------------------------------------------------------- #

REQUIRED_POST_TOKENS = (
    # The recipe must install pyflakes (code_check dep).
    "pyflakes",
    # Fastapi / uvicorn / httpx come from requirements.txt.
    "requirements.txt",
    "python3.11",
    "pip install",
    # Sanity import check — fails the build if mcp_server doesn't import.
    "import mcp_server",
    # Strict shell.
    "set -eux",
)


@pytest.mark.parametrize("token", REQUIRED_POST_TOKENS)
def test_def_post_contains_token(def_text: str, token: str):
    post = _section(def_text, "%post")
    assert post, "Apptainer.def has no %post section"
    assert token in post, (
        f"%post must reference {token!r}; removing it likely breaks an "
        f"acceptance criterion or runtime."
    )


def test_def_post_writes_image_info(def_text: str):
    post = _section(def_text, "%post")
    assert "/etc/chat-ai-image-info" in post, (
        "%post must stamp /etc/chat-ai-image-info (parity with base image)"
    )
    assert "image=mcp" in post, "image-info must identify this as image=mcp"
    assert "task=2.2" in post, "image-info must mark task=2.2"


# --------------------------------------------------------------------------- #
# %environment                                                                #
# --------------------------------------------------------------------------- #


def test_def_environment_defers_proxy_to_base(def_text: str):
    """HTTP(S)_PROXY live on the base layer; mcp must not duplicate them."""
    env = _section(def_text, "%environment")
    assert env, "Apptainer.def has no %environment section"
    assert "Task 2.5" in env, "%environment should reference Task 2.5 / base proxy"
    assert not re.search(r"^\s*export\s+HTTP_PROXY=", env, re.MULTILINE)
    assert not re.search(r"^\s*export\s+HTTPS_PROXY=", env, re.MULTILINE)
    assert not re.search(r"^\s*export\s+NO_PROXY=", env, re.MULTILINE)


@pytest.mark.parametrize("var", ["http_proxy", "https_proxy", "no_proxy"])
def test_def_environment_no_lower_case_proxy(def_text: str, var: str):
    env = _section(def_text, "%environment")
    assert not re.search(rf"^\s*export\s+{var}=", env, re.MULTILINE)


def test_def_environment_sets_pythonpath_and_locale(def_text: str):
    env = _section(def_text, "%environment")
    assert "LANG=" in env
    assert "PYTHONUNBUFFERED=1" in env
    assert "/opt/agentic" in env, (
        "%environment must put /opt/agentic on PYTHONPATH so "
        "`python3.11 -m mcp_server.*` works"
    )


def test_def_environment_exposes_default_port(def_text: str):
    env = _section(def_text, "%environment")
    assert "MCP_SERVER_PORT" in env, (
        "%environment must default MCP_SERVER_PORT (8080) so the runscript "
        "and any consumer can pick it up without re-deriving it."
    )


# --------------------------------------------------------------------------- #
# %runscript — must launch uvicorn against mcp_server.main:app                #
# --------------------------------------------------------------------------- #

def test_def_runscript_starts_uvicorn(def_text: str):
    rs = _section(def_text, "%runscript")
    assert rs, "Apptainer.def has no %runscript section"
    assert "uvicorn" in rs, "%runscript must launch uvicorn"
    assert "mcp_server.main:app" in rs, (
        "%runscript must run the FastAPI app at mcp_server.main:app"
    )
    assert "MCP_SERVER_PORT" in rs, (
        "%runscript must honour ${MCP_SERVER_PORT:-8080}"
    )
    assert "--help" in rs, "%runscript must handle --help"


def test_def_startscript_starts_uvicorn(def_text: str):
    ss = _section(def_text, "%startscript")
    assert ss, "Apptainer.def has no %startscript section"
    assert "uvicorn" in ss and "mcp_server.main:app" in ss, (
        "%startscript must launch the same uvicorn target as %runscript "
        "so `apptainer instance start` produces an equivalent process."
    )


# --------------------------------------------------------------------------- #
# %labels                                                                     #
# --------------------------------------------------------------------------- #

REQUIRED_LABELS = {
    "org.chat-ai.image": "mcp",
    "org.chat-ai.task": "2.2",
    "org.chat-ai.parent": "base",
    "org.chat-ai.python": "3.11",
}


@pytest.mark.parametrize("key,value", list(REQUIRED_LABELS.items()))
def test_def_required_labels_present(def_text: str, key: str, value: str):
    labels = _section(def_text, "%labels")
    assert labels, "Apptainer.def has no %labels section"
    pattern = rf"^\s*{re.escape(key)}\s+{re.escape(value)}\s*$"
    assert re.search(pattern, labels, re.MULTILINE), (
        f"%labels must contain `{key} {value}`"
    )


# --------------------------------------------------------------------------- #
# build_image.sh                                                              #
# --------------------------------------------------------------------------- #

def test_build_script_is_executable():
    mode = BUILD_SCRIPT_PATH.stat().st_mode
    assert mode & stat.S_IXUSR
    assert os.access(BUILD_SCRIPT_PATH, os.X_OK)


def test_build_script_shebang_is_posix_sh(build_script_text: str):
    first = build_script_text.splitlines()[0]
    assert first == "#!/bin/sh", f"shebang must be #!/bin/sh; got {first!r}"


def test_build_script_uses_strict_mode(build_script_text: str):
    assert re.search(r"^\s*set\s+-e", build_script_text, re.MULTILINE)


def test_build_script_checks_apptainer_present(build_script_text: str):
    assert "command -v apptainer" in build_script_text


def test_build_script_checks_base_sif_present(build_script_text: str):
    """Build must short-circuit if Task 2.1's base.sif isn't there."""
    assert "base.sif" in build_script_text
    assert re.search(r'\[ ! -f "?\$BASE_SIF"? \]', build_script_text), (
        "build_image.sh must verify ../base/base.sif exists before invoking "
        "apptainer (the localimage bootstrap will fail without it)"
    )


@pytest.mark.parametrize(
    "flag", ["--fakeroot", "--remote", "--force", "--output", "--help"],
)
def test_build_script_supports_flag(build_script_text: str, flag: str):
    assert flag in build_script_text


def test_build_script_enforces_size_budget(build_script_text: str):
    assert "5368709120" in build_script_text, (
        "build_image.sh must enforce the 5 GB ceiling literal"
    )
    assert re.search(r"exit\s+4", build_script_text), (
        "build_image.sh must `exit 4` when size is exceeded"
    )


def test_build_script_propagates_metadata(build_script_text: str):
    assert "APPTAINERENV_BUILD_SHA" in build_script_text
    assert "APPTAINERENV_BUILD_DATE" in build_script_text


# --------------------------------------------------------------------------- #
# test_image.sh                                                               #
# --------------------------------------------------------------------------- #

def test_test_image_script_is_executable():
    assert os.access(TEST_SCRIPT_PATH, os.X_OK)


def test_test_image_script_shebang_is_posix_sh(test_script_text: str):
    first = test_script_text.splitlines()[0]
    assert first == "#!/bin/sh"


def test_test_image_script_exercises_acceptance_criteria(test_script_text: str):
    """Each Task 2.2 acceptance criterion is probed by the smoke."""
    expected_probes = (
        "/health",
        "list_tools",
        "fs_read",
        "fs_write",
        "fs_list",
        "web_search",
        "web_browse",
        "code_exec",
        "code_check",
        "instance start",
        "path_not_allowed",
        "url_blocked",
        "exec_timeout",
    )
    for probe in expected_probes:
        assert probe in test_script_text, (
            f"test_image.sh must exercise {probe!r} (acceptance criterion)"
        )


# --------------------------------------------------------------------------- #
# Index README                                                                #
# --------------------------------------------------------------------------- #

def test_index_readme_lists_mcp():
    text = INDEX_README_PATH.read_text(encoding="utf-8")
    assert "mcp/" in text, (
        "agentic/containers/README.md must reference the mcp/ subdirectory"
    )


# --------------------------------------------------------------------------- #
# requirements.txt — pyflakes pin shipped to the image                        #
# --------------------------------------------------------------------------- #

def test_requirements_lists_pyflakes():
    text = REQUIREMENTS_PATH.read_text(encoding="utf-8")
    assert re.search(r"^pyflakes\b", text, re.MULTILINE), (
        "agentic/requirements.txt must list pyflakes (pinned) so it ends up "
        "in the MCP image and the dev venv stays consistent."
    )
