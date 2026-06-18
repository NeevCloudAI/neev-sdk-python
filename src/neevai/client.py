import os
from typing import Any

import httpx

from neevai.errors import NeevAIError
from neevai.resources.sandboxes import AsyncSandboxes, Sandboxes
from neevai.resources.templates import AsyncTemplates, Templates
from neevai.transport.lifecycle import (
    AsyncControlTransport,
    AsyncRawClient,
    ControlTransport,
    RawClient,
)
from neevai.types import Scope

DEFAULT_BASE_URL = "https://api.ai.neevcloud.com/agent"
DEFAULT_TIMEOUT_MS = 60_000
DEFAULT_MAX_RETRIES = 2


def _read_env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


class NeevAI:
    """NeevAI platform synchronous client.

    Defaults for ``org_id``, ``project_id``, and ``region`` can be set via
    constructor kwargs or the ``NEEVCLOUD_*`` / ``NEEV_*`` environment variables.
    """

    def __init__(
        self,
        api_key: str | None = None,
        org_id: str | None = None,
        project_id: str | None = None,
        region: str | None = None,
        base_url: str | None = None,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        client: httpx.Client | None = None,
    ):
        resolved_api_key = api_key or _read_env("NEEVCLOUD_API_KEY", "NEEV_API_KEY")
        if not resolved_api_key:
            raise NeevAIError(
                "Missing API key. Pass `api_key` or set the NEEVCLOUD_API_KEY "
                "(or NEEV_API_KEY) environment variable."
            )

        self.default_org_id = org_id or _read_env("NEEVCLOUD_ORG_ID", "NEEV_ORG_ID")
        self.default_project_id = project_id or _read_env("NEEVCLOUD_PROJECT_ID", "NEEV_PROJECT_ID")
        self.default_region = region or _read_env("NEEVCLOUD_REGION", "NEEV_REGION")
        self.base_url = (
            base_url or _read_env("NEEVCLOUD_BASE_URL", "NEEV_BASE_URL") or DEFAULT_BASE_URL
        )

        self._transport = ControlTransport(
            base_url=self.base_url,
            api_key=resolved_api_key,
            timeout_ms=timeout_ms,
            max_retries=max_retries,
            client=client,
        )

        self.raw = RawClient(self._transport)
        self.sandboxes = Sandboxes(self)
        self.templates = Templates(self)

    def close(self) -> None:
        """Closes the underlying HTTP client transport connections."""
        self._transport.close()

    def __enter__(self) -> "NeevAI":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def _resolve_scope(self, org_id: str | None = None, project_id: str | None = None) -> Scope:
        """Merges caller overrides with client defaults and validates them."""
        resolved_org = org_id or self.default_org_id
        resolved_proj = project_id or self.default_project_id

        if not resolved_org:
            raise NeevAIError(
                "Missing org_id. Set it on the client, via NEEVCLOUD_ORG_ID or NEEV_ORG_ID, or per call."
            )
        if not resolved_proj:
            raise NeevAIError(
                "Missing project_id. Set it on the client, via NEEVCLOUD_PROJECT_ID or "
                "NEEV_PROJECT_ID, or per call."
            )

        return Scope(org_id=resolved_org, project_id=resolved_proj)

    def _resolve_region(self, region: str | None = None) -> str:
        """Merges caller overrides with client defaults and validates region."""
        resolved = region or self.default_region
        if not resolved:
            raise NeevAIError(
                "Missing region. Pass `region` in create params, set it on the client, "
                "or set the NEEVCLOUD_REGION or NEEV_REGION environment variable."
            )
        return resolved


class AsyncNeevAI:
    """NeevAI platform asynchronous client.

    Defaults for ``org_id``, ``project_id``, and ``region`` can be set via
    constructor kwargs or the ``NEEVCLOUD_*`` / ``NEEV_*`` environment variables.
    """

    def __init__(
        self,
        api_key: str | None = None,
        org_id: str | None = None,
        project_id: str | None = None,
        region: str | None = None,
        base_url: str | None = None,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        client: httpx.AsyncClient | None = None,
    ):
        resolved_api_key = api_key or _read_env("NEEVCLOUD_API_KEY", "NEEV_API_KEY")
        if not resolved_api_key:
            raise NeevAIError(
                "Missing API key. Pass `api_key` or set the NEEVCLOUD_API_KEY "
                "(or NEEV_API_KEY) environment variable."
            )

        self.default_org_id = org_id or _read_env("NEEVCLOUD_ORG_ID", "NEEV_ORG_ID")
        self.default_project_id = project_id or _read_env("NEEVCLOUD_PROJECT_ID", "NEEV_PROJECT_ID")
        self.default_region = region or _read_env("NEEVCLOUD_REGION", "NEEV_REGION")
        self.base_url = (
            base_url or _read_env("NEEVCLOUD_BASE_URL", "NEEV_BASE_URL") or DEFAULT_BASE_URL
        )

        self._transport = AsyncControlTransport(
            base_url=self.base_url,
            api_key=resolved_api_key,
            timeout_ms=timeout_ms,
            max_retries=max_retries,
            client=client,
        )

        self.raw = AsyncRawClient(self._transport)
        self.sandboxes = AsyncSandboxes(self)
        self.templates = AsyncTemplates(self)

    async def aclose(self) -> None:
        """Closes the underlying HTTP client transport connections asynchronously."""
        await self._transport.aclose()

    async def __aenter__(self) -> "AsyncNeevAI":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.aclose()

    def _resolve_scope(self, org_id: str | None = None, project_id: str | None = None) -> Scope:
        """Merges caller overrides with client defaults and validates them."""
        resolved_org = org_id or self.default_org_id
        resolved_proj = project_id or self.default_project_id

        if not resolved_org:
            raise NeevAIError(
                "Missing org_id. Set it on the client, via NEEVCLOUD_ORG_ID or NEEV_ORG_ID, or per call."
            )
        if not resolved_proj:
            raise NeevAIError(
                "Missing project_id. Set it on the client, via NEEVCLOUD_PROJECT_ID or "
                "NEEV_PROJECT_ID, or per call."
            )

        return Scope(org_id=resolved_org, project_id=resolved_proj)

    def _resolve_region(self, region: str | None = None) -> str:
        """Merges caller overrides with client defaults and validates region."""
        resolved = region or self.default_region
        if not resolved:
            raise NeevAIError(
                "Missing region. Pass `region` in create params, set it on the client, "
                "or set the NEEVCLOUD_REGION or NEEV_REGION environment variable."
            )
        return resolved
