"""Tests for SSH tunnelling (sync + async): a real local socket driven through the
tunnel to an echo WebSocket, so bytes written in come back out."""

import asyncio
import queue
import socket
import threading

import httpx
import pytest

from neevai.runtime.connection import AsyncSandboxConnection, SandboxConnection
from neevai.runtime.ssh import _ssh_url


def test_ssh_url_maps_scheme_and_appends_path():
    assert _ssh_url("https://sbx.example.com") == "wss://sbx.example.com/v1/ssh"
    assert _ssh_url("http://sbx.example.com/") == "ws://sbx.example.com/v1/ssh"


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Reads exactly n bytes (or until the peer closes)."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            break
        buf += chunk
    return buf


# ---- Sync -----------------------------------------------------------------


class EchoSyncWS:
    """Minimal websockets-sync stand-in that echoes each sent frame back."""

    def __init__(self):
        self._q: queue.Queue = queue.Queue()
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
        self._q.put(bytes(data))  # echo straight back as a binary frame

    def close(self, *args, **kwargs):
        self._closed.set()


def _sync_conn() -> SandboxConnection:
    return SandboxConnection(
        connect_url="https://sbx.example.com",
        api_key="test",
        timeout_ms=5000,
        sandbox_id="sb-1",
        client=httpx.Client(),
    )


def test_tunnel_binds_loopback_and_round_trips(monkeypatch):
    monkeypatch.setattr("neevai.runtime.ssh._sync_connect", lambda *a: EchoSyncWS())
    conn = _sync_conn()
    tunnel = conn.ssh.open()
    try:
        assert tunnel.host == "127.0.0.1"
        assert tunnel.port > 0
        with socket.create_connection((tunnel.host, tunnel.port), timeout=5) as client:
            client.sendall(b"hello ssh")
            assert _recv_exact(client, len(b"hello ssh")) == b"hello ssh"
    finally:
        tunnel.close()
        conn.close()


def test_tunnel_dials_ssh_ws_with_bearer(monkeypatch):
    captured: dict = {}

    def fake_connect(url, headers, open_timeout_s):
        captured["url"] = url
        captured["headers"] = headers
        return EchoSyncWS()

    monkeypatch.setattr("neevai.runtime.ssh._sync_connect", fake_connect)
    conn = _sync_conn()
    tunnel = conn.ssh.open()
    try:
        with socket.create_connection((tunnel.host, tunnel.port), timeout=5) as client:
            client.sendall(b"x")
            _recv_exact(client, 1)
    finally:
        tunnel.close()
        conn.close()
    assert captured["url"] == "wss://sbx.example.com/v1/ssh"
    assert captured["headers"]["Authorization"] == "Bearer test"


def test_tunnel_close_stops_listener_and_is_idempotent(monkeypatch):
    monkeypatch.setattr("neevai.runtime.ssh._sync_connect", lambda *a: EchoSyncWS())
    conn = _sync_conn()
    tunnel = conn.ssh.open()
    host, port = tunnel.host, tunnel.port
    tunnel.close()
    tunnel.close()  # idempotent
    conn.close()
    with pytest.raises(OSError):
        socket.create_connection((host, port), timeout=1).close()


def test_tunnel_context_manager_closes(monkeypatch):
    monkeypatch.setattr("neevai.runtime.ssh._sync_connect", lambda *a: EchoSyncWS())
    conn = _sync_conn()
    with conn.ssh.open() as tunnel:
        host, port = tunnel.host, tunnel.port
        with socket.create_connection((host, port), timeout=5) as client:
            client.sendall(b"hi")
            assert _recv_exact(client, 2) == b"hi"
    with pytest.raises(OSError):
        socket.create_connection((host, port), timeout=1).close()
    conn.close()


# ---- Async ----------------------------------------------------------------

_SENTINEL = object()


class EchoAsyncWS:
    """Minimal websockets-asyncio stand-in that echoes each sent frame back."""

    def __init__(self):
        self._q: asyncio.Queue = asyncio.Queue()
        self.sent: list = []
        self._closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self._q.get()
        if item is _SENTINEL:
            raise StopAsyncIteration
        return item

    async def send(self, data):
        self.sent.append(data)
        await self._q.put(bytes(data))  # echo straight back as a binary frame

    async def close(self, *args, **kwargs):
        if not self._closed:
            self._closed = True
            await self._q.put(_SENTINEL)


def _async_conn() -> AsyncSandboxConnection:
    return AsyncSandboxConnection(
        connect_url="https://sbx.example.com",
        api_key="test",
        timeout_ms=5000,
        sandbox_id="sb-1",
        client=httpx.AsyncClient(),
    )


async def test_async_tunnel_binds_loopback_and_round_trips(monkeypatch):
    captured: dict = {}

    async def fake_connect(url, headers, open_timeout_s):
        captured["url"] = url
        captured["headers"] = headers
        return EchoAsyncWS()

    monkeypatch.setattr("neevai.runtime.ssh._async_connect", fake_connect)
    conn = _async_conn()
    tunnel = await conn.ssh.open()
    try:
        assert tunnel.host == "127.0.0.1"
        assert tunnel.port > 0
        reader, writer = await asyncio.open_connection(tunnel.host, tunnel.port)
        writer.write(b"hello async")
        await writer.drain()
        data = await asyncio.wait_for(reader.readexactly(len(b"hello async")), timeout=5)
        assert data == b"hello async"
        assert captured["url"] == "wss://sbx.example.com/v1/ssh"
        assert captured["headers"]["Authorization"] == "Bearer test"
        writer.close()
    finally:
        await tunnel.close()
        await conn.aclose()


async def test_async_tunnel_close_stops_listener(monkeypatch):
    async def fake_connect(url, headers, open_timeout_s):
        return EchoAsyncWS()

    monkeypatch.setattr("neevai.runtime.ssh._async_connect", fake_connect)
    conn = _async_conn()
    tunnel = await conn.ssh.open()
    host, port = tunnel.host, tunnel.port
    await tunnel.close()
    await tunnel.close()  # idempotent
    await conn.aclose()
    with pytest.raises(OSError):
        reader, writer = await asyncio.open_connection(host, port)
        writer.close()
