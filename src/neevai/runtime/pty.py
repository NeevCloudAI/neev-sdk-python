"""Interactive PTY sessions over a WebSocket, reached via ``sandbox.pty``.

Wire protocol: the client sends terminal input as binary frames and control
frames (resize / signal) as JSON text; the server sends terminal output as
binary frames and a ``session`` (carrying ``pty_id``) and ``exit`` frame as JSON
text. The socket closing ends the session.
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlencode

from neevai.errors import NeevAIError

if TYPE_CHECKING:
    from neevai.runtime.connection import AsyncSandboxConnection, SandboxConnection

# If the server never sends the session frame after the socket opens, settle the id
# wait after this grace period (with id None) so create() can never hang.
PTY_SESSION_TIMEOUT_MS = 15_000


def _pty_url(connect_url: str, query: dict[str, Any]) -> str:
    """Builds the ws(s):// PTY upgrade URL from the runtime connect URL and query."""
    ws_base = re.sub(r"^http", "ws", connect_url.rstrip("/"))
    qs = urlencode(query, doseq=True)
    return f"{ws_base}/v1/pty" + (f"?{qs}" if qs else "")


def _pty_query(
    program: str | None,
    args: list[str] | None,
    cols: int,
    rows: int,
    id: str | None,
) -> dict[str, Any]:
    """Builds the PTY query params: `id` to reattach, else program/args/size for a new session."""
    if id:
        # Reattaching to an existing terminal; program/args/size don't apply.
        return {"id": id}
    query: dict[str, Any] = {}
    if program:
        query["program"] = program
    if cols and cols > 0:
        query["cols"] = cols
    if rows and rows > 0:
        query["rows"] = rows
    if args:
        query["arg"] = list(args)
    return query


def _sync_connect(url: str, headers: dict[str, str], open_timeout_s: float) -> Any:
    """Opens a synchronous WebSocket to the PTY endpoint (isolated for testing)."""
    from websockets.sync.client import connect

    return connect(url, additional_headers=headers, open_timeout=open_timeout_s)


async def _async_connect(url: str, headers: dict[str, str], open_timeout_s: float) -> Any:
    """Opens an asynchronous WebSocket to the PTY endpoint (isolated for testing)."""
    from websockets.asyncio.client import connect

    return await connect(url, additional_headers=headers, open_timeout=open_timeout_s)


def _is_session_frame(frame: dict[str, Any]) -> bool:
    return frame.get("type") == "session" and isinstance(frame.get("pty_id"), str)


def _is_exit_frame(frame: dict[str, Any]) -> bool:
    return frame.get("type") == "exit" and isinstance(frame.get("exit_code"), int)


class PtyHandle:
    """A live interactive PTY session (synchronous).

    A background thread pumps terminal output to ``on_data`` and tracks the exit
    code. Send keystrokes with ``send_input``, resize with ``resize``, signal the
    process with ``kill``, close it with ``disconnect``, and block on its exit
    with ``wait``.
    """

    def __init__(self, socket: Any, on_data: Callable[[bytes], None] | None = None):
        self._ws = socket
        self._on_data = on_data
        self._id: str | None = None
        self._exit_code = 0
        self._done = threading.Event()
        self._id_settled = threading.Event()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        try:
            for message in self._ws:
                if isinstance(message, (bytes, bytearray)):
                    if self._on_data is not None:
                        self._on_data(bytes(message))
                elif isinstance(message, str):
                    self._handle_text(message)
        except Exception:
            # The socket closed or errored; the finally block ends the session.
            pass
        finally:
            self._id_settled.set()
            self._done.set()

    def _handle_text(self, text: str) -> None:
        try:
            parsed = json.loads(text)
        except ValueError:
            return
        if not isinstance(parsed, dict):
            return
        frame = cast("dict[str, Any]", parsed)
        if _is_session_frame(frame):
            self._id = str(frame["pty_id"])
            self._id_settled.set()
        elif _is_exit_frame(frame):
            self._exit_code = int(frame["exit_code"])

    def _wait_ready(self, timeout_ms: int) -> None:
        """Blocks until the session id is known, the session ended, or the grace period elapsed."""
        self._id_settled.wait(timeout_ms / 1000.0)

    @property
    def id(self) -> str | None:
        """The terminal id, for reattaching later with ``pty.create(id=...)``."""
        return self._id

    def send_input(self, data: str | bytes) -> None:
        """Sends keystrokes/bytes to the terminal's standard input."""
        self._ws.send(data.encode("utf-8") if isinstance(data, str) else data)

    def resize(self, cols: int, rows: int) -> None:
        """Tells the remote terminal its window changed size (cols/rows in characters)."""
        self._ws.send(json.dumps({"type": "resize", "cols": cols, "rows": rows}))

    def kill(self, signal: str = "SIGTERM") -> None:
        """Sends a signal to the process group by name (default SIGTERM)."""
        self._ws.send(json.dumps({"type": "signal", "signal": signal}))

    def wait(self) -> int:
        """Blocks until the session ends and returns the exit code."""
        self._done.wait()
        return self._exit_code

    def disconnect(self) -> None:
        """Closes the WebSocket; the sandbox reaps the child. ``wait`` then returns."""
        self._ws.close()


class SandboxPty:
    """PTY operations on a sandbox (synchronous), reached via ``sandbox.pty``."""

    def __init__(self, connection: SandboxConnection):
        self._conn = connection

    def create(
        self,
        program: str | None = None,
        args: list[str] | None = None,
        cols: int = 0,
        rows: int = 0,
        id: str | None = None,
        on_data: Callable[[bytes], None] | None = None,
    ) -> PtyHandle:
        """Opens an interactive PTY (or reattaches when ``id`` is set) and returns a handle."""
        transport = self._conn._transport
        url = _pty_url(transport.connect_url, _pty_query(program, args, cols, rows, id))
        headers = transport._auth_headers()
        try:
            socket = _sync_connect(url, headers, PTY_SESSION_TIMEOUT_MS / 1000.0)
        except Exception as e:  # connection/handshake failure
            raise NeevAIError(f"pty connection failed: {e}") from e
        handle = PtyHandle(socket, on_data)
        handle._wait_ready(PTY_SESSION_TIMEOUT_MS)
        return handle


class AsyncPtyHandle:
    """A live interactive PTY session (asynchronous). See :class:`PtyHandle`."""

    def __init__(self, socket: Any, on_data: Callable[[bytes], None] | None = None):
        self._ws = socket
        self._on_data = on_data
        self._id: str | None = None
        self._exit_code = 0
        self._done = asyncio.Event()
        self._id_settled = asyncio.Event()
        self._reader = asyncio.ensure_future(self._read_loop())

    async def _read_loop(self) -> None:
        try:
            async for message in self._ws:
                if isinstance(message, (bytes, bytearray)):
                    if self._on_data is not None:
                        self._on_data(bytes(message))
                elif isinstance(message, str):
                    self._handle_text(message)
        except Exception:
            pass
        finally:
            self._id_settled.set()
            self._done.set()

    def _handle_text(self, text: str) -> None:
        try:
            parsed = json.loads(text)
        except ValueError:
            return
        if not isinstance(parsed, dict):
            return
        frame = cast("dict[str, Any]", parsed)
        if _is_session_frame(frame):
            self._id = str(frame["pty_id"])
            self._id_settled.set()
        elif _is_exit_frame(frame):
            self._exit_code = int(frame["exit_code"])

    async def _wait_ready(self, timeout_ms: int) -> None:
        try:
            await asyncio.wait_for(self._id_settled.wait(), timeout_ms / 1000.0)
        except asyncio.TimeoutError:
            pass

    @property
    def id(self) -> str | None:
        """The terminal id, for reattaching later with ``pty.create(id=...)``."""
        return self._id

    async def send_input(self, data: str | bytes) -> None:
        """Sends keystrokes/bytes to the terminal's standard input."""
        await self._ws.send(data.encode("utf-8") if isinstance(data, str) else data)

    async def resize(self, cols: int, rows: int) -> None:
        """Tells the remote terminal its window changed size (cols/rows in characters)."""
        await self._ws.send(json.dumps({"type": "resize", "cols": cols, "rows": rows}))

    async def kill(self, signal: str = "SIGTERM") -> None:
        """Sends a signal to the process group by name (default SIGTERM)."""
        await self._ws.send(json.dumps({"type": "signal", "signal": signal}))

    async def wait(self) -> int:
        """Waits until the session ends and returns the exit code."""
        await self._done.wait()
        return self._exit_code

    async def disconnect(self) -> None:
        """Closes the WebSocket; the sandbox reaps the child. ``wait`` then returns."""
        await self._ws.close()


class AsyncSandboxPty:
    """PTY operations on a sandbox (asynchronous), reached via ``sandbox.pty``."""

    def __init__(self, connection: AsyncSandboxConnection):
        self._conn = connection

    async def create(
        self,
        program: str | None = None,
        args: list[str] | None = None,
        cols: int = 0,
        rows: int = 0,
        id: str | None = None,
        on_data: Callable[[bytes], None] | None = None,
    ) -> AsyncPtyHandle:
        """Opens an interactive PTY (or reattaches when ``id`` is set) and returns a handle."""
        transport = self._conn._transport
        url = _pty_url(transport.connect_url, _pty_query(program, args, cols, rows, id))
        headers = transport._auth_headers()
        try:
            socket = await _async_connect(url, headers, PTY_SESSION_TIMEOUT_MS / 1000.0)
        except Exception as e:
            raise NeevAIError(f"pty connection failed: {e}") from e
        handle = AsyncPtyHandle(socket, on_data)
        await handle._wait_ready(PTY_SESSION_TIMEOUT_MS)
        return handle
