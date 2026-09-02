"""Basic sanity tests for the Sandboxes resource (the API, sync)."""

import uuid
from unittest.mock import MagicMock

import pytest

from neevai._parse import ResponseValidationError
from neevai.client import AsyncNeevAI, NeevAI
from neevai.errors import BadRequestError, NeevAIError, NotFoundError
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
        "snapshot_type": "full",
        "sandbox_format_version": 1,
        "restorability": "restorable",
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


def test_sandboxes_list_filters(mock_transport):
    client = _make_client(mock_transport)
    web = client.sandboxes.create(
        {"name": "web-server", "sandbox_template_id": "sb-ubuntu-24-04-minimal"}
    )
    client.sandboxes.create(
        {"name": "db-primary", "sandbox_template_id": "sb-ubuntu-24-04-minimal"}
    )

    # name is a case-insensitive substring match.
    by_name = client.sandboxes.list(name="WEB")
    assert [s.name for s in by_name.items] == ["web-server"]
    assert by_name.total == 1

    # sandbox_id narrows to a single sandbox.
    by_id = client.sandboxes.list(sandbox_id=web.id)
    assert [s.id for s in by_id.items] == [web.id]

    # status is an exact lifecycle-phase match.
    client.sandboxes.pause(web.id)
    paused = client.sandboxes.list(status="Paused")
    assert [s.id for s in paused.items] == [web.id]
    pending = client.sandboxes.list(status="Pending")
    assert {s.name for s in pending.items} == {"db-primary"}

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
    assert captured_bodies == [{"name": "demo-snap"}]
    assert str(snap.id) == _first_snapshot_id()
    assert snap.status == SnapshotStatus.Pending
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


def test_sandboxes_rollback(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})
    snap = client.sandboxes.create_snapshot(sb.id, {"name": "restore-me"})

    captured_bodies: list[dict | None] = []
    original_request = client._transport.request

    def capturing_request(method, path, query=None, body=None):
        captured_bodies.append(body)
        return original_request(method, path, query=query, body=body)

    client._transport.request = capturing_request  # type: ignore[method-assign]

    rolled_back = client.sandboxes.rollback(sb.id, str(snap.id))
    assert captured_bodies == [{"snapshot_id": str(snap.id)}]
    assert rolled_back.id == sb.id
    assert rolled_back.phase == "Pending"
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

    sb.rollback(str(pending.id))
    fork = sb.fork("handle-fork")
    assert fork.name == "handle-fork"

    paths = [path for _, path in captured]
    assert any(path.endswith(f"/sandboxes/{sb.id}/snapshots") for path in paths)
    assert any(path.endswith(f"/sandboxes/{sb.id}/rollback") for path in paths)
    assert any(path.endswith(f"/sandboxes/{sb.id}/fork") for path in paths)
    client.close()


def test_sandboxes_create_with_restore(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})
    snap = client.sandboxes.create_snapshot(sb.id, {"name": "seed"})

    restored = client.sandboxes.create(
        {
            "name": "from-snap",
            "sandbox_template_id": "sb-ubuntu-24-04-minimal",
            "restore": str(snap.id),
        }
    )
    assert restored.name == "from-snap"
    client.close()


def _capture_requests(client) -> list[tuple[str, str, dict | None]]:
    """Wrap the client transport, appending (method, path, body) for each call."""
    captured: list[tuple[str, str, dict | None]] = []
    original = client._transport.request

    def capturing(method, path, query=None, body=None):
        captured.append((method, path, body))
        return original(method, path, query=query, body=body)

    client._transport.request = capturing  # type: ignore[method-assign]
    return captured


def test_sandboxes_update_resources_in_place(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-x"})
    captured = _capture_requests(client)

    updated = client.sandboxes.update(sb.id, {"resources": {"cpu": 2, "memory_gb": 4}})

    # Same identity, name, and preview URL template are preserved.
    assert updated.id == sb.id
    assert updated.name == sb.name
    assert updated.data.get("preview_url_template") == sb.data.get("preview_url_template")

    method, path, body = captured[-1]
    assert method == "PATCH"
    assert path.endswith(f"/sandboxes/{sb.id}")
    assert body == {"resources": {"cpu": 2, "memory_gb": 4}}

    # A subsequent get reflects the new shape.
    res = client.sandboxes.get(sb.id).data["resources"]
    assert res["cpu"] == 2 and res["memory_gb"] == 4
    client.close()


def test_sandboxes_update_egress_convenience_matches_create(mock_transport):
    client = _make_client(mock_transport)
    captured = _capture_requests(client)

    created = client.sandboxes.create(
        {"name": "s1", "sandbox_template_id": "sb-x"}, allow_egress=["github.com"]
    )
    create_egress = next(b for (m, _p, b) in captured if m == "POST")["egress"]

    client.sandboxes.update(created.id, {}, allow_egress=["github.com"])
    update_egress = captured[-1][2]["egress"]

    # Criterion 7: the convenience shape is byte-identical between create and update.
    assert update_egress == create_egress
    client.close()


def test_sandboxes_update_resources_and_egress_single_patch(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-x"})
    captured = _capture_requests(client)

    client.sandboxes.update(
        sb.id,
        {
            "resources": {"cpu": 2, "memory_gb": 4},
            "egress": {"mode": "allow_list", "allow": [{"host": "api.github.com"}]},
        },
    )

    patches = [(p, b) for (m, p, b) in captured if m == "PATCH"]
    assert len(patches) == 1
    _path, body = patches[0]
    assert "resources" in body and "egress" in body
    assert body["egress"]["mode"] == "allow_list"
    client.close()


def test_sandboxes_update_empty_raises_without_http(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-x"})
    request_mock = MagicMock(side_effect=client._transport.request)
    client._transport.request = request_mock

    with pytest.raises(NeevAIError, match="empty body") as ei:
        client.sandboxes.update(sb.id, {})
    msg = str(ei.value)
    assert "resources" in msg and "egress" in msg
    request_mock.assert_not_called()
    client.close()


def test_sandboxes_update_disk_gb_surfaces_server_rejection(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-x"})
    captured = _capture_requests(client)

    # disk_gb is not dropped client-side; the server's rejection surfaces unchanged.
    with pytest.raises(BadRequestError):
        client.sandboxes.update(sb.id, {"resources": {"disk_gb": 20}})
    assert captured[-1][2] == {"resources": {"disk_gb": 20}}
    client.close()


def test_sandbox_handle_update_in_place(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-x"})
    same = sb.update({"resources": {"cpu": 2, "memory_gb": 4}})
    assert same is sb
    assert sb.data["resources"]["cpu"] == 2 and sb.data["resources"]["memory_gb"] == 4
    client.close()


@pytest.mark.asyncio
async def test_async_sandboxes_update(async_mock_transport):
    client = AsyncNeevAI(
        api_key="test", org_id="org1", project_id="proj1", client=async_mock_transport
    )
    sb = await client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-x"})
    updated = await client.sandboxes.update(sb.id, {"resources": {"cpu": 2, "memory_gb": 4}})
    assert updated.id == sb.id
    res = (await client.sandboxes.get(sb.id)).data["resources"]
    assert res["cpu"] == 2 and res["memory_gb"] == 4
    await client.aclose()


@pytest.mark.asyncio
async def test_async_sandbox_handle_update(async_mock_transport):
    client = AsyncNeevAI(
        api_key="test", org_id="org1", project_id="proj1", client=async_mock_transport
    )
    sb = await client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-x"})
    same = await sb.update(
        {"resources": {"cpu": 2, "memory_gb": 4}}, allow_egress=["api.github.com"]
    )
    assert same is sb
    assert sb.data["resources"]["cpu"] == 2 and sb.data["resources"]["memory_gb"] == 4
    assert [r["host"] for r in sb.data["egress"]["allow"]] == ["api.github.com"]
    await client.aclose()
