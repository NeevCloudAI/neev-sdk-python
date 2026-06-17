from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, cast

from neevai.errors import NeevAIError
from neevai.types import AgentData, Scope, UpdateAgentParams

if TYPE_CHECKING:
    from neevai.handles.sandbox import AsyncSandbox, Sandbox
    from neevai.resources.agents import Agents, AsyncAgents

DEFAULT_WAIT_TIMEOUT_MS = 120_000
DEFAULT_POLL_INTERVAL_MS = 2_000


def _wait_timeout_message(agent: Agent | AsyncAgent, timeout_ms: int) -> str:
    return f"Agent {agent.id} did not become Ready within {timeout_ms}ms (status: {agent.status})."


def _validate_wait_timings(timeout_ms: int, poll_interval_ms: int) -> None:
    if not math.isfinite(timeout_ms) or timeout_ms <= 0:
        raise NeevAIError("timeout_ms must be a positive finite number.")
    if not math.isfinite(poll_interval_ms) or poll_interval_ms <= 0:
        raise NeevAIError("poll_interval_ms must be a positive finite number.")


def _coerce_agent_data(data: AgentData | Mapping[str, Any]) -> AgentData:
    if isinstance(data, AgentData):
        return data
    return AgentData.model_validate(data)


def _state_as_json(state: AgentData) -> dict[str, Any]:
    return state.model_dump(mode="json")


class Agent:
    """Synchronous lifecycle handle for a single agent.

    Updates its state in-place and can resolve the backing sandbox.
    """

    def __init__(
        self,
        agents: Agents | None,
        data: AgentData | Mapping[str, Any],
        scope: Scope | None = None,
    ):
        self.agents = agents
        self._state = _coerce_agent_data(data)
        self.scope = scope

    @property
    def id(self) -> str:
        """Agent UUID."""
        return str(self._state.id)

    @property
    def name(self) -> str:
        """Human-readable agent name."""
        return self._state.name

    @property
    def status(self) -> str:
        """Current lifecycle status as last fetched from the server."""
        return self._state.status

    @property
    def sandbox_id(self) -> str:
        """UUID of the backing sandbox."""
        return str(self._state.sandbox_id)

    @property
    def agent_template_id(self) -> str:
        """Catalogue template id the agent was created from."""
        return self._state.agent_template_id

    @property
    def config(self) -> dict[str, Any] | None:
        """Effective agent configuration."""
        return self._state.config

    @property
    def created_at(self) -> str:
        """Creation timestamp (ISO 8601)."""
        return cast(str, _state_as_json(self._state)["created_at"])

    @property
    def updated_at(self) -> str:
        """Last update timestamp (ISO 8601)."""
        return cast(str, _state_as_json(self._state)["updated_at"])

    @property
    def data(self) -> dict[str, Any]:
        """Full raw agent record as a JSON-compatible dict."""
        return _state_as_json(self._state)

    def to_json(self) -> dict[str, Any]:
        """Returns the raw record so json.dumps(agent.to_json()) matches the API shape."""
        return _state_as_json(self._state)

    def refresh(self) -> Agent:
        """Re-fetches the agent and updates this handle's state in place."""
        if self.agents is None:
            raise NeevAIError("Cannot refresh an agent handle with no client context.")
        fresh = self.agents.get(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = fresh._state
        return self

    def update(self, params: UpdateAgentParams | Mapping[str, Any]) -> Agent:
        """Updates mutable agent fields in place."""
        if self.agents is None:
            raise NeevAIError("Cannot update an agent handle with no client context.")
        next_state = self.agents.update(
            self.id,
            params,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = next_state._state
        return self

    def pause(self) -> Agent:
        """Pauses the agent and updates this handle in place."""
        if self.agents is None:
            raise NeevAIError("Cannot pause an agent handle with no client context.")
        next_state = self.agents.pause(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = next_state._state
        return self

    def resume(self) -> Agent:
        """Resumes the agent and updates this handle in place."""
        if self.agents is None:
            raise NeevAIError("Cannot resume an agent handle with no client context.")
        next_state = self.agents.resume(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = next_state._state
        return self

    def delete(self) -> None:
        """Permanently deletes the agent and its backing sandbox."""
        if self.agents is None:
            raise NeevAIError("Cannot delete an agent handle with no client context.")
        self.agents.delete(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )

    def sandbox(self) -> Sandbox:
        """Resolves the backing sandbox as a Sandbox handle."""
        if self.agents is None:
            raise NeevAIError("Cannot resolve sandbox on an agent handle with no client context.")
        return self.agents.get_sandbox(self.sandbox_id, self.scope)

    def wait_until_ready(
        self,
        timeout_ms: int = DEFAULT_WAIT_TIMEOUT_MS,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
        on_poll: Callable[[Agent], None] | None = None,
    ) -> Agent:
        """Polls until the agent reaches Ready status.

        Fails fast on Failed or Paused, or raises NeevAIError if the timeout is reached.
        """
        _validate_wait_timings(timeout_ms, poll_interval_ms)
        deadline = (time.time() * 1000.0) + timeout_ms
        while True:
            if on_poll is not None:
                on_poll(self)
            if self.status == "Ready":
                return self
            if self.status == "Failed":
                raise NeevAIError(f"Agent {self.id} is in Failed status and will not become Ready.")
            if self.status == "Paused":
                raise NeevAIError(
                    f"Agent {self.id} is Paused and will not become Ready; call resume() first."
                )

            remaining = deadline - (time.time() * 1000.0)
            if remaining <= 0:
                raise NeevAIError(_wait_timeout_message(self, timeout_ms))

            time.sleep(min(poll_interval_ms, remaining) / 1000.0)
            self.refresh()


class AsyncAgent:
    """Asynchronous lifecycle handle for a single agent."""

    def __init__(
        self,
        agents: AsyncAgents | None,
        data: AgentData | Mapping[str, Any],
        scope: Scope | None = None,
    ):
        self.agents = agents
        self._state = _coerce_agent_data(data)
        self.scope = scope

    @property
    def id(self) -> str:
        return str(self._state.id)

    @property
    def name(self) -> str:
        return self._state.name

    @property
    def status(self) -> str:
        return self._state.status

    @property
    def sandbox_id(self) -> str:
        return str(self._state.sandbox_id)

    @property
    def agent_template_id(self) -> str:
        return self._state.agent_template_id

    @property
    def config(self) -> dict[str, Any] | None:
        return self._state.config

    @property
    def created_at(self) -> str:
        return cast(str, _state_as_json(self._state)["created_at"])

    @property
    def updated_at(self) -> str:
        return cast(str, _state_as_json(self._state)["updated_at"])

    @property
    def data(self) -> dict[str, Any]:
        return _state_as_json(self._state)

    def to_json(self) -> dict[str, Any]:
        return _state_as_json(self._state)

    async def refresh(self) -> AsyncAgent:
        if self.agents is None:
            raise NeevAIError("Cannot refresh an agent handle with no client context.")
        fresh = await self.agents.get(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = fresh._state
        return self

    async def update(self, params: UpdateAgentParams | Mapping[str, Any]) -> AsyncAgent:
        if self.agents is None:
            raise NeevAIError("Cannot update an agent handle with no client context.")
        next_state = await self.agents.update(
            self.id,
            params,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = next_state._state
        return self

    async def pause(self) -> AsyncAgent:
        if self.agents is None:
            raise NeevAIError("Cannot pause an agent handle with no client context.")
        next_state = await self.agents.pause(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = next_state._state
        return self

    async def resume(self) -> AsyncAgent:
        if self.agents is None:
            raise NeevAIError("Cannot resume an agent handle with no client context.")
        next_state = await self.agents.resume(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )
        self._state = next_state._state
        return self

    async def delete(self) -> None:
        if self.agents is None:
            raise NeevAIError("Cannot delete an agent handle with no client context.")
        await self.agents.delete(
            self.id,
            org_id=self.scope.org_id if self.scope else None,
            project_id=self.scope.project_id if self.scope else None,
        )

    async def sandbox(self) -> AsyncSandbox:
        if self.agents is None:
            raise NeevAIError("Cannot resolve sandbox on an agent handle with no client context.")
        return await self.agents.get_sandbox(self.sandbox_id, self.scope)

    async def wait_until_ready(
        self,
        timeout_ms: int = DEFAULT_WAIT_TIMEOUT_MS,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
        on_poll: Callable[[AsyncAgent], None] | None = None,
    ) -> AsyncAgent:
        import asyncio

        _validate_wait_timings(timeout_ms, poll_interval_ms)
        deadline = (time.time() * 1000.0) + timeout_ms
        while True:
            if on_poll is not None:
                on_poll(self)
            if self.status == "Ready":
                return self
            if self.status == "Failed":
                raise NeevAIError(f"Agent {self.id} is in Failed status and will not become Ready.")
            if self.status == "Paused":
                raise NeevAIError(
                    f"Agent {self.id} is Paused and will not become Ready; call resume() first."
                )

            remaining = deadline - (time.time() * 1000.0)
            if remaining <= 0:
                raise NeevAIError(_wait_timeout_message(self, timeout_ms))

            await asyncio.sleep(min(poll_interval_ms, remaining) / 1000.0)
            await self.refresh()
