"""Lightweight vLLM client for MCP-server-internal calls.

Used by the subagent spawning tool and the smart-debug loop in code_exec.
Falls back to OPENAI_BASE_URL / OPENAI_API_KEY env vars that the broker
injects into every container session.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger("agentic.mcp.vllm")

_CHAT_PATH = "/v1/chat/completions"


class VllmCallError(Exception):
    pass


def _resolve_endpoint(base_url: str, api_key: str) -> tuple[str, str]:
    return (
        base_url or os.environ.get("OPENAI_BASE_URL", ""),
        api_key or os.environ.get("OPENAI_API_KEY", ""),
    )


async def call(
    *,
    model: str,
    messages: List[Dict[str, Any]],
    base_url: str = "",
    api_key: str = "",
    temperature: float = 0.3,
    timeout_s: float = 120.0,
    http_client: Optional[httpx.AsyncClient] = None,
) -> str:
    """POST to vLLM /v1/chat/completions and return the first choice content."""
    base_url, api_key = _resolve_endpoint(base_url, api_key)
    if not base_url:
        raise VllmCallError(
            "vLLM base URL not configured — set OPENAI_BASE_URL or MCP_SERVER_VLLM_BASE_URL"
        )

    url = base_url.rstrip("/") + _CHAT_PATH
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": temperature,
    }
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    owns = http_client is None
    client = http_client or httpx.AsyncClient(timeout=httpx.Timeout(timeout_s))
    try:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code >= 400:
            raise VllmCallError(f"vLLM HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise VllmCallError(f"Unexpected vLLM response shape: {exc}") from exc
    except httpx.HTTPError as exc:
        raise VllmCallError(f"vLLM request error: {exc}") from exc
    finally:
        if owns:
            await client.aclose()
