"""Tests for sandbox exec and exec_stream."""

import base64
import json

import httpx
import pytest

from neevai.errors import (
    APITimeoutError,
    NeevAIError,
    NotFoundError,
    PermissionDeniedError,
)
from neevai.runtime.connection import AsyncSandboxConnection, SandboxConnection
from neevai.transport.runtime import SANDBOX_ID_HEADER, RuntimeTransport


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


def test_runtime_transport_sends_x_sandbox_id_header():
    captured: dict[str, str] = {}

    class HeaderCaptureTransport(httpx.MockTransport):
        def __init__(self):
            super().__init__(self.handler)

        def handler(self, request: httpx.Request) -> httpx.Response:
            captured["sandbox_id"] = request.headers.get(SANDBOX_ID_HEADER, "")
            return httpx.Response(200, json={"status": "ok"})

    sandbox_id = "00000000-0000-0000-0000-000000000099"
    transport = RuntimeTransport(
        connect_url="https://sbx.example.com",
        api_key="test",
        timeout_ms=5000,
        client=httpx.Client(transport=HeaderCaptureTransport()),
        sandbox_id=sandbox_id,
    )
    transport.request("POST", "/v1/processes/start", body={"command": "true"})
    assert captured["sandbox_id"] == sandbox_id
    transport.close()


def test_runtime_transport_omits_x_sandbox_id_without_sandbox_id():
    captured: dict[str, str | None] = {}

    class HeaderCaptureTransport(httpx.MockTransport):
        def __init__(self):
            super().__init__(self.handler)

        def handler(self, request: httpx.Request) -> httpx.Response:
            captured["sandbox_id"] = request.headers.get(SANDBOX_ID_HEADER)
            return httpx.Response(200, json={"status": "ok"})

    transport = RuntimeTransport(
        connect_url="https://sbx.example.com",
        api_key="test",
        timeout_ms=5000,
        client=httpx.Client(transport=HeaderCaptureTransport()),
    )
    transport.request("POST", "/v1/files/list", body={"path": "."})
    assert captured["sandbox_id"] is None
    transport.close()


def test_runtime_transport_sanity(runtime_transport):
    transport = RuntimeTransport(
        connect_url="https://sbx.example.com",
        api_key="test",
        timeout_ms=5000,
        client=runtime_transport,
    )
    resp = transport.request("POST", "/v1/exec")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"

    with pytest.raises(NotFoundError):
        transport.request("GET", "/v1/nonexistent")


def test_runtime_transport_timeout():
    class TimeoutMock(httpx.MockTransport):
        def __init__(self):
            super().__init__(self.handler)

        def handler(self, request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("timeout", request=request)

    transport = RuntimeTransport(
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
    assert conn.processes is not None
    conn.close()


def _raw_entry(name: str = "a.txt", type: str = "file", path: str = "a.txt") -> dict:
    return {
        "name": name,
        "type": type,
        "path": path,
        "size": 3,
        "mode": 420,
        "permissions": "rw-r--r--",
        "modified_time": "2026-07-06T00:00:00Z",
    }


class FilesMockTransport(httpx.MockTransport):
    def __init__(self, *, exists: bool = True, watch_frames: list[dict] | None = None):
        self._exists = exists
        self._watch_frames = watch_frames or []
        super().__init__(self.handler)

    def handler(self, request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if p.endswith("/v1/files/stat"):
            return httpx.Response(200, json={"entry": _raw_entry()})
        if p.endswith("/v1/files/exists"):
            return httpx.Response(200, json={"exists": self._exists})
        if p.endswith("/v1/files/mkdir"):
            return httpx.Response(
                200, json={"entry": _raw_entry(name="d", type="directory", path="d")}
            )
        if p.endswith("/v1/files/move"):
            return httpx.Response(200, json={"entry": _raw_entry(name="b.txt", path="b.txt")})
        if p.endswith("/v1/files/remove"):
            return httpx.Response(200, content=b"")
        if p.endswith("/v1/files/watch"):
            return httpx.Response(200, content=_ndjson_lines(self._watch_frames))
        return httpx.Response(404, json={"reason_code": "not_found", "message": "missing"})


def _files_conn(**kw) -> SandboxConnection:
    return SandboxConnection(
        connect_url="https://sbx.example.com",
        api_key="test",
        timeout_ms=5000,
        client=httpx.Client(transport=FilesMockTransport(**kw)),
    )


def test_files_stat_returns_entry():
    conn = _files_conn()
    entry = conn.files.stat("a.txt")
    assert entry.name == "a.txt"
    assert entry.type == "file"
    assert entry.size == 3
    conn.close()


def test_files_exists_true_and_false():
    conn = _files_conn(exists=True)
    assert conn.files.exists("a.txt") is True
    conn.close()
    conn2 = _files_conn(exists=False)
    assert conn2.files.exists("nope") is False
    conn2.close()


def test_files_mkdir_returns_directory_entry():
    conn = _files_conn()
    entry = conn.files.mkdir("d")
    assert entry.type == "directory"
    assert entry.name == "d"
    conn.close()


def test_files_move_returns_destination_entry():
    conn = _files_conn()
    entry = conn.files.move("a.txt", "b.txt")
    assert entry.name == "b.txt"
    conn.close()


def test_files_remove_succeeds():
    conn = _files_conn()
    conn.files.remove("a.txt", recursive=True)  # should not raise
    conn.close()


def test_files_watch_yields_events_and_maps_entry():
    frames = [
        {"type": "create", "path": "new.txt", "entry": _raw_entry(name="new.txt", path="new.txt")},
        {"type": "remove", "path": "old.txt"},
    ]
    conn = _files_conn(watch_frames=frames)
    events = list(conn.files.watch("."))
    assert [e.type for e in events] == ["create", "remove"]
    assert events[0].entry is not None and events[0].entry.name == "new.txt"
    assert events[1].entry is None
    conn.close()


@pytest.mark.asyncio
async def test_async_files_stat_and_watch():
    frames = [{"type": "write", "path": "f.txt", "entry": _raw_entry(name="f.txt", path="f.txt")}]
    conn = AsyncSandboxConnection(
        connect_url="https://sbx.example.com",
        api_key="test",
        timeout_ms=5000,
        client=httpx.AsyncClient(transport=FilesMockTransport(watch_frames=frames)),
    )
    entry = await conn.files.stat("a.txt")
    assert entry.name == "a.txt"
    events = [e async for e in conn.files.watch(".")]
    assert events[0].type == "write"
    assert events[0].entry is not None and events[0].entry.name == "f.txt"
    await conn.aclose()
