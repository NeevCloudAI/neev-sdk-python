"""NeevCloud sandbox tools for agents, independent of any agent framework.

``SandboxTools`` binds the sandbox tool contract to one ``Sandbox`` handle and
``AsyncSandboxTools`` to one ``AsyncSandbox``. Register ``names()`` with the
model, using ``DESCRIPTIONS`` and ``PARAMETERS`` for each tool's description and
JSON Schema and ``TITLES`` for a display title, and pass each tool call to
``call(name, args)``.

Each tool returns a JSON-serializable dict for the model to read. Failures the
model can act on come back as ``{"error": ...}``; auth, permission, rate-limit,
server and network failures raise, because no next tool call can fix them.
A ``NeevAIError`` that is neither an ``APIError`` nor a connection error is a
client-side failure the model can work around, such as a preview URL that never
became routable or an exec stream that ended without an exit status. A file
that is not UTF-8 is an error result too, while command output keeps its text
with U+FFFD in place of bad bytes. A ``resource_exhausted`` 429 on
``start_process`` is an error result as well: stopping a process or retrying
shortly is the model's next move, and so is an edge 524 on ``run_command``,
which means the command was silent too long.
"""

from __future__ import annotations

import asyncio
import json
import math
import re
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping
from typing import TYPE_CHECKING, Any, Literal, NoReturn, SupportsIndex, TypeAlias, TypeVar, cast

from typing_extensions import NotRequired, TypedDict

from neevai.errors import (
    APIConnectionError,
    APIError,
    BadRequestError,
    ConflictError,
    DeadlineExceededError,
    NeevAIError,
    NotFoundError,
    RateLimitError,
)

if TYPE_CHECKING:
    from neevai.handles.sandbox import AsyncSandbox, Sandbox
    from neevai.types import FileEntry, ProcessInfo, ProcessLogsPage, ProcessStatus, Snapshot

__all__ = [
    "DESCRIPTIONS",
    "PARAMETERS",
    "TITLES",
    "AsyncSandboxTools",
    "CheckpointToolResult",
    "DeletePathToolResult",
    "ExposePortToolResult",
    "ListProcessesToolResult",
    "ListedProcess",
    "MovePathToolResult",
    "ReadFileToolResult",
    "ReadProcessOutputToolResult",
    "RollbackToolResult",
    "RunCommandToolResult",
    "SandboxTools",
    "StartProcessToolResult",
    "StatPathToolResult",
    "StopProcessToolResult",
    "ToolErrorResult",
    "ToolName",
    "ToolResult",
    "WriteFileToolResult",
]

ToolName = Literal[
    "run_command",
    "write_file",
    "read_file",
    "expose_port",
    "checkpoint",
    "rollback",
    "start_process",
    "read_process_output",
    "stop_process",
    "stat_path",
    "move_path",
    "delete_path",
    "list_processes",
]


class ToolErrorResult(TypedDict):
    """A failure the model can act on with a different next call."""

    error: str


class RunCommandToolResult(TypedDict):
    """Result of run_command; a non-zero exit_code is a result, not an error."""

    exit_code: int
    stdout: str
    stderr: str


class WriteFileToolResult(TypedDict):
    """Result of write_file."""

    bytes_written: int


class ReadFileToolResult(TypedDict):
    """Result of read_file; next_offset and eof are present on a paged read."""

    content: str
    next_offset: NotRequired[int]
    eof: NotRequired[bool]


class ExposePortToolResult(TypedDict):
    """Result of expose_port."""

    preview_url: str


class CheckpointToolResult(TypedDict):
    """Result of checkpoint."""

    checkpoint_id: str


class RollbackToolResult(TypedDict):
    """Result of rollback."""

    ok: Literal[True]


class StartProcessToolResult(TypedDict):
    """Result of start_process."""

    process_id: str


class ReadProcessOutputToolResult(TypedDict):
    """Result of read_process_output; exit_code is present once exited, while the status is kept."""

    stdout: str
    stderr: str
    cursor: int
    state: Literal["running", "exited"]
    dropped: bool
    exit_code: NotRequired[int | None]


class StopProcessToolResult(TypedDict):
    """Result of stop_process; ok is False when the process had already exited."""

    ok: bool


class StatPathToolResult(TypedDict):
    """Result of stat_path; only exists is present when the path does not exist."""

    exists: bool
    type: NotRequired[Literal["file", "directory", "symlink"]]
    size: NotRequired[int]
    modified_time: NotRequired[str]


class MovePathToolResult(TypedDict):
    """Result of move_path."""

    ok: Literal[True]


class DeletePathToolResult(TypedDict):
    """Result of delete_path."""

    ok: Literal[True]


class ListedProcess(TypedDict):
    """One process in list_processes; exit_code is present once exited."""

    process_id: str
    command: str
    state: Literal["running", "exited"]
    exit_code: NotRequired[int | None]


class ListProcessesToolResult(TypedDict):
    """Result of list_processes."""

    processes: list[ListedProcess]


ToolResult: TypeAlias = (
    ToolErrorResult
    | RunCommandToolResult
    | WriteFileToolResult
    | ReadFileToolResult
    | ExposePortToolResult
    | CheckpointToolResult
    | RollbackToolResult
    | StartProcessToolResult
    | ReadProcessOutputToolResult
    | StopProcessToolResult
    | StatPathToolResult
    | MovePathToolResult
    | DeletePathToolResult
    | ListProcessesToolResult
)

_R = TypeVar("_R")

# Per-stream cap: keep the start (what ran) and the end (how it ended).
_MAX_OUTPUT_BYTES = 10_000
_HEAD_BYTES = 4_000
_TAIL_BYTES = 6_000

_DEFAULT_TIMEOUT_S = 60
_MAX_TIMEOUT_S = 600
_CHECKPOINT_TIMEOUT_S = 300
_CHECKPOINT_POLL_S = 2.0

# sandboxd's blocking process get has a 5-minute ceiling and no per-call bound,
# so wait_s is a bounded poll instead.
_MAX_WAIT_S = 60
_WAIT_POLL_S = 1.0

# Error results keep only their first line, cut to this many characters, so an
# HTML error page from a proxy cannot flood the model's context.
_MAX_ERROR_CHARS = 500
_TIMEOUT_ERROR = "timed out"
_EDGE_TIMEOUT_STATUS = 524
_EDGE_TIMEOUT_ERROR = (
    "the command printed nothing for about 2 minutes and the connection was cut; "
    "it may still be running. Use start_process for long or quiet commands"
)

# SDK errors the model can recover from by changing its next call.
_RECOVERABLE = (BadRequestError, NotFoundError, ConflictError, DeadlineExceededError)


def _refuse(self: object, *args: object, **kwargs: object) -> NoReturn:
    raise TypeError(f"{type(self).__name__} is read-only")


def _thaw(value: Any) -> Any:
    """Returns a plain, mutable deep copy of frozen tool metadata."""
    if isinstance(value, dict):
        return {k: _thaw(v) for k, v in cast("dict[str, Any]", value).items()}
    if isinstance(value, list):
        return [_thaw(v) for v in cast("Iterable[Any]", value)]
    return value


class _FrozenDict(dict[str, Any]):
    """A dict that refuses changes, so shared tool metadata stays intact.

    It still serializes as JSON, and copy, deepcopy and pickle give plain dicts,
    since agent frameworks copy a schema before rewriting it.
    """

    __setitem__ = _refuse  # pyright: ignore[reportAssignmentType]
    __delitem__ = _refuse  # pyright: ignore[reportAssignmentType]
    __ior__ = _refuse  # pyright: ignore[reportAssignmentType]
    clear = _refuse  # pyright: ignore[reportAssignmentType]
    pop = _refuse  # pyright: ignore[reportAssignmentType]
    popitem = _refuse  # pyright: ignore[reportAssignmentType]
    setdefault = _refuse  # pyright: ignore[reportAssignmentType]
    update = _refuse  # pyright: ignore[reportAssignmentType]

    def __copy__(self) -> dict[str, Any]:
        return dict(self)

    def __deepcopy__(self, memo: dict[int, Any]) -> dict[str, Any]:
        thawed: dict[str, Any] = _thaw(self)
        return thawed

    def __reduce_ex__(self, protocol: SupportsIndex) -> tuple[Any, ...]:
        return (dict, (_thaw(self),))


class _FrozenList(list[Any]):
    """A list that refuses changes; a real list because schema checkers reject tuples.

    Like _FrozenDict, copy, deepcopy and pickle give plain lists.
    """

    __setitem__ = _refuse  # pyright: ignore[reportAssignmentType]
    __delitem__ = _refuse  # pyright: ignore[reportAssignmentType]
    __iadd__ = _refuse  # pyright: ignore[reportAssignmentType]
    __imul__ = _refuse  # pyright: ignore[reportAssignmentType]
    append = _refuse  # pyright: ignore[reportAssignmentType]
    extend = _refuse  # pyright: ignore[reportAssignmentType]
    insert = _refuse  # pyright: ignore[reportAssignmentType]
    pop = _refuse  # pyright: ignore[reportAssignmentType]
    remove = _refuse  # pyright: ignore[reportAssignmentType]
    clear = _refuse  # pyright: ignore[reportAssignmentType]
    sort = _refuse  # pyright: ignore[reportAssignmentType]
    reverse = _refuse  # pyright: ignore[reportAssignmentType]

    def __copy__(self) -> list[Any]:
        return list(self)

    def __deepcopy__(self, memo: dict[int, Any]) -> list[Any]:
        thawed: list[Any] = _thaw(self)
        return thawed

    def __reduce_ex__(self, protocol: SupportsIndex) -> tuple[Any, ...]:
        return (list, (_thaw(self),))


def _freeze(value: Any) -> Any:
    """Returns a read-only deep copy: dicts become _FrozenDict and lists _FrozenList."""
    if isinstance(value, dict):
        items = cast("dict[str, Any]", value).items()
        return _FrozenDict({k: _freeze(v) for k, v in items})
    if isinstance(value, (list, tuple)):
        return _FrozenList(_freeze(v) for v in cast("list[Any]", value))
    return value


DESCRIPTIONS: Mapping[str, str] = _freeze(
    {
        "run_command": (
            "Run a shell command in the sandbox with sh -lc and return exit_code, stdout and stderr. "
            "State persists between calls. Output over 10 KB is cut in the middle. "
            "A non-zero exit_code is a normal result: read stderr and try again. "
            "A command that prints nothing for about 2 minutes is cut off by the network, "
            "so run long or quiet work with start_process if you have it."
        ),
        "write_file": "Write a UTF-8 text file in the sandbox. path is relative to /workspace, or absolute inside /workspace.",
        "read_file": (
            "Read a UTF-8 text file from the sandbox. path is relative to /workspace, or absolute inside /workspace. "
            "Without offset or length, content over 10 KB is cut in the middle. "
            "To read a large file in full, pass offset (bytes, default 0) and length (bytes, 1 to 10000) "
            "and keep reading from the returned next_offset until eof is true."
        ),
        "expose_port": (
            "Make a server listening on this port in the sandbox reachable at a public HTTPS preview URL, and return it. "
            "Anyone with the URL can open it without logging in."
        ),
        "checkpoint": "Save the sandbox's full state and return a checkpoint_id. Take one before a risky step.",
        "rollback": "Roll the sandbox back to a checkpoint_id from checkpoint. Every change since that checkpoint is lost.",
        "start_process": (
            "Start a shell command in the background with sh -lc and return its process_id at once. "
            "Use it for servers, builds and anything that may outlast a run_command. "
            "A process left running is killed after an hour. "
            "A resource_exhausted error means the sandbox is at its limit of processes or in-flight requests: "
            "stop a process you no longer need, or retry shortly."
        ),
        "read_process_output": (
            "Read a background process's new stdout and stderr since cursor; pass the returned cursor to the next call. "
            "state is running or exited, with exit_code once exited. "
            "Output over 10 KB per stream is cut in the middle, and the returned cursor still moves past the cut part. "
            "dropped: true means output was overwritten because the buffer keeps about 1 MB, so read more often. "
            "wait_s (0 to 60, default 0) first waits up to that many seconds for a running process to exit, "
            "which saves turns while following a long command. "
            "An exited process's status is kept for about 10 minutes, after which exit_code is no longer returned."
        ),
        "stop_process": (
            "Stop a background process by sending it SIGTERM. ok is false if it had already exited. "
            "An exited process's status is kept for about 10 minutes."
        ),
        "stat_path": (
            "Report whether a path exists in the sandbox and, when it does, its type (file, directory or symlink), "
            "size in bytes and modification time. path is relative to /workspace, or absolute inside /workspace. "
            "A missing path is exists: false, not an error."
        ),
        "move_path": (
            "Move or rename a file or directory in the sandbox, creating the destination's parent directories. "
            "Both paths are relative to /workspace, or absolute inside /workspace. "
            "An existing file at the destination is replaced; an existing directory there is an error."
        ),
        "delete_path": (
            "Delete a file or directory in the sandbox. A directory that is not empty is deleted only with recursive: true. "
            "A missing path is an error. "
            "Deletion cannot be undone, so take a checkpoint first if you have it and may need the files back."
        ),
        "list_processes": (
            "List the background processes started in this sandbox, each with its process_id, command, state "
            "and exit_code once exited. Use it to find a process_id you no longer have. "
            "An exited process is listed for about 10 minutes."
        ),
    }
)

TITLES: Mapping[str, str] = _freeze(
    {
        "run_command": "Run a command",
        "write_file": "Write a file",
        "read_file": "Read a file",
        "expose_port": "Expose a port",
        "checkpoint": "Save a checkpoint",
        "rollback": "Roll back to a checkpoint",
        "start_process": "Start a background process",
        "read_process_output": "Read a process's output",
        "stop_process": "Stop a process",
        "stat_path": "Check a path",
        "move_path": "Move or rename a path",
        "delete_path": "Delete a file or directory",
        "list_processes": "List processes",
    }
)


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


_COMMAND = {"type": "string", "description": "Shell command, run with sh -lc."}
_CWD = {
    "type": "string",
    "description": "Working directory, relative to /workspace or absolute inside /workspace. Default /workspace.",
}
_PATH = {
    "type": "string",
    "description": "File path, relative to /workspace or absolute inside /workspace.",
}
_PROCESS_ID = {"type": "string", "description": "process_id returned by start_process."}
_ANY_PATH = {
    "type": "string",
    "description": "Path, relative to /workspace or absolute inside /workspace.",
}

# _freeze copies every schema, so no two tools share a property dict.
PARAMETERS: Mapping[str, Mapping[str, Any]] = _freeze(
    {
        "run_command": _schema(
            {
                "command": _COMMAND,
                "cwd": _CWD,
                "timeout_s": {
                    "type": "number",
                    "description": "Seconds to wait for the command to finish, 1 to 600. Default 60.",
                    "minimum": 1,
                    "maximum": 600,
                    "default": 60,
                },
            },
            ["command"],
        ),
        "write_file": _schema(
            {
                "path": _PATH,
                "content": {"type": "string", "description": "UTF-8 text to write."},
            },
            ["path", "content"],
        ),
        "read_file": _schema(
            {
                "path": _PATH,
                "offset": {
                    "type": "integer",
                    "description": "Byte to start reading at. Default 0.",
                    "minimum": 0,
                },
                "length": {
                    "type": "integer",
                    "description": "Bytes to read, 1 to 10000. Default 10000 when offset is given.",
                    "minimum": 1,
                    "maximum": 10000,
                },
            },
            ["path"],
        ),
        "expose_port": _schema(
            {
                "port": {
                    "type": "integer",
                    "description": "Port the server listens on inside the sandbox.",
                    "minimum": 1,
                    "maximum": 65535,
                },
            },
            ["port"],
        ),
        "checkpoint": _schema(
            {"label": {"type": "string", "description": "Optional name for the checkpoint."}},
            [],
        ),
        "rollback": _schema(
            {
                "checkpoint_id": {
                    "type": "string",
                    "description": "checkpoint_id returned by checkpoint.",
                },
            },
            ["checkpoint_id"],
        ),
        "start_process": _schema({"command": _COMMAND, "cwd": _CWD}, ["command"]),
        "read_process_output": _schema(
            {
                "process_id": _PROCESS_ID,
                "cursor": {
                    "type": "integer",
                    "description": "cursor returned by the previous read. Omit to read from the oldest output kept.",
                    "minimum": 0,
                },
                "wait_s": {
                    "type": "number",
                    "description": "Seconds to wait for a running process to exit before reading, 0 to 60. Default 0.",
                    "minimum": 0,
                    "maximum": 60,
                    "default": 0,
                },
            },
            ["process_id"],
        ),
        "stop_process": _schema({"process_id": _PROCESS_ID}, ["process_id"]),
        "stat_path": _schema({"path": _ANY_PATH}, ["path"]),
        "move_path": _schema(
            {
                "source": {
                    "type": "string",
                    "description": "Path to move, relative to /workspace or absolute inside /workspace.",
                },
                "destination": {
                    "type": "string",
                    "description": "New path, relative to /workspace or absolute inside /workspace.",
                },
            },
            ["source", "destination"],
        ),
        "delete_path": _schema(
            {
                "path": {
                    "type": "string",
                    "description": "Path to delete, relative to /workspace or absolute inside /workspace.",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Delete a non-empty directory and everything in it. Default false.",
                },
            },
            ["path"],
        ),
        "list_processes": _schema({}, []),
    }
)


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


async def _async_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _now() -> float:
    return time.monotonic()


def _truncate(text: str) -> str:
    """Returns text unchanged up to _MAX_OUTPUT_BYTES, else its head and tail around a marker."""
    data = text.encode("utf-8")
    if len(data) <= _MAX_OUTPUT_BYTES:
        return text
    dropped = len(data) - _HEAD_BYTES - _TAIL_BYTES
    head = data[:_HEAD_BYTES].decode("utf-8", errors="replace")
    tail = data[-_TAIL_BYTES:].decode("utf-8", errors="replace")
    return f"{head}\n…[{dropped} bytes truncated]…\n{tail}"


def _short_error(text: str) -> str:
    """Returns the first line of text, cut to _MAX_ERROR_CHARS with a trailing marker."""
    line = text.split("\n", 1)[0]
    if len(line) <= _MAX_ERROR_CHARS:
        return line
    return line[:_MAX_ERROR_CHARS] + "…"


# Plain decimal numbers only, so "1_000", "0x10" and "inf" are not numbers here
# or in the JS SDK.
_NUMERIC = re.compile(r"[+-]?([0-9]+\.?[0-9]*|\.[0-9]+)([eE][+-]?[0-9]+)?", re.ASCII)
# ASCII whitespace only, the same set the JS SDK strips.
_ASCII_SPACE = " \t\n\r\f\v"


def _parse_number(value: object) -> float | None:
    """Reads a model-supplied number or numeric string; None for bools, non-finite and anything else."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip(_ASCII_SPACE)
        if not _NUMERIC.fullmatch(value):
            return None
    elif not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _number(value: object, default: float) -> float:
    """Reads a model-supplied number, falling back to default when it is not one."""
    number = _parse_number(value)
    return float(default) if number is None else number


def _seconds(value: float) -> str:
    """Formats seconds the way JavaScript prints a number: 30 not 30.0, 2.5 as is."""
    return str(int(value)) if value.is_integer() else repr(value)


def _names(allow_preview: bool, allow_rollback: bool, allow_processes: bool) -> list[ToolName]:
    names: list[ToolName] = [
        "run_command",
        "write_file",
        "read_file",
        "stat_path",
        "move_path",
        "delete_path",
    ]
    if allow_preview:
        names.append("expose_port")
    if allow_rollback:
        names.extend(("checkpoint", "rollback"))
    if allow_processes:
        names.extend(("start_process", "read_process_output", "stop_process", "list_processes"))
    return names


def _check_client_context(sandbox: Sandbox | AsyncSandbox, needs_client: bool) -> None:
    # A handle built without a client can run commands but cannot reach the
    # lifecycle API; fail at construction, not on the model's first call.
    if needs_client and sandbox.sandboxes is None:
        raise ValueError(
            "allow_preview and allow_rollback need a sandbox handle with client context, "
            "such as one from client.sandboxes.create() or get()."
        )


def _disabled(name: str) -> ToolErrorResult:
    return {"error": f"{name} is not enabled for this agent"}


def _check_args(name: str, args: object) -> dict[str, Any] | str:
    """Checks model-supplied args against the tool's schema.

    Returns the args to call with, with integers parsed from numeric strings, or
    the reason they do not fit: the first unknown key, then the first missing
    required key, then the first property of the wrong type, in schema order.
    """
    if args is None:
        args = {}
    if not isinstance(args, Mapping):
        return "expected an object"
    checked: dict[str, Any] = {str(k): v for k, v in args.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    schema = PARAMETERS[name]
    for key in checked:
        if key not in schema["properties"]:
            return f"got an unexpected keyword argument {json.dumps(key, ensure_ascii=False)}"
    for key in schema["required"]:
        if key not in checked:
            return f"missing a required argument: {json.dumps(key, ensure_ascii=False)}"
    for field, prop in schema["properties"].items():
        if field not in checked:
            continue
        value = checked[field]
        kind: str = prop["type"]
        if value is None and field not in schema["required"]:
            continue
        if kind == "string":
            if not isinstance(value, str):
                return f"{field} must be {kind}"
            continue
        if kind == "boolean":
            if not isinstance(value, bool):
                return f"{field} must be {kind}"
            continue
        number = _parse_number(value)
        if number is None or (kind == "integer" and not number.is_integer()):
            return f"{field} must be {kind}"
        if kind == "integer":
            checked[field] = int(number)
    return checked


def _milliseconds(seconds: float) -> int:
    # Half up like JavaScript's Math.round; Python's round() rounds half to even.
    return math.floor(seconds * 1000 + 0.5)


def _command_timeout(timeout_s: object) -> float:
    return float(min(max(_number(timeout_s, _DEFAULT_TIMEOUT_S), 1), _MAX_TIMEOUT_S))


def _wait_seconds(wait_s: object) -> float:
    return float(min(max(_number(wait_s, 0), 0), _MAX_WAIT_S))


def _api_error_text(e: APIError) -> str:
    """Returns the model-facing text of an API error, the same in both SDKs.

    It is "HTTP <status> <code>: <message>", leaving out the code or message when
    absent; the request method, URL and request id never reach the model.
    """
    text = f"HTTP {e.status_code}"
    if e.code:
        text += f" {e.code}"
    message = e._text or e.details
    if message:
        text += f": {message}"
    return _short_error(text)


def _error_result(e: Exception, timeout_error: str) -> ToolErrorResult:
    """Turns an error the model can act on into a short error result; re-raises the rest."""
    if isinstance(e, DeadlineExceededError):
        # The 504 body is often a proxy's HTML page, so say what happened instead.
        return {"error": timeout_error}
    if isinstance(e, _RECOVERABLE):
        return {"error": _api_error_text(e)}
    if isinstance(e, UnicodeDecodeError):
        return {"error": "not UTF-8 text"}
    if isinstance(e, NeevAIError) and not isinstance(e, (APIError, APIConnectionError)):
        return {"error": _short_error(str(e))}
    raise e


def _exec_error(e: APIError) -> ToolErrorResult:
    # The edge in front of the runtime answers 524 when a response stays silent
    # for about 2 minutes; the model can fix that by using start_process, so it
    # gets an error result. Every other status keeps its usual handling.
    if e.status_code != _EDGE_TIMEOUT_STATUS:
        raise e
    return {"error": _EDGE_TIMEOUT_ERROR}


def _start_error(e: RateLimitError) -> ToolErrorResult:
    # sandboxd answers 429 resource_exhausted at both its process cap and its
    # in-flight request cap; stopping a process or retrying fixes either, so the
    # model gets it. Any other 429 raises.
    if e.code != "resource_exhausted":
        raise e
    return {"error": _api_error_text(e)}


def _checkpoint_failed(snap: Snapshot) -> ToolErrorResult:
    reason = f": {snap.error_message}" if snap.error_message else ""
    return {"error": _short_error(f"checkpoint {snap.id} failed{reason}")}


def _checkpoint_timed_out(snap: Snapshot) -> ToolErrorResult:
    return {"error": f"checkpoint {snap.id} not ready after {_CHECKPOINT_TIMEOUT_S} s"}


def _page_result(page: ProcessLogsPage) -> ReadProcessOutputToolResult:
    stdout = "".join(e.data for e in page.entries if e.stream == "stdout")
    stderr = "".join(e.data for e in page.entries if e.stream == "stderr")
    return {
        "stdout": _truncate(stdout),
        "stderr": _truncate(stderr),
        "cursor": page.cursor,
        "state": page.state,
        "dropped": page.dropped,
    }


def _read_window(offset: object, length: object) -> tuple[int, int]:
    """Returns the paged read's start and size, size clamped to 1-10000."""
    start = max(int(_number(offset, 0)), 0)
    size = min(max(int(_number(length, _MAX_OUTPUT_BYTES)), 1), _MAX_OUTPUT_BYTES)
    return start, size


def _is_continuation(byte: int) -> bool:
    return 0x80 <= byte <= 0xBF


def _sequence_length(lead: int) -> int:
    if lead >= 0xF0:
        return 4 if lead <= 0xF7 else 1
    if lead >= 0xE0:
        return 3
    return 2 if lead >= 0xC0 else 1


def _page_text(data: bytes, offset: int, size: int) -> ReadFileToolResult:
    """Turns up to size + 7 bytes read at offset into a page of whole UTF-8 characters that always advances."""
    start = 0
    while start < 3 and start < len(data) and _is_continuation(data[start]):
        start += 1
    if start == 3 and len(data) > 3 and _is_continuation(data[3]):
        raise UnicodeDecodeError("utf-8", data, 3, 4, "invalid continuation byte")
    end = max(min(size, len(data)), start)
    # Only a cut window can end mid-character; at the real end it is bad UTF-8.
    if len(data) > end:
        lead = end - 1
        while lead > start and _is_continuation(data[lead]):
            lead -= 1
        if lead >= start and _sequence_length(data[lead]) > end - lead:
            end = lead
    if end == start and start < len(data):
        end = min(start + _sequence_length(data[start]), len(data))
    return {
        "content": data[start:end].decode("utf-8"),
        "next_offset": offset + end,
        "eof": end >= len(data),
    }


def _listed(proc: ProcessInfo) -> ListedProcess:
    # Show the command the model passed to start_process, not its sh -lc wrapper.
    if proc.name == "sh" and proc.args[:1] == ["-lc"]:
        words = proc.args[1:]
    else:
        words = [proc.name, *proc.args]
    listed: ListedProcess = {
        "process_id": proc.process_id,
        "command": " ".join(words),
        "state": proc.state,
    }
    if proc.state == "exited":
        listed["exit_code"] = proc.exit_code
    return listed


def _is_missing_path(e: NotFoundError) -> bool:
    # Only the runtime's own not_found envelope means the path is missing; a proxy 404 does not.
    return e.status_code == 404 and e.body is not None and e.body.get("reason_code") == "not_found"


def _stat_result(entry: FileEntry) -> StatPathToolResult:
    return {
        "exists": True,
        "type": entry.type,
        "size": entry.size,
        "modified_time": entry.modified_time,
    }


class SandboxTools:
    """The sandbox tool contract bound to one ``Sandbox``; opt-in tools stay off unless enabled."""

    def __init__(
        self,
        sandbox: Sandbox,
        *,
        allow_preview: bool = False,
        allow_rollback: bool = False,
        allow_processes: bool = False,
    ) -> None:
        """Binds the tools to ``sandbox``.

        Args:
            sandbox: The sandbox the tools act on.
            allow_preview: Enable expose_port, which makes a sandbox port public.
            allow_rollback: Enable checkpoint and rollback.
            allow_processes: Enable start_process, read_process_output, stop_process
                and list_processes.

        Raises:
            ValueError: allow_preview or allow_rollback is set on a handle with no client context.
        """
        _check_client_context(sandbox, allow_preview or allow_rollback)
        self._sandbox = sandbox
        self._allow_preview = allow_preview
        self._allow_rollback = allow_rollback
        self._allow_processes = allow_processes

    def names(self) -> list[ToolName]:
        """Returns the tools to register with the model, in contract order."""
        return _names(self._allow_preview, self._allow_rollback, self._allow_processes)

    def call(self, name: str, args: Mapping[str, Any] | None = None) -> ToolResult:
        """Runs the tool the model named with the arguments it sent.

        Args:
            name: The model-facing tool name.
            args: The tool's arguments, as decoded from the model's JSON.

        Returns:
            The tool's result, or an error result for an unknown or disabled tool
            or arguments that do not fit it.
        """
        if name not in DESCRIPTIONS:
            return {"error": _short_error(f"unknown tool: {name}")}
        if name not in self.names():
            return _disabled(name)
        method: Callable[..., ToolResult] = getattr(self, name)
        checked = _check_args(name, args)
        if isinstance(checked, str):
            return {"error": _short_error(f"invalid arguments for {name}: {checked}")}
        return method(**checked)

    def run_command(
        self, command: str, cwd: str | None = None, timeout_s: float | None = None
    ) -> RunCommandToolResult | ToolErrorResult:
        """Runs command with sh -lc; a non-zero exit is a result, not an error.

        Args:
            command: Shell command to run.
            cwd: Working directory, relative to /workspace or absolute inside it.
            timeout_s: Seconds before the command is abandoned, clamped to 1-600.
                Default 60; a non-numeric value takes the default.
        """
        timeout = _command_timeout(timeout_s)

        def run() -> RunCommandToolResult | ToolErrorResult:
            try:
                # Replace bytes that are not UTF-8 rather than lose all of the output.
                r = self._sandbox._connection()._exec(
                    "sh",
                    args=["-lc", command],
                    cwd=cwd,
                    timeout_ms=_milliseconds(timeout),
                    errors="replace",
                )
            except APIError as e:
                return _exec_error(e)
            return {
                "exit_code": r.exit_code,
                "stdout": _truncate(r.stdout),
                "stderr": _truncate(r.stderr),
            }

        return self._recover(
            run, timeout_error=f"command did not finish within {_seconds(timeout)} s"
        )

    def write_file(self, path: str, content: str) -> WriteFileToolResult | ToolErrorResult:
        """Writes a UTF-8 text file and reports the bytes written.

        Args:
            path: File path, relative to /workspace or absolute inside it.
            content: Text to write.
        """

        def write() -> WriteFileToolResult:
            return {"bytes_written": self._sandbox.files.write(path, content)["bytes_written"]}

        return self._recover(write)

    def read_file(
        self, path: str, offset: int | None = None, length: int | None = None
    ) -> ReadFileToolResult | ToolErrorResult:
        """Reads a UTF-8 text file, truncated like command output unless paged.

        Args:
            path: File path, relative to /workspace or absolute inside it.
            offset: Byte to start a paged read at. Default 0.
            length: Bytes in a paged read, clamped to 1-10000. Default 10000.
        """
        if offset is None and length is None:

            def read() -> ReadFileToolResult:
                return {"content": _truncate(self._sandbox.files.read_text(path))}

            return self._recover(read)
        start, size = _read_window(offset, length)

        def page() -> ReadFileToolResult:
            data = self._sandbox.files.read(path, offset=start, length=size + 7)
            return _page_text(data, start, size)

        return self._recover(page)

    def stat_path(self, path: str) -> StatPathToolResult | ToolErrorResult:
        """Reports whether path exists and, if so, its type, size and modification time.

        Args:
            path: Path, relative to /workspace or absolute inside it.
        """

        def stat() -> StatPathToolResult:
            try:
                return _stat_result(self._sandbox.files.stat(path))
            except NotFoundError as e:
                if not _is_missing_path(e):
                    raise
                return {"exists": False}

        return self._recover(stat)

    def move_path(self, source: str, destination: str) -> MovePathToolResult | ToolErrorResult:
        """Moves or renames a file or directory.

        Args:
            source: Path to move, relative to /workspace or absolute inside it.
            destination: New path, relative to /workspace or absolute inside it.
        """

        def move() -> MovePathToolResult:
            self._sandbox.files.move(source, destination)
            return {"ok": True}

        return self._recover(move)

    def delete_path(
        self, path: str, recursive: bool | None = None
    ) -> DeletePathToolResult | ToolErrorResult:
        """Deletes a file or directory; a non-empty directory needs recursive.

        Args:
            path: Path to delete, relative to /workspace or absolute inside it.
            recursive: Delete a non-empty directory and its contents. Only True enables it.
        """

        def delete() -> DeletePathToolResult:
            self._sandbox.files.remove(path, recursive=recursive is True)
            return {"ok": True}

        return self._recover(delete)

    def expose_port(self, port: int) -> ExposePortToolResult | ToolErrorResult:
        """Exposes port and returns its preview URL once it is routable.

        Args:
            port: Port the server listens on inside the sandbox.
        """
        if not self._allow_preview:
            return _disabled("expose_port")

        def expose() -> ExposePortToolResult:
            return {"preview_url": self._sandbox.get_url(port)}

        return self._recover(expose)

    def checkpoint(self, label: str | None = None) -> CheckpointToolResult | ToolErrorResult:
        """Snapshots the sandbox and waits up to 300 s until it can be rolled back to.

        Args:
            label: Optional name for the snapshot.
        """
        if not self._allow_rollback:
            return _disabled("checkpoint")

        def take() -> CheckpointToolResult | ToolErrorResult:
            sandboxes = self._sandbox.sandboxes
            assert sandboxes is not None  # checked in __init__
            scope = self._sandbox.scope
            snap = self._sandbox.snapshot({"name": label} if label else None)
            # The SDK has no snapshot wait, so poll until Ready, Failed, or the deadline.
            deadline = _now() + _CHECKPOINT_TIMEOUT_S
            while True:
                if snap.status == "Ready":
                    return {"checkpoint_id": str(snap.id)}
                if snap.status == "Failed":
                    return _checkpoint_failed(snap)
                remaining = deadline - _now()
                if remaining <= 0:
                    return _checkpoint_timed_out(snap)
                _sleep(min(_CHECKPOINT_POLL_S, remaining))
                snap = sandboxes.get_snapshot(
                    snap.id,
                    org_id=scope.org_id if scope else None,
                    project_id=scope.project_id if scope else None,
                )

        return self._recover(take)

    def rollback(self, checkpoint_id: str) -> RollbackToolResult | ToolErrorResult:
        """Rolls the sandbox back in place to a checkpoint.

        Args:
            checkpoint_id: checkpoint_id returned by checkpoint.
        """
        if not self._allow_rollback:
            return _disabled("rollback")

        def roll() -> RollbackToolResult:
            self._sandbox.rollback(checkpoint_id)
            return {"ok": True}

        return self._recover(roll)

    def start_process(
        self, command: str, cwd: str | None = None
    ) -> StartProcessToolResult | ToolErrorResult:
        """Starts command with sh -lc in the background and returns its process id.

        Args:
            command: Shell command to run.
            cwd: Working directory, relative to /workspace or absolute inside it.
        """
        if not self._allow_processes:
            return _disabled("start_process")

        def start() -> StartProcessToolResult | ToolErrorResult:
            try:
                proc = self._sandbox.processes.start("sh", args=["-lc", command], cwd=cwd)
            except RateLimitError as e:
                return _start_error(e)
            return {"process_id": proc.id}

        return self._recover(start)

    def read_process_output(
        self, process_id: str, cursor: int | None = None, wait_s: float | None = None
    ) -> ReadProcessOutputToolResult | ToolErrorResult:
        """Returns a process's output since cursor, split by stream, and its exit code once exited.

        Args:
            process_id: process_id returned by start_process.
            cursor: cursor returned by the previous read; None reads from the oldest output kept.
            wait_s: Seconds to wait for a running process to exit before reading,
                clamped to 0-60. Default 0; a non-numeric value takes the default.
        """
        if not self._allow_processes:
            return _disabled("read_process_output")

        def read() -> ReadProcessOutputToolResult:
            processes = self._sandbox.processes
            status: ProcessStatus | None = None
            wait = _wait_seconds(wait_s)
            if wait > 0:
                deadline = _now() + wait
                while True:
                    try:
                        status = processes.get(process_id)
                    except NotFoundError:
                        # Let logs report the unknown or expired process.
                        break
                    remaining = deadline - _now()
                    if status.state == "exited" or remaining <= 0:
                        break
                    _sleep(min(_WAIT_POLL_S, remaining))
            page = processes.logs(process_id, cursor=cursor)
            result = _page_result(page)
            # The logs page carries no exit code; an exited page already holds all output.
            if page.state == "exited":
                if status is None or status.state != "exited":
                    try:
                        status = processes.get(process_id)
                    except NotFoundError:
                        # Status was garbage-collected after logs answered; keep the page.
                        return result
                result["exit_code"] = status.exit_code
            return result

        return self._recover(read)

    def stop_process(self, process_id: str) -> StopProcessToolResult | ToolErrorResult:
        """Sends SIGTERM to a process; ok is False when it had already exited.

        Args:
            process_id: process_id returned by start_process.
        """
        if not self._allow_processes:
            return _disabled("stop_process")

        def stop() -> StopProcessToolResult:
            return {"ok": self._sandbox.processes.kill(process_id)}

        return self._recover(stop)

    def list_processes(self) -> ListProcessesToolResult | ToolErrorResult:
        """Lists the background processes with their commands, states and exit codes."""
        if not self._allow_processes:
            return _disabled("list_processes")

        def list_all() -> ListProcessesToolResult:
            return {"processes": [_listed(p) for p in self._sandbox.processes.list()]}

        return self._recover(list_all)

    def _recover(
        self, fn: Callable[[], _R], timeout_error: str = _TIMEOUT_ERROR
    ) -> _R | ToolErrorResult:
        try:
            return fn()
        except (NeevAIError, UnicodeDecodeError) as e:
            return _error_result(e, timeout_error)


class AsyncSandboxTools:
    """The sandbox tool contract bound to one ``AsyncSandbox``. See :class:`SandboxTools`."""

    def __init__(
        self,
        sandbox: AsyncSandbox,
        *,
        allow_preview: bool = False,
        allow_rollback: bool = False,
        allow_processes: bool = False,
    ) -> None:
        """Binds the tools to ``sandbox``. Arguments as for :class:`SandboxTools`.

        Raises:
            ValueError: allow_preview or allow_rollback is set on a handle with no client context.
        """
        _check_client_context(sandbox, allow_preview or allow_rollback)
        self._sandbox = sandbox
        self._allow_preview = allow_preview
        self._allow_rollback = allow_rollback
        self._allow_processes = allow_processes

    def names(self) -> list[ToolName]:
        """Returns the tools to register with the model, in contract order."""
        return _names(self._allow_preview, self._allow_rollback, self._allow_processes)

    async def call(self, name: str, args: Mapping[str, Any] | None = None) -> ToolResult:
        """Runs the tool the model named with the arguments it sent. See :meth:`SandboxTools.call`."""
        if name not in DESCRIPTIONS:
            return {"error": _short_error(f"unknown tool: {name}")}
        if name not in self.names():
            return _disabled(name)
        method: Callable[..., Awaitable[ToolResult]] = getattr(self, name)
        checked = _check_args(name, args)
        if isinstance(checked, str):
            return {"error": _short_error(f"invalid arguments for {name}: {checked}")}
        return await method(**checked)

    async def run_command(
        self, command: str, cwd: str | None = None, timeout_s: float | None = None
    ) -> RunCommandToolResult | ToolErrorResult:
        """Runs command with sh -lc. See :meth:`SandboxTools.run_command`."""
        timeout = _command_timeout(timeout_s)

        async def run() -> RunCommandToolResult | ToolErrorResult:
            try:
                # Replace bytes that are not UTF-8 rather than lose all of the output.
                r = await self._sandbox._connection()._exec(
                    "sh",
                    args=["-lc", command],
                    cwd=cwd,
                    timeout_ms=_milliseconds(timeout),
                    errors="replace",
                )
            except APIError as e:
                return _exec_error(e)
            return {
                "exit_code": r.exit_code,
                "stdout": _truncate(r.stdout),
                "stderr": _truncate(r.stderr),
            }

        return await self._recover(
            run, timeout_error=f"command did not finish within {_seconds(timeout)} s"
        )

    async def write_file(self, path: str, content: str) -> WriteFileToolResult | ToolErrorResult:
        """Writes a UTF-8 text file. See :meth:`SandboxTools.write_file`."""

        async def write() -> WriteFileToolResult:
            written = await self._sandbox.files.write(path, content)
            return {"bytes_written": written["bytes_written"]}

        return await self._recover(write)

    async def read_file(
        self, path: str, offset: int | None = None, length: int | None = None
    ) -> ReadFileToolResult | ToolErrorResult:
        """Reads a UTF-8 text file. See :meth:`SandboxTools.read_file`."""
        if offset is None and length is None:

            async def read() -> ReadFileToolResult:
                return {"content": _truncate(await self._sandbox.files.read_text(path))}

            return await self._recover(read)
        start, size = _read_window(offset, length)

        async def page() -> ReadFileToolResult:
            data = await self._sandbox.files.read(path, offset=start, length=size + 7)
            return _page_text(data, start, size)

        return await self._recover(page)

    async def stat_path(self, path: str) -> StatPathToolResult | ToolErrorResult:
        """Reports whether path exists. See :meth:`SandboxTools.stat_path`."""

        async def stat() -> StatPathToolResult:
            try:
                return _stat_result(await self._sandbox.files.stat(path))
            except NotFoundError as e:
                if not _is_missing_path(e):
                    raise
                return {"exists": False}

        return await self._recover(stat)

    async def move_path(
        self, source: str, destination: str
    ) -> MovePathToolResult | ToolErrorResult:
        """Moves or renames a path. See :meth:`SandboxTools.move_path`."""

        async def move() -> MovePathToolResult:
            await self._sandbox.files.move(source, destination)
            return {"ok": True}

        return await self._recover(move)

    async def delete_path(
        self, path: str, recursive: bool | None = None
    ) -> DeletePathToolResult | ToolErrorResult:
        """Deletes a file or directory. See :meth:`SandboxTools.delete_path`."""

        async def delete() -> DeletePathToolResult:
            await self._sandbox.files.remove(path, recursive=recursive is True)
            return {"ok": True}

        return await self._recover(delete)

    async def expose_port(self, port: int) -> ExposePortToolResult | ToolErrorResult:
        """Exposes port. See :meth:`SandboxTools.expose_port`."""
        if not self._allow_preview:
            return _disabled("expose_port")

        async def expose() -> ExposePortToolResult:
            return {"preview_url": await self._sandbox.get_url(port)}

        return await self._recover(expose)

    async def checkpoint(self, label: str | None = None) -> CheckpointToolResult | ToolErrorResult:
        """Snapshots the sandbox. See :meth:`SandboxTools.checkpoint`."""
        if not self._allow_rollback:
            return _disabled("checkpoint")

        async def take() -> CheckpointToolResult | ToolErrorResult:
            sandboxes = self._sandbox.sandboxes
            assert sandboxes is not None  # checked in __init__
            scope = self._sandbox.scope
            snap = await self._sandbox.snapshot({"name": label} if label else None)
            deadline = _now() + _CHECKPOINT_TIMEOUT_S
            while True:
                if snap.status == "Ready":
                    return {"checkpoint_id": str(snap.id)}
                if snap.status == "Failed":
                    return _checkpoint_failed(snap)
                remaining = deadline - _now()
                if remaining <= 0:
                    return _checkpoint_timed_out(snap)
                await _async_sleep(min(_CHECKPOINT_POLL_S, remaining))
                snap = await sandboxes.get_snapshot(
                    snap.id,
                    org_id=scope.org_id if scope else None,
                    project_id=scope.project_id if scope else None,
                )

        return await self._recover(take)

    async def rollback(self, checkpoint_id: str) -> RollbackToolResult | ToolErrorResult:
        """Rolls the sandbox back. See :meth:`SandboxTools.rollback`."""
        if not self._allow_rollback:
            return _disabled("rollback")

        async def roll() -> RollbackToolResult:
            await self._sandbox.rollback(checkpoint_id)
            return {"ok": True}

        return await self._recover(roll)

    async def start_process(
        self, command: str, cwd: str | None = None
    ) -> StartProcessToolResult | ToolErrorResult:
        """Starts a background process. See :meth:`SandboxTools.start_process`."""
        if not self._allow_processes:
            return _disabled("start_process")

        async def start() -> StartProcessToolResult | ToolErrorResult:
            try:
                proc = await self._sandbox.processes.start("sh", args=["-lc", command], cwd=cwd)
            except RateLimitError as e:
                return _start_error(e)
            return {"process_id": proc.id}

        return await self._recover(start)

    async def read_process_output(
        self, process_id: str, cursor: int | None = None, wait_s: float | None = None
    ) -> ReadProcessOutputToolResult | ToolErrorResult:
        """Reads a process's output. See :meth:`SandboxTools.read_process_output`."""
        if not self._allow_processes:
            return _disabled("read_process_output")

        async def read() -> ReadProcessOutputToolResult:
            processes = self._sandbox.processes
            status: ProcessStatus | None = None
            wait = _wait_seconds(wait_s)
            if wait > 0:
                deadline = _now() + wait
                while True:
                    try:
                        status = await processes.get(process_id)
                    except NotFoundError:
                        break
                    remaining = deadline - _now()
                    if status.state == "exited" or remaining <= 0:
                        break
                    await _async_sleep(min(_WAIT_POLL_S, remaining))
            page = await processes.logs(process_id, cursor=cursor)
            result = _page_result(page)
            if page.state == "exited":
                if status is None or status.state != "exited":
                    try:
                        status = await processes.get(process_id)
                    except NotFoundError:
                        return result
                result["exit_code"] = status.exit_code
            return result

        return await self._recover(read)

    async def stop_process(self, process_id: str) -> StopProcessToolResult | ToolErrorResult:
        """Stops a background process. See :meth:`SandboxTools.stop_process`."""
        if not self._allow_processes:
            return _disabled("stop_process")

        async def stop() -> StopProcessToolResult:
            return {"ok": await self._sandbox.processes.kill(process_id)}

        return await self._recover(stop)

    async def list_processes(self) -> ListProcessesToolResult | ToolErrorResult:
        """Lists the background processes. See :meth:`SandboxTools.list_processes`."""
        if not self._allow_processes:
            return _disabled("list_processes")

        async def list_all() -> ListProcessesToolResult:
            return {"processes": [_listed(p) for p in await self._sandbox.processes.list()]}

        return await self._recover(list_all)

    async def _recover(
        self, fn: Callable[[], Awaitable[_R]], timeout_error: str = _TIMEOUT_ERROR
    ) -> _R | ToolErrorResult:
        try:
            return await fn()
        except (NeevAIError, UnicodeDecodeError) as e:
            return _error_result(e, timeout_error)
