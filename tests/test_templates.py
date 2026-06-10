"""Tests for the Templates resource."""

import httpx
import pytest

from neevai.client import AsyncNeevAI, NeevAI
from tests.conftest import MockControlTransport


def _make_client(mock_transport) -> NeevAI:
    return NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        region="us-east-1",
        client=mock_transport,
    )


def test_templates_list(mock_transport):
    client = _make_client(mock_transport)
    page = client.templates.list()
    assert page.total == 1
    assert page.items[0].id == "sb-ubuntu-26-04-minimal"
    assert page.items[0].status.value == "active"
    client.close()


def test_templates_get(mock_transport):
    client = _make_client(mock_transport)
    template = client.templates.get("sb-ubuntu-26-04-minimal")
    assert template.id == "sb-ubuntu-26-04-minimal"
    client.close()


@pytest.mark.asyncio
async def test_async_templates_list():
    async with AsyncNeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        region="us-east-1",
        client=httpx.AsyncClient(transport=MockControlTransport()),
    ) as client:
        page = await client.templates.list()
        assert page.total == 1


@pytest.mark.asyncio
async def test_async_templates_get():
    async with AsyncNeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        region="us-east-1",
        client=httpx.AsyncClient(transport=MockControlTransport()),
    ) as client:
        template = await client.templates.get("sb-ubuntu-26-04-minimal")
        assert template.name == "Ubuntu 26.04 Minimal"
