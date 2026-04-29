"""Load Markdown SKILL files from a directory — YAML frontmatter, cached."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[misc,assignment]

log = logging.getLogger("agentic-mcp-skills")

_FM_RE = re.compile(
    r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n(.*)$",
    re.DOTALL | re.MULTILINE,
)


@dataclass(frozen=True)
class SkillDoc:
    skill_name: str
    description: str
    body_markdown: str
    #: Normalised lowercase framework identifiers (openhands, goose, opencode…)
    frameworks: Tuple[str, ...]


def frameworks_for_skill(meta: Dict[str, Any]) -> Tuple[str, ...]:
    raw = meta.get("frameworks")
    if isinstance(raw, list):
        out = [str(x).strip().lower() for x in raw if str(x).strip()]
        if out:
            return tuple(sorted(set(out)))

    fw = meta.get("framework") or meta.get("skill_framework")
    if isinstance(fw, str) and fw.strip():
        lowered = fw.strip().lower()
        if lowered == "*":
            return ("*",)
        return (lowered,)

    return ("*",)  # global / all frameworks


def _parse_skill_file(path: Path) -> SkillDoc | None:
    raw = path.read_text(encoding="utf-8")
    m = _FM_RE.match(raw.strip())
    if not m:
        log.warning(
            "skill_invalid_frontmatter",
            extra={
                "path": str(path),
                "detail": "expected leading --- YAML --- block",
            },
        )
        return None

    fm_yaml, body_md = m.group(1).strip(), m.group(2).lstrip("\n")
    if yaml is None:
        log.warning(
            "skill_skip_no_yaml",
            extra={
                "path": str(path),
                "detail": "PyYAML not installed — cannot parse frontmatter",
            },
        )
        return None

    try:
        meta = yaml.safe_load(fm_yaml) or {}
    except yaml.YAMLError as exc:
        log.warning(
            "skill_yaml_error",
            extra={"path": str(path), "detail": str(exc)},
        )
        return None

    if not isinstance(meta, dict):
        log.warning("skill_meta_not_object", extra={"path": str(path)})
        return None

    name = meta.get("skill_name")
    desc = meta.get("description")
    if not isinstance(name, str) or not name.strip():
        log.warning(
            "skill_missing_skill_name",
            extra={"path": str(path)},
        )
        return None
    if not isinstance(desc, str) or not desc.strip():
        log.warning(
            "skill_missing_description",
            extra={"path": str(path)},
        )
        return None

    fws = frameworks_for_skill(meta)
    return SkillDoc(
        skill_name=name.strip(),
        description=desc.strip(),
        body_markdown=body_md.rstrip(),
        frameworks=fws,
    )


class SkillStore:
    """Immutable snapshot of validated skills."""

    def __init__(self, docs: Tuple[SkillDoc, ...]):
        self._docs = docs

    @property
    def docs(self) -> Tuple[SkillDoc, ...]:
        return self._docs

    def for_framework(self, framework: str | None) -> List[SkillDoc]:
        fw = (framework or "").strip().lower()
        selected: List[SkillDoc] = []
        for d in self._docs:
            if "*" in d.frameworks:
                selected.append(d)
                continue
            if not fw:
                continue
            if fw in d.frameworks:
                selected.append(d)
        # Stable order by skill_name
        return sorted(selected, key=lambda x: x.skill_name)


_SKILL_ENTRY: tuple[str, SkillStore] | None = None


def load_skill_store(root: Path | str | None, *, reload: bool = False) -> SkillStore:
    """Load *.md skills from ``root`` directory (flat). Cached process-wide."""

    global _SKILL_ENTRY
    root_path = Path(root) if root else Path("/skills")
    try:
        key = str(root_path.resolve())
    except Exception:
        key = str(root_path)

    if (
        _SKILL_ENTRY is not None
        and not reload
        and _SKILL_ENTRY[0] == key
    ):
        return _SKILL_ENTRY[1]

    if not root_path.is_dir():
        log.warning(
            "skills_directory_missing",
            extra={"path": str(root_path)},
        )
        store = SkillStore(())
        _SKILL_ENTRY = (key, store)
        return store

    docs: List[SkillDoc] = []
    for p in sorted(root_path.glob("*.md")):
        doc = _parse_skill_file(p)
        if doc is not None:
            docs.append(doc)

    store = SkillStore(tuple(docs))
    _SKILL_ENTRY = (key, store)
    log.info(
        "skills_loaded",
        extra={"path": str(root_path), "count": len(store.docs)},
    )
    return store


def reset_skill_cache() -> None:
    global _SKILL_ENTRY
    _SKILL_ENTRY = None
