"""HTTP tests for ``get_skills`` (Task 4.4)."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

import mcp_server.config as cfg
from mcp_server.main import create_app
from mcp_server.skills.loader import reset_skill_cache

REPO_SKILLS = Path(__file__).resolve().parents[1] / "skills"


@pytest.fixture
def skills_client(tmp_path) -> Iterator[TestClient]:
    reset_skill_cache()
    settings = cfg.MCPSettings(
        fs_read_roots=[str(tmp_path)],
        fs_write_roots=[str(tmp_path)],
        web_search_provider="stub",
        skills_dir=str(REPO_SKILLS),
        agent_framework="openhands",
    )
    original = cfg.get_settings
    cfg.get_settings = lambda: settings  # type: ignore[assignment]
    try:
        with TestClient(create_app(settings)) as client:
            yield client
    finally:
        cfg.get_settings = original
        reset_skill_cache()


def test_health_reports_skill_count(skills_client: TestClient):
    r = skills_client.get("/health")
    assert r.status_code == 200
    assert r.json()["skill_count"] >= 4


def test_get_skills_grete_snippet(skills_client: TestClient):
    r = skills_client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "call_tool",
            "params": {
                "name": "get_skills",
                "arguments": {"framework": "openhands"},
            },
        },
    )
    body = r.json()
    assert "result" in body, body
    md_blob = "\n".join(s["markdown"] for s in body["result"]["skills"])
    assert "grete" in md_blob.lower()
