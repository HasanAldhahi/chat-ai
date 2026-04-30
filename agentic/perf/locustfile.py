"""Locust load test for the agentic broker (Phase 5 / Task 5.3).

Run against a broker started in mock mode:

    AGENTIC_SLURM_MOCK_MODE=1 \
    AGENTIC_VAULT_MOCK_MODE=1 \
    AGENTIC_VLLM_BASE_URL=http://127.0.0.1:9999 \
    AGENTIC_AUTH_RATE_PER_USER=1000 \
    AGENTIC_SSE_PUBLISH_RATE_PER_SESSION=1000 \
    uvicorn app.main:app --host 0.0.0.0 --port 8001

Then:

    cd agentic/perf
    locust -f locustfile.py --host http://127.0.0.1:8001 \
        --users 100 --spawn-rate 10 --run-time 5m --headless

The user count + spawn rate match the Task 5.3 acceptance criterion
("100 concurrent users, each sending 10 agent requests"). The default
mix below is the steady-state shape one would expect once a session
is established: many SSE publishes / status polls per submission.

Targets to compare against (Task 5.3 § Performance targets):

* P99 latency for first action      < 5 s
* SSE streaming latency             < 500 ms
* Broker CPU at 100 concurrent users < 50 %
* Slurm queue backlog                < 10 jobs
"""

from __future__ import annotations

import json
import random
import uuid
from typing import Optional

from locust import HttpUser, between, task


def _agent_models():
    return [
        "Agent - OpenHands",
        "Agent - Goose",
        "Agent - opencode",
    ]


class AgenticBrokerUser(HttpUser):
    """One Locust user = one synthetic broker user with a stable X-User."""

    wait_time = between(0.5, 2.0)
    host = "http://127.0.0.1:8001"

    user_id: str = ""
    session_id: str = ""
    job_id: Optional[str] = None

    def on_start(self) -> None:
        # Make X-User unique per Locust user so per-user rate limits do
        # not collapse the load to one shared bucket.
        suffix = uuid.uuid4().hex[:8]
        self.user_id = f"loaduser-{suffix}@gwdg"
        self.session_id = f"sess-{suffix}"
        self.job_id = None

    def _headers(self) -> dict:
        return {
            "Authorization": "Bearer load-test-token",
            "X-User": self.user_id,
            "Content-Type": "application/json",
        }

    # ---------------------------------------------------------------- jobs ----
    @task(3)
    def submit_job(self) -> None:
        """One job submission per "agent task". Heaviest end-to-end path."""
        body = json.dumps(
            {
                "session_id": self.session_id,
                "container_image": "/srv/images/agentic.sif",
            }
        )
        with self.client.post(
            "/api/jobs",
            data=body,
            headers=self._headers(),
            name="POST /api/jobs",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")
                return
            try:
                self.job_id = resp.json().get("job_id")
            except ValueError:
                resp.failure("non-JSON body")

    @task(8)
    def poll_status(self) -> None:
        """Status polling dominates a real session — the front-end pulls
        every couple of seconds while a job is queued/running.
        """
        if not self.job_id:
            return
        with self.client.get(
            f"/api/jobs/{self.job_id}/status",
            headers=self._headers(),
            name="GET /api/jobs/:id/status",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")

    # ------------------------------------------------------------- secrets ----
    @task(2)
    def read_secret(self) -> None:
        with self.client.get(
            "/api/secrets/search_api_key",
            headers=self._headers(),
            name="GET /api/secrets/:type",
            catch_response=True,
        ) as resp:
            # Mock-mode Vault returns a deterministic synthetic secret.
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")

    # ----------------------------------------------------------------- sse ----
    @task(6)
    def publish_sse(self) -> None:
        """The agent runtime streams actions / results / errors via this
        endpoint. Under load the rate limiter (per-session, sliding 1 s)
        should hold — track 429 separately, those are not failures.
        """
        kind = random.choice(["action", "result", "message"])
        body = {
            "event": kind,
            "data": {
                "type": "web_search" if kind == "action" else "summary",
                "message": "load-test event",
                "timestamp": "2026-04-30T12:00:00Z",
            },
        }
        with self.client.post(
            f"/api/sse/{self.session_id}/events",
            data=json.dumps(body),
            headers=self._headers(),
            name="POST /api/sse/:id/events",
            catch_response=True,
        ) as resp:
            if resp.status_code == 429:
                # Rate limit hit — expected under saturation, not a failure.
                resp.success()
                return
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")

    # ---------------------------------------------------------- agent_chat ----
    @task(1)
    def agent_chat_stream(self) -> None:
        """Hits the broker → vLLM bridge. Requires the broker's
        ``AGENTIC_VLLM_BASE_URL`` to point at a running stub or real
        vLLM; otherwise the call returns 502 and shows up as a slow
        failure (which is itself a useful Locust signal).
        """
        body = {
            "model": random.choice(_agent_models()),
            "messages": [{"role": "user", "content": "Summarise CRISPR."}],
            "stream": True,
        }
        with self.client.post(
            "/api/agent/chat",
            data=json.dumps(body),
            headers=self._headers(),
            name="POST /api/agent/chat",
            catch_response=True,
            stream=True,
        ) as resp:
            if resp.status_code >= 500:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")
                return
            # Drain a small prefix so the SSE TTFB is measured properly;
            # Locust will record the time to first byte either way.
            consumed = 0
            for chunk in resp.iter_lines(decode_unicode=False):
                consumed += len(chunk or b"")
                if consumed > 4096:
                    break

    # --------------------------------------------------------------- health ---
    @task(1)
    def health(self) -> None:
        with self.client.get(
            "/health",
            name="GET /health",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}")
