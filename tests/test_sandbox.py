"""Basic sanity tests for the Sandbox handle (sync)."""

import pytest

from neevai.client import NeevAI
from neevai.errors import NeevAIError
from neevai.sandbox import Sandbox


def test_sandbox_properties():
    data = {
        "id": "s1",
        "org_id": "org1",
        "project_id": "proj1",
        "name": "test-sandbox",
        "namespace": "default",
        "region": "us-east-1",
        "image": "ubuntu:22.04",
        "phase": "Ready",
        "replicas": 1,
        "connect_url": "https://sbx.example.com",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    sb = Sandbox(None, data)
    assert sb.id == "s1"
    assert sb.name == "test-sandbox"
    assert sb.phase == "Ready"
    assert sb.replicas == 1
    assert sb.connect_url == "https://sbx.example.com"
    assert sb.to_json() == data


def test_wait_until_ready_ready_phase():
    data = {
        "id": "s1",
        "org_id": "org1",
        "project_id": "proj1",
        "name": "test",
        "namespace": "default",
        "region": "us-east-1",
        "image": "ubuntu:22.04",
        "phase": "Ready",
        "replicas": 1,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    sb = Sandbox(None, data)
    result = sb.wait_until_ready(timeout_ms=100)
    assert result is sb


def test_wait_until_ready_paused_raises():
    data = {
        "id": "s1",
        "org_id": "org1",
        "project_id": "proj1",
        "name": "test",
        "namespace": "default",
        "region": "us-east-1",
        "image": "ubuntu:22.04",
        "phase": "Paused",
        "replicas": 0,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    sb = Sandbox(None, data)
    with pytest.raises(NeevAIError, match="Paused"):
        sb.wait_until_ready(timeout_ms=100)


def test_sandbox_refresh(control_transport):
    client = NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        client=control_transport,
    )
    sb = client.sandboxes.create({"name": "s1", "image": "ubuntu:22.04"})
    assert sb.phase == "Pending"

    sb.refresh()
    assert sb.phase == "Pending"
    assert sb.id is not None

    client.close()
