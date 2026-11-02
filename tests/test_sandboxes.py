"""Basic sanity tests for the Sandboxes resource (the API, sync)."""

import re
import uuid
from unittest.mock import MagicMock

import httpx
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
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-26-04-dev"})
    assert sb.id == _first_sandbox_id()
    assert sb.name == "s1"
    assert sb.phase == "Pending"
    assert sb.data.get("sandbox_template_id") == "sb-ubuntu-26-04-dev"
    client.close()


def test_sandboxes_create_with_model_instance(mock_transport):
    client = _make_client(mock_transport)
    params = CreateSandboxParams(
        name="s1",
        sandbox_template_id="sb-ubuntu-26-04-dev",
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
            "sandbox_template_id": "sb-ubuntu-26-04-dev",
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
            "sandbox_template_id": "sb-ubuntu-26-04-dev",
        }
    )
    assert sandbox.id
    client.close()


def test_sandboxes_get(mock_transport):
    client = _make_client(mock_transport)
    created = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-26-04-dev"})
    fetched = client.sandboxes.get(created.id)
    assert fetched.id == created.id
    assert fetched.name == "s1"
    client.close()


def test_sandboxes_list(mock_transport):
    client = _make_client(mock_transport)
    client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-26-04-dev"})
    client.sandboxes.create({"name": "s2", "sandbox_template_id": "sb-ubuntu-26-04-dev"})

    page = client.sandboxes.list()
    assert len(page.items) == 2
    assert page.total == 2
    assert page.page == 1
    client.close()


def test_sandboxes_list_filters(mock_transport):
    client = _make_client(mock_transport)
    web = client.sandboxes.create(
        {"name": "web-server", "sandbox_template_id": "sb-ubuntu-26-04-dev"}
    )
    client.sandboxes.create({"name": "db-primary", "sandbox_template_id": "sb-ubuntu-26-04-dev"})

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
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-26-04-dev"})
    client.sandboxes.delete(sb.id)
    with pytest.raises(NotFoundError):
        client.sandboxes.get(sb.id)
    client.close()


def test_sandboxes_pause_resume(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-26-04-dev"})
    paused = client.sandboxes.pause(sb.id)
    assert paused.phase == "Paused"
    resumed = client.sandboxes.resume(sb.id)
    assert resumed.phase == "Pending"
    client.close()


def test_sandboxes_pause_accepts_pausing_transitional_phase(mock_transport, monkeypatch):
    """Pause API may return phase=Pausing while reconciliation is in progress."""
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-26-04-dev"})

    original_request = client._transport.request

    def pausing_pause(method, path, **kwargs):
        if method == "POST" and path.endswith(f"/sandboxes/{sb.id}/pause"):
            sandbox = dict(
                original_request("GET", f"/api/v1beta1/orgs/org1/projects/proj1/sandboxes/{sb.id}")
            )
            sandbox["phase"] = "Pausing"
            return sandbox
        return original_request(method, path, **kwargs)

    monkeypatch.setattr(client._transport, "request", pausing_pause)

    paused = client.sandboxes.pause(sb.id)
    assert paused.phase == "Pausing"
    client.close()


def test_sandboxes_pause_sends_an_empty_json_body(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-26-04-dev"})

    captured_bodies: list[dict | None] = []
    original_request = client._transport.request

    def capturing_request(method, path, query=None, body=None):
        captured_bodies.append(body)
        return original_request(method, path, query=query, body=body)

    client._transport.request = capturing_request  # type: ignore[method-assign]

    client.sandboxes.pause(sb.id)
    assert captured_bodies == [{}]
    client.close()


def test_sandboxes_pause_rejects_the_removed_preserve_memory_kwarg(mock_transport):
    """A caller still passing the dropped flag gets a TypeError, not a silently ignored pause."""
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-26-04-dev"})

    with pytest.raises(TypeError):
        client.sandboxes.pause(sb.id, preserve_memory=True)  # type: ignore[call-arg]
    client.close()


def test_sandboxes_metrics(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-26-04-dev"})
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
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-26-04-dev"})

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
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-26-04-dev"})

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
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-26-04-dev"})
    client.sandboxes.create_snapshot(sb.id, {"name": "snap-a"})
    client.sandboxes.create_snapshot(sb.id, {"name": "snap-b"})

    snaps = client.sandboxes.list_snapshots(sb.id)
    assert len(snaps) == 2
    assert all(isinstance(s, Snapshot) for s in snaps)
    assert {s.name for s in snaps} == {"snap-a", "snap-b"}
    client.close()


def test_sandboxes_get_and_delete_snapshot(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-26-04-dev"})
    created = client.sandboxes.create_snapshot(sb.id, {"name": "snap-x"})

    fetched = client.sandboxes.get_snapshot(str(created.id))
    assert fetched.id == created.id
    assert fetched.name == "snap-x"

    client.sandboxes.delete_snapshot(str(created.id))
    with pytest.raises(NotFoundError):
        client.sandboxes.get_snapshot(str(created.id))
    client.close()


def test_snapshot_trigger_is_optional():
    """Older API versions send no trigger; a snapshot must still parse."""
    assert Snapshot.model_validate(snapshot_data()).trigger is None
    pressured = Snapshot.model_validate(snapshot_data(trigger="memory_pressure"))
    assert pressured.trigger == "memory_pressure"


def test_sandboxes_get_snapshot_not_found(mock_transport):
    client = _make_client(mock_transport)
    with pytest.raises(NotFoundError):
        client.sandboxes.get_snapshot("00000000-0000-0000-0000-000000000099")
    client.close()


def test_sandboxes_rollback(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-26-04-dev"})
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
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-26-04-dev"})

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
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-26-04-dev"})

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
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-26-04-dev"})
    snap = client.sandboxes.create_snapshot(sb.id, {"name": "seed"})

    restored = client.sandboxes.create(
        {
            "name": "from-snap",
            "sandbox_template_id": "sb-ubuntu-26-04-dev",
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


# --- In-place resize + live egress update (#31) ---


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


def test_sandboxes_update_execution_trace(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-x"})
    assert sb.execution_trace is True
    captured = _capture_requests(client)

    updated = client.sandboxes.update(sb.id, {"execution_trace": False})

    method, _, body = captured[-1]
    assert method == "PATCH"
    assert body == {"execution_trace": False}
    assert updated.execution_trace is False
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

    # disk_gb is not dropped client-side; the server rejection surfaces unchanged.
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


# --- Lifecycle windows + create-time options (#32) ---


def test_sandboxes_create_with_lifecycle_sends_lifecycle(mock_transport):
    client = _make_client(mock_transport)
    captured = _capture_requests(client)
    sb = client.sandboxes.create(
        {
            "sandbox_template_id": "sb-x",
            "lifecycle": {"max_lifetime_seconds": 3600, "idle_timeout_seconds": 300},
        }
    )
    body = next(b for (m, _p, b) in captured if m == "POST")
    assert body["lifecycle"] == {"max_lifetime_seconds": 3600, "idle_timeout_seconds": 300}
    # The window is observable on the created sandbox.
    assert sb.data["idle_timeout_seconds"] == 300
    client.close()


def test_sandboxes_create_without_lifecycle_omits_key(mock_transport):
    client = _make_client(mock_transport)
    captured = _capture_requests(client)
    client.sandboxes.create({"sandbox_template_id": "sb-x"})
    body = next(b for (m, _p, b) in captured if m == "POST")
    assert "lifecycle" not in body
    client.close()


def test_sandboxes_create_byoi_sends_image_and_command(mock_transport):
    client = _make_client(mock_transport)
    captured = _capture_requests(client)
    client.sandboxes.create(
        {"image": "docker.io/library/python:3.12", "command": ["sleep", "infinity"]}
    )
    body = next(b for (m, _p, b) in captured if m == "POST")
    assert body["image"] == "docker.io/library/python:3.12"
    assert body["command"] == ["sleep", "infinity"]
    client.close()


def test_sandboxes_keepalive(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"sandbox_template_id": "sb-x"})
    captured = _capture_requests(client)
    same = client.sandboxes.keepalive(sb.id)
    assert same.id == sb.id
    method, path, _body = captured[-1]
    assert method == "POST" and path.endswith(f"/sandboxes/{sb.id}/keepalive")
    client.close()


def test_sandboxes_update_timeout_partial_leaves_others_unchanged(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create(
        {
            "sandbox_template_id": "sb-x",
            "lifecycle": {"idle_timeout_seconds": 300, "max_lifetime_seconds": 3600},
        }
    )
    captured = _capture_requests(client)
    updated = client.sandboxes.update_timeout(sb.id, {"idle_timeout_seconds": 600})

    method, path, body = captured[-1]
    assert method == "PUT" and path.endswith(f"/sandboxes/{sb.id}/timeout")
    # Only the passed window is on the wire; the others are not sent (left unchanged).
    assert body == {"idle_timeout_seconds": 600}
    assert updated.data["idle_timeout_seconds"] == 600
    assert updated.data["max_lifetime_seconds"] == 3600
    client.close()


def test_sandboxes_update_timeout_clears_window(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create(
        {"sandbox_template_id": "sb-x", "lifecycle": {"max_lifetime_seconds": 3600}}
    )
    captured = _capture_requests(client)
    updated = client.sandboxes.update_timeout(sb.id, {"max_lifetime_seconds": 0})

    _method, _path, body = captured[-1]
    # 0 turns the window off (per the API: omitted = unchanged, 0 = no limit).
    assert body == {"max_lifetime_seconds": 0}
    assert updated.data["max_lifetime_seconds"] == 0
    client.close()


def test_sandboxes_update_timeout_invalid_on_idle_raises_without_http(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"sandbox_template_id": "sb-x"})
    request_mock = MagicMock(side_effect=client._transport.request)
    client._transport.request = request_mock

    with pytest.raises(NeevAIError):
        client.sandboxes.update_timeout(sb.id, {"on_idle": "explode"})

    request_mock.assert_not_called()
    client.close()


def test_sandboxes_update_timeout_on_idle_serialized_as_json(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"sandbox_template_id": "sb-x"})
    captured = _capture_requests(client)
    client.sandboxes.update_timeout(sb.id, {"on_idle": "delete"})

    _method, _path, body = captured[-1]
    # on_idle must serialize to a plain JSON string, not a Python enum member.
    assert body == {"on_idle": "delete"}
    assert isinstance(body["on_idle"], str)
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


@pytest.mark.asyncio
async def test_async_sandboxes_pause_sends_an_empty_json_body(async_mock_transport):
    """The async pause lost the kwarg too, so it must not reach for a body field either."""
    client = AsyncNeevAI(
        api_key="test", org_id="org1", project_id="proj1", client=async_mock_transport
    )
    sb = await client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-x"})

    captured_bodies: list[dict | None] = []
    original_request = client._transport.request

    async def capturing_request(method, path, query=None, body=None):
        captured_bodies.append(body)
        return await original_request(method, path, query=query, body=body)

    client._transport.request = capturing_request  # type: ignore[method-assign]

    paused = await client.sandboxes.pause(sb.id)
    assert paused.phase == "Paused"
    assert captured_bodies == [{}]

    with pytest.raises(TypeError):
        await client.sandboxes.pause(sb.id, preserve_memory=True)  # type: ignore[call-arg]
    await client.aclose()


@pytest.mark.asyncio
async def test_async_sandboxes_keepalive_and_update_timeout(async_mock_transport):
    client = AsyncNeevAI(
        api_key="test", org_id="org1", project_id="proj1", client=async_mock_transport
    )
    sb = await client.sandboxes.create({"sandbox_template_id": "sb-x"})
    alive = await client.sandboxes.keepalive(sb.id)
    assert alive.id == sb.id
    updated = await client.sandboxes.update_timeout(sb.id, {"idle_timeout_seconds": 120})
    assert updated.data["idle_timeout_seconds"] == 120
    await client.aclose()


def test_rollback_accepts_the_snapshot_id_as_returned(mock_transport):
    """`snap.id` is a UUID; passing it straight to rollback must not fail to serialise."""
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-x"})
    snap = client.sandboxes.create_snapshot(sb.id, {"name": "before"})
    assert isinstance(snap.id, uuid.UUID)
    rolled_back = client.sandboxes.rollback(sb.id, snap.id)
    assert rolled_back.id == sb.id


@pytest.mark.asyncio
async def test_async_rollback_accepts_the_snapshot_id_as_returned(async_mock_transport):
    """The async client serialises a UUID snapshot id the same way."""
    client = AsyncNeevAI(
        api_key="test", org_id="org1", project_id="proj1", client=async_mock_transport
    )
    sb = await client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-x"})
    snap = await client.sandboxes.create_snapshot(sb.id, {"name": "before"})
    rolled_back = await client.sandboxes.rollback(sb.id, snap.id)
    assert rolled_back.id == sb.id
    await client.aclose()


# --- Labels ---

LABELS = {"team": "payments", "ci-run": "4821"}
EMPTY_PAGE = {"items": [], "total": 0, "page": 1, "limit": 20}


def _recorder(captured: list[httpx.Request], status: int = 200, payload=None):
    """Return a mock transport that records each request and answers with ``payload``."""

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(status, json=EMPTY_PAGE if payload is None else payload)

    return httpx.MockTransport(handler)


def test_sandboxes_create_with_labels(mock_transport):
    client = _make_client(mock_transport)
    captured = _capture_requests(client)

    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-x"}, labels=LABELS)

    assert captured[-1][2]["labels"] == LABELS
    assert sb.labels == LABELS
    client.close()


def test_sandboxes_create_labels_in_params(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-x", "labels": LABELS})
    assert sb.labels == LABELS
    client.close()


def test_sandboxes_create_labels_twice_raises_without_http(mock_transport):
    client = _make_client(mock_transport)
    request_mock = MagicMock(side_effect=client._transport.request)
    client._transport.request = request_mock

    with pytest.raises(NeevAIError, match="labels"):
        client.sandboxes.create(
            {"name": "s1", "sandbox_template_id": "sb-x", "labels": LABELS}, labels=LABELS
        )
    request_mock.assert_not_called()
    client.close()


def test_sandbox_labels_empty_when_server_omits_them(mock_transport):
    client = _make_client(mock_transport)
    captured = _capture_requests(client)

    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-x"})

    assert "labels" not in captured[-1][2]
    assert sb.data["labels"] is None
    assert sb.labels == {}
    client.close()


def test_sandboxes_list_labels_sent_as_repeated_params():
    captured: list[httpx.Request] = []
    client = _make_client(httpx.Client(transport=_recorder(captured)))

    client.sandboxes.list(name="web", labels=LABELS)

    params = captured[-1].url.params
    assert params.get_list("label") == ["team=payments", "ci-run=4821"]
    assert params["name"] == "web"
    # Repeated params, not a comma-joined value or a ``label[]`` key.
    assert captured[-1].url.query.decode().count("label=") == 2
    assert "label%5B%5D" not in captured[-1].url.query.decode()
    client.close()


def test_sandboxes_list_without_labels_omits_param():
    captured: list[httpx.Request] = []
    client = _make_client(httpx.Client(transport=_recorder(captured)))

    client.sandboxes.list(labels={})

    assert "label" not in captured[-1].url.params
    client.close()


def test_sandboxes_list_bad_label_surfaces_bad_request():
    captured: list[httpx.Request] = []
    transport = _recorder(captured, status=400, payload={"message": "invalid label"})
    client = _make_client(httpx.Client(transport=transport))

    # The SDK does not check label format; the server's 400 surfaces as BadRequestError.
    with pytest.raises(BadRequestError, match="invalid label"):
        client.sandboxes.list(labels={"Bad Key": "v"})
    assert captured[-1].url.params.get_list("label") == ["Bad Key=v"]
    client.close()


@pytest.mark.asyncio
async def test_async_sandboxes_create_with_labels(async_mock_transport):
    client = AsyncNeevAI(
        api_key="test", org_id="org1", project_id="proj1", client=async_mock_transport
    )
    sb = await client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-x"}, labels=LABELS)
    assert sb.labels == LABELS
    plain = await client.sandboxes.create({"name": "s2", "sandbox_template_id": "sb-x"})
    assert plain.labels == {}
    await client.aclose()


@pytest.mark.asyncio
async def test_async_sandboxes_list_labels_sent_as_repeated_params():
    captured: list[httpx.Request] = []
    client = AsyncNeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        client=httpx.AsyncClient(transport=_recorder(captured)),
    )

    await client.sandboxes.list(labels=LABELS)

    assert captured[-1].url.params.get_list("label") == ["team=payments", "ci-run=4821"]
    await client.aclose()


@pytest.mark.asyncio
async def test_async_sandboxes_list_bad_label_surfaces_bad_request():
    captured: list[httpx.Request] = []
    transport = _recorder(captured, status=400, payload={"message": "invalid label"})
    client = AsyncNeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        client=httpx.AsyncClient(transport=transport),
    )

    with pytest.raises(BadRequestError):
        await client.sandboxes.list(labels={"Bad Key": "v"})
    await client.aclose()


def _scripted_snapshots(client, statuses: list[dict]) -> list[str]:
    """Makes get_snapshot return each scripted status in turn, then the last one forever."""
    calls: list[str] = []
    models = [Snapshot.model_validate(snapshot_data(**s)) for s in statuses]

    def get_snapshot(snapshot_id, org_id=None, project_id=None):
        calls.append(str(snapshot_id))
        return models[min(len(calls) - 1, len(models) - 1)]

    client.sandboxes.get_snapshot = get_snapshot  # type: ignore[method-assign]
    return calls


@pytest.mark.parametrize(
    ("name", "statuses", "timeout_ms", "expected_error", "expected_polls"),
    [
        (
            "success: ready after polling",
            [{"status": "Pending"}, {"status": "Running"}, {"status": "Ready"}],
            5_000,
            None,
            3,
        ),
        ("success: ready at once", [{"status": "Ready"}], 5_000, None, 1),
        (
            "failure: snapshot failed, with its reason",
            [{"status": "Pending"}, {"status": "Failed", "error_message": "disk full"}],
            5_000,
            "failed to capture: disk full",
            2,
        ),
        (
            "failure: not ready before the timeout",
            [{"status": "Pending"}],
            30,
            "was not Ready within 30ms (status: Pending)",
            None,
        ),
    ],
)
def test_sandboxes_wait_for_snapshot(
    mock_transport, name, statuses, timeout_ms, expected_error, expected_polls
):
    client = _make_client(mock_transport)
    calls = _scripted_snapshots(client, statuses)

    if expected_error is None:
        snap = client.sandboxes.wait_for_snapshot(
            "snap-1", timeout_ms=timeout_ms, poll_interval_ms=1
        )
        assert snap.status == SnapshotStatus.Ready
    else:
        with pytest.raises(NeevAIError, match=re.escape(expected_error)):
            client.sandboxes.wait_for_snapshot("snap-1", timeout_ms=timeout_ms, poll_interval_ms=1)
    if expected_polls is not None:
        assert len(calls) == expected_polls
    assert set(calls) == {"snap-1"}
    client.close()


@pytest.mark.parametrize(
    ("timeout_ms", "poll_interval_ms", "bad"),
    [
        (0, 1, "timeout_ms"),
        (-5, 1, "timeout_ms"),
        (float("nan"), 1, "timeout_ms"),
        (100, 0, "poll_interval_ms"),
        (100, float("inf"), "poll_interval_ms"),
    ],
)
def test_sandboxes_wait_for_snapshot_rejects_bad_timings(
    mock_transport, timeout_ms, poll_interval_ms, bad
):
    client = _make_client(mock_transport)
    calls = _scripted_snapshots(client, [{"status": "Ready"}])
    with pytest.raises(NeevAIError, match=f"{bad} must be a positive number"):
        client.sandboxes.wait_for_snapshot(
            "snap-1", timeout_ms=timeout_ms, poll_interval_ms=poll_interval_ms
        )
    assert calls == []
    client.close()


def test_sandbox_handle_snapshot_waits_until_ready(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-26-04-dev"})
    calls = _scripted_snapshots(client, [{"status": "Running"}, {"status": "Ready"}])

    pending = sb.snapshot({"name": "no-wait"})
    assert pending.status == SnapshotStatus.Pending
    assert calls == []

    ready = sb.snapshot({"name": "wait"}, wait_until_ready=True, poll_interval_ms=1)
    assert ready.status == SnapshotStatus.Ready
    assert len(calls) == 2
    client.close()


@pytest.mark.asyncio
async def test_async_sandbox_handle_snapshot_waits_until_ready(async_mock_transport):
    client = AsyncNeevAI(
        api_key="test", org_id="org1", project_id="proj1", client=async_mock_transport
    )
    sb = await client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-x"})
    statuses = [{"status": "Pending"}, {"status": "Failed", "error_message": "no space"}]
    models = [Snapshot.model_validate(snapshot_data(**s)) for s in statuses]
    calls: list[str] = []

    async def get_snapshot(snapshot_id, org_id=None, project_id=None):
        calls.append(str(snapshot_id))
        return models[min(len(calls) - 1, len(models) - 1)]

    client.sandboxes.get_snapshot = get_snapshot  # type: ignore[method-assign]

    with pytest.raises(NeevAIError, match="failed to capture: no space"):
        await sb.snapshot({"name": "wait"}, wait_until_ready=True, poll_interval_ms=1)
    assert len(calls) == 2
    await client.aclose()


def test_sandbox_handle_snapshot_rejects_bad_timing_before_creating(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-26-04-dev"})
    created: list[str] = []

    def create_snapshot(*args, **kwargs):
        created.append("called")
        raise AssertionError("create_snapshot must not run")

    client.sandboxes.create_snapshot = create_snapshot  # type: ignore[method-assign]

    with pytest.raises(NeevAIError, match="timeout_ms must be a positive number"):
        sb.snapshot({"name": "x"}, wait_until_ready=True, timeout_ms=0)
    assert created == []
    client.close()
