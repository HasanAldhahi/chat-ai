"""Structured audit logging service for UAT metrics (Task 5.4)."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

# Configure audit logger to write JSON lines to a file
AUDIT_LOG_PATH = os.getenv(
    "AGENTIC_AUDIT_LOG_PATH",
    str(Path(__file__).parent.parent.parent / "logs" / "broker.jsonl"),
)

logger = logging.getLogger("agentic.audit")


def _ensure_audit_dir() -> None:
    """Create logs directory if it doesn't exist."""
    audit_path = Path(AUDIT_LOG_PATH)
    audit_path.parent.mkdir(parents=True, exist_ok=True)


def _write_audit_event(event: dict[str, Any]) -> None:
    """Write audit event as a JSON line to the audit log file."""
    _ensure_audit_dir()
    
    # Add timestamp if not present
    if "timestamp" not in event:
        event["timestamp"] = datetime.utcnow().isoformat() + "Z"
    
    try:
        with open(AUDIT_LOG_PATH, "a") as f:
            f.write(json.dumps(event) + "\n")
    except Exception as e:
        # Don't fail the request if audit logging fails
        logger.error("audit_log_write_failed", extra={"error": str(e)})


def log_agent_chat_started(user_id: str, agent_model: str, session_id: str) -> None:
    """Log when a user starts an agent chat session (UAT activation metric).
    
    Args:
        user_id: X-User header value
        agent_model: Selected agent label (e.g., "Agent - OpenHands")
        session_id: Session identifier from the request
    """
    _write_audit_event({
        "event": "agent_chat_started",
        "user": user_id,
        "agent_model": agent_model,
        "session_id": session_id,
    })


def log_agent_chat_failed_5xx(
    user_id: str,
    agent_model: str,
    session_id: str,
    status_code: int,
    error: str,
) -> None:
    """Log when an agent chat session fails with a 5xx error (UAT reliability metric).
    
    Args:
        user_id: X-User header value
        agent_model: Selected agent label
        session_id: Session identifier
        status_code: HTTP status code (500-599)
        error: Error message
    """
    _write_audit_event({
        "event": "agent_chat_failed_5xx",
        "user": user_id,
        "agent_model": agent_model,
        "session_id": session_id,
        "status_code": status_code,
        "error": error,
    })


def log_feedback_submitted(
    user_id: str,
    session_id: str,
    rating: int | None = None,
    open_comment: str | None = None,
) -> None:
    """Log when a user submits in-app feedback (UAT sentiment tracking).
    
    Args:
        user_id: X-User header value
        session_id: Session identifier
        rating: 5-point Likert rating (1-5) if provided
        open_comment: Free-form user feedback
    """
    event = {
        "event": "feedback_submitted",
        "user": user_id,
        "session_id": session_id,
    }
    
    if rating is not None:
        event["rating"] = rating
    
    if open_comment:
        event["comment"] = open_comment
    
    _write_audit_event(event)


def log_job_submit(
    user_id: str,
    session_id: str,
    job_id: str,
    status: str,
    agent_model: str | None = None,
) -> None:
    """Log job submission events for operational visibility.
    
    Args:
        user_id: X-User header value
        session_id: Session identifier  
        job_id: Slurm job ID
        status: Job status (e.g., "submitted", "failed")
        agent_model: Agent model if applicable
    """
    event = {
        "event": "job_submit",
        "user": user_id,
        "session_id": session_id,
        "job_id": job_id,
        "status": status,
    }
    
    if agent_model:
        event["agent_model"] = agent_model
    
    _write_audit_event(event)


# Export functions for importing elsewhere
__all__ = [
    "log_agent_chat_started",
    "log_agent_chat_failed_5xx",
    "log_feedback_submitted",
    "log_job_submit",
    "AUDIT_LOG_PATH",
]