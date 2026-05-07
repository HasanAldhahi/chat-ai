"""Local subprocess job executor (Task 6.2).

Implements the same submit / status / cancel interface as ``SlurmClient`` so
``app/routers/jobs.py`` can dispatch to either backend purely based on
``settings.execution_mode``.

Execution priority when a job is submitted:
  1. ``apptainer run <sif_image> [env overrides]``  (if apptainer on PATH)
  2. ``python -m <runtime_module>``                  (if AGENTIC_LOCAL_EXEC_FALLBACK=true)
  3. Raises ``LocalExecError(503)``                  (neither available)

Logs (stdout + stderr of the child) are captured to
``<AGENTIC_LOCAL_JOB_LOG_DIR>/<job_id>/stdout.log``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from app.config import Settings
from app.models.job import (
    CancelReason,
    JobState,
    JobStatusResponse,
    JobSubmissionRequest,
)

log = logging.getLogger("agentic.local_executor")

_DEFAULT_LOG_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "var", "jobs"
)


class LocalExecError(Exception):
    """Maps to an HTTP error status."""

    def __init__(self, message: str, *, http_status: int = 502) -> None:
        super().__init__(message)
        self.http_status = http_status


@dataclass
class _LocalJob:
    job_id: str
    owner: str
    session_id: str
    started_at: float
    proc: Optional[asyncio.subprocess.Process] = None
    state: JobState = JobState.QUEUED
    ended_at: Optional[float] = None
    exit_code: Optional[int] = None
    broker_base_url: str = ""
    session_user_id: str = ""
    reaper_task: Optional[asyncio.Task] = field(default=None, repr=False)  # type: ignore[type-arg]


class LocalExecutor:
    """Spawn runtime containers (or python modules) as local subprocesses."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._jobs: Dict[str, _LocalJob] = {}
        self._log_dir = Path(
            os.environ.get("AGENTIC_LOCAL_JOB_LOG_DIR", _DEFAULT_LOG_DIR)
        )

    # ------------------------------------------------------------------ submit

    async def submit_job(
        self, req: JobSubmissionRequest, *, bearer_token: str = ""
    ) -> "SubmitResult":
        from app.clients.slurm import SubmitResult  # reuse the dataclass

        job_id = f"local-{uuid.uuid4().hex[:12]}"
        job_log_dir = self._log_dir / job_id
        job_log_dir.mkdir(parents=True, exist_ok=True)
        log_file = job_log_dir / "stdout.log"
        # Persistent per-session workspace: all jobs for the same SSE session
        # share this dir so goose can resume its session history across messages.
        session_workspace = self._log_dir / "sessions" / req.session_id
        session_workspace.mkdir(parents=True, exist_ok=True)
        # Expose workspace path on req so _build_argv_env can use it.
        req = req.model_copy(update={"working_directory": req.working_directory or str(session_workspace)})
        # Inject workspace path into environment so runtimes know where to persist.
        req.environment["AGENTIC_SESSION_WORKSPACE"] = str(session_workspace)

        # Each message runs as a standalone one-shot job (no session history).
        run_extra = "run --no-session"
        req.environment["GOOSE_RUN_EXTRA"] = run_extra
        req.environment["APPTAINERENV_GOOSE_RUN_EXTRA"] = run_extra

        argv, env = self._build_argv_env(req, log_file)

        log.info(
            "local_exec.submit",
            extra={
                "job_id": job_id,
                "session_id": req.session_id,
                "argv0": argv[0],
                "log_file": str(log_file),
            },
        )

        fh = open(log_file, "wb")  # noqa: WPS515 — kept open until reaper closes it
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                env=env,
                cwd=req.working_directory or str(Path.home()),
                stdout=fh,
                stderr=asyncio.subprocess.STDOUT,
            )
        except Exception as exc:
            fh.close()
            raise LocalExecError(
                f"failed to start local job: {exc}", http_status=503
            ) from exc

        job = _LocalJob(
            job_id=job_id,
            owner="",  # filled by caller via register()
            session_id=req.session_id,
            started_at=time.monotonic(),
            proc=proc,
            state=JobState.RUNNING,
            broker_base_url=req.environment.get("AGENTIC_BROKER_BASE_URL", ""),
            session_user_id=req.environment.get("AGENTIC_SESSION_USER_ID", ""),
        )
        self._jobs[job_id] = job
        job.reaper_task = asyncio.create_task(
            self._reaper(job, fh), name=f"reaper-{job_id}"
        )

        log.info(
            "local_exec.running",
            extra={"job_id": job_id, "pid": proc.pid},
        )
        return SubmitResult(job_id=job_id)

    # ----------------------------------------------------------------- status

    async def get_status(
        self,
        job_id: str,
        *,
        bearer_token: str = "",
        owner: str = "",
    ) -> JobStatusResponse:
        job = self._jobs.get(job_id)
        if job is None:
            from app.clients.slurm import SlurmNotFoundError
            raise SlurmNotFoundError(f"local job not found: {job_id}")

        if owner and job.owner and job.owner != owner:
            from app.services.job_monitor import JobOwnershipError
            raise JobOwnershipError(
                f"job {job_id} is owned by {job.owner}, not {owner}"
            )

        start_iso = datetime.fromtimestamp(job.started_at, tz=timezone.utc).isoformat()
        end_iso = (
            datetime.fromtimestamp(job.ended_at, tz=timezone.utc).isoformat()
            if job.ended_at
            else None
        )
        return JobStatusResponse(
            job_id=job_id,
            status=job.state,
            start_time=start_iso,
            end_time=end_iso,
            exit_code=job.exit_code,
        )

    # ------------------------------------------------------------------ cancel

    async def cancel(
        self,
        job_id: str,
        *,
        owner: str = "",
        bearer_token: str = "",
        reason: CancelReason = CancelReason.USER_STOP,
    ) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            from app.clients.slurm import SlurmNotFoundError
            raise SlurmNotFoundError(f"local job not found: {job_id}")

        if owner and job.owner and job.owner != owner:
            from app.services.job_monitor import JobOwnershipError
            raise JobOwnershipError(
                f"job {job_id} is owned by {job.owner}, not {owner}"
            )

        if job.state.is_terminal:
            from app.services.job_monitor import JobAlreadyTerminalError
            raise JobAlreadyTerminalError(job.state)

        log.info(
            "local_exec.cancel",
            extra={"job_id": job_id, "reason": reason.value},
        )
        await self._terminate(job, grace_s=self._settings.local_exec_grace_s)
        job.state = JobState.CANCELLED
        job.ended_at = time.monotonic()

    def set_owner(self, job_id: str, owner: str) -> None:
        """Called by the jobs router right after submit to record ownership."""
        if job_id in self._jobs:
            self._jobs[job_id].owner = owner

    # ----------------------------------------------------------------- private

    def _build_argv_env(
        self, req: JobSubmissionRequest, log_file: Path
    ) -> tuple[list[str], dict[str, str]]:
        env = {**os.environ}
        # Strip GWDG proxy when running locally (avoids timeouts outside GWDG).
        if not self._settings.local_exec_keep_proxy:
            env.pop("HTTP_PROXY", None)
            env.pop("HTTPS_PROXY", None)
            env.pop("http_proxy", None)
            env.pop("https_proxy", None)
        # Merge caller-supplied env vars.
        env.update(req.environment)

        # Per-session persistent workspace (set in submit_job before this call).
        session_workspace = env.get("AGENTIC_SESSION_WORKSPACE", str(log_file.parent))

        # Pick a free MCP port per-job so simultaneous containers don't collide.
        import socket as _socket
        with _socket.socket() as _s:
            _s.bind(("127.0.0.1", 0))
            mcp_port = _s.getsockname()[1]

        # Skip apptainer if fallback_to_python is true (use Python module directly)
        if not self._settings.local_exec_fallback_to_python and shutil.which("apptainer"):
            # Bind the per-session workspace + hot-reloaded Python packages.
            # Overlaying goose_runtime and openhands_runtime from the host lets
            # us update sse_forwarder, config, launcher without rebuilding the .sif.
            agentic_dir = str(Path(__file__).parent.parent.parent)
            argv = [
                "apptainer",
                "run",
                "--cleanenv",
                f"--bind={session_workspace}:/workspace",
                f"--bind={agentic_dir}/goose_runtime:/opt/agentic/goose_runtime:ro",
                f"--bind={agentic_dir}/openhands_runtime:/opt/agentic/openhands_runtime:ro",
                # Hot-reload updated MCP server code (web search, tools) without rebuilding .sif.
                f"--bind={agentic_dir}/mcp_server:/opt/agentic/mcp_server:ro",
                # Vendor packages (ddgs + deps) installed for Python 3.11 but not in the image.
                f"--bind={agentic_dir}/.vendor:/opt/agentic/.vendor:ro",
                req.container_image,
            ]
            # Inject env as APPTAINERENV_* so apptainer exports them inside.
            # GOOSE_SESSION_PROMPT is excluded here — arbitrary user text breaks
            # Apptainer's shell-based /.inject-apptainer-env.sh when it contains
            # parentheses or other shell-special chars. Write to a file instead.
            prompt_text = req.environment.get("GOOSE_SESSION_PROMPT", "")
            prompt_file = Path(session_workspace) / "prompt.txt"
            prompt_file.write_text(prompt_text, encoding="utf-8")
            for k, v in req.environment.items():
                if k in ("GOOSE_SESSION_PROMPT", "APPTAINERENV_GOOSE_SESSION_PROMPT"):
                    continue
                env[f"APPTAINERENV_{k}"] = v
            env["APPTAINERENV_GOOSE_SESSION_PROMPT_FILE"] = "/workspace/prompt.txt"
            env.setdefault("APPTAINERENV_GOOSE_MCP_UVICORN_PORT", str(mcp_port))
            env.setdefault("APPTAINERENV_GOOSE_MCP_SERVER_URL", f"http://127.0.0.1:{mcp_port}")
            # Extend PYTHONPATH so the vendor packages (ddgs etc.) are importable.
            env["APPTAINERENV_PYTHONPATH"] = "/opt/agentic/.vendor:/opt/agentic"
            # Override any proxy vars baked into the container image so the
            # runtime can reach the LLM endpoint directly from this host.
            env["APPTAINERENV_HTTP_PROXY"] = ""
            env["APPTAINERENV_HTTPS_PROXY"] = ""
            env["APPTAINERENV_http_proxy"] = ""
            env["APPTAINERENV_https_proxy"] = ""
            env["APPTAINERENV_NO_PROXY"] = "localhost,127.0.0.1,::1"
            env["APPTAINERENV_no_proxy"] = "localhost,127.0.0.1,::1"
            return argv, env

        if self._settings.local_exec_fallback_to_python:
            module = env.get("AGENTIC_RUNTIME_MODULE", "goose_runtime.launcher")
            # Add agentic directory to PYTHONPATH so goose_runtime module can be found.
            agentic_dir = str(Path(__file__).parent.parent.parent)
            pythonpath = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = (
                f"{agentic_dir}:{pythonpath}".rstrip(":")
                if pythonpath and agentic_dir not in pythonpath
                else (pythonpath or agentic_dir)
            )
            # Use the per-session workspace as HOME so goose config and session
            # history persist across messages in the same conversation.
            env["GOOSE_HOME_DIR"] = session_workspace
            env["HOME"] = session_workspace
            env["XDG_CONFIG_HOME"] = f"{session_workspace}/.config"
            env["XDG_DATA_HOME"] = f"{session_workspace}/.local/share"
            # Add goose binary directory to PATH so goose_runtime.launcher can find it.
            goose_bin = shutil.which("goose") or ""
            if goose_bin:
                goose_bin_dir = str(Path(goose_bin).parent)
                env["PATH"] = f"{goose_bin_dir}:{env.get('PATH', os.environ.get('PATH', ''))}"
            env.setdefault("GOOSE_MCP_UVICORN_PORT", str(mcp_port))
            env.setdefault("GOOSE_MCP_SERVER_URL", f"http://127.0.0.1:{mcp_port}")
            # Prefer the venv Python (has all deps); fall back to system Python.
            python_bin = (
                shutil.which("python", path=str(Path(__file__).parent.parent.parent / ".venv/bin"))
                or shutil.which("python3.11")
                or shutil.which("python3")
                or "python3"
            )
            return [python_bin, "-m", module], env

        raise LocalExecError(
            "apptainer not on PATH and AGENTIC_LOCAL_EXEC_FALLBACK_TO_PYTHON=false",
            http_status=503,
        )

    async def _reaper(
        self, job: _LocalJob, log_fh: object
    ) -> None:
        """Wait for the child to exit, update job state, post terminal SSE event."""
        assert job.proc is not None
        try:
            rc = await job.proc.wait()
        except asyncio.CancelledError:
            return
        finally:
            try:
                log_fh.close()  # type: ignore[union-attr]
            except Exception:
                pass

        job.exit_code = rc
        job.ended_at = time.monotonic()

        if job.state == JobState.CANCELLED:
            pass  # already set by cancel()
        elif rc == 0:
            job.state = JobState.SUCCEEDED
        else:
            job.state = JobState.FAILED

        log.info(
            "local_exec.exited",
            extra={
                "job_id": job.job_id,
                "rc": rc,
                "state": job.state.value,
            },
        )

        # Post a terminal SSE event so the front-end async202 promise resolves.
        await self._post_terminal_sse(job, rc)

    @staticmethod
    async def _post_terminal_sse(job: _LocalJob, rc: int) -> None:
        """POST a result/error event to the broker SSE hub when the job exits."""
        if not job.broker_base_url or not job.session_id or not job.session_user_id:
            return
        import httpx  # httpx is already in requirements.txt
        url = f"{job.broker_base_url.rstrip('/')}/api/sse/{job.session_id}/events"
        event = "result" if rc == 0 else "error"
        data: dict = (
            {"output": "Agent job completed.", "code": str(rc)}
            if rc == 0
            else {"message": f"Agent job exited with code {rc}.", "code": str(rc)}
        )
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as client:
                await client.post(
                    url,
                    json={"event": event, "data": data},
                    headers={"X-User": job.session_user_id},
                )
        except Exception as exc:
            log.warning("local_exec.sse_terminal_post_failed", extra={"error": str(exc)})

    @staticmethod
    async def _terminate(
        job: _LocalJob, grace_s: float = 5.0
    ) -> None:
        proc = job.proc
        if proc is None or proc.returncode is not None:
            return
        try:
            proc.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=grace_s)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()


# Tiny dataclass re-export so callers don't need to import from slurm.
@dataclass
class SubmitResult:
    job_id: str
