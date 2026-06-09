import asyncio
import time
from typing import Any

import httpx

from neevai.errors import (
    APIConnectionError,
    APITimeoutError,
    error_from_status,
)
from neevai.transport.retry import calculate_backoff, parse_retry_after


class ControlTransport:
    """Synchronous HTTP transport for NeevAI control-plane API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_ms: int,
        max_retries: int,
        client: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = httpx.Timeout(timeout_ms / 1000.0)
        self.max_retries = max_retries
        self.client = client or httpx.Client()

    def close(self) -> None:
        self.client.close()

    def request(
        self,
        method: str,
        path: str,
        query: dict[str, Any] | None = None,
        body: Any | None = None,
    ) -> Any:
        """Dispatches an HTTP request to control plane with retries & error handling."""
        # Concatenate base + path, preserving path prefixes correctly
        url = f"{self.base_url}/{path.lstrip('/')}"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"

        # Filter out None values from query parameters
        filtered_query = None
        if query:
            filtered_query = {k: str(v) for k, v in query.items() if v is not None}

        attempt = 0
        while True:
            try:
                response = self.client.request(
                    method=method,
                    url=url,
                    params=filtered_query,
                    json=body,
                    headers=headers,
                    timeout=self.timeout,
                )
            except httpx.TimeoutException as e:
                if attempt < self.max_retries:
                    time.sleep(calculate_backoff(attempt))
                    attempt += 1
                    continue
                raise APITimeoutError(f"Request timed out: {method} {url}") from e
            except httpx.RequestError as e:
                if attempt < self.max_retries:
                    time.sleep(calculate_backoff(attempt))
                    attempt += 1
                    continue
                raise APIConnectionError(f"Request failed to reach the NeevAI API at {url}") from e

            # Check if retry is needed for transient status codes (429 or 5xx)
            if (
                response.status_code == 429 or response.status_code >= 500
            ) and attempt < self.max_retries:
                retry_delay = parse_retry_after(response.headers.get("retry-after"))
                if retry_delay is None:
                    retry_delay = calculate_backoff(attempt)
                time.sleep(retry_delay)
                attempt += 1
                continue

            # Handle non-2xx status codes
            if not response.is_success:
                body_parsed = self._parse_error_body(response)
                request_id = response.headers.get("x-request-id")
                raise error_from_status(
                    response.status_code,
                    body_parsed,
                    request_id,
                    request_method=method,
                    request_url=url,
                )

            if response.status_code == 204:
                return None

            return self._parse_json(response)

    def _parse_json(self, response: httpx.Response) -> Any:
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return {"details": response.text}

    def _parse_error_body(self, response: httpx.Response) -> dict[str, Any] | None:
        parsed = self._parse_json(response)
        if parsed is not None:
            return parsed
        if response.text:
            return {"details": response.text}
        return None


class AsyncControlTransport:
    """Asynchronous HTTP transport for NeevAI control-plane API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_ms: int,
        max_retries: int,
        client: httpx.AsyncClient | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = httpx.Timeout(timeout_ms / 1000.0)
        self.max_retries = max_retries
        self.client = client or httpx.AsyncClient()

    async def aclose(self) -> None:
        await self.client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        query: dict[str, Any] | None = None,
        body: Any | None = None,
    ) -> Any:
        """Dispatches an HTTP request to control plane asynchronously with retries."""
        url = f"{self.base_url}/{path.lstrip('/')}"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"

        filtered_query = None
        if query:
            filtered_query = {k: str(v) for k, v in query.items() if v is not None}

        attempt = 0
        while True:
            try:
                response = await self.client.request(
                    method=method,
                    url=url,
                    params=filtered_query,
                    json=body,
                    headers=headers,
                    timeout=self.timeout,
                )
            except httpx.TimeoutException as e:
                if attempt < self.max_retries:
                    await asyncio.sleep(calculate_backoff(attempt))
                    attempt += 1
                    continue
                raise APITimeoutError(f"Request timed out: {method} {url}") from e
            except httpx.RequestError as e:
                if attempt < self.max_retries:
                    await asyncio.sleep(calculate_backoff(attempt))
                    attempt += 1
                    continue
                raise APIConnectionError(f"Request failed to reach the NeevAI API at {url}") from e

            if (
                response.status_code == 429 or response.status_code >= 500
            ) and attempt < self.max_retries:
                retry_delay = parse_retry_after(response.headers.get("retry-after"))
                if retry_delay is None:
                    retry_delay = calculate_backoff(attempt)
                await asyncio.sleep(retry_delay)
                attempt += 1
                continue

            if not response.is_success:
                body_parsed = self._parse_error_body(response)
                request_id = response.headers.get("x-request-id")
                raise error_from_status(
                    response.status_code,
                    body_parsed,
                    request_id,
                    request_method=method,
                    request_url=url,
                )

            if response.status_code == 204:
                return None

            return self._parse_json(response)

    def _parse_json(self, response: httpx.Response) -> Any:
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return {"details": response.text}

    def _parse_error_body(self, response: httpx.Response) -> dict[str, Any] | None:
        parsed = self._parse_json(response)
        if parsed is not None:
            return parsed
        if response.text:
            return {"details": response.text}
        return None


class RawClient:
    """Untyped synchronous API escape hatch client."""

    def __init__(self, transport: ControlTransport):
        self._transport = transport

    def request(
        self,
        method: str,
        path: str,
        query: dict[str, Any] | None = None,
        body: Any | None = None,
    ) -> Any:
        return self._transport.request(method, path, query, body)


class AsyncRawClient:
    """Untyped asynchronous API escape hatch client."""

    def __init__(self, transport: AsyncControlTransport):
        self._transport = transport

    async def request(
        self,
        method: str,
        path: str,
        query: dict[str, Any] | None = None,
        body: Any | None = None,
    ) -> Any:
        return await self._transport.request(method, path, query, body)
