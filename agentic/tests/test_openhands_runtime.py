"""Tests for the OpenHands orchestration layer (Task 2.3).

Three targets:

1. ``translate_openhands_line`` — pure function, full coverage of
   each branch and the unknown-shape fall-through.
2. ``forward_stream`` — async tee from a stream into the broker's
   POST endpoint. Network is mocked at the httpx layer; the broker
   never has to be running.
3. ``wait_for_health`` + env / argv builders — small launcher
   helpers. ``wait_for_health`` is exercised against a mock
   transport that flips from 503 to 200 mid-run.

Subprocess-spawning code paths (``_start_mcp_server``,
``_start_openhands``) are validated by the Apptainer smoke test, not
here — running real ``uvicorn`` from pytest would couple the test
suite to network ports and bleeding-edge timing.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator, List

import httpx
import pytest

import openhands_runtime.config as cfg
from openhands_runtime import launcher, sse_forwarder


# --------------------------------------------------------------------------- #
# translate_openhands_line                                                    #
# --------------------------------------------------------------------------- #

def test_translate_action_line():
    raw = json.dumps({"type": "action", "name": "fs_read", "id": "evt-1"})
    out = sse_forwarder.translate_openhands_line(raw)
    assert out == {
        "event": "action",
        "data": {"type": "action", "name": "fs_read", "id": "evt-1"},
        "id": "evt-1",
    }


@pytest.mark.parametrize(
    "openhands_type,expected",
    [
        ("action", "action"),
        ("observation", "result"),
        ("result", "result"),
        ("tool_result", "result"),
        ("message", "message"),
        ("agent_message", "message"),
        ("error", "error"),
        ("exception", "error"),
        # Unknown shape falls through to message — not dropped.
        ("WhateverNewThing", "message"),
    ],
)
def test_translate_type_mapping(openhands_type: str, expected: str):
    raw = json.dumps({"type": openhands_type})
    out = sse_forwarder.translate_openhands_line(raw)
    assert out is not None
    assert out["event"] == expected


def test_translate_non_json_line_becomes_message():
    out = sse_forwarder.translate_openhands_line("hello plain text\n")
    assert out == {
        "event": "message",
        "data": {"text": "hello plain text"},
        "id": None,
    }


def test_translate_json_array_becomes_message():
    """The protocol is line-of-objects; arrays go through as-is."""
    out = sse_forwarder.translate_openhands_line("[1, 2, 3]")
    assert out is not None
    assert out["event"] == "message"
    assert out["data"]["text"] == "[1, 2, 3]"


def test_translate_blank_line_returns_none():
    assert sse_forwarder.translate_openhands_line("") is None
    assert sse_forwarder.translate_openhands_line("   \r\n") is None


def test_translate_object_without_type_becomes_message():
    out = sse_forwarder.translate_openhands_line('{"foo": "bar"}')
    assert out is not None
    assert out["event"] == "message"
    assert out["data"] == {"foo": "bar"}


# --------------------------------------------------------------------------- #
# forward_stream                                                              #
# --------------------------------------------------------------------------- #

async def _alines(items: List[str]) -> AsyncIterator[str]:
    for item in items:
        yield item


async def test_forward_stream_happy_path():
    posted: List[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        posted.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"delivered_to": 1, "queued": True})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        stats = await sse_forwarder.forward_stream(
            lines=_alines([
                json.dumps({"type": "action", "name": "fs_read"}),
                json.dumps({"type": "observation", "output": "ok"}),
                "raw plain line\n",
            ]),
            broker_sse_url="http://broker.test",
            session_id="sess-001",
            user_id="alice@gwdg",
            http_client=client,
        )
    finally:
        await client.aclose()

    assert stats.forwarded == 3
    assert stats.dropped_post_failed == 0
    assert stats.dropped_overflow == 0
    assert stats.raw_lines == 3
    events = [p["event"] for p in posted]
    assert events == ["action", "result", "message"]


async def test_forward_stream_post_failure_counted_not_raised():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream down")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        stats = await sse_forwarder.forward_stream(
            lines=_alines([json.dumps({"type": "action"})]),
            broker_sse_url="http://broker.test",
            session_id="sess-002",
            http_client=client,
        )
    finally:
        await client.aclose()

    assert stats.forwarded == 0
    assert stats.dropped_post_failed == 1


async def test_forward_stream_no_broker_short_circuits():
    """Empty broker_sse_url ⇒ tee that just counts lines."""
    stats = await sse_forwarder.forward_stream(
        lines=_alines([json.dumps({"type": "action"}), "x", "y"]),
        broker_sse_url="",
        session_id="sess-003",
    )
    assert stats.raw_lines == 3
    assert stats.forwarded == 0
    assert stats.dropped_post_failed == 0


async def test_forward_stream_xuser_header_present():
    seen_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.update(request.headers)
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        await sse_forwarder.forward_stream(
            lines=_alines([json.dumps({"type": "action"})]),
            broker_sse_url="http://broker.test",
            session_id="sess-x",
            user_id="alice@gwdg",
            http_client=client,
        )
    finally:
        await client.aclose()

    assert seen_headers.get("x-user") == "alice@gwdg"


async def test_forward_stream_no_xuser_when_user_id_blank():
    seen_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.update(request.headers)
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        await sse_forwarder.forward_stream(
            lines=_alines([json.dumps({"type": "action"})]),
            broker_sse_url="http://broker.test",
            session_id="sess-x",
            user_id="",
            http_client=client,
        )
    finally:
        await client.aclose()

    assert "x-user" not in seen_headers


# --------------------------------------------------------------------------- #
# wait_for_health                                                             #
# --------------------------------------------------------------------------- #

async def test_wait_for_health_succeeds_after_first_attempt():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "healthy"})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        ok = await launcher.wait_for_health(
            "http://mcp.test/health",
            timeout_s=1.0,
            interval_s=0.05,
            http_client=client,
        )
    finally:
        await client.aclose()
    assert ok is True


async def test_wait_for_health_succeeds_after_warmup():
    counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        if counter["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"status": "healthy"})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        ok = await launcher.wait_for_health(
            "http://mcp.test/health",
            timeout_s=2.0,
            interval_s=0.05,
            http_client=client,
        )
    finally:
        await client.aclose()
    assert ok is True
    assert counter["n"] >= 3


async def test_wait_for_health_times_out():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        ok = await launcher.wait_for_health(
            "http://mcp.test/health",
            timeout_s=0.2,
            interval_s=0.05,
            http_client=client,
        )
    finally:
        await client.aclose()
    assert ok is False


async def test_wait_for_health_swallows_connection_errors():
    """Pre-bound connection refused is the normal case during warmup."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    try:
        ok = await launcher.wait_for_health(
            "http://mcp.test/health",
            timeout_s=0.2,
            interval_s=0.05,
            http_client=client,
        )
    finally:
        await client.aclose()
    assert ok is False  # And critically: did not raise.


# --------------------------------------------------------------------------- #
# env / argv builders                                                         #
# --------------------------------------------------------------------------- #

def test_build_openhands_env_overlays_correct_keys():
    settings = cfg.OpenHandsSettings(
        session_id="sess-42",
        mcp_server_url="http://localhost:9000",
        llm_api_url="http://vllm.test/v1/completions",
        llm_model="qwen3-30b",
        llm_parser="hermes",
        openhands_workspace="/scratch/work",
    )
    env = launcher.build_openhands_env(settings, base_env={"PATH": "/usr/bin"})
    assert env["MCP_SERVER_URL"] == "http://localhost:9000"
    assert env["LLM_API_URL"] == "http://vllm.test/v1/completions"
    assert env["LLM_MODEL"] == "qwen3-30b"
    assert env["LLM_PARSER"] == "hermes"
    assert env["OPENHANDS_SESSION_ID"] == "sess-42"
    assert env["OPENHANDS_WORKSPACE"] == "/scratch/work"
    assert env["PYTHONUNBUFFERED"] == "1"
    assert env["PATH"] == "/usr/bin"


def test_build_openhands_env_propagates_proxy_when_set():
    settings = cfg.OpenHandsSettings(
        https_proxy="http://www-cache.gwdg.de:3128",
    )
    env = launcher.build_openhands_env(settings, base_env={})
    assert env["HTTP_PROXY"] == "http://www-cache.gwdg.de:3128"
    assert env["HTTPS_PROXY"] == "http://www-cache.gwdg.de:3128"
    assert env["NO_PROXY"] == "localhost,127.0.0.1"


def test_build_openhands_env_skips_proxy_when_unset():
    settings = cfg.OpenHandsSettings(https_proxy=None)
    env = launcher.build_openhands_env(settings, base_env={})
    assert "HTTP_PROXY" not in env
    assert "HTTPS_PROXY" not in env


def test_build_openhands_argv_default():
    settings = cfg.OpenHandsSettings()
    argv = launcher.build_openhands_argv(settings)
    assert argv[0] == "openhands"
    assert "--config" in argv
    assert argv[argv.index("--config") + 1] == "/etc/openhands/config.toml"


def test_build_openhands_argv_extra_args_split():
    settings = cfg.OpenHandsSettings(
        openhands_extra_args="--verbose --task 'analyse the code'",
    )
    argv = launcher.build_openhands_argv(settings)
    assert "--verbose" in argv
    # shlex preserves the quoted token as a single argv entry.
    assert "analyse the code" in argv


# --------------------------------------------------------------------------- #
# config                                                                      #
# --------------------------------------------------------------------------- #

def test_settings_defaults_are_safe_for_dev():
    s = cfg.OpenHandsSettings()
    assert s.mcp_server_url == "http://localhost:8080"
    assert s.broker_sse_url == ""           # disabled by default
    assert s.openhands_max_runtime_s > 0
    assert s.mcp_health_timeout_s > s.mcp_health_poll_interval_s


def test_settings_get_settings_is_cached():
    cfg.reset_settings_cache()
    a = cfg.get_settings()
    b = cfg.get_settings()
    assert a is b
