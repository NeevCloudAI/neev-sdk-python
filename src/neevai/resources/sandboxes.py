from typing import TYPE_CHECKING, Any, Dict, List, Optional, TypedDict

from neevai.types import CreateSandboxParams, SandboxMetricsResponse, Scope

if TYPE_CHECKING:
    from neevai.client import AsyncNeevAI, NeevAI
    from neevai.sandbox import AsyncSandbox, Sandbox


class SandboxPage(TypedDict):
    items: List["Sandbox"]
    total: int
    page: int
    limit: int


class AsyncSandboxPage(TypedDict):
    items: List["AsyncSandbox"]
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
        org_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> "Sandbox":
        """Creates a new sandbox in the resolved project context."""
        from neevai.sandbox import Sandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes"

        data = self._client._transport.request("POST", path, body=params)
        return Sandbox(self, data, scope)

    def list(
        self,
        page: Optional[int] = None,
        limit: Optional[int] = None,
        org_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> SandboxPage:
        """Lists all sandboxes in the resolved project context with pagination."""
        from neevai.sandbox import Sandbox

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
        org_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> "Sandbox":
        """Retrieves details of a specific sandbox."""
        from neevai.sandbox import Sandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}"

        data = self._client._transport.request("GET", path)
        return Sandbox(self, data, scope)

    def pause(
        self,
        id: str,
        org_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> "Sandbox":
        """Scales a sandbox to 0 replicas, putting it in Paused state."""
        from neevai.sandbox import Sandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/pause"

        data = self._client._transport.request("POST", path)
        return Sandbox(self, data, scope)

    def resume(
        self,
        id: str,
        org_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> "Sandbox":
        """Scales a sandbox back to 1 replica, moving it back towards Ready."""
        from neevai.sandbox import Sandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/resume"

        data = self._client._transport.request("POST", path)
        return Sandbox(self, data, scope)

    def delete(
        self,
        id: str,
        org_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> None:
        """Deletes a sandbox permanently."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}"

        self._client._transport.request("DELETE", path)

    def metrics(
        self,
        id: str,
        from_: Optional[str] = None,
        to: Optional[str] = None,
        step: Optional[str] = None,
        org_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> SandboxMetricsResponse:
        """Queries the live health metrics for a sandbox."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/metrics"

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
        org_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> "AsyncSandbox":
        """Creates a new sandbox asynchronously."""
        from neevai.sandbox import AsyncSandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes"

        data = await self._client._transport.request("POST", path, body=params)
        return AsyncSandbox(self, data, scope)

    async def list(
        self,
        page: Optional[int] = None,
        limit: Optional[int] = None,
        org_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> AsyncSandboxPage:
        """Lists all sandboxes asynchronously with pagination."""
        from neevai.sandbox import AsyncSandbox

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
        org_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> "AsyncSandbox":
        """Retrieves details of a specific sandbox asynchronously."""
        from neevai.sandbox import AsyncSandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}"

        data = await self._client._transport.request("GET", path)
        return AsyncSandbox(self, data, scope)

    async def pause(
        self,
        id: str,
        org_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> "AsyncSandbox":
        """Scales a sandbox to 0 replicas asynchronously."""
        from neevai.sandbox import AsyncSandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/pause"

        data = await self._client._transport.request("POST", path)
        return AsyncSandbox(self, data, scope)

    async def resume(
        self,
        id: str,
        org_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> "AsyncSandbox":
        """Scales a sandbox back to 1 replica asynchronously."""
        from neevai.sandbox import AsyncSandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/resume"

        data = await self._client._transport.request("POST", path)
        return AsyncSandbox(self, data, scope)

    async def delete(
        self,
        id: str,
        org_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> None:
        """Deletes a sandbox asynchronously."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}"

        await self._client._transport.request("DELETE", path)

    async def metrics(
        self,
        id: str,
        from_: Optional[str] = None,
        to: Optional[str] = None,
        step: Optional[str] = None,
        org_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> SandboxMetricsResponse:
        """Queries the live health metrics asynchronously."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/metrics"

        query = {}
        if from_ is not None:
            query["from"] = from_
        if to is not None:
            query["to"] = to
        if step is not None:
            query["step"] = step

        return await self._client._transport.request("GET", path, query=query)
