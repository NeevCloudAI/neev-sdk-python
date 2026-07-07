from __future__ import annotations

import asyncio
import builtins
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx

from neevai._parse import coerce_model, coerce_params
from neevai.errors import NeevAIError
from neevai.generated.aiagent import SandboxPortList
from neevai.types import (
    CreateSandboxParams,
    CreateSnapshotParams,
    SandboxData,
    SandboxListResponse,
    SandboxMetricsResponse,
    SandboxPort,
    Snapshot,
    SnapshotListResponse,
)

# Defaults for get_url's wait: overall budget and delay between preview-URL probes.
DEFAULT_PORT_WAIT_TIMEOUT_MS = 60_000
DEFAULT_PORT_POLL_INTERVAL_MS = 2_000


def _preview_url_reachable(url: str, timeout_ms: float) -> bool:
    """Probes a preview URL; True once the gateway routes it (stops returning a 403/404)."""
    try:
        resp = httpx.get(url, follow_redirects=False, timeout=timeout_ms / 1000.0)
    except (httpx.HTTPError, httpx.InvalidURL):
        # Connection error, DNS failure, timeout, or a malformed URL — not routable yet.
        return False
    return resp.status_code not in (403, 404)


async def _apreview_url_reachable(url: str, timeout_ms: float) -> bool:
    """Async variant of :func:`_preview_url_reachable`."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, follow_redirects=False, timeout=timeout_ms / 1000.0)
    except (httpx.HTTPError, httpx.InvalidURL):
        return False
    return resp.status_code not in (403, 404)


def _validate_wait_args(timeout_ms: int, poll_interval_ms: int) -> None:
    """Rejects non-positive wait budgets before the polling loop starts."""
    if timeout_ms <= 0:
        raise NeevAIError(f"get_url: timeout_ms must be a positive number (got {timeout_ms}).")
    if poll_interval_ms <= 0:
        raise NeevAIError(
            f"get_url: poll_interval_ms must be a positive number (got {poll_interval_ms})."
        )


def _wait_for_preview_url(url: str, timeout_ms: int, poll_interval_ms: int) -> None:
    """Polls a preview URL until the gateway routes it; raises on timeout."""
    _validate_wait_args(timeout_ms, poll_interval_ms)
    deadline = (time.time() * 1000.0) + timeout_ms
    while True:
        remaining = deadline - (time.time() * 1000.0)
        if remaining <= 0:
            raise NeevAIError(f"Preview URL {url} was not routable within {timeout_ms}ms.")
        # Bound each probe to the remaining budget so a stalled request can't outlast the deadline.
        if _preview_url_reachable(url, remaining):
            return
        wait = min(poll_interval_ms, deadline - (time.time() * 1000.0))
        if wait > 0:
            time.sleep(wait / 1000.0)


async def _await_for_preview_url(url: str, timeout_ms: int, poll_interval_ms: int) -> None:
    """Async variant of :func:`_wait_for_preview_url`."""
    _validate_wait_args(timeout_ms, poll_interval_ms)
    deadline = (time.time() * 1000.0) + timeout_ms
    while True:
        remaining = deadline - (time.time() * 1000.0)
        if remaining <= 0:
            raise NeevAIError(f"Preview URL {url} was not routable within {timeout_ms}ms.")
        if await _apreview_url_reachable(url, remaining):
            return
        wait = min(poll_interval_ms, deadline - (time.time() * 1000.0))
        if wait > 0:
            await asyncio.sleep(wait / 1000.0)


if TYPE_CHECKING:
    from neevai.client import AsyncNeevAI, NeevAI
    from neevai.handles.sandbox import AsyncSandbox, Sandbox


@dataclass
class SandboxPage:
    items: list[Sandbox]
    total: int
    page: int
    limit: int


@dataclass
class AsyncSandboxPage:
    items: list[AsyncSandbox]
    total: int
    page: int
    limit: int


def _prepare_create_params(
    client: NeevAI | AsyncNeevAI,
    params: CreateSandboxParams | Mapping[str, Any],
) -> CreateSandboxParams:
    if isinstance(params, Mapping):
        raw: dict[str, Any] = dict(params)
    else:
        raw = params.model_dump(exclude_unset=True)
    return coerce_params(CreateSandboxParams, raw)


def _prepare_create_snapshot_body(
    params: CreateSnapshotParams | Mapping[str, Any] | None,
) -> dict[str, Any]:
    if params is None:
        raw: dict[str, Any] = {}
    elif isinstance(params, Mapping):
        raw = dict(params)
    else:
        raw = params.model_dump(exclude_unset=True)
    body = coerce_params(CreateSnapshotParams, raw).model_dump(exclude_unset=True)
    body["include_memory"] = False
    return body


class Sandboxes:
    """Operations on the /sandboxes API endpoint (synchronous)."""

    def __init__(self, client: NeevAI):
        self._client = client

    def create(
        self,
        params: CreateSandboxParams | Mapping[str, Any],
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> Sandbox:
        """Creates a new sandbox in the resolved project context."""
        from neevai.handles.sandbox import Sandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes"

        body = _prepare_create_params(self._client, params)
        raw = self._client._transport.request(
            "POST",
            path,
            body=body.model_dump(mode="json", exclude_unset=True),
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
    ) -> Sandbox:
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
    ) -> Sandbox:
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
    ) -> Sandbox:
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

    def expose_port(
        self, id: str, port: int, org_id: str | None = None, project_id: str | None = None
    ) -> SandboxPort:
        """Exposes a port for credential-free preview URLs and returns it with its URL."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/ports"
        raw = self._client._transport.request("POST", path, body={"port": port})
        return coerce_model(SandboxPort, raw)

    def list_ports(
        self, id: str, org_id: str | None = None, project_id: str | None = None
    ) -> builtins.list[SandboxPort]:
        """Lists the ports currently exposed for this sandbox's preview URLs."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/ports"
        raw = self._client._transport.request("GET", path)
        return coerce_model(SandboxPortList, raw).ports

    def revoke_port(
        self, id: str, port: int, org_id: str | None = None, project_id: str | None = None
    ) -> None:
        """Revokes a previously exposed preview port (revoking an unexposed port is a no-op)."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = (
            f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}"
            f"/sandboxes/{id}/ports/{port}"
        )
        self._client._transport.request("DELETE", path)

    def get_port_url(
        self,
        id: str,
        port: int,
        wait_until_ready: bool = True,
        timeout_ms: int = DEFAULT_PORT_WAIT_TIMEOUT_MS,
        poll_interval_ms: int = DEFAULT_PORT_POLL_INTERVAL_MS,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> str:
        """Exposes a port and returns its preview URL, waiting until it is routable by default."""
        exposed = self.expose_port(id, port, org_id=org_id, project_id=project_id)
        if not wait_until_ready:
            return exposed.preview_url
        _wait_for_preview_url(exposed.preview_url, timeout_ms, poll_interval_ms)
        return exposed.preview_url

    def create_snapshot(
        self,
        id: str,
        params: CreateSnapshotParams | Mapping[str, Any] | None = None,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> Snapshot:
        """Creates a snapshot of a sandbox (returns immediately with status Pending)."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = (
            f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/snapshots"
        )
        body = _prepare_create_snapshot_body(params)
        raw = self._client._transport.request("POST", path, body=body)
        return coerce_model(Snapshot, raw)

    def list_snapshots(
        self,
        id: str,
        page: int | None = None,
        limit: int | None = None,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> builtins.list[Snapshot]:
        """Lists snapshots taken from a sandbox."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = (
            f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/snapshots"
        )
        query: dict[str, Any] = {}
        if page is not None:
            query["page"] = page
        if limit is not None:
            query["limit"] = limit
        raw = self._client._transport.request("GET", path, query=query)
        page_data = coerce_model(SnapshotListResponse, raw)
        return list(page_data.items)

    def get_snapshot(
        self,
        snapshot_id: str,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> Snapshot:
        """Retrieves snapshot metadata by ID (project-scoped)."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = (
            f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/snapshots/{snapshot_id}"
        )
        raw = self._client._transport.request("GET", path)
        return coerce_model(Snapshot, raw)

    def delete_snapshot(
        self,
        snapshot_id: str,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> None:
        """Deletes a snapshot permanently."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = (
            f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/snapshots/{snapshot_id}"
        )
        self._client._transport.request("DELETE", path)

    def restore(
        self,
        id: str,
        snapshot_id: str,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> Sandbox:
        """Restores a sandbox in place from a snapshot."""
        from neevai.handles.sandbox import Sandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = (
            f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/restore"
        )
        raw = self._client._transport.request(
            "POST",
            path,
            body={"snapshot_id": snapshot_id},
        )
        data = coerce_model(SandboxData, raw)
        return Sandbox(self, data, scope)

    def fork(
        self,
        id: str,
        name: str,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> Sandbox:
        """Forks a sandbox into a new sandbox seeded from its current state."""
        from neevai.handles.sandbox import Sandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/fork"
        raw = self._client._transport.request("POST", path, body={"name": name})
        data = coerce_model(SandboxData, raw)
        return Sandbox(self, data, scope)


class AsyncSandboxes:
    """Operations on the /sandboxes API endpoint (asynchronous)."""

    def __init__(self, client: AsyncNeevAI):
        self._client = client

    async def create(
        self,
        params: CreateSandboxParams | Mapping[str, Any],
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> AsyncSandbox:
        """Creates a new sandbox asynchronously."""
        from neevai.handles.sandbox import AsyncSandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes"

        body = _prepare_create_params(self._client, params)
        raw = await self._client._transport.request(
            "POST",
            path,
            body=body.model_dump(mode="json", exclude_unset=True),
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
    ) -> AsyncSandbox:
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
    ) -> AsyncSandbox:
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
    ) -> AsyncSandbox:
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

    async def expose_port(
        self, id: str, port: int, org_id: str | None = None, project_id: str | None = None
    ) -> SandboxPort:
        """Exposes a port for credential-free preview URLs and returns it with its URL."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/ports"
        raw = await self._client._transport.request("POST", path, body={"port": port})
        return coerce_model(SandboxPort, raw)

    async def list_ports(
        self, id: str, org_id: str | None = None, project_id: str | None = None
    ) -> builtins.list[SandboxPort]:
        """Lists the ports currently exposed for this sandbox's preview URLs."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/ports"
        raw = await self._client._transport.request("GET", path)
        return coerce_model(SandboxPortList, raw).ports

    async def revoke_port(
        self, id: str, port: int, org_id: str | None = None, project_id: str | None = None
    ) -> None:
        """Revokes a previously exposed preview port (revoking an unexposed port is a no-op)."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = (
            f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}"
            f"/sandboxes/{id}/ports/{port}"
        )
        await self._client._transport.request("DELETE", path)

    async def get_port_url(
        self,
        id: str,
        port: int,
        wait_until_ready: bool = True,
        timeout_ms: int = DEFAULT_PORT_WAIT_TIMEOUT_MS,
        poll_interval_ms: int = DEFAULT_PORT_POLL_INTERVAL_MS,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> str:
        """Exposes a port and returns its preview URL, waiting until it is routable by default."""
        exposed = await self.expose_port(id, port, org_id=org_id, project_id=project_id)
        if not wait_until_ready:
            return exposed.preview_url
        await _await_for_preview_url(exposed.preview_url, timeout_ms, poll_interval_ms)
        return exposed.preview_url

    async def create_snapshot(
        self,
        id: str,
        params: CreateSnapshotParams | Mapping[str, Any] | None = None,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> Snapshot:
        """Creates a snapshot of a sandbox asynchronously."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = (
            f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/snapshots"
        )
        body = _prepare_create_snapshot_body(params)
        raw = await self._client._transport.request("POST", path, body=body)
        return coerce_model(Snapshot, raw)

    async def list_snapshots(
        self,
        id: str,
        page: int | None = None,
        limit: int | None = None,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> builtins.list[Snapshot]:
        """Lists snapshots taken from a sandbox asynchronously."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = (
            f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/snapshots"
        )
        query: dict[str, Any] = {}
        if page is not None:
            query["page"] = page
        if limit is not None:
            query["limit"] = limit
        raw = await self._client._transport.request("GET", path, query=query)
        page_data = coerce_model(SnapshotListResponse, raw)
        return list(page_data.items)

    async def get_snapshot(
        self,
        snapshot_id: str,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> Snapshot:
        """Retrieves snapshot metadata by ID asynchronously."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = (
            f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/snapshots/{snapshot_id}"
        )
        raw = await self._client._transport.request("GET", path)
        return coerce_model(Snapshot, raw)

    async def delete_snapshot(
        self,
        snapshot_id: str,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> None:
        """Deletes a snapshot asynchronously."""
        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = (
            f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/snapshots/{snapshot_id}"
        )
        await self._client._transport.request("DELETE", path)

    async def restore(
        self,
        id: str,
        snapshot_id: str,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> AsyncSandbox:
        """Restores a sandbox in place from a snapshot asynchronously."""
        from neevai.handles.sandbox import AsyncSandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = (
            f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/restore"
        )
        raw = await self._client._transport.request(
            "POST",
            path,
            body={"snapshot_id": snapshot_id},
        )
        data = coerce_model(SandboxData, raw)
        return AsyncSandbox(self, data, scope)

    async def fork(
        self,
        id: str,
        name: str,
        org_id: str | None = None,
        project_id: str | None = None,
    ) -> AsyncSandbox:
        """Forks a sandbox into a new sandbox asynchronously."""
        from neevai.handles.sandbox import AsyncSandbox

        scope = self._client._resolve_scope(org_id=org_id, project_id=project_id)
        path = f"/api/v1beta1/orgs/{scope.org_id}/projects/{scope.project_id}/sandboxes/{id}/fork"
        raw = await self._client._transport.request("POST", path, body={"name": name})
        data = coerce_model(SandboxData, raw)
        return AsyncSandbox(self, data, scope)
