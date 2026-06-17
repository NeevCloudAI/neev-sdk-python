"""Tests for the Agents resource (control plane, sync)."""

import uuid
from unittest.mock import MagicMock

import pytest

from neevai.client import NeevAI
from neevai.errors import NeevAIError, NotFoundError


def _make_client(mock_transport, region: str | None = "us-east-1") -> NeevAI:
    return NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        region=region,
        client=mock_transport,
    )


def _first_agent_id() -> str:
    return str(uuid.UUID(int=0x2001))


def _first_sandbox_id() -> str:
    return str(uuid.UUID(int=1))


def test_agents_create(mock_transport):
    client = _make_client(mock_transport)
    agent = client.agents.create({"name": "my-agent", "agent_template": "claude-code"})
    assert agent.id == _first_agent_id()
    assert agent.name == "my-agent"
    assert agent.status == "Provisioning"
    assert agent.agent_template_id == "ag-claude-code"
    assert agent.sandbox_id == _first_sandbox_id()
    client.close()


def test_agents_create_injects_default_region(mock_transport):
    client = _make_client(mock_transport, region="eu-central-1")
    agent = client.agents.create({"name": "my-agent", "agent_template": "claude-code"})
    sandbox = client.sandboxes.get(agent.sandbox_id)
    assert sandbox.data["region"] == "eu-central-1"
    client.close()


def test_agents_create_omits_region_when_unset(mock_transport, monkeypatch):
    monkeypatch.delenv("NEEVCLOUD_REGION", raising=False)
    client = NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        client=mock_transport,
    )
    agent = client.agents.create({"name": "my-agent", "agent_template": "claude-code"})
    sandbox = client.sandboxes.get(agent.sandbox_id)
    assert sandbox.data["region"] == "us-east-1"
    client.close()


def test_agents_get(mock_transport):
    client = _make_client(mock_transport)
    created = client.agents.create({"name": "my-agent", "agent_template": "claude-code"})
    fetched = client.agents.get(created.id)
    assert fetched.id == created.id
    assert fetched.status == "Ready"
    client.close()


def test_agents_list(mock_transport):
    client = _make_client(mock_transport)
    client.agents.create({"name": "a1", "agent_template": "claude-code"})
    client.agents.create({"name": "a2", "agent_template": "claude-code"})

    page = client.agents.list()
    assert len(page.items) == 2
    assert page.total == 2
    client.close()


def test_agents_list_pagination(mock_transport):
    client = _make_client(mock_transport)
    client.agents.create({"name": "a1", "agent_template": "claude-code"})

    page = client.agents.list(page=2, limit=10)
    assert page.page == 2
    assert page.limit == 10
    client.close()


def test_agents_update(mock_transport):
    client = _make_client(mock_transport)
    agent = client.agents.create({"name": "my-agent", "agent_template": "claude-code"})
    updated = client.agents.update(agent.id, {"resources": {"cpu": 2, "memory_gb": 4}})
    assert updated.id == agent.id
    client.close()


def test_agents_empty_update_raises_without_http(mock_transport):
    client = _make_client(mock_transport)
    agent = client.agents.create({"name": "my-agent", "agent_template": "claude-code"})
    request_mock = MagicMock(side_effect=client._transport.request)
    client._transport.request = request_mock

    with pytest.raises(NeevAIError, match="empty body"):
        client.agents.update(agent.id, {})

    request_mock.assert_not_called()
    client.close()


def test_agents_pause_resume_paths(mock_transport):
    client = _make_client(mock_transport)
    agent = client.agents.create({"name": "my-agent", "agent_template": "claude-code"})
    paused = client.agents.pause(agent.id)
    assert paused.status == "Paused"
    resumed = client.agents.resume(agent.id)
    assert resumed.status == "Provisioning"
    client.close()


def test_agents_delete_returns_no_body(mock_transport):
    client = _make_client(mock_transport)
    agent = client.agents.create({"name": "my-agent", "agent_template": "claude-code"})
    client.agents.delete(agent.id)
    with pytest.raises(NotFoundError):
        client.agents.get(agent.id)
    with pytest.raises(NotFoundError):
        client.sandboxes.get(agent.sandbox_id)
    client.close()


def test_agents_get_not_found(mock_transport):
    client = _make_client(mock_transport)
    with pytest.raises(NotFoundError):
        client.agents.get("00000000-0000-0000-0000-000000000099")
    client.close()


def test_agents_scope_override(mock_transport):
    client = _make_client(mock_transport)
    agent = client.agents.create(
        {"name": "scoped-agent", "agent_template": "claude-code"},
        org_id="org2",
        project_id="proj2",
    )
    assert agent.scope is not None
    assert agent.scope.org_id == "org2"
    assert agent.scope.project_id == "proj2"
    fetched = client.agents.get(agent.id, org_id="org2", project_id="proj2")
    assert fetched.id == agent.id
    client.close()
