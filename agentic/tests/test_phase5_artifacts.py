"""Phase 5: lightweight artifact checks (tasks.md 5.x planning deliverables)."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_production_checklist_exists():
    p = (
        REPO
        / ".specify"
        / "tasks"
        / "001-agentic-layer"
        / "PRODUCTION_CHECKLIST.md"
    )
    assert p.is_file(), "PRODUCTION_CHECKLIST.md must exist for Task 5.x traceability"


def test_skills_framework_doc_exists():
    p = REPO / "agentic" / "docs" / "SKILLS_FRAMEWORK.md"
    assert p.is_file()
