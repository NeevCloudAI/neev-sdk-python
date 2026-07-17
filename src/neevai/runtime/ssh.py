"""Local SSH tunnels to a sandbox, reached via ``sandbox.ssh()``.

A tunnel binds a loopback TCP listener and forwards each accepted connection to the
sandbox's SSH endpoint over an authenticated WebSocket, copying bytes both ways. Point
any ssh client, ``scp``/``rsync``, or IDE remote-dev at ``{host, port}`` — no keys to
manage and no public port. This is host-side only: it opens a local listener, so it is
not available in the browser.
"""

from __future__ import annotations

import asyncio
import re
import socket
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neevai.runtime.connection import AsyncSandboxConnection, SandboxConnection

# WebSocket handshake timeout for a tunnelled connection.
SSH_OPEN_TIMEOUT_MS = 15_000
# Size of the chunk read from the local socket before forwarding.
_CHUNK = 65536


def _ssh_url(connect_url: str) -> str:
    """Builds the ws(s):// SSH upgrade URL from the runtime connect URL."""
    ws_base = re.sub(r"^http", "ws", connect_url.rstrip("/"))
    return f"{ws_base}/v1/ssh"


def _sync_connect(url: str, headers: dict[str, str], open_timeout_s: float) -> Any:
    """Opens a synchronous WebSocket to the SSH endpoint (isolated for testing)."""
    from websockets.sync.client import connect

    return connect(url, additional_headers=headers, open_timeout=open_timeout_s)


async def _async_connect(url: str, headers: dict[str, str], open_timeout_s: float) -> Any:
    """Opens an asynchronous WebSocket to the SSH endpoint (isolated for testing)."""
    from websockets.asyncio.client import connect

    return await connect(url, additional_headers=headers, open_timeout=open_timeout_s)


def _close_quietly(closer: Any) -> None:
    """Calls close() and swallows any error (best-effort teardown)."""
    try:
        closer.close()
    except Exception:
        pass


class SshTunnel:
    """A running SSH tunnel (synchronous).

    A background thread accepts local connections; each is bridged to a fresh
    sandbox SSH WebSocket by a pair of pump threads. ``close()`` stops the listener
    and drops in-flight connections; the tunnel is also a context manager.
    """

    def __init__(
        self,
        listener: socket.socket,
        ws_url: str,
        headers: dict[str, str],
        connect: Any,
        open_timeout_s: float,
    ):
        self.host, self.port = listener.getsockname()[:2]
        self._listener = listener
        self._ws_url = ws_url
        self._headers = headers
        self._connect = connect
        self._open_timeout_s = open_timeout_s
        self._closed = threading.Event()
        self._live: set[tuple[socket.socket, Any]] = set()
        self._lock = threading.Lock()
        self._accept = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept.start()

    def _accept_loop(self) -> None:
        """Accepts local connections until the tunnel is closed, bridging each."""
        while not self._closed.is_set():
            try:
                client, _ = self._listener.accept()
            except OSError:
                break  # listener closed by close()
            if self._closed.is_set():
                # A wakeup connection from close() (see below); do not bridge it.
                client.close()
                break
            threading.Thread(target=self._bridge, args=(client,), daemon=True).start()

    def _bridge(self, client: socket.socket) -> None:
        """Bridges one accepted connection to a fresh sandbox SSH WebSocket."""
        try:
            ws = self._connect(self._ws_url, self._headers, self._open_timeout_s)
        except Exception:
            client.close()
            return
        entry = (client, ws)
        with self._lock:
            if self._closed.is_set():
                client.close()
                _close_quietly(ws)
                return
            self._live.add(entry)

        # ws -> client: SSH output frames become local socket bytes.
        def pump_ws_to_client() -> None:
            try:
                for message in ws:
                    if isinstance(message, (bytes, bytearray)):
                        client.sendall(message)
            except Exception:
                pass
            finally:
                client.close()  # unblocks the recv loop below

        reader = threading.Thread(target=pump_ws_to_client, daemon=True)
        reader.start()

        # client -> ws: local socket bytes become binary SSH frames (this thread).
        try:
            while True:
                data = client.recv(_CHUNK)
                if not data:
                    break
                ws.send(data)
        except Exception:
            pass
        finally:
            _close_quietly(ws)
            client.close()
            with self._lock:
                self._live.discard(entry)

    def close(self) -> None:
        """Stops the listener and drops in-flight connections. Idempotent."""
        if self._closed.is_set():
            return
        self._closed.set()
        # Unblock the accept loop before closing the listener: on Linux, closing a
        # socket from another thread does not interrupt a blocked accept(), so the
        # kernel keeps the port listening until a connection arrives. A throwaway
        # loopback connection wakes accept(); the loop then observes _closed and exits.
        try:
            with socket.create_connection((self.host, self.port), timeout=1):
                pass
        except OSError:
            pass
        self._accept.join(timeout=2)
        _close_quietly(self._listener)
        with self._lock:
            live = list(self._live)
            self._live.clear()
        for client, ws in live:
            client.close()  # unblocks a blocked recv
            _close_quietly(ws)

    def __enter__(self) -> SshTunnel:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class SandboxSsh:
    """SSH tunnelling on a sandbox (synchronous), reached via ``connection.ssh``."""

    def __init__(self, connection: SandboxConnection):
        self._conn = connection

    def open(self, port: int | None = None, host: str = "127.0.0.1") -> SshTunnel:
        """Binds a loopback listener and returns a running tunnel.

        ``port`` of ``None``/``0`` picks a free ephemeral port; ``host`` defaults to
        ``127.0.0.1`` (loopback-only).
        """
        transport = self._conn._transport
        url = _ssh_url(transport.connect_url)
        headers = transport._auth_headers()
        listener = socket.create_server((host, port or 0))
        return SshTunnel(listener, url, headers, _sync_connect, SSH_OPEN_TIMEOUT_MS / 1000.0)


class AsyncSshTunnel:
    """A running SSH tunnel (asynchronous). See :class:`SshTunnel`."""

    def __init__(self, ws_url: str, headers: dict[str, str], connect: Any, open_timeout_s: float):
        self._ws_url = ws_url
        self._headers = headers
        self._connect = connect
        self._open_timeout_s = open_timeout_s
        self._server: asyncio.Server | None = None
        self.host = "127.0.0.1"
        self.port = 0
        self._closed = False
        self._conns: set[asyncio.Task[None]] = set()

    def _bind(self, server: asyncio.Server) -> None:
        """Records the listening server and its bound address."""
        self._server = server
        self.host, self.port = server.sockets[0].getsockname()[:2]

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Bridges one accepted connection to a fresh sandbox SSH WebSocket."""
        task = asyncio.current_task()
        if task is not None:
            self._conns.add(task)
        try:
            ws = await self._connect(self._ws_url, self._headers, self._open_timeout_s)
        except Exception:
            writer.close()
            if task is not None:
                self._conns.discard(task)
            return

        async def pump_ws_to_tcp() -> None:
            try:
                async for message in ws:
                    if isinstance(message, (bytes, bytearray)):
                        writer.write(message)
                        await writer.drain()
            except Exception:
                pass

        async def pump_tcp_to_ws() -> None:
            try:
                while True:
                    data = await reader.read(_CHUNK)
                    if not data:
                        break
                    await ws.send(data)
            except Exception:
                pass

        try:
            await asyncio.gather(pump_ws_to_tcp(), pump_tcp_to_ws())
        finally:
            await _aclose_quietly(ws)
            writer.close()
            if task is not None:
                self._conns.discard(task)

    async def close(self) -> None:
        """Stops the listener and drops in-flight connections. Idempotent."""
        if self._closed:
            return
        self._closed = True
        if self._server is not None:
            self._server.close()
        for task in list(self._conns):
            task.cancel()
        if self._server is not None:
            await self._server.wait_closed()

    async def __aenter__(self) -> AsyncSshTunnel:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()


async def _aclose_quietly(ws: Any) -> None:
    """Awaits close() and swallows any error (best-effort teardown)."""
    try:
        await ws.close()
    except Exception:
        pass


class AsyncSandboxSsh:
    """SSH tunnelling on a sandbox (asynchronous), reached via ``connection.ssh``."""

    def __init__(self, connection: AsyncSandboxConnection):
        self._conn = connection

    async def open(self, port: int | None = None, host: str = "127.0.0.1") -> AsyncSshTunnel:
        """Binds a loopback listener and returns a running tunnel. See :meth:`SandboxSsh.open`."""
        transport = self._conn._transport
        url = _ssh_url(transport.connect_url)
        headers = transport._auth_headers()
        tunnel = AsyncSshTunnel(url, headers, _async_connect, SSH_OPEN_TIMEOUT_MS / 1000.0)
        server = await asyncio.start_server(tunnel._handle, host, port or 0)
        tunnel._bind(server)
        return tunnel
