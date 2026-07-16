from __future__ import annotations

import time
from collections.abc import AsyncGenerator, Callable, Generator, Mapping
from typing import TYPE_CHECKING, Any

from neevai.errors import APIConnectionError, APIError, APITimeoutError, NeevAIError
from neevai.resources.sandboxes import (
    DEFAULT_PORT_POLL_INTERVAL_MS,
    DEFAULT_PORT_WAIT_TIMEOUT_MS,
)
from neevai.types import (
    CreateSnapshotParams,
    ExecResult,
    ExecStreamEvent,
    SandboxData,
    SandboxMetricsResponse,
    SandboxPort,
    Scope,
    Snapshot,
)

if TYPE_CHECKING:
    from neevai.resources.sandboxes import AsyncSandboxes, Sandboxes
    from neevai.runtime.connection import (
        AsyncSandboxConnection,
        AsyncSandboxFiles,
        SandboxConnection,
        SandboxFiles,
    )
    from neevai.runtime.processes import AsyncSandboxProcesses, SandboxProcesses
    from neevai.runtime.pty import AsyncSandboxPty, SandboxPty
    from neevai.runtime.ssh import AsyncSshTunnel, SshTunnel

DEFAULT_WAIT_TIMEOUT_MS = 120_000
DEFAULT_POLL_INTERVAL_MS = 2_000
DEFAULT_RUNTIME_PROBE_TIMEOUT_MS = 5_000


def _wait_timeout_message(sandbox: Sandbox | AsyncSandbox, timeout_ms: int) -> str:
    return (
        f"Sandbox {sandbox.id} did not become Ready within {timeout_ms}ms "
        f"(phase: {sandbox.phase}, replicas: {sandbox.replicas}, "
        f"connect_url: {sandbox.connect_url or '<none>'})."
    )


def _runtime_wait_timeout_message(sandbox: Sandbox | AsyncSandbox, timeout_ms: int) -> str:
    return (
        f"Sandbox {sandbox.id} runtime did not become reachable within {timeout_ms}ms "
        f"(connect_url: {sandbox.connect_url or '<none>'})."
    )


def _is_transient_runtime_error(exc: Exception) -> bool:
    if isinstance(exc, (APIConnectionError, APITimeoutError)):
        return True
    return isinstance(exc, APIError) and exc.status_code in (502, 503, 504)


def _coerce_sandbox_data(data: SandboxData | Mapping[str, Any]) -> SandboxData:
    if isinstance(data, SandboxData):
        return data
    return SandboxData.model_validate(data)


def _state_as_json(state: SandboxData) -> dict[str, Any]:
    return state.model_dump(mode="json")


class Sandbox:
    """Synchronous lifecycle handle for a single sandbox.

    Updates its state in-place and caches the runtime connection.
    """

    def __init__(
        self,
        sandboxes: Sandboxes | None,
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
    def phase(self) -> str:
        """Current lifecycle phase as last fetched from the server."""
        return self._state.phase

    @property
    def replicas(self) -> int:
        """Desired replica count (0 when paused, 1 when running)."""
        return int(_state_as_json(self._state)["replicas"])

    @property
    def connect_url(self) -> str | None:
        """Direct address of the sandbox runtime, or None if not ready/configured."""
        return self._state.connect_url

    @property
    def data(self) -> dict[str, Any]:
        """Full raw sandbox record as a JSON-compatible dict."""
        return _state_as_json(self._state)

    def to_json(self) -> dict[str, Any]:
        """Returns the raw record so json.dumps(sandbox.to_json()) matches the API shape."""
        return _state_as_json(self._state)

    def refresh(self) -> Sandbox:
        """Re-fetches the sandbox and updates this handle's state in place."""
        if self.sandboxes is None:
            raise NeevAIError("Cannot refresh a sandbox handle with no client context.")
        previous_connect_url = self.connect_url
        fresh = self.sandboxes.get(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = fresh._state
        if self.connect_url != previous_connect_url:
            self._invalidate_connection()
        return self

    def pause(self, *, preserve_memory: bool | None = None) -> Sandbox:
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
        self._invalidate_connection()
        return self

    def resume(self) -> Sandbox:
        """Resumes the sandbox (scales to 1 replica) and updates this handle in place."""
        if self.sandboxes is None:
            raise NeevAIError("Cannot resume a sandbox handle with no client context.")
        next_state = self.sandboxes.resume(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = next_state._state
        self._invalidate_connection()
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

    def expose_port(self, port: int) -> SandboxPort:
        """Exposes a port for credential-free preview URLs and returns it with its URL."""
        if self.sandboxes is None:
            raise NeevAIError("Cannot expose a port on a sandbox handle with no client context.")
        return self.sandboxes.expose_port(
            self.id,
            port,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )

    def list_ports(self) -> list[SandboxPort]:
        """Lists the ports currently exposed for this sandbox's preview URLs."""
        if self.sandboxes is None:
            raise NeevAIError("Cannot list ports on a sandbox handle with no client context.")
        return self.sandboxes.list_ports(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )

    def revoke_port(self, port: int) -> None:
        """Revokes a previously exposed preview port."""
        if self.sandboxes is None:
            raise NeevAIError("Cannot revoke a port on a sandbox handle with no client context.")
        self.sandboxes.revoke_port(
            self.id,
            port,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )

    def get_url(
        self,
        port: int,
        wait_until_ready: bool = True,
        timeout_ms: int = DEFAULT_PORT_WAIT_TIMEOUT_MS,
        poll_interval_ms: int = DEFAULT_PORT_POLL_INTERVAL_MS,
    ) -> str:
        """Exposes a port and returns its preview URL, waiting until it is routable by default."""
        if self.sandboxes is None:
            raise NeevAIError("Cannot get a URL on a sandbox handle with no client context.")
        return self.sandboxes.get_port_url(
            self.id,
            port,
            wait_until_ready=wait_until_ready,
            timeout_ms=timeout_ms,
            poll_interval_ms=poll_interval_ms,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )

    def snapshot(
        self,
        params: CreateSnapshotParams | Mapping[str, Any] | None = None,
    ) -> Snapshot:
        """Captures a snapshot of this sandbox (returns immediately with status Pending)."""
        if self.sandboxes is None:
            raise NeevAIError("Cannot snapshot a sandbox handle with no client context.")
        return self.sandboxes.create_snapshot(
            self.id,
            params,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )

    def snapshots(self) -> list[Snapshot]:
        """Lists snapshots taken from this sandbox."""
        if self.sandboxes is None:
            raise NeevAIError("Cannot list snapshots on a sandbox handle with no client context.")
        return self.sandboxes.list_snapshots(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )

    def restore(self, snapshot_id: str) -> Sandbox:
        """Restores this sandbox in place from a snapshot."""
        if self.sandboxes is None:
            raise NeevAIError("Cannot restore a sandbox handle with no client context.")
        next_state = self.sandboxes.restore(
            self.id,
            snapshot_id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = next_state._state
        self._invalidate_connection()
        return self

    def fork(self, name: str) -> Sandbox:
        """Forks this sandbox into a new sandbox seeded from its current state."""
        if self.sandboxes is None:
            raise NeevAIError("Cannot fork a sandbox handle with no client context.")
        return self.sandboxes.fork(
            self.id,
            name,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )

    def wait_until_ready(
        self,
        timeout_ms: int = DEFAULT_WAIT_TIMEOUT_MS,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
        on_poll: Callable[[Sandbox], None] | None = None,
    ) -> Sandbox:
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
    def files(self) -> SandboxFiles:
        """Exposes files operations on the sandbox runtime."""
        return self._connection().files

    @property
    def processes(self) -> SandboxProcesses:
        """Exposes supervised process operations on the sandbox runtime."""
        return self._connection().processes

    @property
    def pty(self) -> SandboxPty:
        """Exposes interactive PTY sessions on the sandbox runtime."""
        return self._connection().pty

    def ssh(self, port: int | None = None, host: str = "127.0.0.1") -> SshTunnel:
        """Opens an SSH tunnel to the sandbox: a loopback listener that forwards each
        connection over an authenticated WebSocket, so any ssh client, ``scp``/``rsync``,
        or IDE remote-dev points at ``{host, port}`` with no keys and no public port.
        Waits for the sandbox to be Ready on first use. Close the tunnel when done."""
        return self._connection().ssh.open(port=port, host=host)

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

    def _invalidate_connection(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _probe_runtime(
        self,
        timeout_ms: int = DEFAULT_RUNTIME_PROBE_TIMEOUT_MS,
    ) -> bool:
        """Probe the sandbox runtime with a fresh connection (never cached on the handle)."""
        connect_url = self.connect_url
        if not connect_url or self.sandboxes is None:
            return False

        from neevai.runtime.connection import SandboxConnection

        conn = SandboxConnection(
            connect_url=connect_url,
            api_key=self.sandboxes._client._transport.api_key,
            timeout_ms=timeout_ms,
            sandbox_id=self.id,
        )
        try:
            conn._transport.request(
                method="POST",
                path="/v1/files/list",
                headers={"Content-Type": "application/json"},
                body={"path": "."},
            )
            return True
        except Exception as exc:
            if _is_transient_runtime_error(exc):
                return False
            raise
        finally:
            conn.close()

    def _wait_for_runtime_ready(
        self,
        timeout_ms: int = DEFAULT_WAIT_TIMEOUT_MS,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
    ) -> None:
        if not self.connect_url:
            return

        self._invalidate_connection()

        deadline = (time.time() * 1000.0) + timeout_ms
        delay_s = poll_interval_ms / 1000.0
        while True:
            if self._probe_runtime():
                return

            remaining = deadline - (time.time() * 1000.0)
            if remaining <= 0:
                raise NeevAIError(_runtime_wait_timeout_message(self, timeout_ms))

            time.sleep(min(delay_s, remaining / 1000.0))
            delay_s = min(delay_s * 1.5, poll_interval_ms * 4 / 1000.0)

    def _connection(self) -> SandboxConnection:
        connect_url = self.connect_url
        if not connect_url:
            raise NeevAIError(
                f"Sandbox {self.id} has no connect_url yet; it must be Ready before "
                "file, exec, or process operations."
            )
        if self._conn is not None and self._conn._transport.connect_url != connect_url.rstrip("/"):
            self._invalidate_connection()
        if not self._conn:
            from neevai.runtime.connection import SandboxConnection

            assert self.sandboxes is not None
            read_timeout = self.sandboxes._client._transport.timeout.read or 60.0
            self._conn = SandboxConnection(
                connect_url=connect_url,
                api_key=self.sandboxes._client._transport.api_key,
                timeout_ms=int(read_timeout * 1000.0),
                sandbox_id=self.id,
            )
        return self._conn


class AsyncSandbox:
    """Asynchronous lifecycle handle for a single sandbox.

    Updates its state in-place and caches the async runtime connection.
    """

    def __init__(
        self,
        sandboxes: AsyncSandboxes | None,
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
    def phase(self) -> str:
        """Current lifecycle phase as last fetched from the server."""
        return self._state.phase

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

    async def refresh(self) -> AsyncSandbox:
        if self.sandboxes is None:
            raise NeevAIError("Cannot refresh a sandbox handle with no client context.")
        previous_connect_url = self.connect_url
        fresh = await self.sandboxes.get(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = fresh._state
        if self.connect_url != previous_connect_url:
            await self._invalidate_connection()
        return self

    async def pause(self, *, preserve_memory: bool | None = None) -> AsyncSandbox:
        if self.sandboxes is None:
            raise NeevAIError("Cannot pause a sandbox handle with no client context.")
        next_state = await self.sandboxes.pause(
            self.id,
            preserve_memory=preserve_memory,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = next_state._state
        await self._invalidate_connection()
        return self

    async def resume(self) -> AsyncSandbox:
        if self.sandboxes is None:
            raise NeevAIError("Cannot resume a sandbox handle with no client context.")
        next_state = await self.sandboxes.resume(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = next_state._state
        await self._invalidate_connection()
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

    async def expose_port(self, port: int) -> SandboxPort:
        """Exposes a port for credential-free preview URLs and returns it with its URL."""
        if self.sandboxes is None:
            raise NeevAIError("Cannot expose a port on a sandbox handle with no client context.")
        return await self.sandboxes.expose_port(
            self.id,
            port,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )

    async def list_ports(self) -> list[SandboxPort]:
        """Lists the ports currently exposed for this sandbox's preview URLs."""
        if self.sandboxes is None:
            raise NeevAIError("Cannot list ports on a sandbox handle with no client context.")
        return await self.sandboxes.list_ports(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )

    async def revoke_port(self, port: int) -> None:
        """Revokes a previously exposed preview port."""
        if self.sandboxes is None:
            raise NeevAIError("Cannot revoke a port on a sandbox handle with no client context.")
        await self.sandboxes.revoke_port(
            self.id,
            port,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )

    async def get_url(
        self,
        port: int,
        wait_until_ready: bool = True,
        timeout_ms: int = DEFAULT_PORT_WAIT_TIMEOUT_MS,
        poll_interval_ms: int = DEFAULT_PORT_POLL_INTERVAL_MS,
    ) -> str:
        """Exposes a port and returns its preview URL, waiting until it is routable by default."""
        if self.sandboxes is None:
            raise NeevAIError("Cannot get a URL on a sandbox handle with no client context.")
        return await self.sandboxes.get_port_url(
            self.id,
            port,
            wait_until_ready=wait_until_ready,
            timeout_ms=timeout_ms,
            poll_interval_ms=poll_interval_ms,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )

    async def snapshot(
        self,
        params: CreateSnapshotParams | Mapping[str, Any] | None = None,
    ) -> Snapshot:
        if self.sandboxes is None:
            raise NeevAIError("Cannot snapshot a sandbox handle with no client context.")
        return await self.sandboxes.create_snapshot(
            self.id,
            params,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )

    async def snapshots(self) -> list[Snapshot]:
        if self.sandboxes is None:
            raise NeevAIError("Cannot list snapshots on a sandbox handle with no client context.")
        return await self.sandboxes.list_snapshots(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )

    async def restore(self, snapshot_id: str) -> AsyncSandbox:
        if self.sandboxes is None:
            raise NeevAIError("Cannot restore a sandbox handle with no client context.")
        next_state = await self.sandboxes.restore(
            self.id,
            snapshot_id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = next_state._state
        await self._invalidate_connection()
        return self

    async def fork(self, name: str) -> AsyncSandbox:
        if self.sandboxes is None:
            raise NeevAIError("Cannot fork a sandbox handle with no client context.")
        return await self.sandboxes.fork(
            self.id,
            name,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )

    async def wait_until_ready(
        self,
        timeout_ms: int = DEFAULT_WAIT_TIMEOUT_MS,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
        on_poll: Callable[[AsyncSandbox], None] | None = None,
    ) -> AsyncSandbox:
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
    def files(self) -> AsyncSandboxFiles:
        return self._connection().files

    @property
    def processes(self) -> AsyncSandboxProcesses:
        """Exposes supervised process operations on the sandbox runtime."""
        return self._connection().processes

    @property
    def pty(self) -> AsyncSandboxPty:
        """Exposes interactive PTY sessions on the sandbox runtime."""
        return self._connection().pty

    async def ssh(self, port: int | None = None, host: str = "127.0.0.1") -> AsyncSshTunnel:
        """Opens an SSH tunnel to the sandbox. See :meth:`Sandbox.ssh`."""
        return await self._connection().ssh.open(port=port, host=host)

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

    async def _invalidate_connection(self) -> None:
        if self._conn is not None:
            await self._conn.aclose()
            self._conn = None

    async def _probe_runtime(
        self,
        timeout_ms: int = DEFAULT_RUNTIME_PROBE_TIMEOUT_MS,
    ) -> bool:
        connect_url = self.connect_url
        if not connect_url or self.sandboxes is None:
            return False

        from neevai.runtime.connection import AsyncSandboxConnection

        conn = AsyncSandboxConnection(
            connect_url=connect_url,
            api_key=self.sandboxes._client._transport.api_key,
            timeout_ms=timeout_ms,
            sandbox_id=self.id,
        )
        try:
            await conn._transport.request(
                method="POST",
                path="/v1/files/list",
                headers={"Content-Type": "application/json"},
                body={"path": "."},
            )
            return True
        except Exception as exc:
            if _is_transient_runtime_error(exc):
                return False
            raise
        finally:
            await conn.aclose()

    async def _wait_for_runtime_ready(
        self,
        timeout_ms: int = DEFAULT_WAIT_TIMEOUT_MS,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
    ) -> None:
        if not self.connect_url:
            return

        import asyncio

        await self._invalidate_connection()

        deadline = (time.time() * 1000.0) + timeout_ms
        delay_s = poll_interval_ms / 1000.0
        while True:
            if await self._probe_runtime():
                return

            remaining = deadline - (time.time() * 1000.0)
            if remaining <= 0:
                raise NeevAIError(_runtime_wait_timeout_message(self, timeout_ms))

            await asyncio.sleep(min(delay_s, remaining / 1000.0))
            delay_s = min(delay_s * 1.5, poll_interval_ms * 4 / 1000.0)

    def _drop_stale_connection(self, connect_url: str) -> None:
        if self._conn is None:
            return
        if self._conn._transport.connect_url == connect_url.rstrip("/"):
            return
        stale = self._conn
        self._conn = None
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(stale.aclose())

    def _connection(self) -> AsyncSandboxConnection:
        connect_url = self.connect_url
        if not connect_url:
            raise NeevAIError(
                f"Sandbox {self.id} has no connect_url yet; it must be Ready before "
                "file, exec, or process operations."
            )
        self._drop_stale_connection(connect_url)
        if not self._conn:
            from neevai.runtime.connection import AsyncSandboxConnection

            assert self.sandboxes is not None
            read_timeout = self.sandboxes._client._transport.timeout.read or 60.0
            self._conn = AsyncSandboxConnection(
                connect_url=connect_url,
                api_key=self.sandboxes._client._transport.api_key,
                timeout_ms=int(read_timeout * 1000.0),
                sandbox_id=self.id,
            )
        return self._conn
