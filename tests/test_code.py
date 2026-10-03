"""Tests for the sandbox code interpreter."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from neevai.errors import (
    APITimeoutError,
    NeevAIError,
    PreconditionFailedError,
    ServiceUnavailableError,
)
from neevai.runtime.connection import AsyncSandboxConnection, SandboxConnection
from neevai.types import CodeResult, OutputMessage

CONNECT_URL = "https://sbx.example.com"

RUN_EVENTS: list[dict[str, Any]] = [
    {"type": "stream", "name": "stdout", "text": "4"},
    {"type": "keepalive"},
    {"type": "stream", "name": "stdout", "text": "2\n"},
    {"type": "stream", "name": "stderr", "text": "warn\n"},
    {"type": "result", "data": {"text/plain": "84"}, "is_main": True},
    {"type": "error", "name": "ValueError", "value": "bad", "traceback": ["tb"]},
    {"type": "end", "reason": "error", "generation": "g1", "execution_count": 3},
]


def _ndjson(events: list[dict[str, Any]]) -> httpx.Response:
    return httpx.Response(200, content="\n".join(json.dumps(e) for e in events).encode())


class Recorder:
    """Answers each request with handle and records what was sent."""

    def __init__(self, handle: Callable[[str], httpx.Response]):
        self.handle = handle
        self.sent: list[tuple[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Prefer") == "wait=0"
        self.sent.append((request.url.path, json.loads(request.content)))
        return self.handle(request.url.path)


def _sync(handle: Callable[[str], httpx.Response]) -> tuple[SandboxConnection, Recorder]:
    rec = Recorder(handle)
    client = httpx.Client(transport=httpx.MockTransport(rec))
    return SandboxConnection(CONNECT_URL, "k", 5000, client=client), rec


def _async(handle: Callable[[str], httpx.Response]) -> tuple[AsyncSandboxConnection, Recorder]:
    rec = Recorder(handle)
    client = httpx.AsyncClient(transport=httpx.MockTransport(rec))
    return AsyncSandboxConnection(CONNECT_URL, "k", 5000, client=client), rec


def test_run_collects_and_calls_back() -> None:
    conn, rec = _sync(lambda _: _ndjson(RUN_EVENTS))
    seen: list[OutputMessage] = []
    results: list[CodeResult] = []
    run = conn.code.run(
        "print(42)",
        context="ctx-1",
        timeout_ms=5000,
        envs={"MODE": "test"},
        on_stdout=seen.append,
        on_result=results.append,
    )

    assert run.stdout == "42\n"
    assert run.stderr == "warn\n"
    assert run.results == [CodeResult(data={"text/plain": "84"}, is_main=True)]
    assert run.error is not None and run.error.name == "ValueError"
    assert (run.end_reason, run.generation, run.truncated) == ("error", "g1", False)
    assert [(m.line, m.error) for m in seen] == [("4", False), ("2\n", False)]
    assert run.logs.stdout == ["4", "2\n"] and run.logs.stderr == ["warn\n"]
    assert (run.text, run.execution_count) == ("84", 3)
    assert len(results) == 1
    assert rec.sent == [
        (
            "/v1/interpreter/run",
            {
                "code": "print(42)",
                "context_id": "ctx-1",
                "timeout_ms": 5000,
                "envs": {"MODE": "test"},
            },
        )
    ]


def test_run_refusal_raises_with_reason() -> None:
    conn, _ = _sync(
        lambda _: httpx.Response(
            412,
            json={
                "reason_code": "failed_precondition",
                "reason": "context_busy",
                "message": "the context is running a cell or starting; retry when it is idle",
            },
        )
    )
    with pytest.raises(PreconditionFailedError) as err:
        conn.code.run("1")
    assert err.value.reason == "context_busy"


def test_run_without_end_raises() -> None:
    conn, _ = _sync(lambda _: _ndjson([{"type": "stream", "name": "stdout", "text": "a"}]))
    with pytest.raises(NeevAIError):
        conn.code.run("1")


def _contexts_answer(path: str) -> httpx.Response:
    op = path.rsplit("/", 1)[-1]
    return httpx.Response(
        200,
        json={
            "create": {
                "context_id": "ctx-1",
                "generation": "g1",
                "language": "python",
                "cwd": "/w/p",
            },
            "list": {
                "contexts": [
                    {"context_id": "default", "state": "busy", "generation": "g0", "rss_mib": 120}
                ]
            },
            "restart": {"generation": "g2"},
            "delete": {},
        }[op],
    )


def test_contexts() -> None:
    conn, rec = _sync(_contexts_answer)

    created = conn.code.create_context(cwd="p")
    assert (created.context_id, created.language, created.cwd) == ("ctx-1", "python", "/w/p")
    listed = conn.code.list_contexts()
    assert [(c.context_id, c.state, c.rss_mib) for c in listed] == [("default", "busy", 120)]
    assert conn.code.restart_context("default") == "g2"
    conn.code.delete_context(created)

    assert rec.sent == [
        ("/v1/interpreter/contexts/create", {"cwd": "p"}),
        ("/v1/interpreter/contexts/list", {}),
        ("/v1/interpreter/contexts/restart", {"context_id": "default"}),
        ("/v1/interpreter/contexts/delete", {"context_id": "ctx-1"}),
    ]


async def test_async_run_and_contexts() -> None:
    conn, _ = _async(lambda _: _ndjson(RUN_EVENTS))
    run = await conn.code.run("print(42)")
    assert (run.stdout, run.end_reason) == ("42\n", "error")

    conn, rec = _async(_contexts_answer)
    assert (await conn.code.create_context(language="python")).context_id == "ctx-1"
    assert len(await conn.code.list_contexts()) == 1
    assert await conn.code.restart_context("default") == "g2"
    await conn.code.delete_context("ctx-1")
    assert rec.sent[0] == ("/v1/interpreter/contexts/create", {"language": "python"})


def test_result_accessors() -> None:
    r = CodeResult(
        data={"text/plain": "<Figure>", "image/png": "iVBOR", "application/json": {"a": 1}},
        is_main=True,
    )
    assert r.formats() == ["text/plain", "image/png", "application/json"]
    assert (r.text, r.png, r.html) == ("<Figure>", "iVBOR", None)
    assert r.json == {"a": 1}


def test_language_checks_refuse_before_any_request() -> None:
    conn, rec = _sync(lambda _: _ndjson(RUN_EVENTS))
    with pytest.raises(NeevAIError):
        conn.code.run("1", language="r")
    with pytest.raises(NeevAIError):
        conn.code.run("1", language="python", context="c")
    assert rec.sent == []


def _waking() -> httpx.Response:
    return httpx.Response(
        503,
        headers={"Retry-After": "2"},
        json={
            "reason_code": "unavailable",
            "reason": "sandbox_waking",
            "message": "the sandbox is waking; retry shortly",
        },
    )


def _answers(*responses: httpx.Response) -> Callable[[str], httpx.Response]:
    queue = list(responses)
    return lambda _: queue.pop(0)


@pytest.fixture
def fast_wake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("neevai.runtime.code._WAKE_RETRY_S", 0.01)


@pytest.mark.usefixtures("fast_wake")
def test_waking_sandbox_is_retried() -> None:
    end = [{"type": "end", "reason": "ok", "generation": "g1"}]
    conn, rec = _sync(_answers(_waking(), _waking(), _ndjson(end)))
    assert conn.code.run("1").end_reason == "ok"
    assert len(rec.sent) == 3

    conn, rec = _sync(_answers(_waking(), _contexts_answer("/v1/interpreter/contexts/create")))
    assert conn.code.create_context().context_id == "ctx-1"
    assert len(rec.sent) == 2


@pytest.mark.usefixtures("fast_wake")
async def test_async_waking_sandbox_is_retried() -> None:
    end = [{"type": "end", "reason": "ok", "generation": "g1"}]
    conn, rec = _async(_answers(_waking(), _ndjson(end)))
    assert (await conn.code.run("1")).end_reason == "ok"
    assert len(rec.sent) == 2

    conn, rec = _async(_answers(_waking(), _contexts_answer("/v1/interpreter/contexts/list")))
    assert len(await conn.code.list_contexts()) == 1
    assert len(rec.sent) == 2


def test_waking_ends_at_the_request_timeout() -> None:
    conn, rec = _sync(lambda _: _waking())
    with pytest.raises(APITimeoutError):
        conn.code.run("1", request_timeout_ms=200)
    assert len(rec.sent) == 1


def test_other_unavailable_is_not_retried() -> None:
    conn, rec = _sync(
        lambda _: httpx.Response(503, json={"reason_code": "unavailable", "message": "starting"})
    )
    with pytest.raises(ServiceUnavailableError):
        conn.code.run("1")
    assert len(rec.sent) == 1
