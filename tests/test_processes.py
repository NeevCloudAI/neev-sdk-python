"""Tests for sandbox process supervisor APIs."""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
import pytest

from neevai.errors import NeevAIError, NotFoundError
from neevai.runtime.sandboxd import AsyncSandboxConnection, SandboxConnection
from neevai.types import Signal

CONNECT_URL = "https://sbx.example.com"
API_KEY = "test-key"
PROCESS_ID = "proc-abc123"
STARTED_AT = 1_700_000_000_000


def _status_payload(
    *,
    state: str = "running",
    exit_code: int | None = None,
    process_id: str = PROCESS_ID,
) -> dict[str, Any]:
    return {
        "process_id": process_id,
        "state": state,
        "exit_code": exit_code,
        "started_at": STARTED_AT,
    }


def _info_payload(**kwargs: Any) -> dict[str, Any]:
    return {
        **_status_payload(**kwargs),
        "name": "sleep",
        "args": ["10"],
        "cwd": "/workspace",
    }


def _ndjson_lines(frames: list[dict[str, Any]]) -> bytes:
    return "\n".join(json.dumps(frame) for frame in frames).encode()


class ProcessMockTransport(httpx.MockTransport):
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        super().__init__(self.handler)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        body = json.loads(request.content) if request.content else {}

        if path.endswith("/v1/processes/start"):
            if body.get("cwd") == "/workspace":
                assert body["program"] == "sleep"
                assert body["args"] == ["10"]
                assert body["env"] == ["FOO=bar"]
                assert body["stdin"] == "input"
            return httpx.Response(200, json=_info_payload())

        if path.endswith("/v1/processes/get"):
            if body.get("wait"):
                return httpx.Response(200, json=_status_payload(state="exited", exit_code=0))
            if body["process_id"] == "missing":
                return httpx.Response(
                    404,
                    json={"reason_code": "not_found", "message": "process not found"},
                )
            return httpx.Response(200, json=_status_payload())

        if path.endswith("/v1/processes/list"):
            return httpx.Response(
                200,
                json={
                    "processes": [
                        _info_payload(),
                        {
                            **_status_payload(process_id="proc-other"),
                            "name": "echo",
                            "args": ["hi"],
                            "cwd": None,
                        },
                    ]
                },
            )

        if path.endswith("/v1/processes/kill"):
            assert body["process_id"] == PROCESS_ID
            if "signal" in body:
                assert body["signal"] in (Signal.KILL, Signal.TERM)
            return httpx.Response(200, json={"signalled": True})

        if path.endswith("/v1/processes/kill-all"):
            if "signal" in body:
                assert body["signal"] in (Signal.INT, Signal.TERM)
            return httpx.Response(200, json={"signalled_count": 2})

        if path.endswith("/v1/processes/logs"):
            if body.get("follow"):
                frames = [
                    {"type": "stdout", "data": base64.b64encode(b"hello ").decode()},
                    {"type": "stdout", "data": base64.b64encode(b"world").decode()},
                    {"type": "exit", "exit_code": 0},
                ]
                return httpx.Response(200, content=_ndjson_lines(frames))
            return httpx.Response(
                200,
                json={
                    "entries": [
                        {"stream": "stdout", "data": "line one\n"},
                        {"stream": "stderr", "data": "line two\n"},
                    ],
                    "cursor": 42,
                    "dropped": True,
                    "state": "running",
                },
            )

        return httpx.Response(404, json={"reason_code": "not_found", "message": "missing"})


@pytest.fixture
def sync_conn() -> SandboxConnection:
    transport = ProcessMockTransport()
    conn = SandboxConnection(
        connect_url=CONNECT_URL,
        api_key=API_KEY,
        timeout_ms=5000,
        client=httpx.Client(transport=transport),
    )
    conn._mock = transport  # type: ignore[attr-defined]
    return conn


@pytest.fixture
def async_conn() -> AsyncSandboxConnection:
    transport = ProcessMockTransport()
    conn = AsyncSandboxConnection(
        connect_url=CONNECT_URL,
        api_key=API_KEY,
        timeout_ms=5000,
        client=httpx.AsyncClient(transport=transport),
    )
    conn._mock = transport  # type: ignore[attr-defined]
    return conn


def test_start_wire_body_and_argv_array(sync_conn: SandboxConnection):
    proc = sync_conn.processes.start(
        ["sleep", "10"],
        cwd="/workspace",
        env={"FOO": "bar"},
        stdin="input",
    )
    assert proc.id == PROCESS_ID
    assert proc.state == "running"
    assert proc.started_at == STARTED_AT
    sync_conn.close()


def test_start_rejects_argv_and_args(sync_conn: SandboxConnection):
    with pytest.raises(NeevAIError, match="not both"):
        sync_conn.processes.start(["sleep", "10"], args=["extra"])
    sync_conn.close()


def test_start_rejects_empty_program(sync_conn: SandboxConnection):
    with pytest.raises(NeevAIError, match="must not be empty"):
        sync_conn.processes.start("")
    sync_conn.close()


def test_get_and_wait(sync_conn: SandboxConnection):
    status = sync_conn.processes.get(PROCESS_ID)
    assert status.process_id == PROCESS_ID
    assert status.state == "running"

    exited = sync_conn.processes.get(PROCESS_ID, wait=True)
    assert exited.state == "exited"
    assert exited.exit_code == 0
    sync_conn.close()


def test_get_not_found(sync_conn: SandboxConnection):
    with pytest.raises(NotFoundError):
        sync_conn.processes.get("missing")
    sync_conn.close()


def test_process_handle_status_and_wait(sync_conn: SandboxConnection):
    proc = sync_conn.processes.start("sleep", args=["1"])
    refreshed = proc.status()
    assert refreshed.state == "running"

    final = proc.wait()
    assert final.state == "exited"
    assert proc.state == "exited"
    sync_conn.close()


def test_list_processes(sync_conn: SandboxConnection):
    processes = sync_conn.processes.list()
    assert len(processes) == 2
    assert processes[0].name == "sleep"
    assert processes[0].args == ["10"]
    assert processes[1].process_id == "proc-other"
    sync_conn.close()


def test_kill_default_signal_omitted(sync_conn: SandboxConnection):
    signalled = sync_conn.processes.kill(PROCESS_ID)
    assert signalled is True
    kill_body = json.loads(sync_conn._mock.requests[-1].content)  # type: ignore[attr-defined]
    assert "signal" not in kill_body
    sync_conn.close()


def test_kill_explicit_signal(sync_conn: SandboxConnection):
    signalled = sync_conn.processes.kill(PROCESS_ID, signal=Signal.KILL)
    assert signalled is True
    kill_body = json.loads(sync_conn._mock.requests[-1].content)  # type: ignore[attr-defined]
    assert kill_body["signal"] == Signal.KILL
    sync_conn.close()


def test_kill_explicit_term_sends_signal(sync_conn: SandboxConnection):
    signalled = sync_conn.processes.kill(PROCESS_ID, signal=Signal.TERM)
    assert signalled is True
    kill_body = json.loads(sync_conn._mock.requests[-1].content)  # type: ignore[attr-defined]
    assert kill_body["signal"] == Signal.TERM
    sync_conn.close()


def test_kill_all_signalled_count(sync_conn: SandboxConnection):
    count = sync_conn.processes.kill_all(signal=Signal.INT)
    assert count == 2
    kill_all_body = json.loads(sync_conn._mock.requests[-1].content)  # type: ignore[attr-defined]
    assert kill_all_body["signal"] == Signal.INT
    sync_conn.close()


def test_kill_all_explicit_term_sends_signal(sync_conn: SandboxConnection):
    count = sync_conn.processes.kill_all(signal=Signal.TERM)
    assert count == 2
    kill_all_body = json.loads(sync_conn._mock.requests[-1].content)  # type: ignore[attr-defined]
    assert kill_all_body["signal"] == Signal.TERM
    sync_conn.close()


def test_process_kill_delegates(sync_conn: SandboxConnection):
    proc = sync_conn.processes.start("sleep", args=["1"])
    assert proc.kill() is True
    sync_conn.close()


def test_logs_poll(sync_conn: SandboxConnection):
    page = sync_conn.processes.logs(PROCESS_ID, cursor=10)
    assert page.entries[0].stream == "stdout"
    assert page.entries[0].data == "line one\n"
    assert page.entries[1].stream == "stderr"
    assert page.cursor == 42
    assert page.dropped is True
    assert page.state == "running"
    sync_conn.close()


def test_follow_decodes_base64_and_exit(sync_conn: SandboxConnection):
    events = list(sync_conn.processes.follow(PROCESS_ID))
    assert events == [
        {"type": "stdout", "data": "hello "},
        {"type": "stdout", "data": "world"},
        {"type": "exit", "exit_code": 0},
    ]
    sync_conn.close()


def test_follow_no_throw_without_exit_frame():
    frames = [{"type": "stdout", "data": base64.b64encode(b"partial").decode()}]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_ndjson_lines(frames))

    conn = SandboxConnection(
        connect_url=CONNECT_URL,
        api_key=API_KEY,
        timeout_ms=5000,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    events = list(conn.processes.follow(PROCESS_ID))
    assert events == [{"type": "stdout", "data": "partial"}]
    conn.close()


def test_follow_multibyte_split_across_frames():
    frames = [
        {"type": "stdout", "data": base64.b64encode(bytes([0xC3])).decode()},
        {"type": "stdout", "data": base64.b64encode(bytes([0xA9])).decode()},
    ]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_ndjson_lines(frames))

    conn = SandboxConnection(
        connect_url=CONNECT_URL,
        api_key=API_KEY,
        timeout_ms=5000,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    stdout = "".join(e["data"] for e in conn.processes.follow(PROCESS_ID) if e["type"] == "stdout")
    assert stdout == "é"
    conn.close()


def test_sandbox_connection_processes_kill_all(sync_conn: SandboxConnection):
    count = sync_conn.processes.kill_all()
    assert count == 2
    sync_conn.close()


@pytest.mark.asyncio
async def test_async_start_and_follow(async_conn: AsyncSandboxConnection):
    proc = await async_conn.processes.start("sleep", args=["10"])
    assert proc.id == PROCESS_ID

    events = [event async for event in async_conn.processes.follow(PROCESS_ID)]
    assert events[-1] == {"type": "exit", "exit_code": 0}
    await async_conn.aclose()


@pytest.mark.asyncio
async def test_async_get_wait_and_kill(async_conn: AsyncSandboxConnection):
    status = await async_conn.processes.get(PROCESS_ID, wait=True)
    assert status.state == "exited"

    proc = await async_conn.processes.start("sleep", args=["1"])
    assert await proc.kill(signal=Signal.KILL) is True
    await async_conn.aclose()
