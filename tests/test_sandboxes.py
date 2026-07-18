"""Basic sanity tests for the Sandboxes resource (the API, sync)."""

import uuid

import pytest

from neevai._parse import ResponseValidationError
from neevai.client import NeevAI
from neevai.errors import NotFoundError
from neevai.generated.aiagent import SnapshotStatus
from neevai.types import CreateSandboxParams, Snapshot


def _make_client(mock_transport) -> NeevAI:
    return NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        client=mock_transport,
    )


def _first_sandbox_id() -> str:
    return str(uuid.UUID(int=1))


def _first_snapshot_id() -> str:
    return str(uuid.UUID(int=0x1001))


def snapshot_data(**overrides) -> dict:
    base = {
        "id": "22222222-2222-2222-2222-222222222222",
        "sandbox_id": "11111111-1111-1111-1111-111111111111",
        "org_id": "org1",
        "project_id": "proj1",
        "status": "Pending",
        "include_memory": False,
        "source_region": "as-south-1",
        "created_at": "2026-06-05T00:00:00Z",
        "updated_at": "2026-06-05T00:00:00Z",
    }
    base.update(overrides)
    return base


def test_sandboxes_create(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})
    assert sb.id == _first_sandbox_id()
    assert sb.name == "s1"
    assert sb.phase == "Pending"
    assert sb.data.get("sandbox_template_id") == "sb-ubuntu-24-04-minimal"
    client.close()


def test_sandboxes_create_with_model_instance(mock_transport):
    client = _make_client(mock_transport)
    params = CreateSandboxParams(
        name="s1",
        sandbox_template_id="sb-ubuntu-24-04-minimal",
        region="as-south-1",
    )
    sb = client.sandboxes.create(params)
    assert sb.name == "s1"
    client.close()


def test_sandboxes_create_allow_internet(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create(
        {"name": "web", "sandbox_template_id": "sb-x"}, allow_internet=True
    )
    egress = sb.data["egress"]
    assert egress["mode"] == "allow_list"
    assert egress["allow_internet"] is True
    # The gate alone is a no-op server-side; the 0.0.0.0/0 + ::/0 routes must ride along.
    assert [r["host"] for r in egress["allow"]] == ["0.0.0.0/0", "::/0"]
    client.close()


def test_sandboxes_create_allow_egress_hosts(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create(
        {"name": "ci", "sandbox_template_id": "sb-x"},
        allow_egress=["github.com", "*.npmjs.org"],
    )
    egress = sb.data["egress"]
    assert egress["allow_internet"] is False
    assert [r["host"] for r in egress["allow"]] == ["github.com", "*.npmjs.org"]
    client.close()


def test_sandboxes_create_explicit_egress_wins(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create(
        {"name": "adv", "sandbox_template_id": "sb-x", "egress": {"mode": "deny_all"}},
        allow_internet=True,
    )
    # An explicit egress is kept as-is; the convenience routes are not added.
    assert sb.data["egress"]["mode"] == "deny_all"
    assert sb.data["egress"]["allow"] is None
    client.close()


def test_sandboxes_create_uses_explicit_region(mock_transport):
    client = NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        client=mock_transport,
    )
    sb = client.sandboxes.create(
        {
            "name": "s1",
            "sandbox_template_id": "sb-ubuntu-24-04-minimal",
            "region": "as-south-1",
        }
    )
    assert sb.data["region"] == "as-south-1"
    client.close()


def test_sandboxes_create_omits_region_when_not_configured(mock_transport):
    client = NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        client=mock_transport,
    )
    # No region configured anywhere: create still succeeds; the server picks the default.
    sandbox = client.sandboxes.create(
        {
            "name": "s1",
            "sandbox_template_id": "sb-ubuntu-24-04-minimal",
        }
    )
    assert sandbox.id
    client.close()


def test_sandboxes_get(mock_transport):
    client = _make_client(mock_transport)
    created = client.sandboxes.create(
        {"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"}
    )
    fetched = client.sandboxes.get(created.id)
    assert fetched.id == created.id
    assert fetched.name == "s1"
    client.close()


def test_sandboxes_list(mock_transport):
    client = _make_client(mock_transport)
    client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})
    client.sandboxes.create({"name": "s2", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})

    page = client.sandboxes.list()
    assert len(page.items) == 2
    assert page.total == 2
    assert page.page == 1
    client.close()


def test_sandboxes_delete(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})
    client.sandboxes.delete(sb.id)
    with pytest.raises(NotFoundError):
        client.sandboxes.get(sb.id)
    client.close()


def test_sandboxes_pause_resume(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})
    paused = client.sandboxes.pause(sb.id)
    assert paused.phase == "Paused"
    resumed = client.sandboxes.resume(sb.id)
    assert resumed.phase == "Pending"
    client.close()


def test_sandboxes_pause_accepts_pausing_transitional_phase(mock_transport, monkeypatch):
    """Pause API may return phase=Pausing while reconciliation is in progress."""
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})

    original_request = client._transport.request

    def pausing_pause(method, path, **kwargs):
        if method == "POST" and path.endswith(f"/sandboxes/{sb.id}/pause"):
            sandbox = dict(
                original_request("GET", f"/api/v1beta1/orgs/org1/projects/proj1/sandboxes/{sb.id}")
            )
            sandbox["phase"] = "Pausing"
            sandbox["replicas"] = 0
            return sandbox
        return original_request(method, path, **kwargs)

    monkeypatch.setattr(client._transport, "request", pausing_pause)

    paused = client.sandboxes.pause(sb.id)
    assert paused.phase == "Pausing"
    assert paused.replicas == 0
    client.close()


def test_sandboxes_pause_sends_empty_json_body_when_preserve_memory_omitted(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})

    captured_bodies: list[dict | None] = []
    original_request = client._transport.request

    def capturing_request(method, path, query=None, body=None):
        captured_bodies.append(body)
        return original_request(method, path, query=query, body=body)

    client._transport.request = capturing_request  # type: ignore[method-assign]

    client.sandboxes.pause(sb.id)
    assert captured_bodies == [{}]
    client.close()


def test_sandboxes_pause_sends_preserve_memory_when_set(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})

    captured_bodies: list[dict | None] = []
    original_request = client._transport.request

    def capturing_request(method, path, query=None, body=None):
        captured_bodies.append(body)
        return original_request(method, path, query=query, body=body)

    client._transport.request = capturing_request  # type: ignore[method-assign]

    client.sandboxes.pause(sb.id, preserve_memory=True)
    assert captured_bodies == [{"preserve_memory": True}]
    client.close()


def test_sandboxes_metrics(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})
    metrics = client.sandboxes.metrics(sb.id)
    assert str(metrics.sandbox_id) == sb.id
    assert metrics.series == []
    client.close()


def test_sandboxes_get_not_found(mock_transport):
    client = _make_client(mock_transport)
    with pytest.raises(NotFoundError):
        client.sandboxes.get("nonexistent")
    client.close()


def test_sandboxes_get_invalid_response_raises(mock_transport, monkeypatch):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})

    original_request = client._transport.request

    def broken_get(method, path, **kwargs):
        if method == "GET" and path.endswith(f"/sandboxes/{sb.id}"):
            return {"id": "not-a-uuid", "name": "broken"}
        return original_request(method, path, **kwargs)

    monkeypatch.setattr(client._transport, "request", broken_get)

    with pytest.raises(ResponseValidationError):
        client.sandboxes.get(sb.id)
    client.close()


def test_sandboxes_create_snapshot(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})

    captured_bodies: list[dict | None] = []
    original_request = client._transport.request

    def capturing_request(method, path, query=None, body=None):
        captured_bodies.append(body)
        return original_request(method, path, query=query, body=body)

    client._transport.request = capturing_request  # type: ignore[method-assign]

    snap = client.sandboxes.create_snapshot(sb.id, {"name": "demo-snap"})
    assert captured_bodies == [{"name": "demo-snap", "include_memory": False}]
    assert str(snap.id) == _first_snapshot_id()
    assert snap.status == SnapshotStatus.Pending
    assert snap.include_memory is False
    client.close()


def test_sandboxes_list_snapshots(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})
    client.sandboxes.create_snapshot(sb.id, {"name": "snap-a"})
    client.sandboxes.create_snapshot(sb.id, {"name": "snap-b"})

    snaps = client.sandboxes.list_snapshots(sb.id)
    assert len(snaps) == 2
    assert all(isinstance(s, Snapshot) for s in snaps)
    assert {s.name for s in snaps} == {"snap-a", "snap-b"}
    client.close()


def test_sandboxes_get_and_delete_snapshot(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})
    created = client.sandboxes.create_snapshot(sb.id, {"name": "snap-x"})

    fetched = client.sandboxes.get_snapshot(str(created.id))
    assert fetched.id == created.id
    assert fetched.name == "snap-x"

    client.sandboxes.delete_snapshot(str(created.id))
    with pytest.raises(NotFoundError):
        client.sandboxes.get_snapshot(str(created.id))
    client.close()


def test_sandboxes_get_snapshot_not_found(mock_transport):
    client = _make_client(mock_transport)
    with pytest.raises(NotFoundError):
        client.sandboxes.get_snapshot("00000000-0000-0000-0000-000000000099")
    client.close()


def test_sandboxes_restore(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})
    snap = client.sandboxes.create_snapshot(sb.id, {"name": "restore-me"})

    captured_bodies: list[dict | None] = []
    original_request = client._transport.request

    def capturing_request(method, path, query=None, body=None):
        captured_bodies.append(body)
        return original_request(method, path, query=query, body=body)

    client._transport.request = capturing_request  # type: ignore[method-assign]

    restored = client.sandboxes.restore(sb.id, str(snap.id))
    assert captured_bodies == [{"snapshot_id": str(snap.id)}]
    assert restored.id == sb.id
    assert restored.phase == "Pending"
    client.close()


def test_sandboxes_fork(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})

    captured_bodies: list[dict | None] = []
    original_request = client._transport.request

    def capturing_request(method, path, query=None, body=None):
        captured_bodies.append(body)
        return original_request(method, path, query=query, body=body)

    client._transport.request = capturing_request  # type: ignore[method-assign]

    forked = client.sandboxes.fork(sb.id, "snapshot-fork")
    assert captured_bodies == [{"name": "snapshot-fork"}]
    assert forked.name == "snapshot-fork"
    assert forked.id != sb.id
    client.close()


def test_sandbox_handle_snapshot_methods(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})

    captured: list[tuple[str, str]] = []
    original_request = client._transport.request

    def capturing_request(method, path, query=None, body=None):
        captured.append((method, path))
        return original_request(method, path, query=query, body=body)

    client._transport.request = capturing_request  # type: ignore[method-assign]

    pending = sb.snapshot({"name": "handle-snap"})
    assert pending.status == SnapshotStatus.Pending

    listed = sb.snapshots()
    assert len(listed) == 1

    sb.restore(str(pending.id))
    fork = sb.fork("handle-fork")
    assert fork.name == "handle-fork"

    paths = [path for _, path in captured]
    assert any(path.endswith(f"/sandboxes/{sb.id}/snapshots") for path in paths)
    assert any(path.endswith(f"/sandboxes/{sb.id}/restore") for path in paths)
    assert any(path.endswith(f"/sandboxes/{sb.id}/fork") for path in paths)
    client.close()


def test_sandboxes_create_from_snapshot(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})
    snap = client.sandboxes.create_snapshot(sb.id, {"name": "seed"})

    restored = client.sandboxes.create(
        {
            "name": "from-snap",
            "sandbox_template_id": "sb-ubuntu-24-04-minimal",
            "from_snapshot": str(snap.id),
        }
    )
    assert restored.name == "from-snap"
    client.close()
