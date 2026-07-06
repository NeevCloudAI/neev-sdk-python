from dataclasses import dataclass
from typing import Literal, TypedDict

from pydantic import BaseModel

__all__ = [
    "AgentData",
    "AgentListResponse",
    "AgentStatus",
    "AgentTemplate",
    "AgentTemplateListResponse",
    "CreateAgentParams",
    "CreateSandboxParams",
    "CreateSnapshotParams",
    "CreateSnapshotRequest",
    "EnvVar",
    "ExecResult",
    "ExecStreamEvent",
    "ExitStreamEvent",
    "FileEntry",
    "ForkSandboxRequest",
    "MetricSeries",
    "PauseSandboxParams",
    "ProcessInfo",
    "ProcessLogEntry",
    "ProcessLogEvent",
    "ProcessLogsPage",
    "ProcessState",
    "ProcessStatus",
    "RestoreSandboxRequest",
    "SandboxData",
    "SandboxEgressConfig",
    "SandboxListResponse",
    "SandboxMetricsResponse",
    "SandboxPhase",
    "SandboxPhaseEnum",
    "SandboxResources",
    "SandboxTemplate",
    "SandboxTemplateListResponse",
    "Scope",
    "Signal",
    "Snapshot",
    "SnapshotListResponse",
    "SnapshotStatus",
    "StderrStreamEvent",
    "StdoutStreamEvent",
    "UpdateAgentParams",
]

# Public re-exports of generated types. These are aliased into
# SDK-friendly names and consumed by `from neevai.types import ...` in
# the rest of the package.
from neevai.generated.aiagent import (  # noqa: F401
    Agent as _GeneratedAgent,
)
from neevai.generated.aiagent import (  # noqa: F401
    AgentStatus as AgentStatus,
)
from neevai.generated.aiagent import (  # noqa: F401
    AgentTemplate as AgentTemplate,
)
from neevai.generated.aiagent import (  # noqa: F401
    AgentTemplateListResponse as AgentTemplateListResponse,
)
from neevai.generated.aiagent import (  # noqa: F401
    CreateAgentRequest as CreateAgentParams,
)
from neevai.generated.aiagent import (  # noqa: F401
    CreateSandboxRequest as CreateSandboxParams,
)
from neevai.generated.aiagent import (  # noqa: F401
    CreateSnapshotRequest as CreateSnapshotRequest,
)
from neevai.generated.aiagent import (  # noqa: F401
    EnvVar as EnvVar,
)
from neevai.generated.aiagent import (  # noqa: F401
    ForkSandboxRequest as ForkSandboxRequest,
)
from neevai.generated.aiagent import (  # noqa: F401
    MetricSeries as MetricSeries,
)
from neevai.generated.aiagent import (  # noqa: F401
    PauseSandboxRequest as PauseSandboxParams,
)
from neevai.generated.aiagent import (  # noqa: F401
    RestoreSandboxRequest as RestoreSandboxRequest,
)
from neevai.generated.aiagent import (  # noqa: F401
    Sandbox as _GeneratedSandbox,
)
from neevai.generated.aiagent import (  # noqa: F401
    SandboxEgressConfig as SandboxEgressConfig,
)
from neevai.generated.aiagent import (  # noqa: F401
    SandboxMetricsResponse as SandboxMetricsResponse,
)
from neevai.generated.aiagent import (  # noqa: F401
    SandboxPhase as SandboxPhaseEnum,
)
from neevai.generated.aiagent import (  # noqa: F401
    SandboxResources as SandboxResources,
)
from neevai.generated.aiagent import (  # noqa: F401
    SandboxTemplate as SandboxTemplate,
)
from neevai.generated.aiagent import (  # noqa: F401
    SandboxTemplateListResponse as SandboxTemplateListResponse,
)
from neevai.generated.aiagent import (  # noqa: F401
    Snapshot as Snapshot,
)
from neevai.generated.aiagent import (  # noqa: F401
    SnapshotListResponse as SnapshotListResponse,
)
from neevai.generated.aiagent import (  # noqa: F401
    SnapshotStatus as SnapshotStatus,
)
from neevai.generated.aiagent import (  # noqa: F401
    UpdateAgentRequest as UpdateAgentParams,
)

# Steady-state phases from the OpenAPI spec, plus transitional values the API may
# return during pause/resume reconciliation (not listed in the spec enum).
SandboxPhase = Literal["Pending", "Ready", "NotReady", "Unknown", "Paused", "Pausing", "Resuming"]


class AgentData(_GeneratedAgent):
    """Agent record with relaxed ``status`` validation.

    The API may return future status strings beyond the OpenAPI
    ``AgentStatus`` enum; accept any string at the SDK boundary.
    """

    status: str  # type: ignore[assignment]  # pyright: ignore[reportIncompatibleVariableOverride]


class AgentListResponse(BaseModel):
    items: list[AgentData]
    total: int
    page: int
    limit: int


class SandboxData(_GeneratedSandbox):
    """Sandbox record with relaxed ``phase`` validation.

    The API may return transitional or future phase strings beyond the
    OpenAPI ``SandboxPhase`` enum; accept any string at the SDK boundary.
    """

    phase: str  # type: ignore[assignment]  # pyright: ignore[reportIncompatibleVariableOverride]


class CreateSnapshotParams(BaseModel):
    """Caller-facing params for creating a sandbox snapshot (excludes ``include_memory``)."""

    name: str | None = None
    retain_for: str | None = None


class SandboxListResponse(BaseModel):
    items: list[SandboxData]
    total: int
    page: int
    limit: int


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

ProcessState = Literal["running", "exited"]


class ProcessStatus(BaseModel):
    """Status snapshot for a supervised sandbox process."""

    process_id: str
    state: ProcessState
    exit_code: int | None = None
    started_at: int


class ProcessInfo(ProcessStatus):
    """Process status plus the command that was started."""

    name: str
    args: list[str]
    cwd: str | None = None


class ProcessLogEntry(BaseModel):
    """Single log line from poll-mode log retrieval."""

    stream: Literal["stdout", "stderr"]
    data: str


class ProcessLogsPage(BaseModel):
    """Page of process log entries with cursor metadata."""

    entries: list[ProcessLogEntry]
    cursor: int
    dropped: bool
    state: ProcessState


ProcessLogEvent = ExecStreamEvent


class Signal:
    """POSIX signal numbers for ``kill`` and ``kill_all``."""

    HUP = 1
    INT = 2
    QUIT = 3
    KILL = 9
    TERM = 15
