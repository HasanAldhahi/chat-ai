"""Request / response schemas for Phase-3 agent chat bridge (Task 3.1 + 2.6)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AgentChatRequest(BaseModel):
    """Body forwarded from Node `/api/chat/agent` → broker."""

    model: str = Field(
        ...,
        description='Agent display name e.g. "Agent - OpenHands"',
    )
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    session_id: str = Field(
        default="",
        description="Client session; echoed in logs / future Slurm wiring",
    )
    stream: bool = True
    temperature: float = Field(default=0.5, ge=0, le=2)
    top_p: float = Field(default=0.5, ge=0, le=1)
    user_id: Optional[str] = Field(
        default=None,
        description="Optional explicit user id; defaults to X-User header",
    )

    model_config = {"extra": "ignore"}
