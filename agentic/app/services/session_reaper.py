"""Session inactivity reaper — cancels idle agent jobs after a configurable timeout.

A session is considered idle when:
  - It has no active SSE subscribers (no open browser tab), AND
  - No SSE events have been published for ``agent_session_idle_timeout_s`` seconds.

Both conditions must hold so we never cancel a session where the agent is
still working but the user has momentarily closed their tab.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from app.config import Settings
from app.models.job import CancelReason

log = logging.getLogger("agentic.session_reaper")


class SessionReaper:
    def __init__(self, app, settings: Settings) -> None:
        self._app = app
        self._settings = settings
        self._task: Optional[asyncio.Task] = None
        self.last_reap_ts: Optional[float] = None
        self.last_cancelled: list = []

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="session-reaper")

    async def aclose(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    async def _loop(self) -> None:
        interval = self._settings.agent_session_reaper_interval_s
        try:
            while True:
                await asyncio.sleep(interval)
                try:
                    await self._reap()
                except Exception:
                    log.exception("session_reaper.error")
        except asyncio.CancelledError:
            log.info("session_reaper.cancelled")
            raise

    async def _reap(self) -> None:
        hub = getattr(self._app.state, "sse_hub", None)
        orchestrator = getattr(self._app.state, "agent_orchestrator", None)
        if hub is None or orchestrator is None:
            return

        executor = getattr(self._app.state, "local_executor", None) or getattr(
            self._app.state, "slurm_client", None
        )

        idle_timeout = self._settings.agent_session_idle_timeout_s
        rooms = {r["session_id"]: r for r in hub.snapshot()}

        cancelled = []
        for session in orchestrator.active_sessions():
            sid, uid = session["session_id"], session["user_id"]
            room = rooms.get(sid)

            if room is None:
                idle = True
            else:
                idle = (
                    room["sse_subscribers"] == 0
                    and room["last_activity_s_ago"] > idle_timeout
                )

            if idle:
                log.info(
                    "session_reaper.cancel",
                    extra={
                        "session_id": sid,
                        "user_id": uid,
                        "reason": "no_room" if room is None else "idle",
                        "last_activity_s_ago": None if room is None else room["last_activity_s_ago"],
                    },
                )
                await orchestrator.cancel_session(
                    session_id=sid,
                    user_id=uid,
                    reason=CancelReason.SESSION_END,
                    executor=executor,
                )
                cancelled.append(sid)

        self.last_reap_ts = time.time()
        self.last_cancelled = cancelled

        if cancelled:
            log.info(
                "session_reaper.evicted",
                extra={"count": len(cancelled), "sessions": cancelled},
            )
