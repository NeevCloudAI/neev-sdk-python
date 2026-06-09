"""Basic sanity tests for the sandbox daemon transport and connection layer."""

import httpx
import pytest

from neevai.dataplane.sandboxd import (
    AsyncSandboxConnection,
    AsyncSandboxFiles,
    SandboxConnection,
    SandboxFiles,
)
from neevai.errors import APIConnectionError, APITimeoutError, NotFoundError
from neevai.transport.dataplane import DataplaneTransport


def test_dataplane_transport_sanity(dataplane_transport):
    transport = DataplaneTransport(
        connect_url="https://sbx.example.com",
        api_key="test",
        timeout_ms=5000,
        client=dataplane_transport,
    )
    resp = transport.request("POST", "/v1/exec")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"

    with pytest.raises(NotFoundError):
        transport.request("GET", "/v1/nonexistent")


def test_dataplane_transport_timeout():
    class TimeoutMock(httpx.MockTransport):
        def __init__(self):
            super().__init__(self.handler)

        def handler(self, request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("timeout", request=request)

    transport = DataplaneTransport(
        connect_url="https://sbx.example.com",
        api_key="test",
        timeout_ms=100,
        client=httpx.Client(transport=TimeoutMock()),
    )
    with pytest.raises(APITimeoutError):
        transport.request("GET", "/v1/exec")


def test_dataplane_transport_connection_error():
    class ConnErrorMock(httpx.MockTransport):
        def __init__(self):
            super().__init__(self.handler)

        def handler(self, request: httpx.Request) -> httpx.Response:
            raise httpx.RequestError("conn error", request=request)

    transport = DataplaneTransport(
        connect_url="https://sbx.example.com",
        api_key="test",
        timeout_ms=1000,
        client=httpx.Client(transport=ConnErrorMock()),
    )
    with pytest.raises(APIConnectionError):
        transport.request("GET", "/v1/exec")


def test_sandbox_connection_init():
    conn = SandboxConnection(
        connect_url="https://sbx.example.com",
        api_key="test",
        timeout_ms=5000,
    )
    assert conn._transport is not None
    assert conn.files is not None
    assert isinstance(conn.files, SandboxFiles)
    conn.close()


def test_async_sandbox_connection_init():
    conn = AsyncSandboxConnection(
        connect_url="https://sbx.example.com",
        api_key="test",
        timeout_ms=5000,
    )
    assert conn._transport is not None
    assert conn.files is not None
    assert isinstance(conn.files, AsyncSandboxFiles)


def test_sandbox_connection_close_idempotent():
    conn = SandboxConnection(
        connect_url="https://sbx.example.com",
        api_key="test",
        timeout_ms=5000,
    )
    conn.close()
    conn.close()
