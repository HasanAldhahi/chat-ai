"""Tests for Task 2.3: OpenHands Apptainer image.

Same static-parse pattern as ``test_apptainer_base.py`` and
``test_apptainer_mcp.py``: read the recipe / scripts as text and
assert structure + required content. No apptainer binary needed.

The acceptance criteria that genuinely require a built ``.sif`` (e.g.
"OpenHands successfully calls fs_read tool" — which needs vLLM + LLM
tokens) are covered by ``agentic/containers/openhands/test_image.sh``,
which the cluster operator runs after building.
"""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTAINERS_DIR = REPO_ROOT / "agentic" / "containers"
OPENHANDS_DIR = CONTAINERS_DIR / "openhands"
DEF_PATH = OPENHANDS_DIR / "Apptainer.def"
BUILD_SCRIPT_PATH = OPENHANDS_DIR / "build_image.sh"
TEST_SCRIPT_PATH = OPENHANDS_DIR / "test_image.sh"
ENTRYPOINT_PATH = OPENHANDS_DIR / "entrypoint.sh"
README_PATH = OPENHANDS_DIR / "README.md"
INDEX_README_PATH = CONTAINERS_DIR / "README.md"
PACKAGE_DIR = REPO_ROOT / "agentic" / "openhands_runtime"
PACKAGE_README = PACKAGE_DIR / "README.md"
CONFIG_TEMPLATE = PACKAGE_DIR / "openhands_config.toml"


@pytest.fixture(scope="module")
def def_text() -> str:
    return DEF_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def build_script_text() -> str:
    return BUILD_SCRIPT_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def test_script_text() -> str:
    return TEST_SCRIPT_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def entrypoint_text() -> str:
    return ENTRYPOINT_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def config_template_text() -> str:
    return CONFIG_TEMPLATE.read_text(encoding="utf-8")


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
        ENTRYPOINT_PATH,
        README_PATH,
        PACKAGE_README,
        CONFIG_TEMPLATE,
    ):
        assert p.is_file(), f"missing required file: {p}"


def test_def_size_sane():
    size = DEF_PATH.stat().st_size
    assert 1_000 < size < 50_000


def test_openhands_runtime_layout():
    for child in (
        "__init__.py",
        "config.py",
        "launcher.py",
        "sse_forwarder.py",
        "openhands_config.toml",
    ):
        assert (PACKAGE_DIR / child).is_file(), f"missing openhands_runtime/{child}"


# --------------------------------------------------------------------------- #
# Apptainer.def — header                                                      #
# --------------------------------------------------------------------------- #

def test_def_bootstrap_localimage(def_text: str):
    assert re.search(r"^Bootstrap:\s*localimage\b", def_text, re.MULTILINE)


def test_def_from_points_at_mcp_sif(def_text: str):
    assert re.search(r"^From:\s*\.\./mcp/mcp\.sif\b", def_text, re.MULTILINE), (
        "OpenHands image must bootstrap from ../mcp/mcp.sif (Task 2.2 image)"
    )


# --------------------------------------------------------------------------- #
# %files                                                                      #
# --------------------------------------------------------------------------- #

def test_def_files_copies_runtime_and_config(def_text: str):
    files = _section(def_text, "%files")
    assert "openhands_runtime" in files
    assert "/etc/openhands/config.toml" in files
    assert "entrypoint.sh" in files


# --------------------------------------------------------------------------- #
# %post — must install OpenHands and validate imports                         #
# --------------------------------------------------------------------------- #

REQUIRED_POST_TOKENS = (
    "openhands-ai",                # the actual package install
    "tomli",                       # TOML config parser dep
    "pip install",
    "import openhands_runtime",    # build-time sanity check
    "set -eux",
    "/etc/chat-ai-image-info",
)


@pytest.mark.parametrize("token", REQUIRED_POST_TOKENS)
def test_def_post_contains_token(def_text: str, token: str):
    post = _section(def_text, "%post")
    assert post, "Apptainer.def has no %post section"
    assert token in post


def test_def_post_pins_openhands_version(def_text: str):
    """Pin must be present; floating version on a fast-moving project is
    a recipe for surprise breakage.
    """
    post = _section(def_text, "%post")
    assert re.search(r"openhands-ai==\d+\.\d+\.\d+", post), (
        "%post must pin openhands-ai (e.g. openhands-ai==0.13.0)"
    )


def test_def_post_image_info_marks_task(def_text: str):
    post = _section(def_text, "%post")
    assert "image=openhands" in post
    assert "task=2.3" in post
    assert "parent=mcp" in post


# --------------------------------------------------------------------------- #
# %environment — proxy defaults come from base image (Task 2.5)              #
# --------------------------------------------------------------------------- #


def test_def_environment_defers_proxy_to_base(def_text: str):
    env = _section(def_text, "%environment")
    assert env, "Apptainer.def has no %environment section"
    assert not re.search(r"^\s*export\s+HTTP_PROXY=", env, re.MULTILINE)
    assert not re.search(r"^\s*export\s+HTTPS_PROXY=", env, re.MULTILINE)
    assert not re.search(r"^\s*export\s+NO_PROXY=", env, re.MULTILINE)


@pytest.mark.parametrize("var", ["http_proxy", "https_proxy", "no_proxy"])
def test_def_environment_no_lower_case_proxy(def_text: str, var: str):
    env = _section(def_text, "%environment")
    assert not re.search(rf"^\s*export\s+{var}=", env, re.MULTILINE)


def test_def_environment_pythonpath_includes_agentic(def_text: str):
    env = _section(def_text, "%environment")
    assert "/opt/agentic" in env, (
        "%environment must put /opt/agentic on PYTHONPATH so "
        "`python3.11 -m openhands_runtime.launcher` works"
    )


# --------------------------------------------------------------------------- #
# %runscript / %startscript — must invoke the launcher                       #
# --------------------------------------------------------------------------- #

def test_def_runscript_invokes_entrypoint(def_text: str):
    rs = _section(def_text, "%runscript")
    assert rs, "Apptainer.def has no %runscript section"
    assert "/opt/agentic/entrypoint.sh" in rs, (
        "%runscript must exec /opt/agentic/entrypoint.sh by default"
    )
    assert "--help" in rs, "%runscript must handle --help"


def test_def_startscript_invokes_entrypoint(def_text: str):
    ss = _section(def_text, "%startscript")
    assert ss, "Apptainer.def has no %startscript section"
    assert "/opt/agentic/entrypoint.sh" in ss


# --------------------------------------------------------------------------- #
# %labels                                                                     #
# --------------------------------------------------------------------------- #

REQUIRED_LABELS = {
    "org.chat-ai.image": "openhands",
    "org.chat-ai.task": "2.3",
    "org.chat-ai.parent": "mcp",
    "org.chat-ai.python": "3.11",
    "org.chat-ai.framework": "openhands-v1",
}


@pytest.mark.parametrize("key,value", list(REQUIRED_LABELS.items()))
def test_def_required_labels_present(def_text: str, key: str, value: str):
    labels = _section(def_text, "%labels")
    pattern = rf"^\s*{re.escape(key)}\s+{re.escape(value)}\s*$"
    assert re.search(pattern, labels, re.MULTILINE), (
        f"%labels must contain `{key} {value}`"
    )


# --------------------------------------------------------------------------- #
# entrypoint.sh                                                               #
# --------------------------------------------------------------------------- #

def test_entrypoint_is_executable():
    assert os.access(ENTRYPOINT_PATH, os.X_OK)


def test_entrypoint_is_posix_sh(entrypoint_text: str):
    first = entrypoint_text.splitlines()[0]
    assert first == "#!/bin/sh"


def test_entrypoint_execs_launcher(entrypoint_text: str):
    assert "openhands_runtime.launcher" in entrypoint_text
    assert re.search(r"^\s*set\s+-eu", entrypoint_text, re.MULTILINE)


# --------------------------------------------------------------------------- #
# build_image.sh                                                              #
# --------------------------------------------------------------------------- #

def test_build_script_is_executable():
    mode = BUILD_SCRIPT_PATH.stat().st_mode
    assert mode & stat.S_IXUSR
    assert os.access(BUILD_SCRIPT_PATH, os.X_OK)


def test_build_script_shebang_is_posix_sh(build_script_text: str):
    first = build_script_text.splitlines()[0]
    assert first == "#!/bin/sh"


def test_build_script_uses_strict_mode(build_script_text: str):
    assert re.search(r"^\s*set\s+-e", build_script_text, re.MULTILINE)


def test_build_script_checks_apptainer_present(build_script_text: str):
    assert "command -v apptainer" in build_script_text


def test_build_script_refuses_when_parent_missing(build_script_text: str):
    """Build must short-circuit when mcp.sif is missing (Task 2.2 image)."""
    assert "mcp.sif" in build_script_text
    assert re.search(r'\[ ! -f "?\$PARENT_SIF"? \]', build_script_text), (
        "build_image.sh must verify ../mcp/mcp.sif exists before invoking "
        "apptainer (the localimage bootstrap fails without it)"
    )


@pytest.mark.parametrize(
    "flag", ["--fakeroot", "--remote", "--force", "--output", "--help"],
)
def test_build_script_supports_flag(build_script_text: str, flag: str):
    assert flag in build_script_text


def test_build_script_enforces_size_budget(build_script_text: str):
    assert "5368709120" in build_script_text
    assert re.search(r"exit\s+4", build_script_text)


# --------------------------------------------------------------------------- #
# test_image.sh                                                               #
# --------------------------------------------------------------------------- #

def test_test_image_script_is_executable():
    assert os.access(TEST_SCRIPT_PATH, os.X_OK)


def test_test_image_script_shebang_is_posix_sh(test_script_text: str):
    first = test_script_text.splitlines()[0]
    assert first == "#!/bin/sh"


def test_test_image_script_exercises_acceptance_criteria(test_script_text: str):
    """Each Task 2.3 acceptance criterion is probed by the smoke."""
    expected_probes = (
        "import openhands",                # OpenHands installed
        "import openhands_runtime",        # adapter importable
        "/etc/openhands/config.toml",       # config template present
        "tomli.load",                       # config is parseable TOML
        "openhands_runtime.launcher",      # launcher invocable
        "instance start",                   # single-command boot
        "/health",                          # MCP up after boot
    )
    for probe in expected_probes:
        assert probe in test_script_text, (
            f"test_image.sh must exercise {probe!r} (acceptance criterion)"
        )


# --------------------------------------------------------------------------- #
# OpenHands config template                                                   #
# --------------------------------------------------------------------------- #

REQUIRED_CONFIG_TOKENS = (
    "[runtime]",
    'type = "local"',                      # acceptance: no Docker/Podman
    "[llm]",
    "${LLM_API_URL}",
    "${LLM_MODEL}",
    "${LLM_PARSER}",
    "[tools]",
    "builtin_enabled = false",             # MCP is the only tool source
    "[[mcp.servers]]",
    "${MCP_SERVER_URL}",
    "/rpc",                                # MCP wire path (Task 2.2)
)


@pytest.mark.parametrize("token", REQUIRED_CONFIG_TOKENS)
def test_openhands_config_template_contains(config_template_text: str, token: str):
    assert token in config_template_text, (
        f"openhands_config.toml must reference {token!r}"
    )


def test_openhands_config_template_no_proxy_hardcode(config_template_text: str):
    """The template doesn't bake a proxy in either."""
    assert "www-cache.gwdg.de" not in config_template_text


# --------------------------------------------------------------------------- #
# Index README                                                                #
# --------------------------------------------------------------------------- #

def test_index_readme_lists_openhands():
    text = INDEX_README_PATH.read_text(encoding="utf-8")
    assert "openhands/" in text, (
        "agentic/containers/README.md must reference the openhands/ subdirectory"
    )
