from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from neevai._parse import coerce_model, coerce_params
from neevai.errors import NeevAIError
from neevai.types import (
    AgentData,
    AgentListResponse,
    CreateAgentParams,
    UpdateAgentParams,
)

if TYPE_CHECKING:
    from neevai.client import AsyncNeevAI, NeevAI
    from neevai.handles.agent import Agent, AsyncAgent
    from neevai.handles.sandbox import AsyncSandbox, Sandbox
    from neevai.resources.sandboxes import AsyncSandboxes, Sandboxes
    from neevai.types import Scope


@dataclass
class AgentPage:
    items: list[Agent]
    total: int
    page: int
    limit: int


@dataclass
class AsyncAgentPage:
    items: list[AsyncAgent]
    total: int
    page: int
    limit: int


@dataclass
class ListAgentsParams:
    page: int | None = None
    limit: int | None = None
    org_id: str | None = None
    project_id: str | None = None


def _agents_path(scope: Scope) -> str:
    return f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/agents"


def _prepare_create_params(
    client: NeevAI | AsyncNeevAI,
    params: CreateAgentParams | Mapping[str, Any],
) -> CreateAgentParams:
    if isinstance(params, Mapping):
        raw: dict[str, Any] = dict(params)
    else:
        raw = params.model_dump(exclude_unset=True)
    if not raw.get("region") and client.default_region:
        raw["region"] = client.default_region
    return coerce_params(CreateAgentParams, raw)


def _prepare_update_body(
    params: UpdateAgentParams | Mapping[str, Any],
) -> dict[str, Any]:
    if isinstance(params, Mapping):
        raw: dict[str, Any] = dict(params)
    else:
        raw = params.model_dump(exclude_unset=True)
    body = coerce_params(UpdateAgentParams, raw).model_dump(exclude_unset=True)
    if not body:
        raise NeevAIError(
            "UpdateAgentParams must include at least one of `egress` or `resources`; empty body is not allowed."
        )
    return body


class Agents:
    """Operations on the /agents API endpoint (control plane, synchronous)."""

    def __init__(self, client: NeevAI, sandboxes: Sandboxes):
        self._client = client
        self._sandboxes = sandboxes

    def get_sandbox(
        self,
        sandbox_id: str,
        scope: Scope | None,
    ) -> Sandbox:
        """Fetches the backing sandbox for an agent by id and scope."""
        return self._sandboxes.get(
            sandbox_id,
            org_id=scope.org_id if scope else None,
            project_id=scope.project_id if scope else None,
        )

    def create(
        self,
        params: CreateAgentParams | Mapping[str, Any],
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> Agent:
        """Creates a new agent from a catalogue template in the resolved project context."""
        from neevai.handles.agent import Agent

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        body = _prepare_create_params(self._client, params)
        raw = self._client._transport.request(
            "POST",
            _agents_path(scope),
            body=body.model_dump(mode="json", exclude_unset=True),
        )
        data = coerce_model(AgentData, raw)
        return Agent(self, data, scope)

    def list(
        self,
        page: int | None = None,
        limit: int | None = None,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> AgentPage:
        """Lists all agents in the resolved project context with pagination."""
        from neevai.handles.agent import Agent

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        query: dict[str, Any] = {}
        if page is not None:
            query["page"] = page
        if limit is not None:
            query["limit"] = limit

        raw = self._client._transport.request("GET", _agents_path(scope), query=query)
        page_data = coerce_model(AgentListResponse, raw)
        wrapped_items = [Agent(self, item, scope) for item in page_data.items]
        return AgentPage(
            items=wrapped_items,
            total=page_data.total,
            page=page_data.page,
            limit=page_data.limit,
        )

    def get(
        self,
        id: str,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> Agent:
        """Retrieves details of a specific agent."""
        from neevai.handles.agent import Agent

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        raw = self._client._transport.request("GET", f"{_agents_path(scope)}/{id}")
        data = coerce_model(AgentData, raw)
        return Agent(self, data, scope)

    def update(
        self,
        id: str,
        params: UpdateAgentParams | Mapping[str, Any],
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> Agent:
        """Updates mutable agent fields in place."""
        from neevai.handles.agent import Agent

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        body = _prepare_update_body(params)
        raw = self._client._transport.request(
            "PATCH",
            f"{_agents_path(scope)}/{id}",
            body=body,
        )
        data = coerce_model(AgentData, raw)
        return Agent(self, data, scope)

    def delete(
        self,
        id: str,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> None:
        """Deletes an agent and its backing sandbox."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        self._client._transport.request("DELETE", f"{_agents_path(scope)}/{id}")

    def pause(
        self,
        id: str,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> Agent:
        """Pauses an agent (suspends its backing sandbox)."""
        from neevai.handles.agent import Agent

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        raw = self._client._transport.request("POST", f"{_agents_path(scope)}/{id}/pause")
        data = coerce_model(AgentData, raw)
        return Agent(self, data, scope)

    def resume(
        self,
        id: str,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> Agent:
        """Resumes a paused agent."""
        from neevai.handles.agent import Agent

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        raw = self._client._transport.request("POST", f"{_agents_path(scope)}/{id}/resume")
        data = coerce_model(AgentData, raw)
        return Agent(self, data, scope)


class AsyncAgents:
    """Operations on the /agents API endpoint (control plane, asynchronous)."""

    def __init__(self, client: AsyncNeevAI, sandboxes: AsyncSandboxes):
        self._client = client
        self._sandboxes = sandboxes

    async def get_sandbox(
        self,
        sandbox_id: str,
        scope: Scope | None,
    ) -> AsyncSandbox:
        """Fetches the backing sandbox for an agent by id and scope."""
        return await self._sandboxes.get(
            sandbox_id,
            org_id=scope.org_id if scope else None,
            project_id=scope.project_id if scope else None,
        )

    async def create(
        self,
        params: CreateAgentParams | Mapping[str, Any],
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> AsyncAgent:
        """Creates a new agent asynchronously."""
        from neevai.handles.agent import AsyncAgent

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        body = _prepare_create_params(self._client, params)
        raw = await self._client._transport.request(
            "POST",
            _agents_path(scope),
            body=body.model_dump(mode="json", exclude_unset=True),
        )
        data = coerce_model(AgentData, raw)
        return AsyncAgent(self, data, scope)

    async def list(
        self,
        page: int | None = None,
        limit: int | None = None,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> AsyncAgentPage:
        """Lists all agents asynchronously with pagination."""
        from neevai.handles.agent import AsyncAgent

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        query: dict[str, Any] = {}
        if page is not None:
            query["page"] = page
        if limit is not None:
            query["limit"] = limit

        raw = await self._client._transport.request("GET", _agents_path(scope), query=query)
        page_data = coerce_model(AgentListResponse, raw)
        wrapped_items = [AsyncAgent(self, item, scope) for item in page_data.items]
        return AsyncAgentPage(
            items=wrapped_items,
            total=page_data.total,
            page=page_data.page,
            limit=page_data.limit,
        )

    async def get(
        self,
        id: str,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> AsyncAgent:
        """Retrieves details of a specific agent asynchronously."""
        from neevai.handles.agent import AsyncAgent

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        raw = await self._client._transport.request("GET", f"{_agents_path(scope)}/{id}")
        data = coerce_model(AgentData, raw)
        return AsyncAgent(self, data, scope)

    async def update(
        self,
        id: str,
        params: UpdateAgentParams | Mapping[str, Any],
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> AsyncAgent:
        """Updates mutable agent fields in place asynchronously."""
        from neevai.handles.agent import AsyncAgent

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        body = _prepare_update_body(params)
        raw = await self._client._transport.request(
            "PATCH",
            f"{_agents_path(scope)}/{id}",
            body=body,
        )
        data = coerce_model(AgentData, raw)
        return AsyncAgent(self, data, scope)

    async def delete(
        self,
        id: str,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> None:
        """Deletes an agent asynchronously."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        await self._client._transport.request("DELETE", f"{_agents_path(scope)}/{id}")

    async def pause(
        self,
        id: str,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> AsyncAgent:
        """Pauses an agent asynchronously."""
        from neevai.handles.agent import AsyncAgent

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        raw = await self._client._transport.request("POST", f"{_agents_path(scope)}/{id}/pause")
        data = coerce_model(AgentData, raw)
        return AsyncAgent(self, data, scope)

    async def resume(
        self,
        id: str,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> AsyncAgent:
        """Resumes a paused agent asynchronously."""
        from neevai.handles.agent import AsyncAgent

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        raw = await self._client._transport.request("POST", f"{_agents_path(scope)}/{id}/resume")
        data = coerce_model(AgentData, raw)
        return AsyncAgent(self, data, scope)
