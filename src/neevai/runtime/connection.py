from collections.abc import AsyncIterator, Iterator

import httpx

from neevai.runtime._stream import (
    _aiter_exec_stream_events,
    _aiter_watch_events,
    _iter_exec_stream_events,
    _iter_watch_events,
    _prepare_argv,
)
from neevai.runtime.schemas import (
    FileEntryResponse,
    FileExistsResponse,
    FileListResponse,
    FileWriteResponse,
)
from neevai.transport.runtime import AsyncRuntimeTransport, RuntimeTransport
from neevai.types import ExecResult, ExecStreamEvent, FileEntry, WatchEvent


def _entries_from_response(data: object) -> list[FileEntry]:
    parsed = FileListResponse.model_validate(data)
    return [FileEntry.model_validate(entry.model_dump()) for entry in parsed.entries]


def _entry_from_response(data: object) -> FileEntry:
    parsed = FileEntryResponse.model_validate(data)
    return FileEntry.model_validate(parsed.entry.model_dump())


def _prepare_exec_body(
    program: str,
    cmd_args: list[str],
    cwd: str | None,
    env: dict[str, str] | None,
    timeout_ms: int | None,
    stdin: str | None,
) -> dict[str, object]:
    env_list = None
    if env:
        env_list = [f"{k}={v}" for k, v in env.items()]
    return {
        "command": program,
        "args": cmd_args,
        "cwd": cwd,
        "env": env_list,
        "timeout_ms": timeout_ms,
        "stdin": stdin,
    }


class SandboxFiles:
    """Synchronous file operations on the sandbox runtime."""

    def __init__(self, connection: "SandboxConnection"):
        self._conn = connection

    def write(self, path: str, content: str | bytes, cwd: str | None = None) -> dict[str, int]:
        """Writes data to a file in the sandbox, returning the bytes written."""
        if isinstance(content, str):
            content = content.encode("utf-8")

        response = self._conn._transport.request(
            method="POST",
            path="/v1/files/write",
            query={"path": path, "cwd": cwd},
            headers={"Content-Type": "application/octet-stream"},
            content=content,
        )
        parsed = FileWriteResponse.model_validate(response.json())
        return {"bytes_written": parsed.bytes_written}

    def read(self, path: str, cwd: str | None = None) -> bytes:
        """Reads a file from the sandbox and returns its raw binary bytes."""
        response = self._conn._transport.request(
            method="POST",
            path="/v1/files/read",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/octet-stream",
            },
            body={"path": path, "cwd": cwd},
        )
        return response.content

    def read_text(self, path: str, cwd: str | None = None) -> str:
        """Reads a file from the sandbox and decodes it as UTF-8 string."""
        return self.read(path, cwd=cwd).decode("utf-8")

    def list(
        self,
        path: str,
        cwd: str | None = None,
        recursive: bool = False,
        max_count: int | None = None,
    ) -> list[FileEntry]:
        """Lists directory entries at a path in the sandbox."""
        body = {
            "path": path,
            "cwd": cwd,
            "recursive": recursive,
            "max_count": max_count,
        }
        response = self._conn._transport.request(
            method="POST",
            path="/v1/files/list",
            headers={"Content-Type": "application/json"},
            body=body,
        )
        return _entries_from_response(response.json())

    def stat(self, path: str, cwd: str | None = None) -> FileEntry:
        """Returns metadata for a single path in the sandbox."""
        response = self._conn._transport.request(
            method="POST",
            path="/v1/files/stat",
            headers={"Content-Type": "application/json"},
            body={"path": path, "cwd": cwd},
        )
        return _entry_from_response(response.json())

    def exists(self, path: str, cwd: str | None = None) -> bool:
        """Reports whether a path exists in the sandbox."""
        response = self._conn._transport.request(
            method="POST",
            path="/v1/files/exists",
            headers={"Content-Type": "application/json"},
            body={"path": path, "cwd": cwd},
        )
        return FileExistsResponse.model_validate(response.json()).exists

    def mkdir(self, path: str, cwd: str | None = None) -> FileEntry:
        """Creates a directory (and parents) in the sandbox, returning its entry."""
        response = self._conn._transport.request(
            method="POST",
            path="/v1/files/mkdir",
            headers={"Content-Type": "application/json"},
            body={"path": path, "cwd": cwd},
        )
        return _entry_from_response(response.json())

    def move(self, source: str, destination: str, cwd: str | None = None) -> FileEntry:
        """Moves or renames a path in the sandbox, returning the destination entry."""
        response = self._conn._transport.request(
            method="POST",
            path="/v1/files/move",
            headers={"Content-Type": "application/json"},
            body={"source": source, "destination": destination, "cwd": cwd},
        )
        return _entry_from_response(response.json())

    def remove(self, path: str, cwd: str | None = None, recursive: bool = False) -> None:
        """Removes a file or directory from the sandbox."""
        self._conn._transport.request(
            method="POST",
            path="/v1/files/remove",
            headers={"Content-Type": "application/json"},
            body={"path": path, "cwd": cwd, "recursive": recursive},
        )

    def watch(
        self,
        path: str,
        cwd: str | None = None,
        recursive: bool = False,
        timeout_ms: int | None = None,
    ) -> Iterator[WatchEvent]:
        """Streams filesystem change events under a path until the watch ends."""
        headers = {"Content-Type": "application/json", "Accept": "application/x-ndjson"}
        body = {"path": path, "cwd": cwd, "recursive": recursive, "timeout_ms": timeout_ms}
        lines = self._conn._transport.stream_request(
            "POST", "/v1/files/watch", headers=headers, body=body
        )
        yield from _iter_watch_events(iter(lines))


class SandboxConnection:
    """Synchronous connection to sandbox runtime."""

    def __init__(
        self,
        connect_url: str,
        api_key: str,
        timeout_ms: int = 60000,
        client: httpx.Client | None = None,
        sandbox_id: str | None = None,
    ):
        self._transport = RuntimeTransport(
            connect_url, api_key, timeout_ms, client=client, sandbox_id=sandbox_id
        )
        self.files = SandboxFiles(self)
        from neevai.runtime.processes import SandboxProcesses
        from neevai.runtime.pty import SandboxPty
        from neevai.runtime.ssh import SandboxSsh

        self.processes = SandboxProcesses(self)
        self.pty = SandboxPty(self)
        self.ssh = SandboxSsh(self)

    def close(self) -> None:
        """Closes the underlying transport connection."""
        self._transport.close()

    def exec_stream(
        self,
        command: str | list[str],
        args: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_ms: int | None = None,
        stdin: str | None = None,
    ) -> Iterator[ExecStreamEvent]:
        """Runs a command and yields stdout/stderr chunks as they arrive."""
        program, cmd_args = _prepare_argv(command, args, prefix="exec")
        body = _prepare_exec_body(program, cmd_args, cwd, env, timeout_ms, stdin)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/x-ndjson",
        }
        lines = self._transport.stream_request("POST", "/v1/exec", headers=headers, body=body)
        yield from _iter_exec_stream_events(iter(lines))

    def exec(
        self,
        command: str | list[str],
        args: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_ms: int | None = None,
        stdin: str | None = None,
    ) -> ExecResult:
        """Runs a shell command inside the sandbox synchronously, parsing NDJSON output."""
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        exit_code = 0
        for event in self.exec_stream(
            command=command,
            args=args,
            cwd=cwd,
            env=env,
            timeout_ms=timeout_ms,
            stdin=stdin,
        ):
            if event["type"] == "stdout":
                stdout_chunks.append(event["data"])
            elif event["type"] == "stderr":
                stderr_chunks.append(event["data"])
            else:
                exit_code = event["exit_code"]
        return ExecResult(
            stdout="".join(stdout_chunks),
            stderr="".join(stderr_chunks),
            exit_code=exit_code,
        )


class AsyncSandboxFiles:
    """Asynchronous file operations on the sandbox runtime."""

    def __init__(self, connection: "AsyncSandboxConnection"):
        self._conn = connection

    async def write(
        self, path: str, content: str | bytes, cwd: str | None = None
    ) -> dict[str, int]:
        """Writes data to a file asynchronously, returning the bytes written."""
        if isinstance(content, str):
            content = content.encode("utf-8")

        response = await self._conn._transport.request(
            method="POST",
            path="/v1/files/write",
            query={"path": path, "cwd": cwd},
            headers={"Content-Type": "application/octet-stream"},
            content=content,
        )
        parsed = FileWriteResponse.model_validate(response.json())
        return {"bytes_written": parsed.bytes_written}

    async def read(self, path: str, cwd: str | None = None) -> bytes:
        """Reads a file asynchronously, returning its raw binary bytes."""
        response = await self._conn._transport.request(
            method="POST",
            path="/v1/files/read",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/octet-stream",
            },
            body={"path": path, "cwd": cwd},
        )
        return response.content

    async def read_text(self, path: str, cwd: str | None = None) -> str:
        """Reads a file asynchronously, decoding as UTF-8."""
        raw_bytes = await self.read(path, cwd=cwd)
        return raw_bytes.decode("utf-8")

    async def list(
        self,
        path: str,
        cwd: str | None = None,
        recursive: bool = False,
        max_count: int | None = None,
    ) -> list[FileEntry]:
        """Lists directory entries asynchronously."""
        body = {
            "path": path,
            "cwd": cwd,
            "recursive": recursive,
            "max_count": max_count,
        }
        response = await self._conn._transport.request(
            method="POST",
            path="/v1/files/list",
            headers={"Content-Type": "application/json"},
            body=body,
        )
        return _entries_from_response(response.json())

    async def stat(self, path: str, cwd: str | None = None) -> FileEntry:
        """Returns metadata for a single path in the sandbox."""
        response = await self._conn._transport.request(
            method="POST",
            path="/v1/files/stat",
            headers={"Content-Type": "application/json"},
            body={"path": path, "cwd": cwd},
        )
        return _entry_from_response(response.json())

    async def exists(self, path: str, cwd: str | None = None) -> bool:
        """Reports whether a path exists in the sandbox."""
        response = await self._conn._transport.request(
            method="POST",
            path="/v1/files/exists",
            headers={"Content-Type": "application/json"},
            body={"path": path, "cwd": cwd},
        )
        return FileExistsResponse.model_validate(response.json()).exists

    async def mkdir(self, path: str, cwd: str | None = None) -> FileEntry:
        """Creates a directory (and parents) in the sandbox, returning its entry."""
        response = await self._conn._transport.request(
            method="POST",
            path="/v1/files/mkdir",
            headers={"Content-Type": "application/json"},
            body={"path": path, "cwd": cwd},
        )
        return _entry_from_response(response.json())

    async def move(self, source: str, destination: str, cwd: str | None = None) -> FileEntry:
        """Moves or renames a path in the sandbox, returning the destination entry."""
        response = await self._conn._transport.request(
            method="POST",
            path="/v1/files/move",
            headers={"Content-Type": "application/json"},
            body={"source": source, "destination": destination, "cwd": cwd},
        )
        return _entry_from_response(response.json())

    async def remove(self, path: str, cwd: str | None = None, recursive: bool = False) -> None:
        """Removes a file or directory from the sandbox."""
        await self._conn._transport.request(
            method="POST",
            path="/v1/files/remove",
            headers={"Content-Type": "application/json"},
            body={"path": path, "cwd": cwd, "recursive": recursive},
        )

    async def watch(
        self,
        path: str,
        cwd: str | None = None,
        recursive: bool = False,
        timeout_ms: int | None = None,
    ) -> AsyncIterator[WatchEvent]:
        """Streams filesystem change events under a path until the watch ends."""
        headers = {"Content-Type": "application/json", "Accept": "application/x-ndjson"}
        body = {"path": path, "cwd": cwd, "recursive": recursive, "timeout_ms": timeout_ms}
        stream_gen = self._conn._transport.stream_request(
            "POST", "/v1/files/watch", headers=headers, body=body
        )

        async def _lines() -> AsyncIterator[str]:
            async for line in stream_gen:
                yield line

        async for event in _aiter_watch_events(_lines()):
            yield event


class AsyncSandboxConnection:
    """Asynchronous connection to sandbox runtime."""

    def __init__(
        self,
        connect_url: str,
        api_key: str,
        timeout_ms: int = 60000,
        client: httpx.AsyncClient | None = None,
        sandbox_id: str | None = None,
    ):
        self._transport = AsyncRuntimeTransport(
            connect_url, api_key, timeout_ms, client=client, sandbox_id=sandbox_id
        )
        self.files = AsyncSandboxFiles(self)
        from neevai.runtime.processes import AsyncSandboxProcesses
        from neevai.runtime.pty import AsyncSandboxPty
        from neevai.runtime.ssh import AsyncSandboxSsh

        self.processes = AsyncSandboxProcesses(self)
        self.pty = AsyncSandboxPty(self)
        self.ssh = AsyncSandboxSsh(self)

    async def aclose(self) -> None:
        """Closes the underlying async transport connection."""
        await self._transport.aclose()

    async def exec_stream(
        self,
        command: str | list[str],
        args: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_ms: int | None = None,
        stdin: str | None = None,
    ) -> AsyncIterator[ExecStreamEvent]:
        """Runs a command asynchronously and yields stdout/stderr chunks as they arrive."""
        program, cmd_args = _prepare_argv(command, args, prefix="exec")
        body = _prepare_exec_body(program, cmd_args, cwd, env, timeout_ms, stdin)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/x-ndjson",
        }
        stream_gen = self._transport.stream_request("POST", "/v1/exec", headers=headers, body=body)

        async def _lines() -> AsyncIterator[str]:
            async for line in stream_gen:
                yield line

        async for event in _aiter_exec_stream_events(_lines()):
            yield event

    async def exec(
        self,
        command: str | list[str],
        args: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_ms: int | None = None,
        stdin: str | None = None,
    ) -> ExecResult:
        """Runs a command asynchronously inside the sandbox, parsing streaming NDJSON output."""
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        exit_code = 0
        async for event in self.exec_stream(
            command=command,
            args=args,
            cwd=cwd,
            env=env,
            timeout_ms=timeout_ms,
            stdin=stdin,
        ):
            if event["type"] == "stdout":
                stdout_chunks.append(event["data"])
            elif event["type"] == "stderr":
                stderr_chunks.append(event["data"])
            else:
                exit_code = event["exit_code"]
        return ExecResult(
            stdout="".join(stdout_chunks),
            stderr="".join(stderr_chunks),
            exit_code=exit_code,
        )
