from dataclasses import dataclass
from typing import Literal, TypedDict, Union

try:
    from typing import NotRequired
except ImportError:
    from typing_extensions import NotRequired

from neevai.generated.aiagent import (
    EnvVar as EnvVar,
)
from neevai.generated.aiagent import (
    MetricSeries as MetricSeries,
)
from neevai.generated.aiagent import (
    Sandbox as SandboxData,
)
from neevai.generated.aiagent import (
    SandboxListResponse as SandboxListResponse,
)
from neevai.generated.aiagent import (
    SandboxMetricsResponse as SandboxMetricsResponse,
)
from neevai.generated.aiagent import (
    SandboxPhase as SandboxPhase,
)

# Aliasing CreateSandboxRequest to CreateSandboxParams
from neevai.generated.aiagent import (
    CreateSandboxRequest as CreateSandboxParams,
)


@dataclass
class Scope:
    """Organization and project identifier representing the tenant scope."""

    org_id: str
    project_id: str


# File system types representing entries in a sandbox directory listing.
class FileEntry(TypedDict):
    name: str
    type: Literal["file", "directory", "symlink"]
    path: str
    size: int
    mode: int
    permissions: str
    modified_time: str
    symlink_target: NotRequired[str]


# Buffered execution result representing stdout, stderr and exit code of a command.
class ExecResult(TypedDict):
    stdout: str
    stderr: str
    exit_code: int
