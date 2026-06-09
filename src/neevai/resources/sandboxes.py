from typing import TYPE_CHECKING, TypedDict

from neevai.types import CreateSandboxParams, SandboxMetricsResponse

if TYPE_CHECKING:
    from neevai.client import AsyncNeevAI, NeevAI
    from neevai.handles.sandbox import AsyncSandbox, Sandbox


class SandboxPage(TypedDict):
    items: list["Sandbox"]
    total: int
    page: int
    limit: int


class AsyncSandboxPage(TypedDict):
    items: list["AsyncSandbox"]
    total: int
    page: int
    limit: int


class Sandboxes:
    """Operations on the /sandboxes API endpoint (control plane, synchronous)."""

    def __init__(self, client: "NeevAI"):
        self._client = client

    def create(
        self,
        params: CreateSandboxParams,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> "Sandbox":
        """Creates a new sandbox in the resolved project context."""
        from neevai.handles.sandbox import Sandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes"

        body = dict(params)
        if not body.get("region"):
            body["region"] = self._client._resolve_region()
        data = self._client._transport.request("POST", path, body=body)
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

        query = {}
        if page is not None:
            query["page"] = page
        if limit is not None:
            query["limit"] = limit

        data = self._client._transport.request("GET", path, query=query)
        wrapped_items = [Sandbox(self, item, scope) for item in data["items"]]
        return SandboxPage(
            items=wrapped_items,
            total=data["total"],
            page=data["page"],
            limit=data["limit"],
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

        data = self._client._transport.request("GET", path)
        return Sandbox(self, data, scope)

    def pause(
        self,
        id: str,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> "Sandbox":
        """Scales a sandbox to 0 replicas, putting it in Paused state."""
        from neevai.handles.sandbox import Sandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/pause"

        data = self._client._transport.request("POST", path)
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

        data = self._client._transport.request("POST", path)
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

        query = {}
        if from_ is not None:
            query["from"] = from_
        if to is not None:
            query["to"] = to
        if step is not None:
            query["step"] = step

        return self._client._transport.request("GET", path, query=query)


class AsyncSandboxes:
    """Operations on the /sandboxes API endpoint (control plane, asynchronous)."""

    def __init__(self, client: "AsyncNeevAI"):
        self._client = client

    async def create(
        self,
        params: CreateSandboxParams,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> "AsyncSandbox":
        """Creates a new sandbox asynchronously."""
        from neevai.handles.sandbox import AsyncSandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes"

        body = dict(params)
        if not body.get("region"):
            body["region"] = self._client._resolve_region()
        data = await self._client._transport.request("POST", path, body=body)
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

        query = {}
        if page is not None:
            query["page"] = page
        if limit is not None:
            query["limit"] = limit

        data = await self._client._transport.request("GET", path, query=query)
        wrapped_items = [AsyncSandbox(self, item, scope) for item in data["items"]]
        return AsyncSandboxPage(
            items=wrapped_items,
            total=data["total"],
            page=data["page"],
            limit=data["limit"],
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

        data = await self._client._transport.request("GET", path)
        return AsyncSandbox(self, data, scope)

    async def pause(
        self,
        id: str,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> "AsyncSandbox":
        """Scales a sandbox to 0 replicas asynchronously."""
        from neevai.handles.sandbox import AsyncSandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/pause"

        data = await self._client._transport.request("POST", path)
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

        data = await self._client._transport.request("POST", path)
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

        query = {}
        if from_ is not None:
            query["from"] = from_
        if to is not None:
            query["to"] = to
        if step is not None:
            query["step"] = step

        return await self._client._transport.request("GET", path, query=query)
