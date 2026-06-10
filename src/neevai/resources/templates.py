from dataclasses import dataclass
from typing import TYPE_CHECKING

from neevai._parse import coerce_model
from neevai.types import SandboxTemplate, SandboxTemplateListResponse

if TYPE_CHECKING:
    from neevai.client import AsyncNeevAI, NeevAI


@dataclass
class TemplatePage:
    items: list[SandboxTemplate]
    total: int
    page: int
    limit: int


@dataclass
class AsyncTemplatePage:
    items: list[SandboxTemplate]
    total: int
    page: int
    limit: int


class Templates:
    """Read-only access to the platform sandbox-template catalogue."""

    def __init__(self, client: "NeevAI"):
        self._client = client

    def list(self, page: int | None = None, limit: int | None = None) -> TemplatePage:
        """Lists available sandbox templates."""
        raw = self._client._transport.request(
            "GET",
            "/api/v1beta1/sandbox-templates",
            query={"page": page, "limit": limit},
        )
        data = coerce_model(SandboxTemplateListResponse, raw)
        return TemplatePage(
            items=data.items,
            total=data.total,
            page=data.page,
            limit=data.limit,
        )

    def get(self, template_id: str) -> SandboxTemplate:
        """Fetches a single sandbox template by id."""
        raw = self._client._transport.request(
            "GET",
            f"/api/v1beta1/sandbox-templates/{template_id}",
        )
        return coerce_model(SandboxTemplate, raw)


class AsyncTemplates:
    """Asynchronous read-only access to the platform sandbox-template catalogue."""

    def __init__(self, client: "AsyncNeevAI"):
        self._client = client

    async def list(self, page: int | None = None, limit: int | None = None) -> AsyncTemplatePage:
        """Lists available sandbox templates asynchronously."""
        raw = await self._client._transport.request(
            "GET",
            "/api/v1beta1/sandbox-templates",
            query={"page": page, "limit": limit},
        )
        data = coerce_model(SandboxTemplateListResponse, raw)
        return AsyncTemplatePage(
            items=data.items,
            total=data.total,
            page=data.page,
            limit=data.limit,
        )

    async def get(self, template_id: str) -> SandboxTemplate:
        """Fetches a single sandbox template by id asynchronously."""
        raw = await self._client._transport.request(
            "GET",
            f"/api/v1beta1/sandbox-templates/{template_id}",
        )
        return coerce_model(SandboxTemplate, raw)
