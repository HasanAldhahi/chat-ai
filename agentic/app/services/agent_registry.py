"""Agent runtime registry (Task 6.3).

Maps frontend agent model ids (e.g. ``"Agent - Goose (Fast reasoning)"``)
to the RuntimeSpec the broker uses to launch a container job.

The canonical frontend list lives in
``front/src/constants/chatAiAgentModels.js``. A CI test
(``tests/test_agent_registry.py``) asserts both sides stay in sync.
"""

from __future__ import annotations

import os
from typing import Dict, Optional

from pydantic import BaseModel


class RuntimeSpec(BaseModel):
    """Immutable description of one agent runtime."""

    model_id: str
    """Exact id string as declared in ``chatAiAgentModels.js``."""

    runtime_key: str
    """Short key: ``goose`` | ``openhands`` | ``opencode`` | ``smolagents``."""

    sif_image: str
    """Path to the .sif relative to ``AGENTIC_CONTAINER_ROOT``.
    E.g. ``"goose/goose.sif"``."""

    python_module: str
    """Fallback when apptainer is not on PATH:
    ``python -m <python_module>`` is used instead of ``apptainer run``."""

    base_env: Dict[str, str]
    """Env vars injected into every job for this runtime.
    The orchestrator adds session-specific vars (session_id, broker URL,
    prompt) on top of these."""

    max_runtime_s: int = 1800
    """Hard cap passed to the local executor and Slurm time-limit."""

    enabled: bool = True
    """False for runtimes whose .sif isn't built yet; broker returns 503."""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

RUNTIMES: Dict[str, RuntimeSpec] = {
    spec.runtime_key: spec
    for spec in [
        RuntimeSpec(
            model_id="Agent - Goose (Fast reasoning)",
            runtime_key="goose",
            sif_image="goose/goose.sif",
            python_module="goose_runtime.launcher",
            base_env={
                "GOOSE_MODE": "auto",
                "GOOSE_CONTEXT_STRATEGY": "summarize",
                "GOOSE_DISABLE_SESSION_NAMING": "true",
                "GOOSE_LOG_LEVEL": "INFO",
            },
            max_runtime_s=1800,
            enabled=True,
        ),
        RuntimeSpec(
            model_id="Agent - OpenHands (Web + Code + Files)",
            runtime_key="openhands",
            sif_image="openhands/openhands.sif",
            python_module="openhands_runtime.launcher",
            base_env={
                "OPENHANDS_LOG_LEVEL": "INFO",
            },
            max_runtime_s=1800,
            enabled=True,
        ),
        RuntimeSpec(
            model_id="Agent - opencode (Code focus)",
            runtime_key="opencode",
            sif_image="opencode/opencode.sif",
            python_module="opencode_runtime.launcher",
            base_env={},
            max_runtime_s=1800,
            enabled=False,
        ),
        RuntimeSpec(
            model_id="Agent - smolagents (Lightweight)",
            runtime_key="smolagents",
            sif_image="smolagents/smolagents.sif",
            python_module="smolagents_runtime.launcher",
            base_env={},
            max_runtime_s=900,
            enabled=False,
        ),
    ]
}

# Secondary index: lower-cased model id → spec (for case-insensitive lookup)
_BY_MODEL_ID: Dict[str, RuntimeSpec] = {
    spec.model_id.lower(): spec for spec in RUNTIMES.values()
}


def lookup(model_id: str) -> Optional[RuntimeSpec]:
    """Return the RuntimeSpec for *model_id*, or ``None`` if not an agent.

    Matching is case-insensitive and also falls back to substring matching
    on the runtime key (so ``"goose"`` anywhere in *model_id* resolves to
    the goose spec).  Returns ``None`` for non-agent model ids.
    """
    needle = model_id.strip().lower()

    # Exact match first.
    if needle in _BY_MODEL_ID:
        return _BY_MODEL_ID[needle]

    # Substring fallback: match on runtime_key inside the model id.
    for key, spec in RUNTIMES.items():
        if key in needle:
            return spec

    return None


def sif_path(spec: RuntimeSpec) -> str:
    """Resolve the absolute path to the .sif for *spec*.

    Uses ``AGENTIC_CONTAINER_ROOT`` env var (defaults to the ``containers/``
    directory next to this file's package root).
    """
    root = os.environ.get(
        "AGENTIC_CONTAINER_ROOT",
        os.path.join(os.path.dirname(__file__), "..", "..", "containers"),
    )
    return os.path.normpath(os.path.join(root, spec.sif_image))
