from dataclasses import dataclass
from typing import Literal, TypedDict

try:
    from typing import NotRequired
except ImportError:
    from typing_extensions import NotRequired

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
    SandboxPhase as SandboxPhase,
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
