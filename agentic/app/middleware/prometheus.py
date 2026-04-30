"""Prometheus metrics middleware for production monitoring (Task 5.5)."""

import logging
import time
from functools import wraps
from typing import Callable

from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from prometheus_client import CollectorRegistry
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

log = logging.getLogger("agentic.prometheus")


# Create a custom registry to avoid conflicts with other metrics
registry = CollectorRegistry()

# HTTP request metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
    registry=registry,
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
    registry=registry,
)

# Active sessions metrics
active_sessions = Gauge(
    "active_sessions",
    "Number of active agentic sessions",
    registry=registry,
)

# Slurm job metrics
slurm_jobs_total = Counter(
    "slurm_jobs_total",
    "Total Slurm jobs submitted",
    ["partition"],
    registry=registry,
)

slurm_jobs_active = Gauge(
    "slurm_jobs_active",
    "Number of active Slurm jobs",
    ["partition"],
    registry=registry,
)

slurm_job_duration_seconds = Histogram(
    "slurm_job_duration_seconds",
    "Slurm job duration",
    ["partition"],
    registry=registry,
)

# vLLM metrics
vllm_requests_total = Counter(
    "vllm_requests_total",
    "Total vLLM inference requests",
    ["model"],
    registry=registry,
)

vllm_requests_duration_seconds = Histogram(
    "vllm_requests_duration_seconds",
    "vLLM inference latency",
    ["model"],
    registry=registry,
)

vllm_requests_failed_total = Counter(
    "vllm_requests_failed_total",
    "Total failed vLLM requests",
    ["model", "status_code"],
    registry=registry,
)

# Agent metrics
agent_sessions_started_total = Counter(
    "agent_sessions_started_total",
    "Total agent sessions started",
    ["agent_model"],
    registry=registry,
)

agent_sessions_failed_5xx_total = Counter(
    "agent_sessions_failed_5xx_total",
    "Total agent sessions failed with 5xx",
    ["agent_model"],
    registry=registry,
)

feedback_submitted_total = Counter(
    "feedback_submitted_total",
    "Total user feedback submitted",
    registry=registry,
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware to collect Prometheus metrics for HTTP requests."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and collect metrics."""
        start_time = time.time()
        method = request.method
        endpoint = request.url.path

        # Sanitize endpoint to remove dynamic segments (e.g., UUIDs)
        endpoint = self._sanitize_endpoint(endpoint)

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            # Record 500 for unhandled exceptions
            status_code = 500
            log.error("Unhandled exception in request", exc_info=exc)
            raise

        # Record metrics
        duration = time.time() - start_time
        http_requests_total.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
        http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration)

        return response

    @staticmethod
    def _sanitize_endpoint(endpoint: str) -> str:
        """Sanitize endpoint path to remove dynamic segments."""
        # Replace UUID patterns
        path_parts = endpoint.split("/")
        sanitized_parts = []
        for part in path_parts:
            if part and (len(part) == 36 and part.count("-") == 4):  # UUID format
                sanitized_parts.append("{id}")
            elif part and part.isdigit():
                sanitized_parts.append("{id}")
            else:
                sanitized_parts.append(part)
        return "/".join(sanitized_parts)


def track_session(
    agent_model: str,
    partition: str = "grete:interactive",
) -> Callable:
    """Decorator to track agent session metrics."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Callable:
            # Increment active sessions
            active_sessions.inc()

            # Track session started
            agent_sessions_started_total.labels(agent_model=agent_model).inc()

            start_time = time.time()

            try:
                result = await func(*args, **kwargs)
                # Track Slurm job duration if applicable
                duration = time.time() - start_time
                slurm_job_duration_seconds.labels(partition=partition).observe(duration)
                return result
            except Exception as exc:
                # Track 5xx failures
                if hasattr(exc, "status_code") and exc.status_code >= 500:
                    agent_sessions_failed_5xx_total.labels(agent_model=agent_model).inc()
                raise
            finally:
                # Decrement active sessions
                active_sessions.dec()

        return wrapper

    return decorator


def track_slurm_job(partition: str = "grete:interactive") -> Callable:
    """Decorator to track Slurm job metrics."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Callable:
            slurm_jobs_total.labels(partition=partition).inc()
            slurm_jobs_active.labels(partition=partition).inc()

            try:
                return await func(*args, **kwargs)
            finally:
                slurm_jobs_active.labels(partition=partition).dec()

        return wrapper

    return decorator


def track_vllm_request(model: str) -> Callable:
    """Decorator to track vLLM inference metrics."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Callable:
            vllm_requests_total.labels(model=model).inc()
            start_time = time.time()

            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                vllm_requests_duration_seconds.labels(model=model).observe(duration)
                return result
            except Exception as exc:
                if hasattr(exc, "status_code"):
                    vllm_requests_failed_total.labels(
                        model=model,
                        status_code=exc.status_code,
                    ).inc()
                raise

        return wrapper

    return decorator


def track_feedback() -> None:
    """Track user feedback submission."""
    feedback_submitted_total.inc()


def metrics_endpoint() -> tuple[bytes, str]:
    """Generate Prometheus metrics for scraping.

    Returns:
        tuple: (metrics_bytes, content_type)
    """
    return generate_latest(registry), CONTENT_TYPE_LATEST