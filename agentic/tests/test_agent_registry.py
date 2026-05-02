"""Tests for app.services.agent_registry (Task 6.3)."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from app.services.agent_registry import RUNTIMES, RuntimeSpec, lookup, sif_path


# ---------------------------------------------------------------------------
# Happy-path lookups
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model_id,expected_key", [
    ("Agent - Goose (Fast reasoning)", "goose"),
    ("🤖 Agent - Goose (Fast reasoning)", "goose"),   # front prefixes emoji
    ("agent - goose (fast reasoning)", "goose"),       # lower-cased
    ("Agent - OpenHands (Web + Code + Files)", "openhands"),
    ("Agent - opencode (Code focus)", "opencode"),
    ("Agent - smolagents (Lightweight)", "smolagents"),
])
def test_lookup_known_agents(model_id: str, expected_key: str) -> None:
    spec = lookup(model_id)
    assert spec is not None, f"lookup({model_id!r}) returned None"
    assert spec.runtime_key == expected_key


def test_lookup_substring_fallback() -> None:
    """Substring match: 'goose' anywhere in model id resolves to goose spec."""
    assert lookup("some-goose-model")
    assert lookup("some-goose-model").runtime_key == "goose"  # type: ignore[union-attr]


def test_lookup_non_agent_returns_none() -> None:
    assert lookup("meta-llama-3.1-8b-instruct") is None
    assert lookup("gpt-4o") is None
    assert lookup("glm-4.7") is None
    assert lookup("") is None


# ---------------------------------------------------------------------------
# Disabled runtimes
# ---------------------------------------------------------------------------

def test_disabled_runtimes_still_in_registry() -> None:
    """Disabled specs must be present; callers decide how to handle them."""
    disabled = [s for s in RUNTIMES.values() if not s.enabled]
    assert len(disabled) >= 2, "opencode and smolagents should be disabled"


def test_lookup_disabled_runtime_returns_spec() -> None:
    """lookup() returns the spec even when enabled=False so callers can 503."""
    spec = lookup("Agent - opencode (Code focus)")
    assert spec is not None
    assert spec.enabled is False


# ---------------------------------------------------------------------------
# RuntimeSpec validation
# ---------------------------------------------------------------------------

def test_all_specs_have_required_fields() -> None:
    for key, spec in RUNTIMES.items():
        assert spec.model_id, f"{key}: model_id empty"
        assert spec.runtime_key == key, f"{key}: runtime_key mismatch"
        assert spec.sif_image.endswith(".sif"), f"{key}: sif_image must end with .sif"
        assert spec.python_module, f"{key}: python_module empty"
        assert spec.max_runtime_s > 0, f"{key}: max_runtime_s must be > 0"


def test_sif_path_uses_container_root_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENTIC_CONTAINER_ROOT", str(tmp_path))
    spec = RUNTIMES["goose"]
    path = sif_path(spec)
    assert path.startswith(str(tmp_path))
    assert path.endswith("goose.sif")


# ---------------------------------------------------------------------------
# Cross-validate with front/src/constants/chatAiAgentModels.js
# ---------------------------------------------------------------------------

_FRONT_MODELS_JS = (
    Path(__file__).parent.parent.parent
    / "front" / "src" / "constants" / "chatAiAgentModels.js"
)


def _parse_front_model_ids() -> list[str]:
    """Extract ``id:`` string literals from chatAiAgentModels.js."""
    text = _FRONT_MODELS_JS.read_text()
    return re.findall(r'id:\s*"([^"]+)"', text)


@pytest.mark.skipif(
    not _FRONT_MODELS_JS.exists(),
    reason="front/src/constants/chatAiAgentModels.js not found",
)
def test_front_agent_ids_covered_by_registry() -> None:
    """Every agent id declared in the front catalog must resolve in the registry."""
    front_ids = [mid for mid in _parse_front_model_ids() if "agent" in mid.lower()]
    assert front_ids, "No agent ids found in chatAiAgentModels.js — check the regex"

    missing = [mid for mid in front_ids if lookup(mid) is None]
    assert not missing, (
        f"These front agent ids have no matching RuntimeSpec:\n"
        + "\n".join(f"  {m!r}" for m in missing)
        + "\nAdd them to RUNTIMES in app/services/agent_registry.py"
    )
