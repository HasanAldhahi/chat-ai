"""Session isolation regressions (Task 5.1: "Two users simultaneously, try
to access each other's workspaces / Slurm jobs / SSE streams"). The broker
already implements per-user ownership for SSE rooms (Task 1.6) and Slurm
jobs (Task 1.4); this suite is a single-purpose tripwire so a regression
shows up the moment those checks are weakened.
"""

from __future__ import annotations

import json
from typing import Dict

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.dependencies import get_settings
from app.main import create_app


def _auth(user: str) -> Dict[str, str]:
    return {
        "Authorization": "Bearer test-token",
        "X-User": user,
        "Content-Type": "application/json",
    }


def _build_jobs_app() -> TestClient:
    settings = Settings(
        slurm_mock_mode=True,
        slurm_status_poll_interval_s=10.0,
        slurm_status_cache_ttl_s=10.0,
        slurm_cancel_grace_period_s=0.0,
        auth_rate_per_user=200,
    )
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def _build_sse_app() -> TestClient:
    settings = Settings(
        sse_publish_rate_per_session=1000,
        auth_rate_per_user=1000,
    )
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


# --------------------------------------------------------------------------- #
# Slurm jobs                                                                  #
# --------------------------------------------------------------------------- #


def test_bob_cannot_read_alices_job_status():
    with _build_jobs_app() as client:
        r = client.post(
            "/api/jobs",
            content=json.dumps(
                {"session_id": "iso-1", "container_image": "/i.sif"}
            ),
            headers=_auth("alice@gwdg"),
        )
        assert r.status_code == 200
        job_id = r.json()["job_id"]

        r = client.get(f"/api/jobs/{job_id}/status", headers=_auth("bob@gwdg"))
        assert r.status_code == 403


def test_bob_cannot_cancel_alices_job():
    with _build_jobs_app() as client:
        r = client.post(
            "/api/jobs",
            content=json.dumps(
                {"session_id": "iso-2", "container_image": "/i.sif"}
            ),
            headers=_auth("alice@gwdg"),
        )
        assert r.status_code == 200
        job_id = r.json()["job_id"]

        r = client.delete(f"/api/jobs/{job_id}", headers=_auth("bob@gwdg"))
        assert r.status_code == 403


# --------------------------------------------------------------------------- #
# SSE                                                                         #
# --------------------------------------------------------------------------- #


def test_bob_cannot_publish_to_alices_session():
    with _build_sse_app() as client:
        # Alice creates the room with the first publish.
        r = client.post(
            "/api/sse/private-1/events",
            json={"event": "action", "data": {}},
            headers=_auth("alice@gwdg"),
        )
        assert r.status_code == 200

        r = client.post(
            "/api/sse/private-1/events",
            json={"event": "action", "data": {}},
            headers=_auth("bob@gwdg"),
        )
        assert r.status_code == 403


def test_bob_cannot_subscribe_to_alices_session():
    with _build_sse_app() as client:
        r = client.post(
            "/api/sse/private-2/events",
            json={"event": "action", "data": {}},
            headers=_auth("alice@gwdg"),
        )
        assert r.status_code == 200
        r = client.get("/api/sse/private-2", headers=_auth("bob@gwdg"))
        assert r.status_code == 403


# --------------------------------------------------------------------------- #
# Health & docs are still accessible without auth.                            #
# --------------------------------------------------------------------------- #


def test_health_remains_anonymous():
    """Sanity guard: the security regressions should never break the
    public health probe used by ops.
    """
    with _build_jobs_app() as client:
        r = client.get("/health")
        assert r.status_code == 200
