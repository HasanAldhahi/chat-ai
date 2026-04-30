"""Tests for feature flags endpoint (Task 5.4 UAT)."""

import os

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    """Create a test client."""
    app = create_app()
    return TestClient(app)


def test_get_features_returns_all_flags(client: TestClient) -> None:
    """Test that the features endpoint returns all feature flags."""
    response = client.get("/api/agent/config/features")

    assert response.status_code == 200

    flags = response.json()
    assert "betaBanner" in flags
    assert "uatEnabled" in flags
    assert "multimodalEnabled" in flags
    assert "toolsLandingPageEnabled" in flags


def test_features_endpoint_works_without_auth(client: TestClient) -> None:
    """Test that the features endpoint works without authentication."""
    # This is intentional: the features endpoint should be accessible
    # to the frontend before user authentication.
    response = client.get("/api/agent/config/features")

    assert response.status_code == 200
    # No X-User header provided, but it still works


def test_default_beta_banner_enabled(client: TestClient) -> None:
    """Test that the beta banner is enabled by default for UAT."""
    response = client.get("/api/agent/config/features")

    assert response.status_code == 200

    flags = response.json()
    # Default is True for UAT beta banner
    assert flags["betaBanner"] is True


# Subprocess env test: AGENTIC_UAT_ENV=production pytest tests/test_feature_flags.py::test_uat_enabled_false_in_production -v
# The following env-based tests require subprocess-level env injection because pydantic_settings caches at import time.


def test_expired_request_id_header_is_properly_parsed(client: TestClient) -> None:
    """Test that other request parsing still works with features endpoint."""
    response = client.get(
        "/api/agent/config/features",
        headers={"X-Request-ID": "test-request-123"},
    )

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == "test-request-123"


def test_features_endpoint_returns_json(client: TestClient) -> None:
    """Test that the features endpoint returns valid JSON."""
    response = client.get("/api/agent/config/features")

    assert response.headers["content-type"] == "application/json"
    flags = response.json()

    # Verify all values are bool (no None or other types)
    for key, value in flags.items():
        assert isinstance(value, bool), f"{key} should be bool, got {type(value)}"