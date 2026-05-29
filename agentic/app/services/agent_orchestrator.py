"""Agent session orchestrator (Task 6.4).

When a chat turn arrives for an agent model, ``ensure_runtime`` looks up
the ``RuntimeSpec``, submits a container job (via ``LocalExecutor`` or
``SlurmClient`` depending on ``settings.execution_mode``), and stores the
``(session_id, user_id) → job_id`` mapping so subsequent turns can reuse
the same running container.

The runtime container is expected to:
  1. Start the MCP uvicorn server.
  2. Run the agent CLI (goose run / openhands / …).
  3. Forward its stdout as SSE events to the broker via
     ``POST {broker_base_url}/api/sse/{session_id}/events``.

Env vars injected per runtime:
  - ``GOOSE_*``      for goose_runtime
  - ``OPENHANDS_*``  for openhands_runtime
  (mirroring their ``pydantic_settings`` ``env_prefix`` values)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional, Tuple

from app.config import Settings
from app.models.job import CancelReason, JobState, JobSubmissionRequest
from app.services.agent_registry import RuntimeSpec, lookup, sif_path

log = logging.getLogger("agentic.orchestrator")

# (session_id, user_id) → job_id
_SessionKey = Tuple[str, str]


class OrchestrationError(Exception):
    def __init__(self, message: str, *, http_status: int = 503) -> None:
        super().__init__(message)
        self.http_status = http_status


class AgentOrchestrator:
    """Submit and track one runtime container job per agent session."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sessions: Dict[_SessionKey, str] = {}  # key → job_id
        self._lock = asyncio.Lock()

    # ---------------------------------------------------------------- public

    async def ensure_runtime(
        self,
        *,
        session_id: str,
        user_id: str,
        model_id: str,
        llm_model: str | None = None,
        prompt: str,
        bearer_token: str = "",
        executor=None,   # LocalExecutor | SlurmClient — injected by router
    ) -> Dict[str, str]:
        """Idempotently start a runtime for *(session_id, user_id)*.

        Returns ``{"job_id": ..., "session_id": ...}``.
        Raises :class:`OrchestrationError` (503) when the runtime is
        disabled, the .sif is missing, or the executor refuses the job.
        """
        spec = lookup(model_id)
        if spec is None:
            raise OrchestrationError(
                f"model {model_id!r} is not an agent model",
                http_status=400,
            )
        if not spec.enabled:
            raise OrchestrationError(
                f"runtime {spec.runtime_key!r} is not enabled on this broker — "
                "the container image has not been built yet",
                http_status=503,
            )

        key: _SessionKey = (session_id, user_id)
        async with self._lock:
            # Local jobs run `goose run --no-session` which is one-shot per prompt.
            # Never reuse a local job — each message needs its own fresh container.
            if self._settings.execution_mode != "local":
                existing_job_id = self._sessions.get(key)
                if existing_job_id:
                    still_running = await self._is_running(existing_job_id, executor)
                    if still_running:
                        log.info(
                            "orchestrator.reuse",
                            extra={"session_id": session_id, "job_id": existing_job_id},
                        )
                        return {"job_id": existing_job_id, "session_id": session_id}
                    del self._sessions[key]

            job_id = await self._launch(
                spec=spec,
                session_id=session_id,
                user_id=user_id,
                llm_model=llm_model,
                prompt=prompt,
                bearer_token=bearer_token,
                executor=executor,
            )
            self._sessions[key] = job_id
            return {"job_id": job_id, "session_id": session_id}

    def active_sessions(self) -> List[Dict]:
        """Point-in-time list of (session_id, user_id, job_id) for the admin endpoint."""
        return [
            {"session_id": sid, "user_id": uid, "job_id": job_id}
            for (sid, uid), job_id in self._sessions.items()
        ]

    async def cancel_session(
        self,
        *,
        session_id: str,
        user_id: str,
        reason: CancelReason = CancelReason.SESSION_END,
        executor=None,
    ) -> None:
        """Cancel the running job for a session, if any."""
        key: _SessionKey = (session_id, user_id)
        job_id = self._sessions.pop(key, None)
        if not job_id or executor is None:
            return
        try:
            await executor.cancel(job_id, owner=user_id, reason=reason)
        except Exception as exc:
            log.warning(
                "orchestrator.cancel_error",
                extra={"session_id": session_id, "job_id": job_id, "error": str(exc)},
            )

    # --------------------------------------------------------------- private

    async def _launch(
        self,
        *,
        spec: RuntimeSpec,
        session_id: str,
        user_id: str,
        llm_model: str | None = None,
        prompt: str,
        bearer_token: str,
        executor,
    ) -> str:
        image = sif_path(spec)
        broker_url = self._broker_url()
        # NOTE: Runtime forwarders expect just the base URL, they append /api/sse/{session_id}/events themselves
        sse_ingest_url = broker_url

        # When the orchestrator is active, prepend the system prompt to the
        # session prompt so Goose passes it as context to GLM-4.7 via -t TEXT.
        if self._settings.orchestrator_enabled:
            from app.routers.agent_chat import _ORCHESTRATOR_SYSTEM_PROMPT
            prompt = (
                f"[SYSTEM CONTEXT — follow these rules for this entire session]\n"
                f"{_ORCHESTRATOR_SYSTEM_PROMPT}\n\n"
                f"[USER TASK]\n{prompt}"
            )

        env = {**spec.base_env}
        env.update(self._runtime_env(spec, session_id, user_id, prompt, sse_ingest_url))
        # Well-known vars the local executor uses to post a terminal SSE event.
        env["AGENTIC_BROKER_BASE_URL"] = broker_url
        env["AGENTIC_SESSION_USER_ID"] = user_id
        # Pass LLM config to runtime so it can call the model.
        if self._settings.vllm_base_url:
            env.setdefault("OPENAI_BASE_URL", self._settings.vllm_base_url.rstrip("/"))
            env.setdefault("OPENAI_API_KEY", self._settings.vllm_api_key or "local")
            env.setdefault("GOOSE_PROVIDER", "openai")
            env.setdefault("GOOSE_MODEL", llm_model or self._settings.vllm_model)
        # For local dev without vLLM, forward any GOOSE_*/ANTHROPIC_*/OPENAI_* vars already
        # present in the broker's own environment so the runtime inherits them.
        import os as _os
        for _k, _v in _os.environ.items():
            if _k.startswith(("GOOSE_PROVIDER", "GOOSE_MODEL", "ANTHROPIC_", "OPENAI_")):
                env.setdefault(_k, _v)

        req = JobSubmissionRequest(
            session_id=session_id,
            container_image=image,
            environment=env,
        )

        log.info(
            "orchestrator.launch",
            extra={
                "session_id": session_id,
                "user_id": user_id,
                "runtime": spec.runtime_key,
                "image": image,
                "sse_ingest": sse_ingest_url,
            },
        )

        try:
            result = await executor.submit_job(req, bearer_token=bearer_token)
        except Exception as exc:
            http_status = getattr(exc, "http_status", 503)
            raise OrchestrationError(str(exc), http_status=http_status) from exc

        if hasattr(executor, "set_owner"):
            executor.set_owner(result.job_id, user_id)

        log.info(
            "orchestrator.launch_ok",
            extra={"session_id": session_id, "job_id": result.job_id},
        )
        return result.job_id

    async def _is_running(self, job_id: str, executor) -> bool:
        if executor is None:
            return False
        try:
            status = await executor.get_status(job_id)
            return not status.status.is_terminal
        except Exception:
            return False

    def _broker_url(self) -> str:
        if self._settings.broker_base_url:
            return self._settings.broker_base_url.rstrip("/")
        return f"http://127.0.0.1:{self._settings.port}"

    @staticmethod
    def _runtime_env(
        spec: RuntimeSpec,
        session_id: str,
        user_id: str,
        prompt: str,
        sse_ingest_url: str,
    ) -> Dict[str, str]:
        """Build per-session env vars keyed by the runtime's env_prefix."""
        key = spec.runtime_key.upper()  # GOOSE, OPENHANDS, OPENCODE, …
        # run_extra is intentionally left empty here; local_executor.py sets
        # GOOSE_RUN_EXTRA directly so it can make file-system-aware decisions.
        return {
            f"{key}_SESSION_ID": session_id,
            f"{key}_USER_ID": user_id,
            f"{key}_SESSION_PROMPT": prompt,
            f"{key}_BROKER_SSE_URL": sse_ingest_url,
            # APPTAINERENV_* so values survive into the container
            f"APPTAINERENV_{key}_SESSION_ID": session_id,
            f"APPTAINERENV_{key}_USER_ID": user_id,
            f"APPTAINERENV_{key}_SESSION_PROMPT": prompt,
            f"APPTAINERENV_{key}_BROKER_SSE_URL": sse_ingest_url,
        }
