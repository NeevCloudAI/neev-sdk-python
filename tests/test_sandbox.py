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


def test_wait_until_ready_ready_phase_does_not_probe_runtime(mock_transport, monkeypatch):
    """wait_until_ready returns when control plane is Ready without probing the data plane."""
    client = NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        region="us-east-1",
        client=mock_transport,
    )
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})
    _mark_ready(sb)

    probe_calls = {"count": 0}

    def counting_probe(self, timeout_ms=5_000):
        probe_calls["count"] += 1
        return True

    monkeypatch.setattr(Sandbox, "_probe_runtime", counting_probe)

    sb.wait_until_ready(timeout_ms=100)
    assert probe_calls["count"] == 0
    assert sb._conn is None

    client.close()


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
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})
    assert sb.phase == "Pending"

    sb.refresh()
    assert sb.phase == "Pending"
    assert sb.id == str(uuid.UUID(int=1))

    client.close()


def _mark_ready(sb, *, connect_url: str = "https://old.example.com") -> None:
    from tests.conftest import _FAKE_DB

    record = _FAKE_DB["sandboxes"][sb.id]
    record["phase"] = "Ready"
    record["replicas"] = 1
    record["connect_url"] = connect_url
    sb.refresh()


def test_sandbox_restore_invalidates_cached_connection(mock_transport):
    """Restore must drop the data-plane connection created before reconciliation."""
    client = NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        region="us-east-1",
        client=mock_transport,
    )
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})
    _mark_ready(sb, connect_url="https://old.example.com")

    old_conn = sb._connection()
    assert sb._conn is old_conn

    snap = client.sandboxes.create_snapshot(sb.id, {"name": "restore-me"})
    sb.restore(str(snap.id))

    assert sb._conn is None
    assert sb.phase == "Pending"

    _mark_ready(sb, connect_url="https://new.example.com")
    new_conn = sb._connection()
    assert new_conn is not old_conn
    assert new_conn._transport.connect_url == "https://new.example.com"

    client.close()


def test_sandbox_pause_and_resume_invalidate_cached_connection(mock_transport):
    client = NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        region="us-east-1",
        client=mock_transport,
    )
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})
    _mark_ready(sb)

    sb._connection()
    assert sb._conn is not None

    sb.pause()
    assert sb._conn is None

    sb.resume()
    assert sb._conn is None

    client.close()


def test_sandbox_restore_does_not_wait_for_runtime(mock_transport, monkeypatch):
    """restore invalidates the connection but does not probe the data plane."""
    client = NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        region="us-east-1",
        client=mock_transport,
    )
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})
    _mark_ready(sb, connect_url="https://same.example.com")

    sb._connection()
    snap = client.sandboxes.create_snapshot(sb.id, {"name": "restore-me"})
    sb.restore(str(snap.id))
    _mark_ready(sb, connect_url="https://same.example.com")

    probe_calls = {"count": 0}

    def counting_probe(self, timeout_ms=5_000):
        probe_calls["count"] += 1
        return True

    monkeypatch.setattr(Sandbox, "_probe_runtime", counting_probe)

    sb.wait_until_ready(timeout_ms=100)
    assert probe_calls["count"] == 0
    assert sb._conn is None

    client.close()


def test_wait_for_runtime_ready_clears_cached_connection(mock_transport, monkeypatch):
    """Runtime readiness waits must drop any pre-existing cached data-plane client."""
    client = NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        region="us-east-1",
        client=mock_transport,
    )
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})
    _mark_ready(sb, connect_url="https://same.example.com")

    sb._connection()
    assert sb._conn is not None

    monkeypatch.setattr(Sandbox, "_probe_runtime", lambda self, timeout_ms=5_000: True)

    sb._wait_for_runtime_ready(timeout_ms=1_000)
    assert sb._conn is None

    client.close()


def test_sandbox_connection_passes_sandbox_id_to_transport(mock_transport):
    client = NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        region="us-east-1",
        client=mock_transport,
    )
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})
    _mark_ready(sb)

    conn = sb._connection()
    assert conn._transport.sandbox_id == sb.id

    client.close()


def test_sandbox_refresh_invalidates_connection_when_connect_url_changes(mock_transport):
    client = NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        region="us-east-1",
        client=mock_transport,
    )
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})
    _mark_ready(sb, connect_url="https://first.example.com")

    first_conn = sb._connection()
    _mark_ready(sb, connect_url="https://second.example.com")

    second_conn = sb._connection()
    assert second_conn is not first_conn
    assert second_conn._transport.connect_url == "https://second.example.com"

    client.close()
