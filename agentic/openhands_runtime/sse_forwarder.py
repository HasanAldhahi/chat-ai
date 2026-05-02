"""Forward OpenHands events to the broker's SSE endpoint.

OpenHands V1 emits machine-readable lines on stdout (one JSON object
per line, plus interleaved human-readable lines). This forwarder:

1. Consumes lines from an async stream (the OpenHands stdout).
2. Parses each line as JSON; non-JSON lines are emitted as
   ``message`` events with the raw text in ``data.text``.
3. Translates OpenHands events to one of the broker's vocabulary:
   ``action``, ``result``, ``error``, ``message``.
4. POSTs each translated event to
   ``{broker_sse_url}/api/sse/{session_id}/events`` with the
   appropriate ``X-User`` header.

The broker's SSE hub is the load-bearing fan-out (Task 1.6) — this
module is pure plumbing. Drop-on-overflow rather than block: if the
broker is down or the queue is full, we log + drop and let the
agent keep running.

Tests pin the network at the httpx-mock layer, same convention as
the broker's own client tests.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterable, Callable, Dict, List, Optional, Tuple

import httpx


log = logging.getLogger("openhands-sse-forwarder")


VALID_EVENTS = ("action", "result", "error", "message")


LineTranslator = Callable[[str], Optional[Dict[str, Any]]]


@dataclass
class ForwarderStats:
    """Counters returned by :func:`forward_stream` for assertions in tests."""

    forwarded: int = 0
    dropped_overflow: int = 0
    dropped_bad_json: int = 0
    dropped_post_failed: int = 0
    raw_lines: int = 0
    posted_events: List[Tuple[str, Dict[str, Any]]] = field(default_factory=list)


def translate_openhands_line(line: str) -> Optional[Dict[str, Any]]:
    """Map a single OpenHands stdout line to the broker's SSE shape.

    Returns ``None`` for empty/whitespace-only lines. Otherwise
    returns ``{"event": "<vocab>", "data": <object>, "id": <str|None>}``
    matching the broker's ``POST /api/sse/{session}/events`` body.

    Heuristics for translating OpenHands' output:

    - Valid JSON object with ``"type"`` field — the type maps to:
        - ``action``     -> ``action``
        - ``observation``-> ``result``
        - ``message``    -> ``message``
        - ``error``      -> ``error``
        - anything else  -> ``message``
    - Valid JSON object without ``"type"`` — emitted as ``message``.
    - Non-JSON / non-object — emitted as ``message`` with
      ``data.text`` set to the raw line.

    The unknown-shape fall-throughs are *intentional*: it's worse to
    drop a line because a future OpenHands version added a new field
    than to forward a slightly misclassified one.
    """
    text = line.rstrip("\r\n")
    if not text.strip():
        return None

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {
            "event": "message",
            "data": {"text": text},
            "id": None,
        }

    if not isinstance(payload, dict):
        return {
            "event": "message",
            "data": {"text": text},
            "id": None,
        }

    raw_type = (payload.get("type") or "").lower()
    mapping = {
        "action": "action",
        "observation": "result",
        "result": "result",
        "tool_result": "result",
        "message": "message",
        "agent_message": "message",
        "error": "error",
        "exception": "error",
    }
    event = mapping.get(raw_type, "message")

    return {
        "event": event,
        "data": payload,
        "id": payload.get("id"),
    }


async def _post_one(
    client: httpx.AsyncClient,
    url: str,
    headers: Dict[str, str],
    body: Dict[str, Any],
    timeout_s: float,
) -> bool:
    try:
        r = await client.post(url, headers=headers, json=body, timeout=timeout_s)
    except httpx.HTTPError as exc:
        log.warning("sse_post_failed", extra={"reason": str(exc)})
        return False
    if r.status_code >= 400:
        log.warning(
            "sse_post_bad_status",
            extra={"status_code": r.status_code, "body": r.text[:200]},
        )
        return False
    return True


async def forward_stream(
    *,
    lines: AsyncIterable[str],
    broker_sse_url: str,
    session_id: str,
    user_id: str = "",
    timeout_s: float = 5.0,
    max_inflight: int = 32,
    http_client: Optional[httpx.AsyncClient] = None,
    translate_line: LineTranslator = translate_openhands_line,
) -> ForwarderStats:
    """Read lines from ``lines`` and POST translated events to the broker.

    If ``broker_sse_url`` is falsy, behaves as a tee that just counts
    raw lines (useful for ``--no-broker`` dry runs and unit tests).

    ``translate_line`` defaults to OpenHands semantics; Goose can swap
    in its own heuristic without forking POST wiring (Task 4.1).

    Returns a :class:`ForwarderStats` once the input stream closes.
    Designed for graceful degradation: a broker outage / 5xx never
    blocks the agent subprocess — dropped events are counted and
    logged.
    """
    stats = ForwarderStats()

    if not broker_sse_url:
        async for raw in lines:
            stats.raw_lines += 1
        return stats

    url = broker_sse_url.rstrip("/") + f"/api/sse/{session_id}/events"
    headers = {"Content-Type": "application/json"}
    if user_id:
        headers["X-User"] = user_id

    # Semaphore caps concurrent in-flight HTTP POSTs to max_inflight.
    # Tasks are spawned per-line so the queue never overflows — large tool
    # outputs (file reads, shell output) are fully forwarded, not dropped.
    sem = asyncio.Semaphore(max_inflight)
    pending: List[asyncio.Task] = []  # type: ignore[type-arg]

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=timeout_s)

    async def post_one_item(item: Dict[str, Any]) -> None:
        async with sem:
            ok = await _post_one(client, url, headers, item, timeout_s)
            if ok:
                stats.forwarded += 1
                stats.posted_events.append((item["event"], item["data"]))
            else:
                stats.dropped_post_failed += 1

    try:
        async for raw in lines:
            stats.raw_lines += 1
            translated = translate_line(raw)
            if translated is None:
                continue
            task = asyncio.create_task(post_one_item(translated))
            pending.append(task)

        # Wait for all in-flight POSTs to complete before returning.
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
    finally:
        if owns_client:
            await client.aclose()

    return stats
