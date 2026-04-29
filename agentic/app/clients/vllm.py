"""Async client for cluster vLLM (OpenAI-compatible chat.completions) — Task 2.6."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from app.config import Settings

log = logging.getLogger("agentic.vllm")


class VllmError(Exception):
    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


async def stream_chat_completion(
    settings: Settings,
    *,
    messages: List[Dict[str, Any]],
    stream: bool = True,
    temperature: float = 0.5,
    top_p: float = 0.5,
    agent_model: str = "",
    http_client: Optional[httpx.AsyncClient] = None,
) -> AsyncIterator[bytes]:
    """Yield raw SSE bytes from vLLM. Does not log message content."""
    if not settings.vllm_base_url:
        raise VllmError("vLLM base URL not configured (AGENTIC_VLLM_BASE_URL)", status_code=503)

    url = settings.vllm_base_url.rstrip("/") + settings.vllm_chat_path
    payload: Dict[str, Any] = {
        "model": settings.vllm_model,
        "messages": messages,
        "stream": stream,
        "temperature": temperature,
        "top_p": top_p,
    }

    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if settings.vllm_api_key:
        headers["Authorization"] = f"Bearer {settings.vllm_api_key}"

    owns = http_client is None
    client = http_client or httpx.AsyncClient(
        timeout=httpx.Timeout(settings.vllm_request_timeout_s),
    )
    t0 = time.perf_counter()
    try:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                raise VllmError(
                    f"vLLM error HTTP {resp.status_code}: {body[:500]!r}",
                    status_code=502,
                )
            async for chunk in resp.aiter_bytes():
                yield chunk
    finally:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        log.info(
            "vllm_stream_finished",
            extra={
                "latency_ms": round(elapsed_ms, 2),
                "stream": stream,
                "agent_model": agent_model,
                "vllm_model": settings.vllm_model,
                "message_count": len(messages),
            },
        )
        if owns:
            await client.aclose()


async def chat_completion_json(
    settings: Settings,
    *,
    messages: List[Dict[str, Any]],
    temperature: float = 0.5,
    top_p: float = 0.5,
    agent_model: str = "",
    http_client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """Single JSON object response (non-streaming POST)."""
    if not settings.vllm_base_url:
        raise VllmError("vLLM base URL not configured (AGENTIC_VLLM_BASE_URL)", status_code=503)

    url = settings.vllm_base_url.rstrip("/") + settings.vllm_chat_path
    payload: Dict[str, Any] = {
        "model": settings.vllm_model,
        "messages": messages,
        "stream": False,
        "temperature": temperature,
        "top_p": top_p,
    }
    headers = {"Content-Type": "application/json"}
    if settings.vllm_api_key:
        headers["Authorization"] = f"Bearer {settings.vllm_api_key}"

    owns = http_client is None
    client = http_client or httpx.AsyncClient(
        timeout=httpx.Timeout(settings.vllm_request_timeout_s),
    )
    t0 = time.perf_counter()
    try:
        r = await client.post(url, json=payload, headers=headers)
        if r.status_code >= 400:
            raise VllmError(
                f"vLLM error HTTP {r.status_code}: {r.text[:500]}",
                status_code=502,
            )
        text = r.content.decode("utf-8")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise VllmError(f"invalid JSON from vLLM: {text[:200]!r}", status_code=502) from exc
    finally:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        log.info(
            "vllm_chat_complete",
            extra={
                "latency_ms": round(elapsed_ms, 2),
                "stream": False,
                "agent_model": agent_model,
                "vllm_model": settings.vllm_model,
                "message_count": len(messages),
            },
        )
        if owns:
            await client.aclose()
