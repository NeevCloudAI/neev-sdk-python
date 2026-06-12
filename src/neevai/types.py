from dataclasses import dataclass
from typing import Literal, TypedDict

from pydantic import BaseModel

__all__ = [
    "CreateSandboxParams",
    "EnvVar",
    "ExecResult",
    "ExecStreamEvent",
    "ExitStreamEvent",
    "FileEntry",
    "MetricSeries",
    "SandboxData",
    "SandboxListResponse",
    "SandboxMetricsResponse",
    "SandboxPhase",
    "SandboxPhaseEnum",
    "SandboxTemplate",
    "SandboxTemplateListResponse",
    "Scope",
    "StderrStreamEvent",
    "StdoutStreamEvent",
]

# Public re-exports of generated types. These are aliased into
# SDK-friendly names and consumed by `from neevai.types import ...` in
# the rest of the package.
from neevai.generated.aiagent import (  # noqa: F401
    CreateSandboxRequest as CreateSandboxParams,
)
from neevai.generated.aiagent import (  # noqa: F401
    EnvVar as EnvVar,
)
from neevai.generated.aiagent import (  # noqa: F401
    MetricSeries as MetricSeries,
)
from neevai.generated.aiagent import (  # noqa: F401
    Sandbox as SandboxData,
)
from neevai.generated.aiagent import (  # noqa: F401
    SandboxListResponse as SandboxListResponse,
)
from neevai.generated.aiagent import (  # noqa: F401
    SandboxMetricsResponse as SandboxMetricsResponse,
)
from neevai.generated.aiagent import (  # noqa: F401
    SandboxPhase as SandboxPhaseEnum,
)
from neevai.generated.aiagent import (  # noqa: F401
    SandboxTemplate as SandboxTemplate,
)
from neevai.generated.aiagent import (  # noqa: F401
    SandboxTemplateListResponse as SandboxTemplateListResponse,
)

# String phase literals for backward-compatible comparisons in consumer code.
SandboxPhase = Literal["Pending", "Ready", "NotReady", "Unknown", "Paused"]


@dataclass
class Scope:
    """Organization and project identifier representing the tenant scope."""

    org_id: str
    project_id: str


class FileEntry(BaseModel):
    """Entry in a sandbox directory listing."""

    name: str
    type: Literal["file", "directory", "symlink"]
    path: str
    size: int
    mode: int
    permissions: str
    modified_time: str
    symlink_target: str | None = None


class ExecResult(BaseModel):
    """Buffered execution result: stdout, stderr, and exit code."""

    stdout: str
    stderr: str
    exit_code: int


class StdoutStreamEvent(TypedDict):
    type: Literal["stdout"]
    data: str


class StderrStreamEvent(TypedDict):
    type: Literal["stderr"]
    data: str


class ExitStreamEvent(TypedDict):
    type: Literal["exit"]
    exit_code: int


ExecStreamEvent = StdoutStreamEvent | StderrStreamEvent | ExitStreamEvent
