"""Basic sanity tests for the Sandbox handle (sync)."""

import uuid

import pytest

from neevai.client import NeevAI
from neevai.errors import NeevAIError
from neevai.handles.sandbox import Sandbox


def _sandbox_data(**overrides):
    base = {
        "id": "00000000-0000-0000-0000-000000000001",
        "org_id": "org1",
        "project_id": "proj1",
        "name": "test-sandbox",
        "region": "us-east-1",
        "image": "ubuntu:22.04",
        "phase": "Ready",
        "replicas": 1,
        "connect_url": "https://sbx.example.com",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def test_sandbox_properties():
    data = _sandbox_data()
    sb = Sandbox(None, data)
    assert sb.id == "00000000-0000-0000-0000-000000000001"
    assert sb.name == "test-sandbox"
    assert sb.phase == "Ready"
    assert sb.replicas == 1
    assert sb.connect_url == "https://sbx.example.com"
    assert sb.to_json()["id"] == data["id"]
    assert sb.to_json()["name"] == data["name"]


def test_wait_until_ready_ready_phase():
    data = _sandbox_data(connect_url=None)
    sb = Sandbox(None, data)
    result = sb.wait_until_ready(timeout_ms=100)
    assert result is sb


def test_wait_until_ready_paused_raises():
    data = _sandbox_data(phase="Paused", replicas=0, connect_url=None)
    sb = Sandbox(None, data)
    with pytest.raises(NeevAIError, match="Paused"):
        sb.wait_until_ready(timeout_ms=100)


def test_sandbox_refresh(control_transport):
    client = NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        region="us-east-1",
        client=control_transport,
    )
    sb = client.sandboxes.create(
        {"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal", "image": "ubuntu:22.04"}
    )
    assert sb.phase == "Pending"

    sb.refresh()
    assert sb.phase == "Pending"
    assert sb.id == str(uuid.UUID(int=1))

    client.close()
