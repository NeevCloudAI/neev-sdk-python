from __future__ import annotations

import builtins
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from neevai._egress import build_egress, prepare_update_body
from neevai._parse import coerce_model, coerce_params
from neevai.generated.aiagent import SandboxPortList
from neevai.resources.sandboxes import (
    DEFAULT_PORT_POLL_INTERVAL_MS,
    DEFAULT_PORT_WAIT_TIMEOUT_MS,
    _await_for_preview_url,
    _wait_for_preview_url,
)
from neevai.types import (
    AgentData,
    AgentListResponse,
    AuditTrail,
    CreateAgentParams,
    SandboxPort,
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
    allow_internet: bool | None = None,
    allow_egress: list[str] | None = None,
) -> CreateAgentParams:
    if isinstance(params, Mapping):
        raw: dict[str, Any] = dict(params)
    else:
        raw = params.model_dump(exclude_unset=True)
    # Translate the allow_internet/allow_egress convenience into the egress policy,
    # unless the caller already set an explicit egress (which takes precedence).
    if raw.get("egress") is None:
        egress = build_egress(allow_internet, allow_egress)
        if egress is not None:
            raw["egress"] = egress
    return coerce_params(CreateAgentParams, raw)


class Agents:
    """Operations on the /agents API endpoint (synchronous)."""

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
        *,
        allow_internet: bool | None = None,
        allow_egress: list[str] | None = None,
    ) -> Agent:
        """Creates a new agent from a catalogue template in the resolved project context.

        Egress is deny-all by default. ``allow_internet=True`` opens all egress
        (0.0.0.0/0 and ::/0); ``allow_egress`` allows specific hosts (FQDN or CIDR). An
        explicit ``egress`` in ``params`` takes precedence over both.
        """
        from neevai.handles.agent import Agent

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        body = _prepare_create_params(
            self._client, params, allow_internet=allow_internet, allow_egress=allow_egress
        )
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
        """Retrieves details of a specific agent by its id or its name.

        Names are unique within a project, so either identifies one agent.
        """
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
        *,
        allow_internet: bool | None = None,
        allow_egress: builtins.list[str] | None = None,
    ) -> Agent:
        """Updates mutable agent fields (resources, egress, idle window) in place.

        ``allow_internet=True`` opens all egress (0.0.0.0/0 and ::/0); ``allow_egress``
        allows specific hosts (FQDN or CIDR). An explicit ``egress`` in ``params`` takes
        precedence over both. ``egress_add`` / ``egress_remove`` edit the existing
        allow-list in place instead (removals apply first) and cannot be combined with
        ``egress`` or the convenience flags. ``idle_timeout_seconds`` sets the idle
        window; 0 removes the limit. At least one of ``resources``, ``egress``,
        ``egress_add``, ``egress_remove`` or ``idle_timeout_seconds`` must result.
        """
        from neevai.handles.agent import Agent

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        body = prepare_update_body(
            UpdateAgentParams, params, allow_internet=allow_internet, allow_egress=allow_egress
        )
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

    def keepalive(
        self,
        id: str,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> Agent:
        """Resets an agent's idle timer, keeping a busy agent running.

        Call it periodically while work is in progress, for example once per agent turn.
        """
        from neevai.handles.agent import Agent

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        raw = self._client._transport.request("POST", f"{_agents_path(scope)}/{id}/keepalive")
        data = coerce_model(AgentData, raw)
        return Agent(self, data, scope)

    def rollback(
        self,
        id: str,
        snapshot_id: str | UUID,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> Agent:
        """Rolls an agent's backing sandbox back in place to a snapshot.

        The snapshot must belong to a sandbox in the same project.
        """
        from neevai.handles.agent import Agent

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        raw = self._client._transport.request(
            "POST",
            f"{_agents_path(scope)}/{id}/rollback",
            body={"snapshot_id": snapshot_id},
        )
        data = coerce_model(AgentData, raw)
        return Agent(self, data, scope)

    def audit(
        self,
        id: str,
        *,
        from_: str | None = None,
        to: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> AuditTrail:
        """Reads one page of the command audit trail for an agent.

        Same shape and recording rules as the sandbox trail, newest first. The
        response's ``sandbox_id`` is the sandbox backing the agent, not the agent id.
        Pass the previous page's ``next_cursor`` as ``cursor`` to read older records.
        """
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        query: dict[str, Any] = {}
        if from_ is not None:
            query["from"] = from_
        if to is not None:
            query["to"] = to
        if cursor is not None:
            query["cursor"] = cursor
        if limit is not None:
            query["limit"] = limit

        raw = self._client._transport.request(
            "GET", f"{_agents_path(scope)}/{id}/audit", query=query
        )
        return coerce_model(AuditTrail, raw)

    def expose_port(
        self,
        id: str,
        port: int,
        org_id: str | None = None,
        project_id: str | None = None,
        *,
        slug: str | None = None,
    ) -> SandboxPort:
        """Exposes an agent port for credential-free preview URLs and returns it with its URL.

        The URL needs no credential: its slug is the only thing gating it, so treat it
        as a secret. Omit ``slug`` and a random, unguessable one is generated. Passing a
        different ``slug`` (8 lowercase letters/digits) for an already exposed port
        replaces it and breaks the previous URL — use that to rotate a leaked URL.
        """
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        body: dict[str, Any] = {"port": port}
        if slug is not None:
            body["slug"] = slug
        raw = self._client._transport.request(
            "POST", f"{_agents_path(scope)}/{id}/ports", body=body
        )
        return coerce_model(SandboxPort, raw)

    def list_ports(
        self, id: str, org_id: str | None = None, project_id: str | None = None
    ) -> builtins.list[SandboxPort]:
        """Lists the ports currently exposed for this agent's preview URLs."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        raw = self._client._transport.request("GET", f"{_agents_path(scope)}/{id}/ports")
        return coerce_model(SandboxPortList, raw).ports

    def revoke_port(
        self, id: str, port: int, org_id: str | None = None, project_id: str | None = None
    ) -> None:
        """Revokes a previously exposed agent preview port (revoking an unexposed port is a no-op)."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        self._client._transport.request("DELETE", f"{_agents_path(scope)}/{id}/ports/{port}")

    def get_port_url(
        self,
        id: str,
        port: int,
        wait_until_ready: bool = True,
        timeout_ms: int = DEFAULT_PORT_WAIT_TIMEOUT_MS,
        poll_interval_ms: int = DEFAULT_PORT_POLL_INTERVAL_MS,
        org_id: str | None = None,
        project_id: str | None = None,
        *,
        slug: str | None = None,
    ) -> str:
        """Exposes an agent port and returns its preview URL, waiting until it is routable by default.

        ``slug`` is forwarded to ``expose_port``: omit it for a random one.
        """
        exposed = self.expose_port(id, port, org_id=org_id, project_id=project_id, slug=slug)
        if not wait_until_ready:
            return exposed.preview_url
        _wait_for_preview_url(exposed.preview_url, timeout_ms, poll_interval_ms)
        return exposed.preview_url


class AsyncAgents:
    """Operations on the /agents API endpoint (asynchronous)."""

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
        *,
        allow_internet: bool | None = None,
        allow_egress: list[str] | None = None,
    ) -> AsyncAgent:
        """Creates a new agent asynchronously.

        Egress is deny-all by default. ``allow_internet=True`` opens all egress
        (0.0.0.0/0 and ::/0); ``allow_egress`` allows specific hosts (FQDN or CIDR). An
        explicit ``egress`` in ``params`` takes precedence over both.
        """
        from neevai.handles.agent import AsyncAgent

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        body = _prepare_create_params(
            self._client, params, allow_internet=allow_internet, allow_egress=allow_egress
        )
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
        """Retrieves details of a specific agent by its id or its name asynchronously.

        Names are unique within a project, so either identifies one agent.
        """
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
        *,
        allow_internet: bool | None = None,
        allow_egress: builtins.list[str] | None = None,
    ) -> AsyncAgent:
        """Updates mutable agent fields (resources, egress, idle window) in place asynchronously.

        ``allow_internet=True`` opens all egress (0.0.0.0/0 and ::/0); ``allow_egress``
        allows specific hosts (FQDN or CIDR). An explicit ``egress`` in ``params`` takes
        precedence over both. ``egress_add`` / ``egress_remove`` edit the existing
        allow-list in place instead (removals apply first) and cannot be combined with
        ``egress`` or the convenience flags. ``idle_timeout_seconds`` sets the idle
        window; 0 removes the limit. At least one of ``resources``, ``egress``,
        ``egress_add``, ``egress_remove`` or ``idle_timeout_seconds`` must result.
        """
        from neevai.handles.agent import AsyncAgent

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        body = prepare_update_body(
            UpdateAgentParams, params, allow_internet=allow_internet, allow_egress=allow_egress
        )
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

    async def keepalive(
        self,
        id: str,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> AsyncAgent:
        """Resets an agent's idle timer, keeping a busy agent running asynchronously.

        Call it periodically while work is in progress, for example once per agent turn.
        """
        from neevai.handles.agent import AsyncAgent

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        raw = await self._client._transport.request("POST", f"{_agents_path(scope)}/{id}/keepalive")
        data = coerce_model(AgentData, raw)
        return AsyncAgent(self, data, scope)

    async def rollback(
        self,
        id: str,
        snapshot_id: str | UUID,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> AsyncAgent:
        """Rolls an agent's backing sandbox back in place to a snapshot asynchronously.

        The snapshot must belong to a sandbox in the same project.
        """
        from neevai.handles.agent import AsyncAgent

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        raw = await self._client._transport.request(
            "POST",
            f"{_agents_path(scope)}/{id}/rollback",
            body={"snapshot_id": snapshot_id},
        )
        data = coerce_model(AgentData, raw)
        return AsyncAgent(self, data, scope)

    async def audit(
        self,
        id: str,
        *,
        from_: str | None = None,
        to: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> AuditTrail:
        """Reads one page of the command audit trail for an agent asynchronously.

        Same shape and recording rules as the sandbox trail, newest first. The
        response's ``sandbox_id`` is the sandbox backing the agent, not the agent id.
        Pass the previous page's ``next_cursor`` as ``cursor`` to read older records.
        """
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        query: dict[str, Any] = {}
        if from_ is not None:
            query["from"] = from_
        if to is not None:
            query["to"] = to
        if cursor is not None:
            query["cursor"] = cursor
        if limit is not None:
            query["limit"] = limit

        raw = await self._client._transport.request(
            "GET", f"{_agents_path(scope)}/{id}/audit", query=query
        )
        return coerce_model(AuditTrail, raw)

    async def expose_port(
        self,
        id: str,
        port: int,
        org_id: str | None = None,
        project_id: str | None = None,
        *,
        slug: str | None = None,
    ) -> SandboxPort:
        """Exposes an agent port for credential-free preview URLs and returns it with its URL.

        The URL needs no credential: its slug is the only thing gating it, so treat it
        as a secret. Omit ``slug`` and a random, unguessable one is generated. Passing a
        different ``slug`` (8 lowercase letters/digits) for an already exposed port
        replaces it and breaks the previous URL — use that to rotate a leaked URL.
        """
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        body: dict[str, Any] = {"port": port}
        if slug is not None:
            body["slug"] = slug
        raw = await self._client._transport.request(
            "POST", f"{_agents_path(scope)}/{id}/ports", body=body
        )
        return coerce_model(SandboxPort, raw)

    async def list_ports(
        self, id: str, org_id: str | None = None, project_id: str | None = None
    ) -> builtins.list[SandboxPort]:
        """Lists the ports currently exposed for this agent's preview URLs."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        raw = await self._client._transport.request("GET", f"{_agents_path(scope)}/{id}/ports")
        return coerce_model(SandboxPortList, raw).ports

    async def revoke_port(
        self, id: str, port: int, org_id: str | None = None, project_id: str | None = None
    ) -> None:
        """Revokes a previously exposed agent preview port (revoking an unexposed port is a no-op)."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        await self._client._transport.request("DELETE", f"{_agents_path(scope)}/{id}/ports/{port}")

    async def get_port_url(
        self,
        id: str,
        port: int,
        wait_until_ready: bool = True,
        timeout_ms: int = DEFAULT_PORT_WAIT_TIMEOUT_MS,
        poll_interval_ms: int = DEFAULT_PORT_POLL_INTERVAL_MS,
        org_id: str | None = None,
        project_id: str | None = None,
        *,
        slug: str | None = None,
    ) -> str:
        """Exposes an agent port and returns its preview URL, waiting until it is routable by default.

        ``slug`` is forwarded to ``expose_port``: omit it for a random one.
        """
        exposed = await self.expose_port(id, port, org_id=org_id, project_id=project_id, slug=slug)
        if not wait_until_ready:
            return exposed.preview_url
        await _await_for_preview_url(exposed.preview_url, timeout_ms, poll_interval_ms)
        return exposed.preview_url
