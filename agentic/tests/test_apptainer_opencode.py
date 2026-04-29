"""Static checks for Task 4.3: OpenCode Apptainer image (no binary build)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
OC_DIR = REPO_ROOT / "agentic" / "containers" / "opencode"
DEF_PATH = OC_DIR / "Apptainer.def"
BUILD_SCRIPT_PATH = OC_DIR / "build_image.sh"
TEST_SCRIPT_PATH = OC_DIR / "test_image.sh"
ENTRYPOINT_PATH = OC_DIR / "entrypoint.sh"
README_PATH = OC_DIR / "README.md"


@pytest.fixture(scope="module")
def def_text() -> str:
    return DEF_PATH.read_text(encoding="utf-8")


def test_required_files_exist():
    for p in (
        DEF_PATH,
        BUILD_SCRIPT_PATH,
        TEST_SCRIPT_PATH,
        ENTRYPOINT_PATH,
        README_PATH,
    ):
        assert p.is_file(), f"missing {p}"


def test_bootstraps_from_mcp(def_text: str):
    assert "From: ../mcp/mcp.sif" in def_text


def test_installs_via_github_tarball(def_text: str):
    assert "anomalyco/opencode" in def_text


def test_scripts_executable_bit():
    for p in (BUILD_SCRIPT_PATH, TEST_SCRIPT_PATH, ENTRYPOINT_PATH):
        mode = p.stat().st_mode
        assert mode & 0o111, f"not executable: {p}"


def test_bundles_opencode_runtime(def_text: str):
    assert "../../opencode_runtime /opt/agentic/opencode_runtime" in def_text


def test_post_imports_launcher(def_text: str):
    assert "opencode_runtime.launcher" in def_text


def test_mcp_stdio_gateway_import(def_text: str):
    assert "opencode_runtime.mcp_stdio_gateway" in def_text
