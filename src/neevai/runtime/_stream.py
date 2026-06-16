"""Shared NDJSON stream decoding and argv helpers for sandboxd."""

# pyright: reportUnusedFunction=false

from __future__ import annotations

import base64
import codecs
import json
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field

from pydantic import TypeAdapter

from neevai.errors import NeevAIError, error_from_status
from neevai.runtime.schemas import (
    ErrorFrame,
    ExecFrame,
    ExitFrame,
    ProcessLogFrame,
    StderrFrame,
    StdoutFrame,
)
from neevai.types import ExecStreamEvent, ProcessLogEvent

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
_LOG_FRAME_ADAPTER: TypeAdapter[ProcessLogFrame] = TypeAdapter(ProcessLogFrame)


def _prepare_argv(
    command: str | list[str],
    args: list[str] | None,
    *,
    prefix: str = "exec",
) -> tuple[str, list[str]]:
    if isinstance(command, list):
        if args:
            raise NeevAIError(
                f"{prefix}: pass arguments either in the command array or via args, not both."
            )
        argv = command
    else:
        argv = [command] + (args or [])
    if prefix == "processes" and (not argv or not argv[0]):
        raise NeevAIError(f"{prefix}: program must not be empty.")
    return argv[0], argv[1:]


@dataclass
class _StreamState:
    out_decoder: codecs.IncrementalDecoder = field(
        default_factory=lambda: codecs.getincrementaldecoder("utf-8")()
    )
    err_decoder: codecs.IncrementalDecoder = field(
        default_factory=lambda: codecs.getincrementaldecoder("utf-8")()
    )
    saw_exit: bool = False


def _parse_exec_frame(raw: object) -> ExecFrame:
    return _EXEC_FRAME_ADAPTER.validate_python(raw)


def _parse_log_frame(raw: object) -> ProcessLogFrame:
    return _LOG_FRAME_ADAPTER.validate_python(raw)


def _yield_exec_frame_events(
    frame: ExecFrame,
    state: _StreamState,
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


def _yield_log_frame_events(
    frame: ProcessLogFrame,
    state: _StreamState,
) -> Iterator[ProcessLogEvent]:
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
    else:
        assert isinstance(frame, ExitFrame)
        rest_out = state.out_decoder.decode(b"", final=True)
        if rest_out:
            yield {"type": "stdout", "data": rest_out}
        rest_err = state.err_decoder.decode(b"", final=True)
        if rest_err:
            yield {"type": "stderr", "data": rest_err}
        state.saw_exit = True
        yield {"type": "exit", "exit_code": frame.exit_code}


def _iter_exec_stream_events(lines: Iterator[str]) -> Iterator[ExecStreamEvent]:
    state = _StreamState()
    for line in lines:
        trimmed = line.strip()
        if not trimmed:
            continue
        frame = _parse_exec_frame(json.loads(trimmed))
        yield from _yield_exec_frame_events(frame, state)

    if not state.saw_exit:
        raise NeevAIError(
            "exec stream ended without an exit status (the command may have timed out)."
        )


async def _aiter_exec_stream_events(lines: AsyncIterator[str]) -> AsyncIterator[ExecStreamEvent]:
    state = _StreamState()
    async for line in lines:
        trimmed = line.strip()
        if not trimmed:
            continue
        frame = _parse_exec_frame(json.loads(trimmed))
        for event in _yield_exec_frame_events(frame, state):
            yield event

    if not state.saw_exit:
        raise NeevAIError(
            "exec stream ended without an exit status (the command may have timed out)."
        )


def _iter_process_log_events(lines: Iterator[str]) -> Iterator[ProcessLogEvent]:
    state = _StreamState()
    for line in lines:
        trimmed = line.strip()
        if not trimmed:
            continue
        frame = _parse_log_frame(json.loads(trimmed))
        yield from _yield_log_frame_events(frame, state)


async def _aiter_process_log_events(lines: AsyncIterator[str]) -> AsyncIterator[ProcessLogEvent]:
    state = _StreamState()
    async for line in lines:
        trimmed = line.strip()
        if not trimmed:
            continue
        frame = _parse_log_frame(json.loads(trimmed))
        for event in _yield_log_frame_events(frame, state):
            yield event
