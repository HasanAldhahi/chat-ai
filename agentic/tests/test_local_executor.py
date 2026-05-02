"""Tests for LocalExecutor (Task 6.2)."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from app.clients.slurm import SlurmNotFoundError
from app.config import Settings
from app.models.job import CancelReason, JobState, JobSubmissionRequest
from app.services.job_monitor import JobAlreadyTerminalError, JobOwnershipError
from app.services.local_executor import LocalExecError, LocalExecutor


def _settings(**kwargs) -> Settings:
    base = dict(
        execution_mode="local",
        local_exec_grace_s=2.0,
        local_exec_fallback_to_python=False,
        local_exec_keep_proxy=False,
        slurm_mock_mode=False,
    )
    base.update(kwargs)
    return Settings(**base)


def _req(cmd: str = "/bin/true", env: dict | None = None) -> JobSubmissionRequest:
    return JobSubmissionRequest(
        session_id="test-sess-001",
        container_image=cmd,
        environment=env or {},
    )


# ---------------------------------------------------------------------------
# submit + status lifecycle (uses /bin/true — exits 0 immediately)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_true_succeeds(tmp_path: Path) -> None:
    os.environ["AGENTIC_LOCAL_JOB_LOG_DIR"] = str(tmp_path)
    exc = LocalExecutor(_settings())

    # Override _build_argv_env to use /bin/true directly (no apptainer needed).
    exc._build_argv_env = lambda req, _log: (["/bin/true"], dict(os.environ))  # type: ignore[method-assign]

    result = await exc.submit_job(_req())
    assert result.job_id.startswith("local-")

    # Wait for reaper
    await asyncio.sleep(0.3)

    status = await exc.get_status(result.job_id)
    assert status.status == JobState.SUCCEEDED
    assert status.exit_code == 0
    assert status.start_time is not None


@pytest.mark.asyncio
async def test_submit_false_fails(tmp_path: Path) -> None:
    os.environ["AGENTIC_LOCAL_JOB_LOG_DIR"] = str(tmp_path)
    exc = LocalExecutor(_settings())
    exc._build_argv_env = lambda req, _log: (["/bin/false"], dict(os.environ))  # type: ignore[method-assign]

    result = await exc.submit_job(_req())
    await asyncio.sleep(0.3)

    status = await exc.get_status(result.job_id)
    assert status.status == JobState.FAILED
    assert status.exit_code != 0


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancel_running_job(tmp_path: Path) -> None:
    os.environ["AGENTIC_LOCAL_JOB_LOG_DIR"] = str(tmp_path)
    exc = LocalExecutor(_settings(local_exec_grace_s=1.0))
    exc._build_argv_env = lambda req, _log: (["/bin/sleep", "60"], dict(os.environ))  # type: ignore[method-assign]

    result = await exc.submit_job(_req())
    exc.set_owner(result.job_id, "alice@gwdg")

    # While running
    status = await exc.get_status(result.job_id, owner="alice@gwdg")
    assert status.status == JobState.RUNNING

    await exc.cancel(result.job_id, owner="alice@gwdg", reason=CancelReason.USER_STOP)
    await asyncio.sleep(0.2)

    status = await exc.get_status(result.job_id, owner="alice@gwdg")
    assert status.status == JobState.CANCELLED


@pytest.mark.asyncio
async def test_cancel_already_terminal_raises(tmp_path: Path) -> None:
    os.environ["AGENTIC_LOCAL_JOB_LOG_DIR"] = str(tmp_path)
    exc = LocalExecutor(_settings())
    exc._build_argv_env = lambda req, _log: (["/bin/true"], dict(os.environ))  # type: ignore[method-assign]

    result = await exc.submit_job(_req())
    await asyncio.sleep(0.3)

    with pytest.raises(JobAlreadyTerminalError):
        await exc.cancel(result.job_id)


# ---------------------------------------------------------------------------
# ownership enforcement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cross_user_status_raises(tmp_path: Path) -> None:
    os.environ["AGENTIC_LOCAL_JOB_LOG_DIR"] = str(tmp_path)
    exc = LocalExecutor(_settings())
    exc._build_argv_env = lambda req, _log: (["/bin/sleep", "60"], dict(os.environ))  # type: ignore[method-assign]

    result = await exc.submit_job(_req())
    exc.set_owner(result.job_id, "alice@gwdg")

    with pytest.raises(JobOwnershipError):
        await exc.get_status(result.job_id, owner="bob@gwdg")

    # cleanup
    await exc.cancel(result.job_id, owner="alice@gwdg")


@pytest.mark.asyncio
async def test_cross_user_cancel_raises(tmp_path: Path) -> None:
    os.environ["AGENTIC_LOCAL_JOB_LOG_DIR"] = str(tmp_path)
    exc = LocalExecutor(_settings())
    exc._build_argv_env = lambda req, _log: (["/bin/sleep", "60"], dict(os.environ))  # type: ignore[method-assign]

    result = await exc.submit_job(_req())
    exc.set_owner(result.job_id, "alice@gwdg")

    with pytest.raises(JobOwnershipError):
        await exc.cancel(result.job_id, owner="bob@gwdg")

    await exc.cancel(result.job_id, owner="alice@gwdg")


# ---------------------------------------------------------------------------
# not-found
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_status_unknown_job_raises(tmp_path: Path) -> None:
    os.environ["AGENTIC_LOCAL_JOB_LOG_DIR"] = str(tmp_path)
    exc = LocalExecutor(_settings())
    with pytest.raises(SlurmNotFoundError):
        await exc.get_status("local-nonexistent")


# ---------------------------------------------------------------------------
# fallback: apptainer absent + fallback enabled → python -m module
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_python_fallback_when_apptainer_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    os.environ["AGENTIC_LOCAL_JOB_LOG_DIR"] = str(tmp_path)
    monkeypatch.setenv("AGENTIC_RUNTIME_MODULE", "py_compile")  # stdlib, always importable

    # Pretend apptainer is not on PATH
    import shutil
    original_which = shutil.which

    def _no_apptainer(name: str, **kw):
        if name == "apptainer":
            return None
        return original_which(name, **kw)

    monkeypatch.setattr(shutil, "which", _no_apptainer)

    exc = LocalExecutor(_settings(local_exec_fallback_to_python=True))
    from pathlib import Path as _Path
    argv, _ = exc._build_argv_env(_req(), _Path("/tmp/fake.log"))
    assert argv[1:] == ["-m", "py_compile"]
    assert "python" in argv[0]


@pytest.mark.asyncio
async def test_no_fallback_raises_503(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    os.environ["AGENTIC_LOCAL_JOB_LOG_DIR"] = str(tmp_path)
    import shutil
    original_which = shutil.which
    monkeypatch.setattr(shutil, "which", lambda n, **kw: None if n == "apptainer" else original_which(n, **kw))

    exc = LocalExecutor(_settings(local_exec_fallback_to_python=False))
    from pathlib import Path as _Path
    with pytest.raises(LocalExecError) as exc_info:
        exc._build_argv_env(_req(), _Path("/tmp/fake.log"))
    assert exc_info.value.http_status == 503


# ---------------------------------------------------------------------------
# log file captured
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stdout_captured_to_log_file(tmp_path: Path) -> None:
    os.environ["AGENTIC_LOCAL_JOB_LOG_DIR"] = str(tmp_path)
    exc = LocalExecutor(_settings())
    exc._build_argv_env = lambda req, _log: (  # type: ignore[method-assign]
        ["/bin/sh", "-c", "echo hello-from-job"],
        dict(os.environ),
    )

    result = await exc.submit_job(_req())
    await asyncio.sleep(0.3)

    log_file = tmp_path / result.job_id / "stdout.log"
    assert log_file.exists()
    assert b"hello-from-job" in log_file.read_bytes()
