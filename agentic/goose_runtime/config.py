"""Environment for goose_runtime (``GOOSE_*`` prefix)."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GooseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GOOSE_",
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

    goose_max_runtime_s: float = Field(default=30 * 60, gt=0)
    session_prompt: str = Field(
        default="Summarize the workspace in one sentence.",
        description="Headless task text passed to `goose run -t`.",
    )
    session_prompt_file: str = Field(
        default="",
        description="Path to a file containing the prompt (overrides session_prompt when set).",
    )
    home_dir: str = Field(
        default="/workspace",
        description="writable HOME so ~/.config/goose can live on the bind-mount",
    )
    goose_config_subdir: str = Field(default=".goose-runtime")

    goose_cli: str = Field(default="goose")
    run_extra: str = Field(
        default="run --no-session",
        description="Argv fragment between goose binary and -t TEXT",
    )
    goose_mode: str = Field(default="auto")
    goose_context_strategy: str = Field(default="summarize")

    #: If non-empty: single argv string for ``shlex.split`` — bypasses Goose (tests use ``/bin/cat``).
    dev_command_override: str = Field(default="")

    llm_provider: str = Field(
        default="openai",
        description="Exported as GOOSE_PROVIDER (see Goose headless docs).",
    )
    llm_model: str = Field(
        default="",
        description="Exported as GOOSE_MODEL. If empty, Goose uses its own default for the provider.",
    )


@lru_cache
def get_settings() -> GooseSettings:
    return GooseSettings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
