"""Tests for interactive PTY sessions (sync + async) over a faked WebSocket."""

import asyncio
import json
import queue
import threading

import httpx
import pytest

from neevai.errors import NeevAIError
from neevai.runtime.connection import AsyncSandboxConnection, SandboxConnection
from neevai.runtime.pty import _pty_query, _pty_url

# ---- URL / query helpers --------------------------------------------------


def test_pty_url_maps_scheme_and_appends_path():
    assert _pty_url("https://sbx.example.com", {}) == "wss://sbx.example.com/v1/pty"
    assert _pty_url("http://sbx.example.com/", {}) == "ws://sbx.example.com/v1/pty"


def test_pty_query_reattach_ignores_session_params():
    assert _pty_query("bash", ["-l"], 80, 24, "term-1") == {"id": "term-1"}


def test_pty_query_new_session():
    assert _pty_query("bash", ["-l", "-c", "ls"], 80, 24, None) == {
        "program": "bash",
        "cols": 80,
        "rows": 24,
        "arg": ["-l", "-c", "ls"],
    }


# ---- Sync -----------------------------------------------------------------


class FakeSyncSocket:
    """Minimal stand-in for a websockets sync connection driven by a scripted queue."""

    def __init__(self, incoming):
        self._q: queue.Queue = queue.Queue()
        for message in incoming:
            self._q.put(message)
        self.sent: list = []
        self._closed = threading.Event()

    def __iter__(self):
        return self

    def __next__(self):
        while True:
            try:
                return self._q.get(timeout=0.02)
            except queue.Empty:
                if self._closed.is_set():
                    raise StopIteration from None

    def send(self, data):
        self.sent.append(data)

    def close(self, *args, **kwargs):
        self._closed.set()


def _conn() -> SandboxConnection:
    return SandboxConnection(
        connect_url="https://sbx.example.com",
        api_key="test",
        timeout_ms=5000,
        sandbox_id="sb-1",
        client=httpx.Client(),
    )


def _install_sync(monkeypatch, incoming) -> dict:
    captured: dict = {"socket": FakeSyncSocket(incoming)}

    def fake_connect(url, headers, open_timeout_s):
        captured["url"] = url
        captured["headers"] = headers
        return captured["socket"]

    monkeypatch.setattr("neevai.runtime.pty._sync_connect", fake_connect)
    return captured


def test_pty_create_reports_id_and_streams_output(monkeypatch):
    cap = _install_sync(
        monkeypatch,
        [
            json.dumps({"type": "session", "pty_id": "pty-1"}),
            b"hello world",
            json.dumps({"type": "exit", "exit_code": 0}),
        ],
    )
    chunks: list[bytes] = []
    conn = _conn()
    handle = conn.pty.create(program="bash", cols=80, rows=24, on_data=chunks.append)
    assert handle.id == "pty-1"
    assert "program=bash" in cap["url"] and "cols=80" in cap["url"]
    assert cap["headers"]["Authorization"] == "Bearer test"
    assert cap["headers"]["X-Sandbox-Id"] == "sb-1"
    handle.disconnect()
    assert handle.wait() == 0
    assert b"".join(chunks) == b"hello world"
    conn.close()


def test_pty_send_input_resize_kill_frames(monkeypatch):
    cap = _install_sync(monkeypatch, [json.dumps({"type": "session", "pty_id": "p"})])
    conn = _conn()
    handle = conn.pty.create()
    handle.send_input("ls\n")
    handle.resize(120, 40)
    handle.kill("SIGINT")
    sent = cap["socket"].sent
    assert b"ls\n" in sent
    resize = json.loads(next(s for s in sent if isinstance(s, str) and "resize" in s))
    assert resize == {"type": "resize", "cols": 120, "rows": 40}
    signal = json.loads(next(s for s in sent if isinstance(s, str) and "signal" in s))
    assert signal == {"type": "signal", "signal": "SIGINT"}
    handle.disconnect()
    assert handle.wait() == 0
    conn.close()


def test_pty_reattach_sends_id(monkeypatch):
    cap = _install_sync(monkeypatch, [json.dumps({"type": "session", "pty_id": "p"})])
    conn = _conn()
    conn.pty.create(id="term-existing")
    assert "id=term-existing" in cap["url"]
    assert "program" not in cap["url"]
    conn.close()


def test_pty_exit_code_propagates(monkeypatch):
    _install_sync(
        monkeypatch,
        [
            json.dumps({"type": "session", "pty_id": "p"}),
            json.dumps({"type": "exit", "exit_code": 42}),
        ],
    )
    conn = _conn()
    handle = conn.pty.create()
    handle.disconnect()
    assert handle.wait() == 42
    conn.close()


def test_pty_connection_failure_raises(monkeypatch):
    def boom(url, headers, open_timeout_s):
        raise OSError("connection refused")

    monkeypatch.setattr("neevai.runtime.pty._sync_connect", boom)
    conn = _conn()
    with pytest.raises(NeevAIError, match="pty connection failed"):
        conn.pty.create()
    conn.close()


# ---- Async ----------------------------------------------------------------


class FakeAsyncSocket:
    def __init__(self, incoming):
        self._q: asyncio.Queue = asyncio.Queue()
        for message in incoming:
            self._q.put_nowait(message)
        self.sent: list = []
        self._closed = asyncio.Event()

    def __aiter__(self):
        return self

    async def __anext__(self):
        while True:
            if not self._q.empty():
                return self._q.get_nowait()
            if self._closed.is_set():
                raise StopAsyncIteration
            await asyncio.sleep(0.005)

    async def send(self, data):
        self.sent.append(data)

    async def close(self, *args, **kwargs):
        self._closed.set()


@pytest.mark.asyncio
async def test_async_pty_create_send_and_exit(monkeypatch):
    sock = FakeAsyncSocket(
        [
            json.dumps({"type": "session", "pty_id": "a1"}),
            b"out",
            json.dumps({"type": "exit", "exit_code": 3}),
        ]
    )

    async def fake_connect(url, headers, open_timeout_s):
        return sock

    monkeypatch.setattr("neevai.runtime.pty._async_connect", fake_connect)
    chunks: list[bytes] = []
    conn = AsyncSandboxConnection(
        connect_url="https://sbx.example.com",
        api_key="test",
        timeout_ms=5000,
        sandbox_id="sb-1",
        client=httpx.AsyncClient(),
    )
    handle = await conn.pty.create(program="bash", on_data=chunks.append)
    assert handle.id == "a1"
    await handle.send_input("x")
    assert b"x" in sock.sent
    await handle.resize(90, 30)
    await handle.disconnect()
    assert await handle.wait() == 3
    assert b"".join(chunks) == b"out"
    await conn.aclose()
