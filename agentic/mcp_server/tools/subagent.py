"""Subagent spawning tool: delegate_subtask.

Lets the Master Orchestrator (GLM-4.7) dispatch work to a specialist model
running on the same vLLM cluster, without the orchestrator needing to solve
the problem itself.  The call is fully async and awaited inline — the
orchestrator receives the specialist's response as a plain text result.

Capability → model mapping is read from MCPSettings so every cluster can
tune the exact model IDs via env vars (MCP_SERVER_MODEL_CODING, etc.)
without touching code.
"""

from __future__ import annotations

import logging
import os
from enum import Enum
from typing import Any, Dict

import httpx

from .. import vllm_client
from ..config import get_settings
from ..errors import ToolError, ToolErrorCode

log = logging.getLogger("agentic.mcp.subagent")


class Capability(str, Enum):
    coding = "coding"
    summarization = "summarization"
    vision = "vision"
    heavy_logic = "heavy_logic"


def _resolve_model(capability: str) -> str:
    s = get_settings()
    mapping: Dict[str, str] = {
        Capability.coding: s.model_coding,
        Capability.summarization: s.model_summarization,
        Capability.vision: s.model_vision,
        Capability.heavy_logic: s.model_heavy_logic,
    }
    try:
        return mapping[Capability(capability)]
    except ValueError:
        valid = [c.value for c in Capability]
        raise ToolError(
            code=ToolErrorCode.INVALID_PARAMS,
            message=f"Unknown capability {capability!r}. Valid values: {valid}",
        )


async def delegate_subtask(args: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch a task to the appropriate specialist subagent model."""
    task_description = args.get("task_description")
    if not isinstance(task_description, str) or not task_description.strip():
        raise ToolError(
            code=ToolErrorCode.INVALID_PARAMS,
            message="`task_description` must be a non-empty string",
        )
    capability = args.get("capability")
    if not isinstance(capability, str):
        raise ToolError(
            code=ToolErrorCode.INVALID_PARAMS,
            message="`capability` must be a string",
        )

    model = _resolve_model(capability)
    s = get_settings()

    log.info(
        "subagent.dispatch",
        extra={
            "capability": capability,
            "model": model,
            "task_len": len(task_description),
        },
    )

    # Notify the frontend that this specialist model has started.
    await _post_model_event(model, capability, phase="start", task=task_description)

    try:
        result = await vllm_client.call(
            model=model,
            messages=[{"role": "user", "content": task_description}],
            base_url=s.vllm_base_url,
            api_key=s.vllm_api_key,
            timeout_s=s.vllm_timeout_s,
        )
    except vllm_client.VllmCallError as exc:
        log.warning(
            "subagent.call_failed",
            extra={"capability": capability, "model": model, "error": str(exc)},
        )
        # Tell the frontend the specialist finished (with an error).
        await _post_model_event(model, capability, phase="end", error=str(exc))
        raise ToolError(
            code=ToolErrorCode.EXEC_FAILED,
            message=f"Subagent [{capability}] call failed: {exc}",
            rpc_code=-32001,
        )

    log.info(
        "subagent.done",
        extra={"capability": capability, "model": model, "result_len": len(result)},
    )
    # Tell the frontend the specialist finished successfully.
    await _post_model_event(model, capability, phase="end")
    return {
        "capability": capability,
        "model": model,
        "result": result,
    }


async def _post_model_event(
    model: str,
    capability: str,
    *,
    phase: str,
    task: str = "",
    error: str = "",
) -> None:
    """Tell the broker (→ browser) that a specialist model started or finished.

    ``phase`` is ``"start"`` or ``"end"``; the frontend uses it to show a live
    "running" chip while the subagent is working and mark it done afterwards.
    Best-effort: any failure is swallowed so it never breaks the actual task.
    """
    session_id = os.environ.get("GOOSE_SESSION_ID", "")
    broker_url = os.environ.get("GOOSE_BROKER_SSE_URL", "")
    user_id = os.environ.get("GOOSE_USER_ID", "")
    if not session_id or not broker_url:
        return
    sse_url = broker_url.rstrip("/") + f"/api/sse/{session_id}/events"
    data: Dict[str, Any] = {"model": model, "capability": capability, "phase": phase}
    if task:
        data["task"] = task[:280]
    if error:
        data["error"] = error
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                sse_url,
                json={"event": "model.active", "data": data},
                headers={"X-User": user_id, "Content-Type": "application/json"},
            )
    except Exception:
        pass
