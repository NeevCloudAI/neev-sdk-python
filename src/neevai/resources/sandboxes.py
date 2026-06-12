from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from neevai._parse import coerce_model, coerce_params
from neevai.types import (
    CreateSandboxParams,
    SandboxData,
    SandboxListResponse,
    SandboxMetricsResponse,
)

if TYPE_CHECKING:
    from neevai.client import AsyncNeevAI, NeevAI
    from neevai.handles.sandbox import AsyncSandbox, Sandbox


@dataclass
class SandboxPage:
    items: list["Sandbox"]
    total: int
    page: int
    limit: int


@dataclass
class AsyncSandboxPage:
    items: list["AsyncSandbox"]
    total: int
    page: int
    limit: int


def _prepare_create_params(
    client: "NeevAI | AsyncNeevAI",
    params: CreateSandboxParams | Mapping[str, Any],
) -> CreateSandboxParams:
    if isinstance(params, Mapping):
        raw: dict[str, Any] = dict(params)
    else:
        raw = params.model_dump(exclude_unset=True)
    if not raw.get("region"):
        raw["region"] = client._resolve_region()
    return coerce_params(CreateSandboxParams, raw)


class Sandboxes:
    """Operations on the /sandboxes API endpoint (control plane, synchronous)."""

    def __init__(self, client: "NeevAI"):
        self._client = client

    def create(
        self,
        params: CreateSandboxParams | Mapping[str, Any],
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> "Sandbox":
        """Creates a new sandbox in the resolved project context."""
        from neevai.handles.sandbox import Sandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes"

        body = _prepare_create_params(self._client, params)
        raw = self._client._transport.request(
            "POST",
            path,
            body=body.model_dump(exclude_unset=True),
        )
        data = coerce_model(SandboxData, raw)
        return Sandbox(self, data, scope)

    def list(
        self,
        page: int | None = None,
        limit: int | None = None,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> SandboxPage:
        """Lists all sandboxes in the resolved project context with pagination."""
        from neevai.handles.sandbox import Sandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes"

        query: dict[str, Any] = {}
        if page is not None:
            query["page"] = page
        if limit is not None:
            query["limit"] = limit

        raw = self._client._transport.request("GET", path, query=query)
        page_data = coerce_model(SandboxListResponse, raw)
        wrapped_items = [Sandbox(self, item, scope) for item in page_data.items]
        return SandboxPage(
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
    ) -> "Sandbox":
        """Retrieves details of a specific sandbox."""
        from neevai.handles.sandbox import Sandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}"

        raw = self._client._transport.request("GET", path)
        data = coerce_model(SandboxData, raw)
        return Sandbox(self, data, scope)

    def pause(
        self,
        id: str,
        *,
        preserve_memory: bool | None = None,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> "Sandbox":
        """Scales a sandbox to 0 replicas, putting it in Paused state."""
        from neevai.handles.sandbox import Sandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/pause"

        body: dict[str, Any] = {}
        if preserve_memory is not None:
            body["preserve_memory"] = preserve_memory
        raw = self._client._transport.request("POST", path, body=body)
        data = coerce_model(SandboxData, raw)
        return Sandbox(self, data, scope)

    def resume(
        self,
        id: str,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> "Sandbox":
        """Scales a sandbox back to 1 replica, moving it back towards Ready."""
        from neevai.handles.sandbox import Sandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/resume"

        raw = self._client._transport.request("POST", path)
        data = coerce_model(SandboxData, raw)
        return Sandbox(self, data, scope)

    def delete(
        self,
        id: str,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> None:
        """Deletes a sandbox permanently."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}"

        self._client._transport.request("DELETE", path)

    def metrics(
        self,
        id: str,
        from_: str | None = None,
        to: str | None = None,
        step: str | None = None,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> SandboxMetricsResponse:
        """Queries the live health metrics for a sandbox."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = (
            f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/metrics"
        )

        query: dict[str, Any] = {}
        if from_ is not None:
            query["from"] = from_
        if to is not None:
            query["to"] = to
        if step is not None:
            query["step"] = step

        raw = self._client._transport.request("GET", path, query=query)
        return coerce_model(SandboxMetricsResponse, raw)


class AsyncSandboxes:
    """Operations on the /sandboxes API endpoint (control plane, asynchronous)."""

    def __init__(self, client: "AsyncNeevAI"):
        self._client = client

    async def create(
        self,
        params: CreateSandboxParams | Mapping[str, Any],
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> "AsyncSandbox":
        """Creates a new sandbox asynchronously."""
        from neevai.handles.sandbox import AsyncSandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes"

        body = _prepare_create_params(self._client, params)
        raw = await self._client._transport.request(
            "POST",
            path,
            body=body.model_dump(exclude_unset=True),
        )
        data = coerce_model(SandboxData, raw)
        return AsyncSandbox(self, data, scope)

    async def list(
        self,
        page: int | None = None,
        limit: int | None = None,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> AsyncSandboxPage:
        """Lists all sandboxes asynchronously with pagination."""
        from neevai.handles.sandbox import AsyncSandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes"

        query: dict[str, Any] = {}
        if page is not None:
            query["page"] = page
        if limit is not None:
            query["limit"] = limit

        raw = await self._client._transport.request("GET", path, query=query)
        page_data = coerce_model(SandboxListResponse, raw)
        wrapped_items = [AsyncSandbox(self, item, scope) for item in page_data.items]
        return AsyncSandboxPage(
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
    ) -> "AsyncSandbox":
        """Retrieves details of a specific sandbox asynchronously."""
        from neevai.handles.sandbox import AsyncSandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}"

        raw = await self._client._transport.request("GET", path)
        data = coerce_model(SandboxData, raw)
        return AsyncSandbox(self, data, scope)

    async def pause(
        self,
        id: str,
        *,
        preserve_memory: bool | None = None,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> "AsyncSandbox":
        """Scales a sandbox to 0 replicas asynchronously."""
        from neevai.handles.sandbox import AsyncSandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/pause"

        body: dict[str, Any] = {}
        if preserve_memory is not None:
            body["preserve_memory"] = preserve_memory
        raw = await self._client._transport.request("POST", path, body=body)
        data = coerce_model(SandboxData, raw)
        return AsyncSandbox(self, data, scope)

    async def resume(
        self,
        id: str,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> "AsyncSandbox":
        """Scales a sandbox back to 1 replica asynchronously."""
        from neevai.handles.sandbox import AsyncSandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/resume"

        raw = await self._client._transport.request("POST", path)
        data = coerce_model(SandboxData, raw)
        return AsyncSandbox(self, data, scope)

    async def delete(
        self,
        id: str,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> None:
        """Deletes a sandbox asynchronously."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}"

        await self._client._transport.request("DELETE", path)

    async def metrics(
        self,
        id: str,
        from_: str | None = None,
        to: str | None = None,
        step: str | None = None,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> SandboxMetricsResponse:
        """Queries the live health metrics asynchronously."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = (
            f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/metrics"
        )

        query: dict[str, Any] = {}
        if from_ is not None:
            query["from"] = from_
        if to is not None:
            query["to"] = to
        if step is not None:
            query["step"] = step

        raw = await self._client._transport.request("GET", path, query=query)
        return coerce_model(SandboxMetricsResponse, raw)
