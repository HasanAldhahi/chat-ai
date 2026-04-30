"""US-006 Secret injection — the agent retrieves user-scoped credentials
through the broker's ``/api/secrets/{type}`` endpoint, and the broker
enforces per-user Vault path scoping so Bob cannot reach Alice's path.
"""

from __future__ import annotations

from typing import Dict

import httpx


def _kv(value: str = "sk-real-secret"):
    return {
        "request_id": "abc",
        "lease_duration": 1800,
        "data": {
            "data": {"search_api_key": value},
            "metadata": {"version": 1},
        },
    }


def _auth(user: str) -> Dict[str, str]:
    return {
        "Authorization": "Bearer test",
        "X-User": user,
        "Content-Type": "application/json",
    }


def test_us006_agent_receives_secret_for_self(make_broker_client_with_vault):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_kv())

    client, captured = make_broker_client_with_vault(handler)
    with client as c:
        r = c.get("/api/secrets/search_api_key", headers=_auth("alice@gwdg"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["secret_type"] == "search_api_key"
    assert body["value"] == "sk-real-secret"
    assert any("/users/alice/" in url for url in captured)


def test_us006_path_is_scoped_per_user(make_broker_client_with_vault):
    """Alice and Bob each fetch their own secret. The broker must hit
    *each user's* Vault path; never the other one's.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_kv())

    client, captured = make_broker_client_with_vault(handler)
    with client as c:
        r = c.get("/api/secrets/search_api_key", headers=_auth("alice@gwdg"))
        assert r.status_code == 200
        r = c.get("/api/secrets/search_api_key", headers=_auth("bob@gwdg"))
        assert r.status_code == 200

    assert any("/users/alice/" in u for u in captured), captured
    assert any("/users/bob/" in u for u in captured), captured
    # And no request for one user ever read the other user's path.
    assert not any("/users/alice/" in u and "bob" in u for u in captured)
    assert not any("/users/bob/" in u and "alice" in u for u in captured)


def test_us006_missing_x_user_blocks_secret_read(make_broker_client_with_vault):
    """No X-User → 401 from auth middleware *before* any Vault round-trip."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json=_kv())

    client, _ = make_broker_client_with_vault(handler)
    with client as c:
        r = c.get("/api/secrets/search_api_key")
    assert r.status_code == 401
    assert calls == [], "Vault must not be reached without X-User"


def test_us006_invalid_secret_type_returns_422(broker_client, auth_headers):
    """Mock Vault is fine here — the route's enum-typed path parameter
    rejects unknown secret_types at the FastAPI layer with 422.
    """
    r = broker_client.get(
        "/api/secrets/no_such_type", headers=auth_headers("alice@gwdg")
    )
    assert r.status_code == 422
