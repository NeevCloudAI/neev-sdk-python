"""Tests for the control‑plane transport layer (retry & back‑off)."""

import email.utils
import time
import httpx
import pytest

from neevai.transport.control import ControlTransport, calculate_backoff, parse_retry_after
from neevai.errors import APIConnectionError, APITimeoutError, NotFoundError


def test_calculate_backoff_values():
    for attempt in range(5):
        backoff = calculate_backoff(attempt)
        base = min(0.250 * (2 ** attempt), 8.0)
        assert 0.5 * base <= backoff <= base


def test_parse_retry_after_seconds():
    assert parse_retry_after("5") == 5.0
    assert parse_retry_after("0") == 0.0
    assert parse_retry_after(None) is None


def test_parse_retry_after_http_date():
    future = time.time() + 10
    http_date = email.utils.formatdate(timeval=future, usegmt=True)
    parsed = parse_retry_after(http_date)
    assert 9.0 <= parsed <= 11.0


class FlakyMockTransport(httpx.MockTransport):
    """First request fails with 429+Retry‑After, second succeeds."""

    def __init__(self):
        super().__init__(self.handler)
        self.call_count = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.call_count += 1
        if self.call_count == 1:
            return httpx.Response(
                status_code=429,
                headers={"retry-after": "1"},
                json={"message": "rate limit"},
            )
        return httpx.Response(status_code=200, json={"ok": True})


def test_control_transport_retries():
    mock = FlakyMockTransport()
    transport = ControlTransport(
        base_url="https://example.com",
        api_key="test",
        timeout_ms=5000,
        max_retries=2,
        client=httpx.Client(transport=mock),
    )
    resp = transport.request("GET", "/test")
    assert resp == {"ok": True}
    assert mock.call_count == 2


def test_control_transport_timeout():
    class TimeoutMock(httpx.MockTransport):
        def __init__(self):
            super().__init__(self.handler)

        def handler(self, request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("timeout", request=request)

    transport = ControlTransport(
        base_url="https://example.com",
        api_key="test",
        timeout_ms=100,
        max_retries=0,
        client=httpx.Client(transport=TimeoutMock()),
    )
    with pytest.raises(APITimeoutError):
        transport.request("GET", "/timeout")


def test_control_transport_connection_error():
    class ConnErrorMock(httpx.MockTransport):
        def __init__(self):
            super().__init__(self.handler)

        def handler(self, request: httpx.Request) -> httpx.Response:
            raise httpx.RequestError("conn error", request=request)

    transport = ControlTransport(
        base_url="https://example.com",
        api_key="test",
        timeout_ms=1000,
        max_retries=0,
        client=httpx.Client(transport=ConnErrorMock()),
    )
    with pytest.raises(APIConnectionError):
        transport.request("GET", "/conn")


def test_control_transport_sanity(control_transport):
    transport = ControlTransport(
        base_url="https://example.com",
        api_key="test",
        timeout_ms=5000,
        max_retries=0,
        client=control_transport,
    )
    resp = transport.request("GET", "/v1/sandboxes")
    assert resp == {"items": []}

    created = transport.request("POST", "/v1/sandboxes", body={"name": "s1", "image": "ubuntu:22.04"})
    assert created["name"] == "s1"
    assert created["id"] == "1"

    fetched = transport.request("GET", f"/v1/sandboxes/{created['id']}")
    assert fetched["id"] == created["id"]

    transport.request("DELETE", f"/v1/sandboxes/{created['id']}")
    with pytest.raises(NotFoundError):
        transport.request("GET", f"/v1/sandboxes/{created['id']}")
