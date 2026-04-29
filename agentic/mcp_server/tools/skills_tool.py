"""MCP ``get_skills`` tool."""

from __future__ import annotations

from typing import Any, Dict, List

from .. import config as cfg_module
from ..skills.loader import load_skill_store


async def get_skills(args: Dict[str, Any]) -> Dict[str, Any]:
    """Return Markdown skill payloads for ``framework``.

    Omit ``framework`` to use ``MCP_SERVER_AGENT_FRAMEWORK`` (lowercase id).
    """
    settings = cfg_module.get_settings()
    explicit_fw = args.get("framework") or args.get("agent_framework")
    if isinstance(explicit_fw, str) and explicit_fw.strip():
        framework = explicit_fw.strip().lower()
    else:
        framework = getattr(settings, "agent_framework", "").strip().lower()

    store = load_skill_store(settings.skills_dir, reload=False)

    rows: List[Dict[str, str]] = []
    for doc in store.for_framework(framework):
        rows.append(
            {
                "skill_name": doc.skill_name,
                "description": doc.description,
                "markdown": doc.body_markdown,
            },
        )

    return {
        "framework": framework,
        "skills": rows,
    }
