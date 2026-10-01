"""Tests for sandbox preview ports: expose / list / revoke / get_url."""

import pytest

from neevai.client import AsyncNeevAI, NeevAI
from neevai.errors import NeevAIError


def _client(mock_transport) -> NeevAI:
    return NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        client=mock_transport,
    )


def _new_sandbox(client: NeevAI):
    return client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})


def test_expose_port_returns_port_and_url(mock_transport):
    client = _client(mock_transport)
    sb = _new_sandbox(client)
    exposed = sb.expose_port(8080)
    assert exposed.port == 8080
    assert exposed.preview_url.startswith("https://8080-")
    client.close()


def test_list_ports_reflects_exposed(mock_transport):
    client = _client(mock_transport)
    sb = _new_sandbox(client)
    sb.expose_port(8080)
    sb.expose_port(3000)
    ports = {p.port for p in sb.list_ports()}
    assert ports == {8080, 3000}
    client.close()


def test_expose_port_is_idempotent(mock_transport):
    client = _client(mock_transport)
    sb = _new_sandbox(client)
    first = sb.expose_port(8080)
    second = sb.expose_port(8080)
    assert first.preview_url == second.preview_url
    assert len(sb.list_ports()) == 1
    client.close()


def test_revoke_port_removes_it(mock_transport):
    client = _client(mock_transport)
    sb = _new_sandbox(client)
    sb.expose_port(8080)
    sb.revoke_port(8080)
    assert sb.list_ports() == []
    client.close()


def test_get_url_no_wait_returns_preview_url(mock_transport):
    client = _client(mock_transport)
    sb = _new_sandbox(client)
    url = sb.get_url(8080, wait_until_ready=False)
    assert url.startswith("https://8080-")
    client.close()


def test_get_url_waits_until_reachable(mock_transport, monkeypatch):
    monkeypatch.setattr(
        "neevai.resources.sandboxes._preview_url_reachable", lambda url, timeout_ms: True
    )
    client = _client(mock_transport)
    sb = _new_sandbox(client)
    url = sb.get_url(8080)
    assert url.startswith("https://8080-")
    client.close()


def test_get_url_raises_when_not_routable_before_timeout(mock_transport, monkeypatch):
    monkeypatch.setattr(
        "neevai.resources.sandboxes._preview_url_reachable", lambda url, timeout_ms: False
    )
    client = _client(mock_transport)
    sb = _new_sandbox(client)
    with pytest.raises(NeevAIError, match="was not routable"):
        sb.get_url(8080, timeout_ms=1, poll_interval_ms=1)
    client.close()


def test_get_url_rejects_non_positive_timeout(mock_transport):
    client = _client(mock_transport)
    sb = _new_sandbox(client)
    with pytest.raises(NeevAIError, match="timeout_ms"):
        sb.get_url(8080, timeout_ms=0)
    with pytest.raises(NeevAIError, match="poll_interval_ms"):
        sb.get_url(8080, poll_interval_ms=0)
    client.close()


@pytest.mark.asyncio
async def test_async_expose_list_revoke(async_mock_transport):
    client = AsyncNeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        client=async_mock_transport,
    )
    sb = await client.sandboxes.create(
        {"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"}
    )
    exposed = await sb.expose_port(8080)
    assert exposed.port == 8080
    ports = {p.port for p in await sb.list_ports()}
    assert ports == {8080}
    await sb.revoke_port(8080)
    assert await sb.list_ports() == []
    await client.aclose()


@pytest.mark.asyncio
async def test_async_get_url_no_wait(async_mock_transport):
    client = AsyncNeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        client=async_mock_transport,
    )
    sb = await client.sandboxes.create(
        {"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"}
    )
    url = await sb.get_url(8080, wait_until_ready=False)
    assert url.startswith("https://8080-")
    await client.aclose()


def test_expose_port_returns_a_slug_and_keeps_it_when_omitted(mock_transport):
    client = _client(mock_transport)
    sb = _new_sandbox(client)
    first = sb.expose_port(8080)
    assert len(first.slug) == 8
    assert first.slug in first.preview_url
    assert sb.expose_port(8080).slug == first.slug
    client.close()


def test_expose_port_with_a_new_slug_rotates_the_url(mock_transport):
    client = _client(mock_transport)
    sb = _new_sandbox(client)
    old = sb.expose_port(8080)
    rotated = sb.expose_port(8080, slug="rot8te00")
    assert rotated.slug == "rot8te00"
    assert rotated.preview_url != old.preview_url
    assert [p.slug for p in sb.list_ports()] == ["rot8te00"]
    client.close()


def test_slug_is_sent_only_when_given(mock_transport):
    client = _client(mock_transport)
    sb = _new_sandbox(client)
    bodies: list = []
    original = client._transport.request

    def capturing(method, path, query=None, body=None):
        bodies.append(body)
        return original(method, path, query=query, body=body)

    client._transport.request = capturing  # type: ignore[method-assign]
    client.sandboxes.expose_port(sb.id, 8080)
    client.sandboxes.expose_port(sb.id, 8080, slug="abcd1234")
    sb.get_url(8080, wait_until_ready=False, slug="efgh5678")
    assert bodies == [
        {"port": 8080},
        {"port": 8080, "slug": "abcd1234"},
        {"port": 8080, "slug": "efgh5678"},
    ]
    client.close()


@pytest.mark.asyncio
async def test_async_expose_port_and_get_url_forward_slug(async_mock_transport):
    client = AsyncNeevAI(
        api_key="test", org_id="org1", project_id="proj1", client=async_mock_transport
    )
    sb = await client.sandboxes.create(
        {"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"}
    )
    assert (await sb.expose_port(8080, slug="abcd1234")).slug == "abcd1234"
    url = await sb.get_url(8080, wait_until_ready=False, slug="efgh5678")
    assert "efgh5678" in url
    await client.aclose()
