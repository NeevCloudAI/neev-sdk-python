"""Tests for the Agent handle."""

import json
import uuid

import pytest

from neevai.client import NeevAI
from neevai.errors import NeevAIError


def _make_client(mock_transport) -> NeevAI:
    return NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        client=mock_transport,
    )


def _first_agent_id() -> str:
    return str(uuid.UUID(int=0x2001))


def _first_sandbox_id() -> str:
    return str(uuid.UUID(int=1))


def test_agent_handle_fields(mock_transport):
    client = _make_client(mock_transport)
    agent = client.agents.create({"name": "my-agent", "agent_template": "claude-code"})
    assert agent.id == _first_agent_id()
    assert agent.name == "my-agent"
    assert agent.status == "Provisioning"
    assert agent.sandbox_id == _first_sandbox_id()
    assert agent.agent_template_id == "ag-claude-code"
    assert agent.config is None
    assert agent.created_at
    assert agent.updated_at
    client.close()


def test_agent_to_json_and_data(mock_transport):
    client = _make_client(mock_transport)
    agent = client.agents.create({"name": "my-agent", "agent_template": "claude-code"})
    payload = agent.to_json()
    assert payload["id"] == agent.id
    assert payload["name"] == "my-agent"
    assert payload["agent_template_id"] == "ag-claude-code"
    assert payload["sandbox_id"] == agent.sandbox_id
    assert json.dumps(agent.to_json()) == json.dumps(agent.data)
    client.close()


def test_agent_pause_update_resume_in_place(mock_transport):
    client = _make_client(mock_transport)
    agent = client.agents.create({"name": "my-agent", "agent_template": "claude-code"})
    agent.pause()
    assert agent.status == "Paused"
    agent.update({"resources": {"cpu": 2, "memory_gb": 4}})
    agent.resume()
    assert agent.status == "Provisioning"
    client.close()


def test_agent_sandbox_fetches_backing_sandbox(mock_transport):
    client = _make_client(mock_transport)
    agent = client.agents.create({"name": "my-agent", "agent_template": "claude-code"})
    sandbox = agent.sandbox()
    assert sandbox.id == agent.sandbox_id
    client.close()


def test_agent_wait_until_ready(mock_transport):
    client = _make_client(mock_transport)
    agent = client.agents.create({"name": "my-agent", "agent_template": "claude-code"})
    agent.wait_until_ready(timeout_ms=5_000, poll_interval_ms=10)
    assert agent.status == "Ready"
    client.close()


def test_agent_wait_until_ready_timeout(mock_transport, monkeypatch):
    client = _make_client(mock_transport)
    agent = client.agents.create({"name": "my-agent", "agent_template": "claude-code"})

    def _never_ready(self):
        self._state.status = "Provisioning"
        return self

    monkeypatch.setattr(type(agent), "refresh", _never_ready)

    with pytest.raises(NeevAIError, match="did not become Ready"):
        agent.wait_until_ready(timeout_ms=50, poll_interval_ms=10)
    client.close()


def test_agent_wait_until_ready_paused_fails_fast(mock_transport):
    client = _make_client(mock_transport)
    agent = client.agents.create({"name": "my-agent", "agent_template": "claude-code"})
    agent.pause()
    with pytest.raises(NeevAIError, match="Paused"):
        agent.wait_until_ready(timeout_ms=5_000, poll_interval_ms=10)
    client.close()


def test_agent_wait_until_ready_failed_fails_fast(mock_transport):
    client = _make_client(mock_transport)
    agent = client.agents.create({"name": "my-agent", "agent_template": "claude-code"})
    agent._state.status = "Failed"
    with pytest.raises(NeevAIError, match="Failed"):
        agent.wait_until_ready(timeout_ms=5_000, poll_interval_ms=10)
    client.close()


@pytest.mark.parametrize(
    "timeout_ms,poll_interval_ms",
    [
        (0, 100),
        (-1, 100),
        (100, 0),
        (100, float("inf")),
        (float("nan"), 100),
    ],
)
def test_agent_wait_until_ready_invalid_timings(mock_transport, timeout_ms, poll_interval_ms):
    client = _make_client(mock_transport)
    agent = client.agents.create({"name": "my-agent", "agent_template": "claude-code"})
    with pytest.raises(NeevAIError, match="positive finite"):
        agent.wait_until_ready(timeout_ms=timeout_ms, poll_interval_ms=poll_interval_ms)
    client.close()
