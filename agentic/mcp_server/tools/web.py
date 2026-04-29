"""Web tools.

``web_search``: configurable provider; ``stub`` (default) returns a
deterministic placeholder result set so the rest of the system can be
exercised end-to-end without an API key. ``serpapi`` is a worked
example of a real provider — swap by setting ``MCP_SERVER_WEB_SEARCH_PROVIDER``.

``web_browse``: HTTP GET via httpx. The first-pass URL filter rejects
private / loopback / link-local IP literals; full DNS-based filtering
is the egress proxy's job (Task 2.5).

httpx is the same client the broker uses — same proxy plumbing,
same env-driven config, same testing surface (the test suite mocks
``httpx.AsyncClient`` rather than monkey-patching network calls).
"""

from __future__ import annotations

from typing import Any, Dict, List

import httpx

from .. import config
from ..errors import ToolError, ToolErrorCode
from ..security import proxy_kwargs, validate_url


def _settings():
    return config.get_settings()


async def _client(timeout_s: float) -> httpx.AsyncClient:
    s = _settings()
    return httpx.AsyncClient(
        timeout=timeout_s,
        follow_redirects=True,
        **proxy_kwargs(s.web_proxy_url),
    )


# --------------------------------------------------------------------------- #
# web_search                                                                  #
# --------------------------------------------------------------------------- #

def _stub_results(query: str, n: int) -> List[Dict[str, Any]]:
    return [
        {
            "title": f"[stub {i}] {query}",
            "url": f"https://example.invalid/q?{query}&n={i}",
            "snippet": (
                f"Stub search result #{i} for {query!r}. Configure "
                f"MCP_SERVER_WEB_SEARCH_PROVIDER and provide an API key "
                f"to fetch real results."
            ),
        }
        for i in range(1, n + 1)
    ]


async def web_search(args: Dict[str, Any]) -> Dict[str, Any]:
    query = args.get("query")
    n = int(args.get("num_results", 10))
    if not isinstance(query, str) or not query.strip():
        raise ToolError(
            code=ToolErrorCode.INVALID_PARAMS,
            message="`query` must be a non-empty string",
        )
    if n <= 0 or n > 50:
        raise ToolError(
            code=ToolErrorCode.INVALID_PARAMS,
            message="num_results must be 1..50",
        )

    s = _settings()
    provider = s.web_search_provider.lower()

    if provider == "stub":
        return {"query": query, "provider": "stub", "results": _stub_results(query, n)}

    if not s.web_search_api_key:
        raise ToolError(
            code=ToolErrorCode.SEARCH_PROVIDER_UNAVAILABLE,
            message=(
                f"web_search provider {provider!r} requires an API key; "
                f"set MCP_SERVER_WEB_SEARCH_API_KEY (broker plumbs from Vault)."
            ),
            rpc_code=-32000,
        )

    # serpapi shape: GET search.json?q=...&api_key=...&num=...
    params = {"q": query, "num": n, "api_key": s.web_search_api_key}
    try:
        async with await _client(s.web_request_timeout_s) as client:
            r = await client.get(s.web_search_endpoint, params=params)
    except httpx.HTTPError as exc:
        raise ToolError(
            code=ToolErrorCode.NETWORK_ERROR,
            message=f"search provider request failed: {exc}",
            rpc_code=-32000,
        ) from exc

    if r.status_code >= 400:
        raise ToolError(
            code=ToolErrorCode.NETWORK_ERROR,
            message=f"search provider returned HTTP {r.status_code}",
            rpc_code=-32000,
            data={"status_code": r.status_code},
        )

    payload = r.json()
    results = []
    for item in (payload.get("organic_results") or [])[:n]:
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            }
        )
    return {"query": query, "provider": provider, "results": results}


# --------------------------------------------------------------------------- #
# web_browse                                                                  #
# --------------------------------------------------------------------------- #

async def web_browse(args: Dict[str, Any]) -> Dict[str, Any]:
    url = args.get("url")
    validate_url(url)  # raises ToolError on bad input

    s = _settings()
    cap = int(args.get("max_bytes") or s.web_max_response_bytes)
    if cap > s.web_max_response_bytes:
        cap = s.web_max_response_bytes

    try:
        async with await _client(s.web_request_timeout_s) as client:
            r = await client.get(url)
    except httpx.HTTPError as exc:
        raise ToolError(
            code=ToolErrorCode.NETWORK_ERROR,
            message=f"GET {url!r} failed: {exc}",
            rpc_code=-32000,
        ) from exc

    body = r.content
    truncated = False
    if len(body) > cap:
        body = body[:cap]
        truncated = True

    # Best-effort decode. If the response isn't UTF-8 we fall back
    # to httpx's encoding guess so non-Latin pages aren't silently dropped.
    try:
        text = body.decode(r.encoding or "utf-8", errors="replace")
    except LookupError:
        text = body.decode("utf-8", errors="replace")

    return {
        "url": str(r.url),
        "status_code": r.status_code,
        "content_type": r.headers.get("content-type", ""),
        "text": text,
        "size_bytes": len(r.content),
        "truncated": truncated,
    }
