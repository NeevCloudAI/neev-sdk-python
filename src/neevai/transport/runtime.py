from collections.abc import AsyncGenerator, Generator
from typing import Any

import httpx

from neevai.errors import error_from_status

SANDBOX_ID_HEADER = "X-Sandbox-Id"


class RuntimeTransport:
    """Synchronous HTTP transport for sandbox runtime."""

    def __init__(
        self,
        connect_url: str,
        api_key: str,
        timeout_ms: int = 60000,
        client: httpx.Client | None = None,
        sandbox_id: str | None = None,
    ):
        self.connect_url = connect_url.rstrip("/")
        self.api_key = api_key
        self.sandbox_id = sandbox_id
        self.timeout = httpx.Timeout(timeout_ms / 1000.0)
        self.client = client or httpx.Client()

    def _auth_headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if self.sandbox_id:
            headers[SANDBOX_ID_HEADER] = self.sandbox_id
        return headers

    def close(self) -> None:
        self.client.close()

    def request(
        self,
        method: str,
        path: str,
        query: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        content: str | bytes | None = None,
        body: Any | None = None,
    ) -> httpx.Response:
        """Sends a request to the sandbox runtime without retries."""
        url = f"{self.connect_url}/{path.lstrip('/')}"

        req_headers = self._auth_headers()
        if headers:
            req_headers.update(headers)

        filtered_query = None
        if query:
            filtered_query = {k: str(v) for k, v in query.items() if v is not None}

        try:
            response = self.client.request(
                method=method,
                url=url,
                params=filtered_query,
                headers=req_headers,
                content=content,
                json=body,
                timeout=self.timeout,
            )
        except httpx.TimeoutException as e:
            from neevai.errors import APITimeoutError

            raise APITimeoutError("Sandbox runtime request timed out") from e
        except httpx.RequestError as e:
            from neevai.errors import APIConnectionError

            raise APIConnectionError("Failed to reach the sandbox runtime") from e

        if not response.is_success:
            raise self._runtime_error(response)

        return response

    def stream_request(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        body: Any | None = None,
    ) -> Generator[str, None, None]:
        """Streams the response body line by line for NDJSON exec streams."""
        url = f"{self.connect_url}/{path.lstrip('/')}"
        req_headers = self._auth_headers()
        if headers:
            req_headers.update(headers)

        try:
            with self.client.stream(
                method=method,
                url=url,
                headers=req_headers,
                json=body,
                timeout=self.timeout,
            ) as response:
                if not response.is_success:
                    response.read()  # Buffer response text for mapping error
                    raise self._runtime_error(response)
                yield from response.iter_lines()
        except httpx.TimeoutException as e:
            from neevai.errors import APITimeoutError

            raise APITimeoutError("Sandbox runtime request timed out during stream") from e
        except httpx.RequestError as e:
            from neevai.errors import APIConnectionError

            raise APIConnectionError("Failed to reach the sandbox runtime during stream") from e

    def _runtime_error(self, response: httpx.Response) -> Exception:
        text = response.text
        body = None
        if len(text) > 0:
            try:
                parsed = response.json()
                body = {
                    "error": parsed.get("reason_code", ""),
                    "details": parsed.get("message", ""),
                }
            except ValueError:
                body = {
                    "error": "",
                    "details": text,
                }
        request_id = response.headers.get("x-request-id")
        return error_from_status(response.status_code, body, request_id)


class AsyncRuntimeTransport:
    """Asynchronous HTTP transport for sandbox runtime."""

    def __init__(
        self,
        connect_url: str,
        api_key: str,
        timeout_ms: int = 60000,
        client: httpx.AsyncClient | None = None,
        sandbox_id: str | None = None,
    ):
        self.connect_url = connect_url.rstrip("/")
        self.api_key = api_key
        self.sandbox_id = sandbox_id
        self.timeout = httpx.Timeout(timeout_ms / 1000.0)
        self.client = client or httpx.AsyncClient()

    def _auth_headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if self.sandbox_id:
            headers[SANDBOX_ID_HEADER] = self.sandbox_id
        return headers

    async def aclose(self) -> None:
        await self.client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        query: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        content: str | bytes | None = None,
        body: Any | None = None,
    ) -> httpx.Response:
        """Sends an async request to the sandbox runtime without retries."""
        url = f"{self.connect_url}/{path.lstrip('/')}"

        req_headers = self._auth_headers()
        if headers:
            req_headers.update(headers)

        filtered_query = None
        if query:
            filtered_query = {k: str(v) for k, v in query.items() if v is not None}

        try:
            response = await self.client.request(
                method=method,
                url=url,
                params=filtered_query,
                headers=req_headers,
                content=content,
                json=body,
                timeout=self.timeout,
            )
        except httpx.TimeoutException as e:
            from neevai.errors import APITimeoutError

            raise APITimeoutError("Sandbox runtime request timed out") from e
        except httpx.RequestError as e:
            from neevai.errors import APIConnectionError

            raise APIConnectionError("Failed to reach the sandbox runtime") from e

        if not response.is_success:
            raise self._runtime_error(response)

        return response

    async def stream_request(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        body: Any | None = None,
    ) -> AsyncGenerator[str, None]:
        """Streams the response body line by line for NDJSON exec streams."""
        url = f"{self.connect_url}/{path.lstrip('/')}"
        req_headers = self._auth_headers()
        if headers:
            req_headers.update(headers)

        try:
            async with self.client.stream(
                method=method,
                url=url,
                headers=req_headers,
                json=body,
                timeout=self.timeout,
            ) as response:
                if not response.is_success:
                    await response.aread()
                    raise self._runtime_error(response)
                async for line in response.aiter_lines():
                    yield line
        except httpx.TimeoutException as e:
            from neevai.errors import APITimeoutError

            raise APITimeoutError("Sandbox runtime request timed out during stream") from e
        except httpx.RequestError as e:
            from neevai.errors import APIConnectionError

            raise APIConnectionError("Failed to reach the sandbox runtime during stream") from e

    def _runtime_error(self, response: httpx.Response) -> Exception:
        text = response.text
        body = None
        if len(text) > 0:
            try:
                parsed = response.json()
                body = {
                    "error": parsed.get("reason_code", ""),
                    "details": parsed.get("message", ""),
                }
            except ValueError:
                body = {
                    "error": "",
                    "details": text,
                }
        request_id = response.headers.get("x-request-id")
        return error_from_status(response.status_code, body, request_id)
