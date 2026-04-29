"""Environment for opencode_runtime (``OPENCODE_*`` prefix)."""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urljoin

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OpenCodeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPENCODE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: str = Field(default="INFO")
    session_id: str = Field(default="dev-session")
    user_id: str = Field(default="")

    mcp_server_url: str = Field(default="http://localhost:8080")
    mcp_health_timeout_s: float = Field(default=20.0, gt=0)
    mcp_health_poll_interval_s: float = Field(default=0.5, gt=0)
    mcp_uvicorn_port: int = Field(default=8080, ge=1, le=65535)

    broker_sse_url: str = Field(
        default="",
        description="Broker URL for SSE ingest; empty disables forwarding.",
    )
    sse_post_timeout_s: float = Field(default=5.0, gt=0)
    sse_max_inflight: int = Field(default=32, ge=1)

    opencode_max_runtime_s: float = Field(default=30 * 60, gt=0)
    session_prompt: str = Field(
        default="Respond with exactly: pong",
        description="Passed to `opencode run …` after MCP is reachable.",
    )
    home_dir: str = Field(
        default="/workspace",
        description="HOME and parent of ~/.config/opencode (bind-mount).",
    )

    opencode_bin: str = Field(default="opencode")
    opencode_model: str = Field(
        default="openai/qwen-placeholder",
        description="OpenCode `provider/model`; broker should override.",
    )
    opencode_run_extra: str = Field(
        default="",
        description="Argv fragment between `run`/`--model` and the prompt.",
    )

    #: If non-empty: shell argv replaces `opencode …` entirely (tests: `/bin/true`).
    dev_command_override: str = Field(default="")


def mcp_rpc_url(settings: OpenCodeSettings) -> str:
    """Full JSON-RPC endpoint (``…/rpc``) for MCP HTTP inside the container."""
    base = settings.mcp_server_url.rstrip("/") + "/"
    return urljoin(base, "rpc")


@lru_cache
def get_settings() -> OpenCodeSettings:
    return OpenCodeSettings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
