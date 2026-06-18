"""Hand-written Pydantic schemas for sandboxd (data-plane) responses."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class FileWriteResponse(BaseModel):
    bytes_written: int


class FileListEntry(BaseModel):
    name: str
    type: Literal["file", "directory", "symlink"]
    path: str
    size: int
    mode: int
    permissions: str
    modified_time: str
    symlink_target: str | None = None


class FileListResponse(BaseModel):
    entries: list[FileListEntry]


class StdoutFrame(BaseModel):
    type: Literal["stdout"]
    data: str


class StderrFrame(BaseModel):
    type: Literal["stderr"]
    data: str


class ExitFrame(BaseModel):
    type: Literal["exit"]
    exit_code: int = 0


class ErrorFrame(BaseModel):
    type: Literal["error"]
    reason_code: str = "internal"
    message: str | None = None


ExecFrame = Annotated[
    StdoutFrame | StderrFrame | ExitFrame | ErrorFrame,
    Field(discriminator="type"),
]

ProcessLogFrame = Annotated[
    StdoutFrame | StderrFrame | ExitFrame,
    Field(discriminator="type"),
]


class RawProcessStatus(BaseModel):
    process_id: str
    state: Literal["running", "exited"]
    exit_code: int | None = None
    started_at: int


class RawProcessInfo(RawProcessStatus):
    name: str
    args: list[str]
    cwd: str | None = None


class RawProcessLogEntry(BaseModel):
    data: str


class RawProcessLogsPage(BaseModel):
    entries: list[RawProcessLogEntry]
    cursor: int
    dropped: bool
    state: Literal["running", "exited"]


class RawProcessListResponse(BaseModel):
    processes: list[RawProcessInfo]


class RawKillResponse(BaseModel):
    signalled: bool


class RawKillAllResponse(BaseModel):
    signalled_count: int
