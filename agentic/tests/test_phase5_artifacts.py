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


def test_security_pentest_report_exists():
    p = (
        REPO
        / ".specify"
        / "tasks"
        / "001-agentic-layer"
        / "SECURITY_PENTEST_REPORT.md"
    )
    assert p.is_file(), "SECURITY_PENTEST_REPORT.md must exist for Task 5.1 traceability"


def test_e2e_testing_doc_exists():
    p = REPO / "agentic" / "docs" / "E2E_TESTING.md"
    assert p.is_file(), "E2E_TESTING.md must exist for Task 5.2 traceability"
