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


def test_performance_testing_doc_exists():
    p = REPO / "agentic" / "docs" / "PERFORMANCE_TESTING.md"
    assert p.is_file(), "PERFORMANCE_TESTING.md must exist for Task 5.3 traceability"


def test_performance_report_template_exists():
    p = (
        REPO
        / ".specify"
        / "tasks"
        / "001-agentic-layer"
        / "PERFORMANCE_REPORT.md"
    )
    assert p.is_file(), "PERFORMANCE_REPORT.md must exist for Task 5.3 traceability"


def test_locustfile_exists():
    p = REPO / "agentic" / "perf" / "locustfile.py"
    assert p.is_file(), "perf/locustfile.py must exist for Task 5.3 load campaigns"


def test_uat_plan_doc_exists():
    p = REPO / "agentic" / "docs" / "UAT_PLAN.md"
    assert p.is_file(), "UAT_PLAN.md must exist for Task 5.4 traceability"


def test_uat_report_template_exists():
    p = (
        REPO
        / ".specify"
        / "tasks"
        / "001-agentic-layer"
        / "UAT_REPORT.md"
    )
    assert p.is_file(), "UAT_REPORT.md must exist for Task 5.4 traceability"


# Task 5.5 Production Readiness -------------------------------------------------------------------
def test_runbook_slurm_exist():
    p = REPO / "agentic" / "docs" / "runbook-slurm-job-failures.md"
    assert p.is_file(), "runbook-slurm-job-failures.md must exist for Task 5.5"


def test_runbook_broker_exist():
    p = REPO / "agentic" / "docs" / "runbook-broker-downtime.md"
    assert p.is_file(), "runbook-broker-downtime.md must exist for Task 5.5"


def test_runbook_vault_exist():
    p = REPO / "agentic" / "docs" / "runbook-vault-unavailability.md"
    assert p.is_file(), "runbook-vault-unavailability.md must exist for Task 5.5"


def test_runbook_security_exist():
    p = REPO / "agentic" / "docs" / "runbook-security-incident-response.md"
    assert p.is_file(), "runbook-security-incident-response.md must exist for Task 5.5"


def test_prometheus_middleware_exist():
    p = REPO / "agentic" / "app" / "middleware" / "prometheus.py"
    assert p.is_file(), "prometheus.py middleware must exist for Task 5.5"


def test_metrics_endpoint_exist():
    p = REPO / "agentic" / "app" / "routers" / "metrics.py"
    assert p.is_file(), "metrics.py router must exist for Task 5.5"
