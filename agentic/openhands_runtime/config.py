"""Runtime configuration for the OpenHands orchestration layer.

Environment-first (`OPENHANDS_*` prefix). The broker is responsible
for plumbing per-session values (session_id, broker SSE URL,
HTTPS_PROXY) via `APPTAINERENV_*` at submit time; everything else
has sensible defaults that work both in tests and inside the
container without further configuration.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OpenHandsSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPENHANDS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "agentic-openhands-runtime"
    log_level: str = Field(default="INFO")

    # --- Per-session identity (broker-injected) -----------------------------
    session_id: str = Field(
        default="dev-session",
        description="Identifier shared with the broker so SSE messages "
        "land in the right room. The broker injects this via "
        "APPTAINERENV_OPENHANDS_SESSION_ID.",
    )
    user_id: str = Field(
        default="",
        description="X-User passed back to the broker when forwarding "
        "events. Empty in dev/tests.",
    )

    # --- MCP server --------------------------------------------------------
    mcp_server_url: str = Field(
        default="http://localhost:8080",
        description="Where the in-container MCP server listens.",
    )
    mcp_health_timeout_s: float = Field(
        default=20.0,
        gt=0,
        description="Max seconds to wait for the MCP server's /health "
        "probe before giving up the orchestration.",
    )
    mcp_health_poll_interval_s: float = Field(
        default=0.5,
        gt=0,
    )
    mcp_uvicorn_port: int = Field(
        default=8080,
        ge=1,
        le=65535,
        description="Port the launcher binds uvicorn to (host=0.0.0.0). "
        "Must match the host part of mcp_server_url.",
    )

    # --- LLM / vLLM --------------------------------------------------------
    llm_api_url: str = Field(
        default="http://vllm.local/v1/completions",
        description="OpenAI-compatible completions endpoint exposed by "
        "the cluster's vLLM deployment. Plumbed in per-session.",
    )
    llm_model: str = Field(
        default="qwen3-30b",
        description="Model id passed to vLLM. The cluster's vLLM "
        "deployment must serve it.",
    )
    llm_parser: str = Field(
        default="hermes",
        description="vLLM tool-call parser. Must match the cluster "
        "deployment's --tool-call-parser flag.",
    )

    # --- Broker SSE forwarding --------------------------------------------
    broker_sse_url: str = Field(
        default="",
        description="Broker base URL where structured agent events are "
        "POSTed (e.g. http://agentic-broker:8001). Empty disables "
        "forwarding — useful for local dry-runs and tests.",
    )
    sse_post_timeout_s: float = Field(
        default=5.0,
        gt=0,
    )
    sse_max_inflight: int = Field(
        default=32,
        ge=1,
        description="Bounded queue depth between the OpenHands "
        "subprocess and the SSE forwarder. Excess events are dropped "
        "with a structured warning rather than back-pressuring "
        "OpenHands itself.",
    )

    # --- OpenHands subprocess ---------------------------------------------
    openhands_command: str = Field(
        default="openhands",
        description="Executable name / path. The container ships "
        "OpenHands V1 on PATH; tests can point this at /bin/cat or a "
        "synthetic script.",
    )
    openhands_extra_args: str = Field(
        default="",
        description="Whitespace-separated extra args passed to the "
        "OpenHands command (after the standard --config flag).",
    )
    openhands_config_path: str = Field(
        default="/etc/openhands/config.toml",
        description="Path to the OpenHands TOML config inside the "
        "container.",
    )
    openhands_workspace: str = Field(
        default="/workspace",
        description="Bind-mounted scratch dir; OpenHands' workdir.",
    )
    openhands_max_runtime_s: float = Field(
        default=30 * 60,
        gt=0,
        description="Hard cap on how long the OpenHands subprocess "
        "may run before the launcher kills it. Slurm enforces a "
        "broader cap; this is the in-container safety net.",
    )

    # --- Proxy (broker-injected; consumed via os.environ at runtime) ------
    https_proxy: Optional[str] = Field(
        default=None,
        description="If set, exported back into OpenHands' env so its "
        "outbound HTTPS goes through the GWDG WWW-Cache. Mirrors what "
        "the broker plumbs via APPTAINERENV_HTTPS_PROXY.",
    )


@lru_cache
def get_settings() -> OpenHandsSettings:
    return OpenHandsSettings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
