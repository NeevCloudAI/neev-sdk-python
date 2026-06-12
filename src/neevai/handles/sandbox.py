import time
from collections.abc import AsyncGenerator, Callable, Generator, Mapping
from typing import TYPE_CHECKING, Any

from neevai.errors import NeevAIError
from neevai.types import (
    ExecResult,
    ExecStreamEvent,
    SandboxData,
    SandboxMetricsResponse,
    SandboxPhase,
    Scope,
)

if TYPE_CHECKING:
    from neevai.resources.sandboxes import AsyncSandboxes, Sandboxes
    from neevai.runtime.sandboxd import (
        AsyncSandboxConnection,
        AsyncSandboxFiles,
        SandboxConnection,
        SandboxFiles,
    )

DEFAULT_WAIT_TIMEOUT_MS = 120_000
DEFAULT_POLL_INTERVAL_MS = 2_000


def _wait_timeout_message(sandbox: "Sandbox | AsyncSandbox", timeout_ms: int) -> str:
    return (
        f"Sandbox {sandbox.id} did not become Ready within {timeout_ms}ms "
        f"(phase: {sandbox.phase}, replicas: {sandbox.replicas}, "
        f"connect_url: {sandbox.connect_url or '<none>'})."
    )


def _coerce_sandbox_data(data: SandboxData | Mapping[str, Any]) -> SandboxData:
    if isinstance(data, SandboxData):
        return data
    return SandboxData.model_validate(data)


def _state_as_json(state: SandboxData) -> dict[str, Any]:
    return state.model_dump(mode="json")


class Sandbox:
    """Synchronous lifecycle handle for a single sandbox.

    Updates its state in-place and caches the data-plane connection.
    """

    def __init__(
        self,
        sandboxes: "Sandboxes | None",
        data: SandboxData | Mapping[str, Any],
        scope: Scope | None = None,
    ):
        self.sandboxes = sandboxes
        self._state = _coerce_sandbox_data(data)
        self.scope = scope
        self._conn: SandboxConnection | None = None

    @property
    def id(self) -> str:
        """Sandbox UUID."""
        return str(self._state.id)

    @property
    def name(self) -> str:
        """Human-readable sandbox name."""
        return self._state.name

    @property
    def phase(self) -> SandboxPhase:
        """Current lifecycle phase as last fetched from the server."""
        return self._state.phase.value

    @property
    def replicas(self) -> int:
        """Desired replica count (0 when paused, 1 when running)."""
        return int(_state_as_json(self._state)["replicas"])

    @property
    def connect_url(self) -> str | None:
        """Direct address of the sandbox daemon, or None if not ready/configured."""
        return self._state.connect_url

    @property
    def data(self) -> dict[str, Any]:
        """Full raw sandbox record as a JSON-compatible dict."""
        return _state_as_json(self._state)

    def to_json(self) -> dict[str, Any]:
        """Returns the raw record so json.dumps(sandbox.to_json()) matches the API shape."""
        return _state_as_json(self._state)

    def refresh(self) -> "Sandbox":
        """Re-fetches the sandbox and updates this handle's state in place."""
        if self.sandboxes is None:
            raise NeevAIError("Cannot refresh a sandbox handle with no client context.")
        fresh = self.sandboxes.get(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = fresh._state
        return self

    def pause(self, *, preserve_memory: bool | None = None) -> "Sandbox":
        """Pauses the sandbox (scales to 0 replicas) and updates this handle in place."""
        if self.sandboxes is None:
            raise NeevAIError("Cannot pause a sandbox handle with no client context.")
        next_state = self.sandboxes.pause(
            self.id,
            preserve_memory=preserve_memory,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = next_state._state
        return self

    def resume(self) -> "Sandbox":
        """Resumes the sandbox (scales to 1 replica) and updates this handle in place."""
        if self.sandboxes is None:
            raise NeevAIError("Cannot resume a sandbox handle with no client context.")
        next_state = self.sandboxes.resume(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = next_state._state
        return self

    def delete(self) -> None:
        """Permanently deletes the sandbox."""
        if self.sandboxes is None:
            raise NeevAIError("Cannot delete a sandbox handle with no client context.")
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
        if self.sandboxes is None:
            raise NeevAIError("Cannot query metrics on a sandbox handle with no client context.")
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
        on_poll: Callable[["Sandbox"], None] | None = None,
    ) -> "Sandbox":
        """Polls until the sandbox reaches the Ready phase.

        Fails fast if Paused, or throws NeevAIError if the timeout is reached first.
        """
        deadline = (time.time() * 1000.0) + timeout_ms
        while True:
            if on_poll is not None:
                on_poll(self)
            if self.phase == "Ready":
                return self
            if self.phase == "Paused":
                raise NeevAIError(
                    f"Sandbox {self.id} is Paused and will not become Ready; call resume() first."
                )

            remaining = deadline - (time.time() * 1000.0)
            if remaining <= 0:
                raise NeevAIError(_wait_timeout_message(self, timeout_ms))

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
    ) -> ExecResult:
        """Runs a command inside the sandbox."""
        return self._connection().exec(
            command=command,
            args=args,
            cwd=cwd,
            env=env,
            timeout_ms=timeout_ms,
            stdin=stdin,
        )

    def exec_stream(
        self,
        command: str | list[str],
        args: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_ms: int | None = None,
        stdin: str | None = None,
    ) -> Generator[ExecStreamEvent, None, None]:
        """Runs a command and yields stdout/stderr chunks as they arrive, then an exit event."""
        yield from self._connection().exec_stream(
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
            from neevai.runtime.sandboxd import SandboxConnection

            assert self.sandboxes is not None
            read_timeout = self.sandboxes._client._transport.timeout.read or 60.0
            self._conn = SandboxConnection(
                connect_url=connect_url,
                api_key=self.sandboxes._client._transport.api_key,
                timeout_ms=int(read_timeout * 1000.0),
            )
        return self._conn


class AsyncSandbox:
    """Asynchronous lifecycle handle for a single sandbox.

    Updates its state in-place and caches the async data-plane connection.
    """

    def __init__(
        self,
        sandboxes: "AsyncSandboxes | None",
        data: SandboxData | Mapping[str, Any],
        scope: Scope | None = None,
    ):
        self.sandboxes = sandboxes
        self._state = _coerce_sandbox_data(data)
        self.scope = scope
        self._conn: AsyncSandboxConnection | None = None

    @property
    def id(self) -> str:
        return str(self._state.id)

    @property
    def name(self) -> str:
        return self._state.name

    @property
    def phase(self) -> SandboxPhase:
        return self._state.phase.value

    @property
    def replicas(self) -> int:
        return int(_state_as_json(self._state)["replicas"])

    @property
    def connect_url(self) -> str | None:
        return self._state.connect_url

    @property
    def data(self) -> dict[str, Any]:
        return _state_as_json(self._state)

    def to_json(self) -> dict[str, Any]:
        return _state_as_json(self._state)

    async def refresh(self) -> "AsyncSandbox":
        if self.sandboxes is None:
            raise NeevAIError("Cannot refresh a sandbox handle with no client context.")
        fresh = await self.sandboxes.get(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = fresh._state
        return self

    async def pause(self, *, preserve_memory: bool | None = None) -> "AsyncSandbox":
        if self.sandboxes is None:
            raise NeevAIError("Cannot pause a sandbox handle with no client context.")
        next_state = await self.sandboxes.pause(
            self.id,
            preserve_memory=preserve_memory,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = next_state._state
        return self

    async def resume(self) -> "AsyncSandbox":
        if self.sandboxes is None:
            raise NeevAIError("Cannot resume a sandbox handle with no client context.")
        next_state = await self.sandboxes.resume(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = next_state._state
        return self

    async def delete(self) -> None:
        if self.sandboxes is None:
            raise NeevAIError("Cannot delete a sandbox handle with no client context.")
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
        if self.sandboxes is None:
            raise NeevAIError("Cannot query metrics on a sandbox handle with no client context.")
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
        on_poll: Callable[["AsyncSandbox"], None] | None = None,
    ) -> "AsyncSandbox":
        deadline = (time.time() * 1000.0) + timeout_ms
        import asyncio

        while True:
            if on_poll is not None:
                on_poll(self)
            if self.phase == "Ready":
                return self
            if self.phase == "Paused":
                raise NeevAIError(
                    f"Sandbox {self.id} is Paused and will not become Ready; call resume() first."
                )

            remaining = deadline - (time.time() * 1000.0)
            if remaining <= 0:
                raise NeevAIError(_wait_timeout_message(self, timeout_ms))

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
    ) -> ExecResult:
        return await self._connection().exec(
            command=command,
            args=args,
            cwd=cwd,
            env=env,
            timeout_ms=timeout_ms,
            stdin=stdin,
        )

    async def exec_stream(
        self,
        command: str | list[str],
        args: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_ms: int | None = None,
        stdin: str | None = None,
    ) -> AsyncGenerator[ExecStreamEvent, None]:
        async for event in self._connection().exec_stream(
            command=command,
            args=args,
            cwd=cwd,
            env=env,
            timeout_ms=timeout_ms,
            stdin=stdin,
        ):
            yield event

    def _connection(self) -> "AsyncSandboxConnection":
        if not self._conn:
            connect_url = self.connect_url
            if not connect_url:
                raise NeevAIError(
                    f"Sandbox {self.id} has no connect_url yet; it must be Ready before file or exec operations."
                )
            from neevai.runtime.sandboxd import AsyncSandboxConnection

            assert self.sandboxes is not None
            read_timeout = self.sandboxes._client._transport.timeout.read or 60.0
            self._conn = AsyncSandboxConnection(
                connect_url=connect_url,
                api_key=self.sandboxes._client._transport.api_key,
                timeout_ms=int(read_timeout * 1000.0),
            )
        return self._conn
