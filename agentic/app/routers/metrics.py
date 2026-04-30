"""Metrics endpoint for Prometheus scraping (Task 5.5)."""

from fastapi import APIRouter, Response

from app.middleware.prometheus import metrics_endpoint

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/")
async def get_metrics() -> Response:
    """Prometheus metrics endpoint for monitoring.

    This endpoint exposes Prometheus metrics for scraping by monitoring systems.
    The metrics include:
    - HTTP request metrics (total, latency)
    - Active sessions
    - Slurm job metrics (submitted, active, duration)
    - vLLM inference metrics (requests, latency, failures)
    - Agent session metrics (started, 5xx failures)
    - User feedback submissions

    Returns:
        Response: Prometheus metrics in text format.
    """
    metrics_bytes, content_type = metrics_endpoint()
    return Response(content=metrics_bytes, media_type=content_type)