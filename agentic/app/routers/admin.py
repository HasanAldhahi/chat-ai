"""Admin status endpoint — live view of sessions, users, and SSE subscribers."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request

from app.dependencies import get_agent_orchestrator, get_sse_hub
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.sse_hub import SseHub


router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/status")
async def status(
    request: Request,
    hub: SseHub = Depends(get_sse_hub),
    orchestrator: AgentOrchestrator = Depends(get_agent_orchestrator),
):
    """Return a live snapshot of active sessions, users, SSE connections, and reaper state."""
    sse_rooms = {r["session_id"]: r for r in hub.snapshot()}
    jobs = {j["session_id"]: j for j in orchestrator.active_sessions()}

    all_ids = set(sse_rooms) | set(jobs)
    sessions = []
    for sid in all_ids:
        room = sse_rooms.get(sid, {})
        job = jobs.get(sid, {})
        sessions.append({
            "session_id": sid,
            "user_id": job.get("user_id") or room.get("user_id") or "",
            "job_id": job.get("job_id"),
            "sse_subscribers": room.get("sse_subscribers", 0),
            "last_activity_s_ago": room.get("last_activity_s_ago"),
            "total_published": room.get("total_published", 0),
        })

    unique_users = len({s["user_id"] for s in sessions if s["user_id"]})

    reaper = getattr(request.app.state, "session_reaper", None)
    reaper_info = {
        "idle_timeout_s": request.app.state.session_reaper._settings.agent_session_idle_timeout_s
        if reaper else None,
        "interval_s": request.app.state.session_reaper._settings.agent_session_reaper_interval_s
        if reaper else None,
        "last_reap": reaper.last_reap_ts and datetime.fromtimestamp(reaper.last_reap_ts, tz=timezone.utc).isoformat(),
        "last_cancelled": reaper.last_cancelled if reaper else [],
    } if reaper else None

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "active_sessions": len(sessions),
        "unique_users": unique_users,
        "total_sse_subscribers": sum(s["sse_subscribers"] for s in sessions),
        "sessions": sessions,
        "reaper": reaper_info,
    }
