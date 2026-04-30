"""Tests for feedback endpoint (Task 5.4 UAT infrastructure)."""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.audit_logger import AUDIT_LOG_PATH


@pytest.fixture
def client():
    """Create a test client for the feedback endpoint."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def mock_audit_log(tmp_path):
    """Mock the audit log path for testing."""
    temp_log = tmp_path / "test_feedback_audit.jsonl"
    
    with patch("app.services.audit_logger.AUDIT_LOG_PATH", str(temp_log)):
        yield temp_log


def test_submit_feedback_with_rating(
    client: TestClient,
    mock_audit_log,
) -> None:
    """Test submitting feedback with a rating."""
    response = client.post(
        "/api/agent/feedback",
        json={
            "rating": 5,
            "open_comment": None,
        },
        headers={
            "X-User": "test-user-1@gwdg",
            "X-Session-Id": "test-session-123",
        },
    )
    
    assert response.status_code == 201
    assert response.json()["status"] == "success"
    
    # Verify audit log was written
    log_lines = mock_audit_log.read_text().strip().split("\n")
    assert len(log_lines) == 1
    
    event = json.loads(log_lines[0])
    assert event["event"] == "feedback_submitted"
    assert event["user"] == "test-user-1@gwdg"
    assert event["session_id"] == "test-session-123"
    assert event["rating"] == 5
    assert "comment" not in event


def test_submit_feedback_with_comment(
    client: TestClient,
    mock_audit_log,
) -> None:
    """Test submitting feedback with a comment."""
    comment = "The streaming progress updates are very helpful!"
    response = client.post(
        "/api/agent/feedback",
        json={
            "rating": 4,
            "open_comment": comment,
        },
        headers={
            "X-User": "test-user-2@gwdg",
            "X-Session-Id": "test-session-456",
        },
    )
    
    assert response.status_code == 201
    
    # Verify audit log
    log_line = mock_audit_log.read_text().strip()
    event = json.loads(log_line)
    
    assert event["rating"] == 4
    assert event["comment"] == comment


def test_submit_feedback_with_context(
    client: TestClient,
    mock_audit_log,
) -> None:
    """Test submitting feedback with context metadata."""
    response = client.post(
        "/api/agent/feedback",
        json={
            "rating": 3,
            "open_comment": "A bit slow on first action",
            "context": "after-5-sessions",
        },
        headers={
            "X-User": "test-user-3@gwdg",
        },
    )
    
    assert response.status_code == 201


def test_submit_feedback_without_x_user(client: TestClient) -> None:
    """Test that feedback submission requires X-User header."""
    response = client.post(
        "/api/agent/feedback",
        json={
            "rating": 5,
        },
    )
    
    assert response.status_code == 401
    assert "X-User" in response.json()["detail"]


def test_submit_feedback_without_rating_or_comment(client: TestClient) -> None:
    """Test that feedback requires at least rating or comment."""
    response = client.post(
        "/api/agent/feedback",
        json={
            "rating": None,
            "open_comment": None,
        },
        headers={
            "X-User": "test-user-4@gwdg",
        },
    )
    
    assert response.status_code == 400
    assert "at least" in response.json()["detail"]


def test_submit_feedback_rating_out_of_range_low(client: TestClient) -> None:
    """Test that rating must be at least 1."""
    response = client.post(
        "/api/agent/feedback",
        json={
            "rating": 0,  # Invalid
        },
        headers={
            "X-User": "test-user-5@gwdg",
        },
    )
    
    assert response.status_code == 422  # Validation error


def test_submit_feedback_rating_out_of_range_high(client: TestClient) -> None:
    """Test that rating must be at most 5."""
    response = client.post(
        "/api/agent/feedback",
        json={
            "rating": 6,  # Invalid
        },
        headers={
            "X-User": "test-user-6@gwdg",
        },
    )
    
    assert response.status_code == 422  # Validation error


def test_submit_feedback_max_comment_length(
    client: TestClient,
    mock_audit_log,
) -> None:
    """Test that comments are limited to 2000 characters."""
    # Create a comment exactly at the limit
    max_comment = "x" * 2000
    
    response = client.post(
        "/api/agent/feedback",
        json={
            "open_comment": max_comment,
        },
        headers={
            "X-User": "test-user-7@gwdg",
        },
    )
    
    assert response.status_code == 201
    
    # Verify the comment was saved
    event = json.loads(mock_audit_log.read_text().strip())
    assert len(event["comment"]) == 2000


def test_submit_feedback_exceeds_max_comment_length(client: TestClient) -> None:
    """Test that comments exceeding 2000 characters are rejected."""
    over_limit = "x" * 2001
    
    response = client.post(
        "/api/agent/feedback",
        json={
            "open_comment": over_limit,
        },
        headers={
            "X-User": "test-user-8@gwdg",
        },
    )
    
    assert response.status_code == 422  # Validation error


def test_submit_multiple_feedback_entries(
    client: TestClient,
    mock_audit_log,
) -> None:
    """Test submitting multiple feedback entries."""
    # Simulate a user submitting feedback over multiple sessions
    for i in range(3):
        client.post(
            "/api/agent/feedback",
            json={
                "rating": (i % 5) + 1,
                "open_comment": f"Session {i+1}",
            },
            headers={
                "X-User": "test-user-9@gwdg",
                "X-Session-Id": f"session-{i+1}",
            },
        )
    
    log_lines = mock_audit_log.read_text().strip().split("\n")
    assert len(log_lines) == 3
    
    # Verify each entry
    for i, log_line in enumerate(log_lines):
        event = json.loads(log_line)
        assert event["rating"] == (i % 5) + 1
        assert event["comment"] == f"Session {i+1}"


def test_feedback_endpoint_handles_missing_session_id(
    client: TestClient,
    mock_audit_log,
) -> None:
    """Test that feedback endpoint works when X-Session-Id is not provided."""
    response = client.post(
        "/api/agent/feedback",
        json={
            "rating": 5,
        },
        headers={
            "X-User": "test-user-10@gwdg",
            # No X-Session-Id header
        },
    )
    
    assert response.status_code == 201
    
    # Verify session_id defaults to "unknown"
    event = json.loads(mock_audit_log.read_text().strip())
    assert event["session_id"] == "unknown"