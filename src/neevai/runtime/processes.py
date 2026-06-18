"""Supervised long-running process APIs on the sandbox daemon."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING

from neevai.errors import NeevAIError
from neevai.runtime._stream import (
    _aiter_process_log_events,
    _iter_process_log_events,
    _prepare_argv,
)
from neevai.runtime.schemas import (
    RawKillAllResponse,
    RawKillResponse,
    RawProcessInfo,
    RawProcessListResponse,
    RawProcessLogsPage,
    RawProcessStatus,
)
from neevai.types import (
    ProcessInfo,
    ProcessLogEntry,
    ProcessLogEvent,
    ProcessLogsPage,
    ProcessStatus,
)

if TYPE_CHECKING:
    from neevai.runtime.sandboxd import AsyncSandboxConnection, SandboxConnection


def _prepare_start_body(
    program: str,
    cmd_args: list[str],
    cwd: str | None,
    env: dict[str, str] | None,
    stdin: str | None,
) -> dict[str, object]:
    if not program:
        raise NeevAIError("processes: program must not be empty.")
    env_list = None
    if env:
        env_list = [f"{k}={v}" for k, v in env.items()]
    return {
        "program": program,
        "args": cmd_args,
        "cwd": cwd,
        "env": env_list,
        "stdin": stdin,
    }


def _map_status(raw: RawProcessStatus) -> ProcessStatus:
    return ProcessStatus.model_validate(raw.model_dump())


def _map_info(raw: RawProcessInfo) -> ProcessInfo:
    return ProcessInfo.model_validate(raw.model_dump())


def _map_logs_page(raw: RawProcessLogsPage) -> ProcessLogsPage:
    return ProcessLogsPage(
        entries=[ProcessLogEntry.model_validate(entry.model_dump()) for entry in raw.entries],
        cursor=raw.cursor,
        dropped=raw.dropped,
        state=raw.state,
    )


def _signal_body_value(signal: int | None) -> int | None:
    if signal is None:
        return None
    return signal


class Process:
    """Handle for a single supervised sandbox process."""

    def __init__(self, processes: SandboxProcesses, status: ProcessStatus):
        self._processes = processes
        self._status = status

    @property
    def id(self) -> str:
        return self._status.process_id

    @property
    def state(self) -> str:
        return self._status.state

    @property
    def exit_code(self) -> int | None:
        return self._status.exit_code

    @property
    def started_at(self) -> int:
        return self._status.started_at

    def status(self) -> ProcessStatus:
        refreshed = self._processes.get(self.id, wait=False)
        self._status = refreshed
        return refreshed

    def wait(self) -> ProcessStatus:
        refreshed = self._processes.get(self.id, wait=True)
        self._status = refreshed
        return refreshed

    def kill(self, signal: int | None = None) -> bool:
        return self._processes.kill(self.id, signal=signal)

    def logs(self, cursor: int | None = None) -> ProcessLogsPage:
        return self._processes.logs(self.id, cursor=cursor)

    def follow(self, cursor: int | None = None) -> Iterator[ProcessLogEvent]:
        yield from self._processes.follow(self.id, cursor=cursor)


class AsyncProcess:
    """Async handle for a single supervised sandbox process."""

    def __init__(self, processes: AsyncSandboxProcesses, status: ProcessStatus):
        self._processes = processes
        self._status = status

    @property
    def id(self) -> str:
        return self._status.process_id

    @property
    def state(self) -> str:
        return self._status.state

    @property
    def exit_code(self) -> int | None:
        return self._status.exit_code

    @property
    def started_at(self) -> int:
        return self._status.started_at

    async def status(self) -> ProcessStatus:
        refreshed = await self._processes.get(self.id, wait=False)
        self._status = refreshed
        return refreshed

    async def wait(self) -> ProcessStatus:
        refreshed = await self._processes.get(self.id, wait=True)
        self._status = refreshed
        return refreshed

    async def kill(self, signal: int | None = None) -> bool:
        return await self._processes.kill(self.id, signal=signal)

    async def logs(self, cursor: int | None = None) -> ProcessLogsPage:
        return await self._processes.logs(self.id, cursor=cursor)

    async def follow(self, cursor: int | None = None) -> AsyncIterator[ProcessLogEvent]:
        async for event in self._processes.follow(self.id, cursor=cursor):
            yield event


class SandboxProcesses:
    """Synchronous supervised process operations on the sandbox daemon."""

    def __init__(self, connection: SandboxConnection):
        self._conn = connection

    def start(
        self,
        program: str | list[str],
        args: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stdin: str | None = None,
    ) -> Process:
        prog, cmd_args = _prepare_argv(program, args, prefix="processes")
        body = _prepare_start_body(prog, cmd_args, cwd, env, stdin)
        response = self._conn._transport.request(
            method="POST",
            path="/v1/processes/start",
            headers={"Content-Type": "application/json"},
            body=body,
        )
        status = _map_status(RawProcessStatus.model_validate(response.json()))
        return Process(self, status)

    def get(self, process_id: str, *, wait: bool = False) -> ProcessStatus:
        body: dict[str, object] = {"process_id": process_id}
        if wait:
            body["wait"] = True
        response = self._conn._transport.request(
            method="POST",
            path="/v1/processes/get",
            headers={"Content-Type": "application/json"},
            body=body,
        )
        return _map_status(RawProcessStatus.model_validate(response.json()))

    def list(self) -> list[ProcessInfo]:
        response = self._conn._transport.request(
            method="POST",
            path="/v1/processes/list",
            headers={"Content-Type": "application/json"},
            body={},
        )
        parsed = RawProcessListResponse.model_validate(response.json())
        return [_map_info(item) for item in parsed.processes]

    def kill(self, process_id: str, signal: int | None = None) -> bool:
        body: dict[str, object] = {"process_id": process_id}
        signal_value = _signal_body_value(signal)
        if signal_value is not None:
            body["signal"] = signal_value
        response = self._conn._transport.request(
            method="POST",
            path="/v1/processes/kill",
            headers={"Content-Type": "application/json"},
            body=body,
        )
        return RawKillResponse.model_validate(response.json()).signalled

    def kill_all(self, signal: int | None = None) -> int:
        body: dict[str, object] = {}
        signal_value = _signal_body_value(signal)
        if signal_value is not None:
            body["signal"] = signal_value
        response = self._conn._transport.request(
            method="POST",
            path="/v1/processes/kill-all",
            headers={"Content-Type": "application/json"},
            body=body,
        )
        return RawKillAllResponse.model_validate(response.json()).signalled_count

    def logs(self, process_id: str, cursor: int | None = None) -> ProcessLogsPage:
        body: dict[str, object] = {"process_id": process_id}
        if cursor is not None:
            body["cursor"] = cursor
        response = self._conn._transport.request(
            method="POST",
            path="/v1/processes/logs",
            headers={"Content-Type": "application/json"},
            body=body,
        )
        return _map_logs_page(RawProcessLogsPage.model_validate(response.json()))

    def follow(self, process_id: str, cursor: int | None = None) -> Iterator[ProcessLogEvent]:
        body: dict[str, object] = {"process_id": process_id, "follow": True}
        if cursor is not None:
            body["cursor"] = cursor
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/x-ndjson",
        }
        lines = self._conn._transport.stream_request(
            "POST",
            "/v1/processes/logs",
            headers=headers,
            body=body,
        )
        yield from _iter_process_log_events(iter(lines))


class AsyncSandboxProcesses:
    """Asynchronous supervised process operations on the sandbox daemon."""

    def __init__(self, connection: AsyncSandboxConnection):
        self._conn = connection

    async def start(
        self,
        program: str | list[str],
        args: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stdin: str | None = None,
    ) -> AsyncProcess:
        prog, cmd_args = _prepare_argv(program, args, prefix="processes")
        body = _prepare_start_body(prog, cmd_args, cwd, env, stdin)
        response = await self._conn._transport.request(
            method="POST",
            path="/v1/processes/start",
            headers={"Content-Type": "application/json"},
            body=body,
        )
        status = _map_status(RawProcessStatus.model_validate(response.json()))
        return AsyncProcess(self, status)

    async def get(self, process_id: str, *, wait: bool = False) -> ProcessStatus:
        body: dict[str, object] = {"process_id": process_id}
        if wait:
            body["wait"] = True
        response = await self._conn._transport.request(
            method="POST",
            path="/v1/processes/get",
            headers={"Content-Type": "application/json"},
            body=body,
        )
        return _map_status(RawProcessStatus.model_validate(response.json()))

    async def list(self) -> list[ProcessInfo]:
        response = await self._conn._transport.request(
            method="POST",
            path="/v1/processes/list",
            headers={"Content-Type": "application/json"},
            body={},
        )
        parsed = RawProcessListResponse.model_validate(response.json())
        return [_map_info(item) for item in parsed.processes]

    async def kill(self, process_id: str, signal: int | None = None) -> bool:
        body: dict[str, object] = {"process_id": process_id}
        signal_value = _signal_body_value(signal)
        if signal_value is not None:
            body["signal"] = signal_value
        response = await self._conn._transport.request(
            method="POST",
            path="/v1/processes/kill",
            headers={"Content-Type": "application/json"},
            body=body,
        )
        return RawKillResponse.model_validate(response.json()).signalled

    async def kill_all(self, signal: int | None = None) -> int:
        body: dict[str, object] = {}
        signal_value = _signal_body_value(signal)
        if signal_value is not None:
            body["signal"] = signal_value
        response = await self._conn._transport.request(
            method="POST",
            path="/v1/processes/kill-all",
            headers={"Content-Type": "application/json"},
            body=body,
        )
        return RawKillAllResponse.model_validate(response.json()).signalled_count

    async def logs(self, process_id: str, cursor: int | None = None) -> ProcessLogsPage:
        body: dict[str, object] = {"process_id": process_id}
        if cursor is not None:
            body["cursor"] = cursor
        response = await self._conn._transport.request(
            method="POST",
            path="/v1/processes/logs",
            headers={"Content-Type": "application/json"},
            body=body,
        )
        return _map_logs_page(RawProcessLogsPage.model_validate(response.json()))

    async def follow(
        self, process_id: str, cursor: int | None = None
    ) -> AsyncIterator[ProcessLogEvent]:
        body: dict[str, object] = {"process_id": process_id, "follow": True}
        if cursor is not None:
            body["cursor"] = cursor
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/x-ndjson",
        }
        stream_gen = self._conn._transport.stream_request(
            "POST",
            "/v1/processes/logs",
            headers=headers,
            body=body,
        )

        async def _lines() -> AsyncIterator[str]:
            async for line in stream_gen:
                yield line

        async for event in _aiter_process_log_events(_lines()):
            yield event
