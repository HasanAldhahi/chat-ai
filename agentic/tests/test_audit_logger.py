"""Tests for audit logging service (Task 5.4 UAT infrastructure)."""

import json
from pathlib import Path

import pytest

from app.services.audit_logger import (
    AUDIT_LOG_PATH,
    log_agent_chat_failed_5xx,
    log_agent_chat_started,
    log_feedback_submitted,
    log_job_submit,
)


@pytest.fixture
def temp_audit_log(tmp_path: Path) -> Path:
    """Create a temporary audit log file for testing."""
    temp_log = tmp_path / "test_audit.jsonl"
    # Override the AUDIT_LOG_PATH for this test
    import os
    os.environ["AGENTIC_AUDIT_LOG_PATH"] = str(temp_log)
    
    # Reload the module to pick up the new environment variable
    import importlib
    import app.services.audit_logger
    importlib.reload(app.services.audit_logger)
    
    yield temp_log
    
    # Clean up
    if temp_log.exists():
        temp_log.unlink()


def test_log_agent_chat_started_writes_jsonl(temp_audit_log: Path) -> None:
    """Test that log_agent_chat_started writes a valid JSON line."""
    log_agent_chat_started(
        user_id="test-user",
        agent_model="Agent - OpenHands",
        session_id="test-session-123",
    )
    
    # Read the log file and verify content
    with open(temp_audit_log, "r") as f:
        log_line = f.read().strip()
    
    event = json.loads(log_line)
    
    assert event["event"] == "agent_chat_started"
    assert event["user"] == "test-user"
    assert event["agent_model"] == "Agent - OpenHands"
    assert event["session_id"] == "test-session-123"
    assert "timestamp" in event
    assert event["timestamp"].endswith("Z")


def test_log_agent_chat_failed_5xx_writes_jsonl(temp_audit_log: Path) -> None:
    """Test that log_agent_chat_failed_5xx writes a valid JSON line."""
    log_agent_chat_failed_5xx(
        user_id="test-user",
        agent_model="Agent - OpenHands",
        session_id="test-session-123",
        status_code=500,
        error="Internal server error from vLLM",
    )
    
    log_line = temp_audit_log.read_text().strip()
    event = json.loads(log_line)
    
    assert event["event"] == "agent_chat_failed_5xx"
    assert event["user"] == "test-user"
    assert event["agent_model"] == "Agent - OpenHands"
    assert event["session_id"] == "test-session-123"
    assert event["status_code"] == 500
    assert event["error"] == "Internal server error from vLLM"
    assert "timestamp" in event


def test_log_feedback_submitted_with_rating(temp_audit_log: Path) -> None:
    """Test that log_feedback_submitted writes a valid JSON line with rating."""
    log_feedback_submitted(
        user_id="test-user",
        session_id="test-session-123",
        rating=5,
        open_comment=None,
    )
    
    log_line = temp_audit_log.read_text().strip()
    event = json.loads(log_line)
    
    assert event["event"] == "feedback_submitted"
    assert event["user"] == "test-user"
    assert event["session_id"] == "test-session-123"
    assert event["rating"] == 5
    assert "comment" not in event


def test_log_feedback_submitted_with_comment(temp_audit_log: Path) -> None:
    """Test that log_feedback_submitted writes a valid JSON line with comment."""
    comment = "The agent was very helpful for my data analysis task."
    log_feedback_submitted(
        user_id="test-user",
        session_id="test-session-123",
        rating=4,
        open_comment=comment,
    )
    
    log_line = temp_audit_log.read_text().strip()
    event = json.loads(log_line)
    
    assert event["event"] == "feedback_submitted"
    assert event["rating"] == 4
    assert event["comment"] == comment


def test_log_job_submit_writes_jsonl(temp_audit_log: Path) -> None:
    """Test that log_job_submit writes a valid JSON line."""
    log_job_submit(
        user_id="test-user",
        session_id="test-session-123",
        job_id="12345",
        status="submitted",
        agent_model="Agent - OpenHands",
    )
    
    log_line = temp_audit_log.read_text().strip()
    event = json.loads(log_line)
    
    assert event["event"] == "job_submit"
    assert event["user"] == "test-user"
    assert event["session_id"] == "test-session-123"
    assert event["job_id"] == "12345"
    assert event["status"] == "submitted"
    assert event["agent_model"] == "Agent - OpenHands"


def test_log_job_submit_without_agent_model(temp_audit_log: Path) -> None:
    """Test that log_job_submit works without optional agent_model."""
    log_job_submit(
        user_id="test-user",
        session_id="test-session-123",
        job_id="12346",
        status="failed",
        agent_model=None,
    )
    
    log_line = temp_audit_log.read_text().strip()
    event = json.loads(log_line)
    
    assert event["event"] == "job_submit"
    assert event["job_id"] == "12346"
    assert event["status"] == "failed"
    assert "agent_model" not in event


def test_multiple_events_append_to_log(temp_audit_log: Path) -> None:
    """Test that multiple events are properly appended as separate lines."""
    # Write multiple events
    log_agent_chat_started("user-1", "Agent - OpenHands", "session-1")
    log_agent_chat_failed_5xx("user-1", "Agent - OpenHands", "session-1", 500, "error")
    log_feedback_submitted("user-1", "session-1", rating=4)
    
    log_lines = temp_audit_log.read_text().strip().split("\n")
    
    assert len(log_lines) == 3
    
    event1 = json.loads(log_lines[0])
    assert event1["event"] == "agent_chat_started"
    
    event2 = json.loads(log_lines[1])
    assert event2["event"] == "agent_chat_failed_5xx"
    
    event3 = json.loads(log_lines[2])
    assert event3["event"] == "feedback_submitted"


def test_audit_log_directory_created_if_not_exists(tmp_path: Path) -> None:
    """Test that the audit log directory is created if it doesn't exist."""
    nested_path = tmp_path / "nested" / "directory" / "audit.jsonl"
    import os
    os.environ["AGENTIC_AUDIT_LOG_PATH"] = str(nested_path)
    
    # Reload module
    import importlib
    import app.services.audit_logger
    importlib.reload(app.services.audit_logger)
    from app.services.audit_logger import log_agent_chat_started
    
    # This should create the nested directories
    log_agent_chat_started("test-user", "Agent - OpenHands", "test-session")
    
    assert nested_path.parent.exists()
    assert nested_path.exists()
    
    # Clean up
    if nested_path.exists():
        nested_path.unlink()