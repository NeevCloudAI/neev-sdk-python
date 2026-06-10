import base64
import codecs
import json
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field

import httpx
from pydantic import TypeAdapter

from neevai.errors import NeevAIError, error_from_status
from neevai.runtime.schemas import (
    ErrorFrame,
    ExecFrame,
    ExitFrame,
    FileListResponse,
    FileWriteResponse,
    StderrFrame,
    StdoutFrame,
)
from neevai.transport.runtime import AsyncDataplaneTransport, DataplaneTransport
from neevai.types import ExecResult, ExecStreamEvent, FileEntry

REASON_STATUS: dict[str, int] = {
    "permission_denied": 403,
    "invalid_argument": 400,
    "not_found": 404,
    "failed_precondition": 412,
    "resource_exhausted": 429,
    "deadline_exceeded": 504,
    "unavailable": 503,
    "internal": 500,
}

_EXEC_FRAME_ADAPTER: TypeAdapter[ExecFrame] = TypeAdapter(ExecFrame)


def _parse_exec_frame(raw: object) -> ExecFrame:
    return _EXEC_FRAME_ADAPTER.validate_python(raw)


def _entries_from_response(data: object) -> list[FileEntry]:
    parsed = FileListResponse.model_validate(data)
    return [FileEntry.model_validate(entry.model_dump()) for entry in parsed.entries]


def _prepare_exec_argv(
    command: str | list[str],
    args: list[str] | None,
) -> tuple[str, list[str]]:
    if isinstance(command, list):
        if args:
            raise NeevAIError(
                "exec: pass arguments either in the command array or via args, not both."
            )
        argv = command
    else:
        argv = [command] + (args or [])
    return argv[0], argv[1:]


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


@dataclass
class _ExecStreamState:
    out_decoder: codecs.IncrementalDecoder = field(
        default_factory=lambda: codecs.getincrementaldecoder("utf-8")()
    )
    err_decoder: codecs.IncrementalDecoder = field(
        default_factory=lambda: codecs.getincrementaldecoder("utf-8")()
    )
    saw_exit: bool = False


def _yield_frame_events(
    frame: ExecFrame,
    state: _ExecStreamState,
) -> Iterator[ExecStreamEvent]:
    if isinstance(frame, StdoutFrame):
        if frame.data:
            text = state.out_decoder.decode(base64.b64decode(frame.data))
            if text:
                yield {"type": "stdout", "data": text}
    elif isinstance(frame, StderrFrame):
        if frame.data:
            text = state.err_decoder.decode(base64.b64decode(frame.data))
            if text:
                yield {"type": "stderr", "data": text}
    elif isinstance(frame, ExitFrame):
        rest_out = state.out_decoder.decode(b"", final=True)
        if rest_out:
            yield {"type": "stdout", "data": rest_out}
        rest_err = state.err_decoder.decode(b"", final=True)
        if rest_err:
            yield {"type": "stderr", "data": rest_err}
        state.saw_exit = True
        yield {"type": "exit", "exit_code": frame.exit_code}
    else:
        assert isinstance(frame, ErrorFrame)
        status = REASON_STATUS.get(frame.reason_code, 500)
        raise error_from_status(
            status,
            {"error": frame.reason_code, "details": frame.message},
            None,
        )


def _iter_exec_stream_events(lines: Iterator[str]) -> Iterator[ExecStreamEvent]:
    state = _ExecStreamState()
    for line in lines:
        trimmed = line.strip()
        if not trimmed:
            continue
        frame = _parse_exec_frame(json.loads(trimmed))
        yield from _yield_frame_events(frame, state)

    if not state.saw_exit:
        raise NeevAIError(
            "exec stream ended without an exit status (the command may have timed out)."
        )


async def _aiter_exec_stream_events(lines: AsyncIterator[str]) -> AsyncIterator[ExecStreamEvent]:
    state = _ExecStreamState()
    async for line in lines:
        trimmed = line.strip()
        if not trimmed:
            continue
        frame = _parse_exec_frame(json.loads(trimmed))
        for event in _yield_frame_events(frame, state):
            yield event

    if not state.saw_exit:
        raise NeevAIError(
            "exec stream ended without an exit status (the command may have timed out)."
        )


class SandboxFiles:
    """Synchronous file operations on the sandbox daemon."""

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


class SandboxConnection:
    """Synchronous connection to regional sandbox data-plane daemon."""

    def __init__(
        self,
        connect_url: str,
        api_key: str,
        timeout_ms: int = 60000,
        client: httpx.Client | None = None,
    ):
        self._transport = DataplaneTransport(connect_url, api_key, timeout_ms, client=client)
        self.files = SandboxFiles(self)

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
        program, cmd_args = _prepare_exec_argv(command, args)
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
    """Asynchronous file operations on the sandbox daemon."""

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


class AsyncSandboxConnection:
    """Asynchronous connection to regional sandbox data-plane daemon."""

    def __init__(
        self,
        connect_url: str,
        api_key: str,
        timeout_ms: int = 60000,
        client: httpx.AsyncClient | None = None,
    ):
        self._transport = AsyncDataplaneTransport(connect_url, api_key, timeout_ms, client=client)
        self.files = AsyncSandboxFiles(self)

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
        program, cmd_args = _prepare_exec_argv(command, args)
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
