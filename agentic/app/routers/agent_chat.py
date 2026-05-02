"""Agent chat bridge: Node → broker → runtime container or vLLM (Tasks 2.6 + 3.1 + 6.4 + 6.5)."""

from __future__ import annotations

import logging
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.clients import vllm as vllm_client
from app.config import Settings, get_settings
from app.dependencies import (
    get_agent_orchestrator,
    get_local_executor,
    get_slurm_client,
)
from app.models.agent_chat import AgentChatRequest
from app.models.job import CancelReason
from app.services.agent_orchestrator import AgentOrchestrator, OrchestrationError
from app.services.agent_registry import lookup
from app.services.local_executor import LocalExecutor

router = APIRouter(tags=["agent-chat"])
log = logging.getLogger("agentic.agent_chat")


def _require_x_user(request: Request) -> str:
    x_user = request.headers.get("X-User", "").strip()
    if not x_user:
        raise HTTPException(status_code=401, detail="X-User header required")
    return x_user


def _extract_prompt(body: AgentChatRequest) -> str:
    """Pull the last user message text for use as the runtime session prompt."""
    for msg in reversed(body.messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        return part.get("text", "")
    return ""


@router.post("/api/agent/chat", response_model=None)
async def agent_chat(
    request: Request,
    body: AgentChatRequest,
    settings: Settings = Depends(get_settings),
    orchestrator: AgentOrchestrator = Depends(get_agent_orchestrator),
    executor: LocalExecutor = Depends(get_local_executor),
    slurm=Depends(get_slurm_client),
) -> JSONResponse | StreamingResponse:
    """Route agent chat requests.

    - **Agent model** (e.g. "Agent - Goose"): submit a runtime container job,
      return HTTP 202 ``{"job_id", "session_id"}``. The actual response arrives
      over SSE at ``GET /api/sse/{session_id}``.
    - **Non-agent model**: forward directly to vLLM (Task 2.6 passthrough).
    """
    x_user = _require_x_user(request)
    user_id = body.user_id or x_user

    if not body.messages:
        raise HTTPException(status_code=422, detail="messages must be non-empty")

    spec = lookup(body.model)

    # ---------------------------------------------------------------- agent path
    if spec is not None:
        if not spec.enabled:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Agent runtime {spec.runtime_key!r} is not yet available on this broker "
                    "(container image not built). Check agentic/containers/ and Task 6.1."
                ),
            )

        session_id = body.session_id or x_user.replace("@", "-")
        prompt = _extract_prompt(body)
        log.info(
            "agent_chat.debug",
            extra={
                "execution_mode": settings.execution_mode,
                "use_slurm": settings.execution_mode != "local",
            },
        )
        backend = executor if settings.execution_mode == "local" else slurm

        try:
            result = await orchestrator.ensure_runtime(
                session_id=session_id,
                user_id=user_id,
                model_id=body.model,
                prompt=prompt,
                bearer_token=request.headers.get("Authorization", "").removeprefix("Bearer ").strip(),
                executor=backend,
            )
        except OrchestrationError as exc:
            log.warning(
                "agent_chat.orchestration_error",
                extra={"user_id": user_id, "model": body.model, "error": str(exc)},
            )
            raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc

        log.info(
            "agent_chat.launched",
            extra={
                "user_id": user_id,
                "model": body.model,
                "session_id": session_id,
                "job_id": result["job_id"],
                "execution_mode": settings.execution_mode,
            },
        )
        # 202: runtime is starting, response comes over SSE.
        return JSONResponse(status_code=202, content=result)

    # --------------------------------------------------- vLLM passthrough path
    # Non-agent models (or when execution_mode is used with a plain model id)
    # keep the original Task 2.6 behaviour: stream straight from vLLM.
    agent_label = body.model

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
        status = 500 if exc.status_code >= 500 else exc.status_code
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    return JSONResponse(content=data)


@router.delete("/api/agent/sessions/{session_id}", response_model=None)
async def cancel_agent_session(
    session_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    orchestrator: AgentOrchestrator = Depends(get_agent_orchestrator),
    executor: LocalExecutor = Depends(get_local_executor),
    slurm=Depends(get_slurm_client),
) -> JSONResponse:
    """Cancel the running agent job for a session (triggered by front-end Stop button)."""
    x_user = _require_x_user(request)
    backend = executor if settings.execution_mode == "local" else slurm
    await orchestrator.cancel_session(
        session_id=session_id,
        user_id=x_user,
        reason=CancelReason.USER_STOP,
        executor=backend,
    )
    log.info("agent_session.cancelled", extra={"session_id": session_id, "user_id": x_user})
    return JSONResponse(content={"session_id": session_id, "cancelled": True})


@router.get("/api/vllm/health")
async def vllm_health_probe(
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Lightweight probe: GET base URL HEAD/GET — no prompt data."""
    if not settings.vllm_base_url:
        return JSONResponse({"ok": False, "reason": "AGENTIC_VLLM_BASE_URL not set"})
    import httpx

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            r = await client.get(settings.vllm_base_url.rstrip("/") + "/health")
            return JSONResponse({"ok": r.status_code < 500, "status_code": r.status_code})
    except httpx.HTTPError as exc:
        return JSONResponse({"ok": False, "reason": str(exc)})
