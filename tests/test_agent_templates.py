"""Tests for the AgentTemplates resource."""

import httpx
import pytest

from neevai.client import AsyncNeevAI, NeevAI
from neevai.errors import NotFoundError
from tests.conftest import MockControlTransport


def _make_client(mock_transport) -> NeevAI:
    return NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        region="us-east-1",
        client=mock_transport,
    )


def test_agent_templates_list(mock_transport):
    client = _make_client(mock_transport)
    page = client.agent_templates.list()
    assert page.total == 1
    assert page.items[0].id == "ag-claude-code"
    assert page.items[0].name == "claude-code"
    client.close()


def test_agent_templates_get(mock_transport):
    client = _make_client(mock_transport)
    template = client.agent_templates.get("ag-claude-code")
    assert template.id == "ag-claude-code"
    assert template.name == "claude-code"
    client.close()


def test_agent_templates_get_not_found(mock_transport):
    client = _make_client(mock_transport)
    with pytest.raises(NotFoundError):
        client.agent_templates.get("ag-missing")
    client.close()


def test_agent_templates_paths_not_under_orgs(mock_transport):
    client = _make_client(mock_transport)
    captured: list[str] = []
    original = client._transport.request

    def _capture(method, path, **kwargs):
        captured.append(path)
        return original(method, path, **kwargs)

    client._transport.request = _capture  # type: ignore[method-assign]
    client.agent_templates.list()
    client.agent_templates.get("ag-claude-code")
    assert all("/orgs/" not in p for p in captured)
    assert captured[0] == "/api/v1beta1/agent-templates"
    assert captured[1] == "/api/v1beta1/agent-templates/ag-claude-code"
    client.close()


def test_agent_templates_omit_page_limit_when_unset(mock_transport):
    client = _make_client(mock_transport)
    captured_queries: list[dict] = []
    original = client._transport.request

    def _capture(method, path, **kwargs):
        captured_queries.append(kwargs.get("query", {}))
        return original(method, path, **kwargs)

    client._transport.request = _capture  # type: ignore[method-assign]
    client.agent_templates.list()
    assert captured_queries[0] == {}
    client.close()


def test_agent_templates_pagination(mock_transport):
    client = _make_client(mock_transport)
    page = client.agent_templates.list(page=2, limit=5)
    assert page.page == 2
    assert page.limit == 5
    client.close()


@pytest.mark.asyncio
async def test_async_agent_templates_list():
    async with AsyncNeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        region="us-east-1",
        client=httpx.AsyncClient(transport=MockControlTransport()),
    ) as client:
        page = await client.agent_templates.list()
        assert page.total == 1


@pytest.mark.asyncio
async def test_async_agent_templates_get():
    async with AsyncNeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        region="us-east-1",
        client=httpx.AsyncClient(transport=MockControlTransport()),
    ) as client:
        template = await client.agent_templates.get("ag-claude-code")
        assert template.name == "claude-code"
