import time
from typing import TYPE_CHECKING

from neevai.errors import NeevAIError
from neevai.types import SandboxData, SandboxMetricsResponse, SandboxPhase, Scope

if TYPE_CHECKING:
    from neevai.resources.sandboxes import AsyncSandboxes, Sandboxes
    from neevai.sandboxd import (
        AsyncSandboxConnection,
        AsyncSandboxFiles,
        ExecResult,
        SandboxConnection,
        SandboxFiles,
    )

DEFAULT_WAIT_TIMEOUT_MS = 120_000
DEFAULT_POLL_INTERVAL_MS = 2_000


class Sandbox:
    """Synchronous lifecycle handle for a single sandbox.

    Updates its state in-place and caches the data-plane connection.
    """

    def __init__(self, sandboxes: "Sandboxes", data: SandboxData, scope: Scope | None = None):
        self.sandboxes = sandboxes
        self._state = data
        self.scope = scope
        self._conn: SandboxConnection | None = None

    @property
    def id(self) -> str:
        """Sandbox UUID."""
        return self._state["id"]

    @property
    def name(self) -> str:
        """Human-readable sandbox name."""
        return self._state["name"]

    @property
    def phase(self) -> SandboxPhase:
        """Current lifecycle phase as last fetched from the server."""
        return self._state["phase"]

    @property
    def replicas(self) -> int:
        """Desired replica count (0 when paused, 1 when running)."""
        return self._state["replicas"]

    @property
    def connect_url(self) -> str | None:
        """Direct address of the sandbox daemon, or None if not ready/configured."""
        return self._state.get("connect_url")

    @property
    def data(self) -> SandboxData:
        """Full raw sandbox record exactly as returned by the API."""
        return self._state

    def to_json(self) -> SandboxData:
        """Returns the raw record so json.dumps(sandbox.to_json()) matches the API shape."""
        return self._state

    def refresh(self) -> "Sandbox":
        """Re-fetches the sandbox and updates this handle's state in place."""
        fresh = self.sandboxes.get(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = fresh.data
        return self

    def pause(self) -> "Sandbox":
        """Pauses the sandbox (scales to 0 replicas) and updates this handle in place."""
        next_state = self.sandboxes.pause(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = next_state.data
        return self

    def resume(self) -> "Sandbox":
        """Resumes the sandbox (scales to 1 replica) and updates this handle in place."""
        next_state = self.sandboxes.resume(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = next_state.data
        return self

    def delete(self) -> None:
        """Permanently deletes the sandbox."""
        self.sandboxes.delete(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )

    def metrics(
        self,
        from_: str | None = None,
        to: str | None = None,
        step: str | None = None,
    ) -> SandboxMetricsResponse:
        """Queries live health metrics for this sandbox."""
        return self.sandboxes.metrics(
            self.id,
            from_=from_,
            to=to,
            step=step,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )

    def wait_until_ready(
        self,
        timeout_ms: int = DEFAULT_WAIT_TIMEOUT_MS,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
    ) -> "Sandbox":
        """Polls until the sandbox reaches the Ready phase.

        Fails fast if Paused, or throws NeevAIError if the timeout is reached first.
        """
        deadline = (time.time() * 1000.0) + timeout_ms
        while True:
            if self.phase == "Ready":
                return self
            if self.phase == "Paused":
                raise NeevAIError(
                    f"Sandbox {self.id} is Paused and will not become Ready; call resume() first."
                )

            remaining = deadline - (time.time() * 1000.0)
            if remaining <= 0:
                raise NeevAIError(
                    f"Sandbox {self.id} did not become Ready within {timeout_ms}ms (phase: {self.phase})."
                )

            time.sleep(min(poll_interval_ms, remaining) / 1000.0)
            self.refresh()

    @property
    def files(self) -> "SandboxFiles":
        """Exposes files operations on the sandbox daemon."""
        return self._connection().files

    def exec(
        self,
        command: str | list[str],
        args: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_ms: int | None = None,
        stdin: str | None = None,
    ) -> "ExecResult":
        """Runs a command inside the sandbox."""
        return self._connection().exec(
            command=command,
            args=args,
            cwd=cwd,
            env=env,
            timeout_ms=timeout_ms,
            stdin=stdin,
        )

    def _connection(self) -> "SandboxConnection":
        if not self._conn:
            connect_url = self.connect_url
            if not connect_url:
                raise NeevAIError(
                    f"Sandbox {self.id} has no connect_url yet; it must be Ready before file or exec operations."
                )
            from neevai.sandboxd import SandboxConnection

            self._conn = SandboxConnection(
                connect_url=connect_url,
                api_key=self.sandboxes._client._transport.api_key,
                timeout_ms=self.sandboxes._client._transport.timeout.read
                * 1000.0,  # Match client timeout
            )
        return self._conn


class AsyncSandbox:
    """Asynchronous lifecycle handle for a single sandbox.

    Updates its state in-place and caches the async data-plane connection.
    """

    def __init__(self, sandboxes: "AsyncSandboxes", data: SandboxData, scope: Scope | None = None):
        self.sandboxes = sandboxes
        self._state = data
        self.scope = scope
        self._conn: AsyncSandboxConnection | None = None

    @property
    def id(self) -> str:
        return self._state["id"]

    @property
    def name(self) -> str:
        return self._state["name"]

    @property
    def phase(self) -> SandboxPhase:
        return self._state["phase"]

    @property
    def replicas(self) -> int:
        return self._state["replicas"]

    @property
    def connect_url(self) -> str | None:
        return self._state.get("connect_url")

    @property
    def data(self) -> SandboxData:
        return self._state

    def to_json(self) -> SandboxData:
        return self._state

    async def refresh(self) -> "AsyncSandbox":
        fresh = await self.sandboxes.get(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = fresh.data
        return self

    async def pause(self) -> "AsyncSandbox":
        next_state = await self.sandboxes.pause(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = next_state.data
        return self

    async def resume(self) -> "AsyncSandbox":
        next_state = await self.sandboxes.resume(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = next_state.data
        return self

    async def delete(self) -> None:
        await self.sandboxes.delete(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )

    async def metrics(
        self,
        from_: str | None = None,
        to: str | None = None,
        step: str | None = None,
    ) -> SandboxMetricsResponse:
        return await self.sandboxes.metrics(
            self.id,
            from_=from_,
            to=to,
            step=step,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )

    async def wait_until_ready(
        self,
        timeout_ms: int = DEFAULT_WAIT_TIMEOUT_MS,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
    ) -> "AsyncSandbox":
        deadline = (time.time() * 1000.0) + timeout_ms
        import asyncio

        while True:
            if self.phase == "Ready":
                return self
            if self.phase == "Paused":
                raise NeevAIError(
                    f"Sandbox {self.id} is Paused and will not become Ready; call resume() first."
                )

            remaining = deadline - (time.time() * 1000.0)
            if remaining <= 0:
                raise NeevAIError(
                    f"Sandbox {self.id} did not become Ready within ${timeout_ms}ms (phase: ${self.phase})."
                )

            await asyncio.sleep(min(poll_interval_ms, remaining) / 1000.0)
            await self.refresh()

    @property
    def files(self) -> "AsyncSandboxFiles":
        return self._connection().files

    async def exec(
        self,
        command: str | list[str],
        args: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_ms: int | None = None,
        stdin: str | None = None,
    ) -> "ExecResult":
        return await self._connection().exec(
            command=command,
            args=args,
            cwd=cwd,
            env=env,
            timeout_ms=timeout_ms,
            stdin=stdin,
        )

    def _connection(self) -> "AsyncSandboxConnection":
        if not self._conn:
            connect_url = self.connect_url
            if not connect_url:
                raise NeevAIError(
                    f"Sandbox {self.id} has no connect_url yet; it must be Ready before file or exec operations."
                )
            from neevai.sandboxd import AsyncSandboxConnection

            self._conn = AsyncSandboxConnection(
                connect_url=connect_url,
                api_key=self.sandboxes._client._transport.api_key,
                timeout_ms=self.sandboxes._client._transport.timeout.read * 1000.0,
            )
        return self._conn
