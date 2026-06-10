"""Tests for sandbox exec and exec_stream."""

import base64
import json

import httpx
import pytest

from neevai.runtime.sandboxd import AsyncSandboxConnection, SandboxConnection
from neevai.errors import APIConnectionError, APITimeoutError, NeevAIError, NotFoundError, PermissionDeniedError
from neevai.transport.runtime import AsyncDataplaneTransport, DataplaneTransport


def _ndjson_lines(frames: list[dict]) -> bytes:
    return "\n".join(json.dumps(frame) for frame in frames).encode()


class ExecStreamMockTransport(httpx.MockTransport):
    def __init__(self, frames: list[dict]):
        self.frames = frames
        super().__init__(self.handler)

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/v1/exec"):
            return httpx.Response(200, content=_ndjson_lines(self.frames))
        return httpx.Response(404, json={"reason_code": "not_found", "message": "missing"})


def test_exec_drains_ndjson_stream():
    frames = [
        {"type": "stdout", "data": base64.b64encode(b"hello ").decode()},
        {"type": "stderr", "data": base64.b64encode(b"warn").decode()},
        {"type": "stdout", "data": base64.b64encode(b"world").decode()},
        {"type": "exit", "exit_code": 0},
    ]
    conn = SandboxConnection(
        connect_url="https://sbx.example.com",
        api_key="test",
        timeout_ms=5000,
        client=httpx.Client(transport=ExecStreamMockTransport(frames)),
    )
    result = conn.exec("echo", args=["hi"])
    assert result.stdout == "hello world"
    assert result.stderr == "warn"
    assert result.exit_code == 0
    conn.close()


def test_exec_stream_yields_incremental_events():
    frames = [
        {"type": "stdout", "data": base64.b64encode(b"hello ").decode()},
        {"type": "stdout", "data": base64.b64encode(b"world").decode()},
        {"type": "stderr", "data": base64.b64encode(b"warn").decode()},
        {"type": "exit", "exit_code": 0},
    ]
    conn = SandboxConnection(
        connect_url="https://sbx.example.com",
        api_key="test",
        timeout_ms=5000,
        client=httpx.Client(transport=ExecStreamMockTransport(frames)),
    )
    events = list(conn.exec_stream("echo", args=["hi"]))
    assert events == [
        {"type": "stdout", "data": "hello "},
        {"type": "stdout", "data": "world"},
        {"type": "stderr", "data": "warn"},
        {"type": "exit", "exit_code": 0},
    ]
    conn.close()


def test_exec_stream_decodes_multibyte_char_split_across_frames():
    frames = [
        {"type": "stdout", "data": base64.b64encode(bytes([0xC3])).decode()},
        {"type": "stdout", "data": base64.b64encode(bytes([0xA9])).decode()},
        {"type": "exit", "exit_code": 0},
    ]
    conn = SandboxConnection(
        connect_url="https://sbx.example.com",
        api_key="test",
        timeout_ms=5000,
        client=httpx.Client(transport=ExecStreamMockTransport(frames)),
    )
    stdout = "".join(e["data"] for e in conn.exec_stream("printf") if e["type"] == "stdout")
    assert stdout == "é"
    conn.close()


def test_exec_stream_raises_on_error_frame():
    frames = [{"type": "error", "reason_code": "permission_denied", "message": "denied"}]
    conn = SandboxConnection(
        connect_url="https://sbx.example.com",
        api_key="test",
        timeout_ms=5000,
        client=httpx.Client(transport=ExecStreamMockTransport(frames)),
    )
    with pytest.raises(PermissionDeniedError):
        list(conn.exec_stream("whoami"))
    conn.close()


def test_exec_stream_raises_when_no_exit_frame():
    frames = [{"type": "stdout", "data": base64.b64encode(b"partial").decode()}]
    conn = SandboxConnection(
        connect_url="https://sbx.example.com",
        api_key="test",
        timeout_ms=5000,
        client=httpx.Client(transport=ExecStreamMockTransport(frames)),
    )
    with pytest.raises(NeevAIError, match="exit status"):
        list(conn.exec_stream("sleep"))
    conn.close()


def test_exec_rejects_argv_and_args():
    conn = SandboxConnection(
        connect_url="https://sbx.example.com",
        api_key="test",
        timeout_ms=5000,
        client=httpx.Client(transport=ExecStreamMockTransport([])),
    )
    with pytest.raises(NeevAIError):
        conn.exec(["git", "status"], args=["-s"])
    conn.close()


@pytest.mark.asyncio
async def test_async_exec_stream_yields_events():
    frames = [
        {"type": "stdout", "data": base64.b64encode(b"ok").decode()},
        {"type": "exit", "exit_code": 0},
    ]
    conn = AsyncSandboxConnection(
        connect_url="https://sbx.example.com",
        api_key="test",
        timeout_ms=5000,
        client=httpx.AsyncClient(transport=ExecStreamMockTransport(frames)),
    )
    events = [event async for event in conn.exec_stream("true")]
    assert events[-1] == {"type": "exit", "exit_code": 0}
    await conn.aclose()


def test_dataplane_transport_sanity(dataplane_transport):
    transport = DataplaneTransport(
        connect_url="https://sbx.example.com",
        api_key="test",
        timeout_ms=5000,
        client=dataplane_transport,
    )
    resp = transport.request("POST", "/v1/exec")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"

    with pytest.raises(NotFoundError):
        transport.request("GET", "/v1/nonexistent")


def test_dataplane_transport_timeout():
    class TimeoutMock(httpx.MockTransport):
        def __init__(self):
            super().__init__(self.handler)

        def handler(self, request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("timeout", request=request)

    transport = DataplaneTransport(
        connect_url="https://sbx.example.com",
        api_key="test",
        timeout_ms=100,
        client=httpx.Client(transport=TimeoutMock()),
    )
    with pytest.raises(APITimeoutError):
        transport.request("GET", "/v1/exec")


def test_sandbox_connection_init():
    conn = SandboxConnection(
        connect_url="https://sbx.example.com",
        api_key="test",
        timeout_ms=5000,
    )
    assert conn._transport is not None
    assert conn.files is not None
    conn.close()
