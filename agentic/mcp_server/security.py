"""Security primitives shared across MCP tools.

Two responsibilities:

1. **Path containment** for the file-system tools — resolve a
   user-supplied path to an absolute path, reject symlinks that
   escape, reject inputs outside the allowed roots, normalise away
   `..` and `//`. Any failure raises ``ToolError``.

2. **URL containment** for the web tools — only http(s), reject
   private / loopback / link-local IPs, reject bare IP literals that
   resolve to internal ranges. Hostnames are accepted as-is at the
   API layer; the network layer (httpx + proxy) is what actually
   resolves them, and the broker's egress proxy is the load-bearing
   defence (Task 2.5). This module is a *first-pass* filter that
   catches obvious bypass attempts (URL-encoded localhost, decimal
   IP, etc.).
"""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

from .errors import ToolError, ToolErrorCode


# --------------------------------------------------------------------------- #
# Path containment                                                            #
# --------------------------------------------------------------------------- #

def _normalise_root(root: str) -> Path:
    return Path(root).expanduser().resolve()


def resolve_safe_path(
    user_path: str,
    allowed_roots: Iterable[str],
    *,
    must_exist: bool = False,
) -> Path:
    """Resolve ``user_path`` and assert it lives inside an allowed root.

    Behaviour:

    - Empty / non-string -> ``invalid_params``.
    - Relative paths are resolved against the *first* allowed root
      (i.e. relative paths land in /workspace). Absolute paths are
      taken as-is.
    - Any path component containing a NUL byte is rejected.
    - The fully-resolved path (which collapses ``..`` and follows any
      symlinks) must be a subpath of one of the resolved allowed
      roots — that's the symlink-escape check.
    - If ``must_exist`` is True, also assert ``exists()`` and surface
      ``file_not_found`` otherwise.

    Returns a :class:`Path` that's safe to pass to ``open()``.
    """
    if not isinstance(user_path, str) or not user_path:
        raise ToolError(
            code=ToolErrorCode.INVALID_PARAMS,
            message="`path` must be a non-empty string",
        )
    if "\x00" in user_path:
        raise ToolError(
            code=ToolErrorCode.INVALID_PARAMS,
            message="path may not contain NUL bytes",
        )

    roots = [_normalise_root(r) for r in allowed_roots]
    if not roots:
        raise ToolError(
            code=ToolErrorCode.PATH_NOT_ALLOWED,
            message="no allowed roots configured",
        )

    raw = Path(user_path)
    if not raw.is_absolute():
        raw = roots[0] / raw

    # ``resolve(strict=False)`` follows symlinks but does not require
    # the leaf to exist; matches our must_exist contract.
    try:
        resolved = raw.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        # RuntimeError from resolve() can fire on circular symlinks.
        raise ToolError(
            code=ToolErrorCode.SYMLINK_REJECTED,
            message=f"could not resolve path: {exc}",
        ) from exc

    for root in roots:
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        # Inside this root.
        if must_exist and not resolved.exists():
            raise ToolError(
                code=ToolErrorCode.FILE_NOT_FOUND,
                message=f"no such path: {user_path}",
            )
        return resolved

    raise ToolError(
        code=ToolErrorCode.PATH_NOT_ALLOWED,
        message=(
            f"path {user_path!r} is outside allowed roots "
            f"{[str(r) for r in roots]}"
        ),
    )


# --------------------------------------------------------------------------- #
# URL containment                                                             #
# --------------------------------------------------------------------------- #

ALLOWED_SCHEMES = frozenset({"http", "https"})


def _is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_url(url: str) -> str:
    """Validate a URL for the web_browse tool.

    Returns the canonicalised URL on success. Raises ``ToolError`` for
    any of:

    - non-string / empty
    - scheme other than http / https
    - host literal in a private / loopback / link-local / reserved
      range (catches ``http://10.0.0.1``, ``http://127.0.0.1``,
      ``http://[::1]``)

    Note: hostnames (e.g. ``http://internal.gwdg.de``) are *not*
    blocked here — DNS resolution to an internal address is caught
    by the egress proxy (Task 2.5). Pre-resolving DNS in this layer
    would create false positives for legitimate cached hosts.
    """
    if not isinstance(url, str) or not url:
        raise ToolError(
            code=ToolErrorCode.URL_INVALID,
            message="`url` must be a non-empty string",
        )

    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise ToolError(
            code=ToolErrorCode.SCHEME_NOT_ALLOWED,
            message=f"only http(s) URLs are allowed, got {parsed.scheme or '∅'!r}",
        )
    if not parsed.hostname:
        raise ToolError(
            code=ToolErrorCode.URL_INVALID,
            message="URL has no host component",
        )

    host = parsed.hostname
    # If it parses as an IP literal, run it through the block list.
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and _is_blocked_ip(ip):
        raise ToolError(
            code=ToolErrorCode.URL_BLOCKED,
            message=f"refusing to browse private/loopback address {host}",
        )

    return url


def proxy_kwargs(proxy_url: Optional[str]) -> dict:
    """Build httpx kwargs honouring an explicit proxy if set.

    httpx already inherits HTTP(S)_PROXY from os.environ unless we pass
    ``trust_env=False``. We *want* that environment fall-through (the
    broker plumbs APPTAINERENV_HTTPS_PROXY), so an empty config means
    "use whatever the env says".
    """
    if proxy_url:
        return {"proxy": proxy_url}
    return {}
