"""Agent chat bridge: Node → broker → vLLM (Tasks 2.6 + 3.1)."""

from __future__ import annotations

import logging
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.clients import vllm as vllm_client
from app.config import Settings, get_settings
from app.models.agent_chat import AgentChatRequest
from app.services.audit_logger import log_agent_chat_failed_5xx, log_agent_chat_started

router = APIRouter(tags=["agent-chat"])
log = logging.getLogger("agentic.agent_chat")


def _require_x_user(request: Request) -> str:
    x_user = request.headers.get("X-User", "").strip()
    if not x_user:
        raise HTTPException(status_code=401, detail="X-User header required")
    return x_user


@router.post("/api/agent/chat")
async def agent_chat(
    request: Request,
    body: AgentChatRequest,
    settings: Settings = Depends(get_settings),
):
    """Forward chat-style agent requests to the cluster vLLM (Hermes / tool-ready).

    Streams OpenAI-compatible SSE when ``body.stream`` is true. Does not
    execute Slurm/OpenHands here — that remains a separate submission
    flow; this endpoint unblocks Phase 3 UI + model routing.
    """
    x_user = _require_x_user(request)

    if not body.messages:
        raise HTTPException(status_code=422, detail="messages must be non-empty")

    if "agent" not in body.model.lower():
        raise HTTPException(
            status_code=400,
            detail='model must be an agent model (e.g. "Agent - OpenHands")',
        )

    agent_label = body.model
    
    # Generate session_id from request for UAT tracking
    session_id = request.headers.get("X-Session-Id", x_user)
    
    # Log agent chat start for UAT activation metrics
    log_agent_chat_started(
        user_id=x_user,
        agent_model=agent_label,
        session_id=session_id,
    )

    if body.stream:

        async def byte_iter() -> AsyncIterator[bytes]:
            try:
                async for chunk in vllm_client.stream_chat_completion(
                    settings,
                    messages=body.messages,
                    stream=True,
                    temperature=body.temperature,
                    top_p=body.top_p,
                    agent_model=agent_label,
                ):
                    yield chunk
            except vllm_client.VllmError as exc:
                # Log 5xx failures for UAT reliability metrics
                if exc.status_code >= 500:
                    log_agent_chat_failed_5xx(
                        user_id=x_user,
                        agent_model=agent_label,
                        session_id=session_id,
                        status_code=exc.status_code,
                        error=str(exc),
                    )
                log.warning(
                    "vllm_upstream_error",
                    extra={"error": str(exc), "agent_model": agent_label},
                )
                raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        return StreamingResponse(byte_iter(), media_type="text/event-stream")

    try:
        data = await vllm_client.chat_completion_json(
            settings,
            messages=body.messages,
            temperature=body.temperature,
            top_p=body.top_p,
            agent_model=agent_label,
        )
    except vllm_client.VllmError as exc:
        # Log 5xx failures for UAT reliability metrics
        if exc.status_code >= 500:
            log_agent_chat_failed_5xx(
                user_id=x_user,
                agent_model=agent_label,
                session_id=session_id,
                status_code=exc.status_code,
                error=str(exc),
            )
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    return JSONResponse(content=data)


@router.get("/api/vllm/health")
async def vllm_health_probe(
    settings: Settings = Depends(get_settings),
):
    """Lightweight probe: GET base URL HEAD/GET — no prompt data."""
    if not settings.vllm_base_url:
        return {"ok": False, "reason": "AGENTIC_VLLM_BASE_URL not set"}
    import httpx

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(5.0),
        ) as client:
            r = await client.get(settings.vllm_base_url.rstrip("/") + "/health")
            ok = r.status_code < 500
            return {"ok": ok, "status_code": r.status_code}
    except httpx.HTTPError as exc:
        return {"ok": False, "reason": str(exc)}
