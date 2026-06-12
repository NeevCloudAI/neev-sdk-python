"""
Shared, framework-agnostic helper used by the agent examples in this folder.

``SandboxCodeExecutor`` wraps the NeevAI SDK and exposes run_python / run_shell
tools backed by a gVisor-isolated Neev sandbox.
"""

from __future__ import annotations

import os
import random
import string
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from neevai import NeevAI
from neevai.types import ExecResult

if TYPE_CHECKING:
    from neevai.handles.sandbox import Sandbox


@dataclass
class RunResult:
    stdout: str
    stderr: str
    exit_code: int


class SandboxCodeExecutor:
    """Reusable code executor backed by one Neev sandbox."""

    def __init__(
        self,
        template_id: str | None = None,
        region: str | None = None,
        name_prefix: str = "agent-demo",
    ):
        self._client = NeevAI()
        self._template_id = template_id or os.environ.get(
            "NEEVCLOUD_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal"
        )
        self._region = region or os.environ.get("NEEVCLOUD_REGION", "as-south-1")
        self._name_prefix = name_prefix
        self._sandbox: Sandbox | None = None

    def _ensure(self) -> Sandbox:
        if self._sandbox is None:
            suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
            log(f"creating sandbox (template={self._template_id}, region={self._region})…")
            self._sandbox = self._client.sandboxes.create(
                {
                    "name": f"{self._name_prefix}-{suffix}",
                    "sandbox_template_id": self._template_id,
                    "region": self._region,
                }
            )
            log(f"created {self._sandbox.id} ({self._sandbox.phase}); waiting until ready…")
            self._sandbox.wait_until_ready()
            log(f"ready: {self._sandbox.connect_url or '(no connect url)'}")
        return self._sandbox

    def run_python(self, code: str) -> RunResult:
        sandbox = self._ensure()
        sandbox.files.write("snippet.py", code)
        return self._logged("python3 snippet.py", lambda: sandbox.exec(["python3", "snippet.py"]))

    def run_shell(self, command: str) -> RunResult:
        sandbox = self._ensure()
        return self._logged(command, lambda: sandbox.exec(["sh", "-c", command]))

    def cleanup(self) -> None:
        if self._sandbox is not None:
            log(f"deleting sandbox {self._sandbox.id}")
            self._sandbox.delete()
            self._sandbox = None
        self._client.close()

    def _logged(self, label: str, run) -> RunResult:
        log(f"exec: {label}")
        try:
            result: ExecResult = run()
            log(f"  -> exit {result.exit_code}")
            return RunResult(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.exit_code,
            )
        except Exception as err:
            log(f"  -> failed: {err}")
            raise


def log(message: str) -> None:
    print(f"[neev] {message}", file=sys.stderr)


def format_run_result(result: RunResult) -> str:
    parts = [f"exit code: {result.exit_code}"]
    if result.stdout.strip():
        parts.append(f"stdout:\n{result.stdout.strip()}")
    if result.stderr.strip():
        parts.append(f"stderr:\n{result.stderr.strip()}")
    return "\n".join(parts)
