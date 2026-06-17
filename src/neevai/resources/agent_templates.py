from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from neevai._parse import coerce_model
from neevai.types import AgentTemplate, AgentTemplateListResponse

if TYPE_CHECKING:
    from neevai.client import AsyncNeevAI, NeevAI


@dataclass
class AgentTemplatePage:
    items: list[AgentTemplate]
    total: int
    page: int
    limit: int


@dataclass
class AsyncAgentTemplatePage:
    items: list[AgentTemplate]
    total: int
    page: int
    limit: int


@dataclass
class ListAgentTemplatesParams:
    page: int | None = None
    limit: int | None = None


class AgentTemplates:
    """Read-only access to the platform agent-template catalogue."""

    def __init__(self, client: "NeevAI"):
        self._client = client

    def list(self, page: int | None = None, limit: int | None = None) -> AgentTemplatePage:
        """Lists available agent templates."""
        query: dict[str, Any] = {}
        if page is not None:
            query["page"] = page
        if limit is not None:
            query["limit"] = limit
        raw = self._client._transport.request(
            "GET",
            "/api/v1beta1/agent-templates",
            query=query,
        )
        data = coerce_model(AgentTemplateListResponse, raw)
        return AgentTemplatePage(
            items=data.items,
            total=data.total,
            page=data.page,
            limit=data.limit,
        )

    def get(self, template_id: str) -> AgentTemplate:
        """Fetches a single agent template by id."""
        raw = self._client._transport.request(
            "GET",
            f"/api/v1beta1/agent-templates/{template_id}",
        )
        return coerce_model(AgentTemplate, raw)


class AsyncAgentTemplates:
    """Asynchronous read-only access to the platform agent-template catalogue."""

    def __init__(self, client: "AsyncNeevAI"):
        self._client = client

    async def list(
        self, page: int | None = None, limit: int | None = None
    ) -> AsyncAgentTemplatePage:
        """Lists available agent templates asynchronously."""
        query: dict[str, Any] = {}
        if page is not None:
            query["page"] = page
        if limit is not None:
            query["limit"] = limit
        raw = await self._client._transport.request(
            "GET",
            "/api/v1beta1/agent-templates",
            query=query,
        )
        data = coerce_model(AgentTemplateListResponse, raw)
        return AsyncAgentTemplatePage(
            items=data.items,
            total=data.total,
            page=data.page,
            limit=data.limit,
        )

    async def get(self, template_id: str) -> AgentTemplate:
        """Fetches a single agent template by id asynchronously."""
        raw = await self._client._transport.request(
            "GET",
            f"/api/v1beta1/agent-templates/{template_id}",
        )
        return coerce_model(AgentTemplate, raw)
