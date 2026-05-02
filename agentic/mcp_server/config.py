"""Runtime configuration for the MCP server.

Environment-first (``MCP_SERVER_*`` prefix) so the same image runs in
local dev, in pytest, and inside the Apptainer container with no code
changes. Where the broker uses ``AGENTIC_*``, this server uses
``MCP_SERVER_*`` to keep the two namespaces independent.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MCP_SERVER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "agentic-mcp-server"
    log_level: str = Field(default="INFO")

    host: str = "0.0.0.0"
    port: int = 8080

    # --- File system tool boundaries ---------------------------------------
    fs_read_roots: List[str] = Field(
        default_factory=lambda: ["/workspace", "/home/user"],
        description="Roots the read tools may traverse. Anything outside "
        "is rejected with `path_not_allowed`.",
    )
    fs_write_roots: List[str] = Field(
        default_factory=lambda: ["/workspace"],
        description="Subset of `fs_read_roots` where writes are permitted. "
        "User home is read-only by default.",
    )
    fs_max_read_bytes: int = Field(
        default=10 * 1024 * 1024,
        ge=1,
        description="Hard ceiling on a single fs_read response (acceptance: 10 MB).",
    )
    fs_max_write_bytes: int = Field(
        default=1 * 1024 * 1024,
        ge=1,
        description="Hard ceiling on a single fs_write payload (acceptance: 1 MB).",
    )
    fs_max_list_entries: int = Field(
        default=2_000,
        ge=1,
        description="Cap on entries returned by fs_list. Prevents accidental "
        "denial-of-service from listing huge directories.",
    )

    # --- Web tool boundaries -----------------------------------------------
    web_proxy_url: str = Field(
        default="",
        description="Proxy URL for outbound HTTP(S). Empty means use the "
        "process environment (HTTPS_PROXY etc.). The broker plumbs this "
        "via APPTAINERENV_HTTPS_PROXY at session start.",
    )
    web_request_timeout_s: float = Field(default=30.0, gt=0)
    web_max_response_bytes: int = Field(
        default=5 * 1024 * 1024,
        ge=1,
        description="Cap on web_browse response body. Larger responses are "
        "truncated and a `response_too_large` error is returned.",
    )
    web_search_provider: str = Field(
        default="duckduckgo",
        description="`duckduckgo` uses DuckDuckGo (no API key required). "
        "`stub` returns deterministic placeholder results (useful for tests). "
        "`serpapi` calls SerpApi with web_search_api_key.",
    )
    web_search_endpoint: str = Field(
        default="https://serpapi.com/search.json",
        description="Endpoint for the configured search provider.",
    )
    web_search_api_key: str = Field(
        default="",
        description="API key for the search provider. Plumbed in from "
        "Vault by the broker; never logged.",
    )
    web_blocked_host_suffixes: List[str] = Field(
        default_factory=lambda: [
            "internal.gwdg.de",
            ".internal",
            ".local",
            ".corp",
        ],
        description="Hostname patterns blocked by web_browse / web_search "
        "(Task 2.5). A leading '.' means suffix match; otherwise exact host "
        "or subdomain of that label.",
    )

    # --- Code tool boundaries ----------------------------------------------
    code_python_bin: str = Field(
        default="python3.11",
        description="Interpreter for code_exec / code_check.",
    )
    code_exec_default_timeout_s: float = Field(default=10.0, gt=0)
    code_exec_max_timeout_s: float = Field(
        default=30.0,
        gt=0,
        description="Acceptance criterion: tool times out at 30 s. Caller "
        "may request smaller; this is the upper bound.",
    )
    code_exec_max_output_bytes: int = Field(
        default=64 * 1024,
        ge=1024,
        description="Per-stream (stdout, stderr) cap. Excess is truncated "
        "and a marker is appended so the agent knows.",
    )

    @field_validator(
        "fs_read_roots",
        "fs_write_roots",
        "web_blocked_host_suffixes",
        mode="before",
    )
    @classmethod
    def _split_csv(cls, v):
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v


@lru_cache
def get_settings() -> MCPSettings:
    return MCPSettings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
