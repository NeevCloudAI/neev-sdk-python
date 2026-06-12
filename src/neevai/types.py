from dataclasses import dataclass
from typing import Literal, TypedDict

from pydantic import BaseModel

__all__ = [
    "CreateSandboxParams",
    "CreateSnapshotRequest",
    "EnvVar",
    "ExecResult",
    "ExecStreamEvent",
    "ExitStreamEvent",
    "FileEntry",
    "ForkSandboxRequest",
    "MetricSeries",
    "PauseSandboxParams",
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
    "Snapshot",
    "SnapshotListResponse",
    "SnapshotStatus",
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

# Steady-state phases from the OpenAPI spec, plus transitional values the API may
# return during pause/resume reconciliation (not listed in the spec enum).
SandboxPhase = Literal["Pending", "Ready", "NotReady", "Unknown", "Paused", "Pausing", "Resuming"]


class SandboxData(_GeneratedSandbox):
    """Sandbox record with relaxed ``phase`` validation.

    The control plane may return transitional or future phase strings beyond the
    OpenAPI ``SandboxPhase`` enum; accept any string at the SDK boundary.
    """

    phase: str  # type: ignore[assignment]  # pyright: ignore[reportIncompatibleVariableOverride]


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
