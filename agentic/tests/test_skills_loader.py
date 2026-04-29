"""Unit tests for mcp_server.skills loader (Task 4.4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_server.skills.loader import load_skill_store, reset_skill_cache

REPO_SKILLS = Path(__file__).resolve().parents[1] / "skills"


@pytest.fixture(autouse=True)
def _clear_skill_cache():
    reset_skill_cache()
    yield
    reset_skill_cache()


def test_bundled_skills_load():
    st = load_skill_store(REPO_SKILLS, reload=True)
    assert len(st.docs) >= 4
    names = {d.skill_name for d in st.docs}
    assert "gwdg_slurm_scripts" in names
    assert "file_permissions" in names


def test_openhands_gets_slurm_and_wildcards():
    st = load_skill_store(REPO_SKILLS, reload=True)
    oh = st.for_framework("openhands")
    names = {d.skill_name for d in oh}
    assert "gwdg_slurm_scripts" in names
    assert "file_permissions" in names
    assert "tool_syntax" in names


def test_empty_framework_gets_only_wildcard(tmp_path):
    good = tmp_path / "wild.md"
    good.write_text(
        "---\n"
        "skill_name: only_star\n"
        'description: "x"\n'
        "framework: \"*\"\n"
        "---\n\n"
        "body\n",
        encoding="utf-8",
    )
    (tmp_path / "miss.md").write_text(
        "---\n"
        "skill_name: oh_only\n"
        'description: "y"\n'
        "framework: openhands\n"
        "---\n\n"
        "x\n",
        encoding="utf-8",
    )
    st = load_skill_store(tmp_path, reload=True)
    empty_fw = st.for_framework("")
    assert {d.skill_name for d in empty_fw} == {"only_star"}


def test_invalid_frontmatter_skipped(tmp_path, caplog):
    import logging

    (tmp_path / "bad.md").write_text("no yaml frontmatter", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        st = load_skill_store(tmp_path, reload=True)
    assert len(st.docs) == 0
