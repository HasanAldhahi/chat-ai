"""Feedback endpoint for in-app surveys (UAT Task 5.4)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.services.audit_logger import log_feedback_submitted

router = APIRouter(prefix="/api/agent", tags=["feedback"])
log = logging.getLogger("agentic.feedback")


class FeedbackRequest(BaseModel):
    """Request model for in-app feedback submission."""
    
    rating: Annotated[
        int | None,
        Field(
            ge=1,
            le=5,
            description="5-point Likert rating (1-5)",
        ),
    ] = None
    
    open_comment: Annotated[
        str | None,
        Field(
            max_length=2000,
            description="Free-form feedback or surprise observation",
        ),
    ] = None
    
    # Optional: tag which context the feedback is from
    context: Annotated[
        str | None,
        Field(
            description="Context: 'after-5-sessions', 'mid-cohort', 'post-cohort'",
        ),
    ] = None


class FeedbackResponse(BaseModel):
    """Response model for feedback submission."""
    
    status: str
    message: str


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit in-app feedback",
    description=(
        "Endpoint for collecting user feedback during UAT campaign. "
        "Supports 5-point Likert ratings and open comments. "
        "Automatically logged to audit file for UAT metrics."
    ),
    responses={
        400: {"description": "Invalid feedback data"},
        401: {"description": "X-User header required"},
    },
)
async def submit_feedback(
    request: Request,
    feedback: FeedbackRequest,
) -> FeedbackResponse:
    """Submit user feedback for UAT sentiment tracking.
    
    This endpoint is called by the chat UI during the UAT campaign:
    - After every 5 agent chat sessions (micro-survey)
    - Mid-cohort email survey results
    - Post-cohort interviews (manually entered)
    
    All feedback is logged to the audit log for NPS calculation
    and theme synthesis in `UAT_REPORT.md`.
    """
    # Extract user identifier
    x_user = request.headers.get("X-User", "").strip()
    if not x_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User header required for feedback tracking",
        )
    
    # Validate that at least one field is provided
    if feedback.rating is None and not feedback.open_comment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide at least a rating or comment",
        )
    
    # Extract session_id from headers if available
    session_id = request.headers.get("X-Session-Id", "unknown")
    
    # Log to audit file for UAT metrics
    log_feedback_submitted(
        user_id=x_user,
        session_id=session_id,
        rating=feedback.rating,
        open_comment=feedback.open_comment,
    )
    
    log.info(
        "feedback_received",
        extra={
            "user": x_user,
            "session_id": session_id,
            "rating": feedback.rating,
            "has_comment": bool(feedback.open_comment),
        },
    )
    
    return FeedbackResponse(
        status="success",
        message="Feedback received. Thank you for participating in UAT!",
    )