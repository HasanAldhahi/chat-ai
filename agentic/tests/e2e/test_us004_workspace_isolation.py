"""US-004 Workspace isolation — two concurrent users must not be able
to reach each other's Slurm jobs or SSE sessions through the broker.
"""

from __future__ import annotations

import json


def _submit(client, headers, session_id: str = "iso-1") -> str:
    r = client.post(
        "/api/jobs",
        content=json.dumps({"session_id": session_id, "container_image": "/i.sif"}),
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["job_id"]


def test_us004_bob_cannot_see_alices_job_status(broker_client, auth_headers):
    job_id = _submit(broker_client, auth_headers("alice@gwdg"), session_id="iso-A")

    r = broker_client.get(
        f"/api/jobs/{job_id}/status", headers=auth_headers("bob@gwdg")
    )
    assert r.status_code == 403


def test_us004_bob_cannot_cancel_alices_job(broker_client, auth_headers):
    job_id = _submit(broker_client, auth_headers("alice@gwdg"), session_id="iso-B")

    r = broker_client.delete(
        f"/api/jobs/{job_id}", headers=auth_headers("bob@gwdg")
    )
    assert r.status_code == 403


def test_us004_alice_can_see_her_own_job(broker_client, auth_headers):
    job_id = _submit(broker_client, auth_headers("alice@gwdg"), session_id="iso-C")

    r = broker_client.get(
        f"/api/jobs/{job_id}/status", headers=auth_headers("alice@gwdg")
    )
    assert r.status_code == 200, r.text


def test_us004_sse_publish_locked_to_first_owner(broker_client, auth_headers):
    """Alice creates the SSE room; Bob's publish fails 403."""
    r = broker_client.post(
        "/api/sse/iso-D/events",
        json={"event": "action", "data": {}},
        headers=auth_headers("alice@gwdg"),
    )
    assert r.status_code == 200

    r = broker_client.post(
        "/api/sse/iso-D/events",
        json={"event": "action", "data": {}},
        headers=auth_headers("bob@gwdg"),
    )
    assert r.status_code == 403


def test_us004_sse_subscribe_locked_to_first_owner(broker_client, auth_headers):
    """Alice creates the room; Bob's GET subscription fails 403 before
    any bytes flow, so a leaked session_id does not become a side
    channel.
    """
    r = broker_client.post(
        "/api/sse/iso-E/events",
        json={"event": "action", "data": {}},
        headers=auth_headers("alice@gwdg"),
    )
    assert r.status_code == 200

    r = broker_client.get("/api/sse/iso-E", headers=auth_headers("bob@gwdg"))
    assert r.status_code == 403
