"""Tests for in-place sandbox resize: sandboxes.update / sandbox.update."""

import pytest

from neevai._parse import ResponseValidationError
from neevai.client import AsyncNeevAI, NeevAI
from neevai.errors import NeevAIError
from neevai.handles.sandbox import Sandbox
from neevai.types import SandboxResources, UpdateSandboxParams


def _client(mock_transport) -> NeevAI:
    return NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        client=mock_transport,
    )


def _new_sandbox(client: NeevAI, **overrides):
    params = {
        "name": "s1",
        "sandbox_template_id": "sb-ubuntu-24-04-minimal",
        "resources": {"cpu": 1, "memory_gb": 2},
    }
    params.update(overrides)
    return client.sandboxes.create(params)


def _capture(client) -> list[tuple[str, str, dict | None]]:
    """Record (method, path, body) for every request the client makes from here on."""
    calls: list[tuple[str, str, dict | None]] = []
    original_request = client._transport.request

    def capturing_request(method, path, query=None, body=None):
        calls.append((method, path, body))
        return original_request(method, path, query=query, body=body)

    client._transport.request = capturing_request  # type: ignore[method-assign]
    return calls


def test_update_patches_the_sandbox_item_path(mock_transport):
    client = _client(mock_transport)
    sb = _new_sandbox(client)
    calls = _capture(client)

    updated = client.sandboxes.update(sb.id, {"resources": {"cpu": 2, "memory_gb": 4}})

    assert calls == [
        (
            "PATCH",
            f"/api/v1beta1/orgs/org1/projects/proj1/sandboxes/{sb.id}",
            {"resources": {"cpu": 2.0, "memory_gb": 4}},
        )
    ]
    assert updated.id == sb.id
    assert updated.data["resources"] == {"cpu": 2.0, "memory_gb": 4, "disk_gb": None}
    client.close()


def test_update_sends_only_the_sizes_the_caller_set(mock_transport):
    client = _client(mock_transport)
    sb = _new_sandbox(client)
    calls = _capture(client)

    updated = client.sandboxes.update(sb.id, {"resources": {"cpu": 4}})

    assert calls[0][2] == {"resources": {"cpu": 4.0}}
    # memory_gb was not in the body, so the server-side value survives the resize.
    assert updated.data["resources"]["memory_gb"] == 2
    client.close()


def test_update_accepts_a_params_model(mock_transport):
    client = _client(mock_transport)
    sb = _new_sandbox(client)
    calls = _capture(client)

    params = UpdateSandboxParams(resources=SandboxResources(cpu=2.5))
    updated = client.sandboxes.update(sb.id, params)

    assert calls[0][2] == {"resources": {"cpu": 2.5}}
    assert updated.data["resources"]["cpu"] == 2.5
    client.close()


def test_update_rejects_a_body_without_resources(mock_transport):
    client = _client(mock_transport)
    sb = _new_sandbox(client)
    with pytest.raises(NeevAIError):
        client.sandboxes.update(sb.id, {})
    client.close()


def test_update_rejects_a_misspelled_size_instead_of_resizing_nothing(mock_transport):
    """`SandboxResources` ignores unknown keys, so a typo must fail loudly, not PATCH an empty resize."""
    client = _client(mock_transport)
    sb = _new_sandbox(client)
    calls = _capture(client)

    with pytest.raises(NeevAIError, match="misspelled"):
        client.sandboxes.update(sb.id, {"resources": {"memory": 8}})
    with pytest.raises(NeevAIError, match="misspelled"):
        client.sandboxes.update(sb.id, {"resources": {}})

    # Nothing reached the wire, so the sandbox keeps the sizing it was created with.
    assert calls == []
    assert client.sandboxes.get(sb.id).data["resources"] == {
        "cpu": 1.0,
        "memory_gb": 2,
        "disk_gb": None,
    }
    client.close()


def test_update_rejects_unknown_fields_and_out_of_range_sizes(mock_transport):
    client = _client(mock_transport)
    sb = _new_sandbox(client)
    with pytest.raises(ResponseValidationError):
        client.sandboxes.update(sb.id, {"resources": {"cpu": 2}, "name": "renamed"})
    with pytest.raises(ResponseValidationError):
        client.sandboxes.update(sb.id, {"resources": {"cpu": 99}})
    client.close()


def test_update_scope_override_lands_in_the_path(mock_transport):
    client = _client(mock_transport)
    sb = client.sandboxes.create(
        {"name": "scoped", "sandbox_template_id": "sb-ubuntu-24-04-minimal"},
        org_id="org2",
        project_id="proj2",
    )
    calls = _capture(client)

    updated = client.sandboxes.update(
        sb.id, {"resources": {"cpu": 2}}, org_id="org2", project_id="proj2"
    )

    assert calls[0][1] == f"/api/v1beta1/orgs/org2/projects/proj2/sandboxes/{sb.id}"
    assert updated.scope is not None
    assert updated.scope.org_id == "org2"
    assert updated.scope.project_id == "proj2"
    client.close()


def test_handle_update_refreshes_its_own_state(mock_transport):
    client = _client(mock_transport)
    sb = _new_sandbox(client)
    assert sb.data["resources"]["cpu"] == 1.0

    same_handle = sb.update({"resources": {"cpu": 3}})

    assert same_handle is sb
    assert sb.data["resources"]["cpu"] == 3.0
    client.close()


def test_handle_update_keeps_the_cached_connection_when_the_url_is_unchanged(mock_transport):
    client = _client(mock_transport)
    sb = _new_sandbox(client)

    from tests.conftest import _FAKE_DB

    record = _FAKE_DB["sandboxes"][sb.id]
    record["phase"] = "Ready"
    record["connect_url"] = "https://sbx.example.com"
    sb.refresh()

    conn = sb._connection()
    sb.update({"resources": {"cpu": 2}})

    # A resize does not restart the sandbox, so the runtime connection stays usable.
    assert sb._conn is conn
    client.close()


def test_handle_update_without_client_context_raises():
    sb = Sandbox(
        None,
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "org_id": "org1",
            "project_id": "proj1",
            "name": "orphan",
            "region": "as-south-1",
            "image": "ubuntu:22.04",
            "phase": "Ready",
            "replicas": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )
    with pytest.raises(NeevAIError, match="no client context"):
        sb.update({"resources": {"cpu": 2}})


@pytest.mark.asyncio
async def test_async_update_patches_and_refreshes_the_handle(async_mock_transport):
    client = AsyncNeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        client=async_mock_transport,
    )
    sb = await client.sandboxes.create(
        {
            "name": "s1",
            "sandbox_template_id": "sb-ubuntu-24-04-minimal",
            "resources": {"cpu": 1, "memory_gb": 2},
        }
    )
    calls: list[tuple[str, str, dict | None]] = []
    original_request = client._transport.request

    async def capturing_request(method, path, query=None, body=None):
        calls.append((method, path, body))
        return await original_request(method, path, query=query, body=body)

    client._transport.request = capturing_request

    updated = await client.sandboxes.update(sb.id, {"resources": {"cpu": 2, "memory_gb": 4}})
    assert calls == [
        (
            "PATCH",
            f"/api/v1beta1/orgs/org1/projects/proj1/sandboxes/{sb.id}",
            {"resources": {"cpu": 2.0, "memory_gb": 4}},
        )
    ]
    assert updated.data["resources"]["cpu"] == 2.0

    same_handle = await sb.update({"resources": {"cpu": 3}})
    assert same_handle is sb
    assert sb.data["resources"]["cpu"] == 3.0
    # The cpu-only resize left the earlier memory size in place.
    assert sb.data["resources"]["memory_gb"] == 4
    await client.aclose()


@pytest.mark.asyncio
async def test_async_update_rejects_invalid_params(async_mock_transport):
    client = AsyncNeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        client=async_mock_transport,
    )
    sb = await client.sandboxes.create(
        {"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"}
    )
    with pytest.raises(NeevAIError):
        await client.sandboxes.update(sb.id, {})
    with pytest.raises(NeevAIError, match="misspelled"):
        await client.sandboxes.update(sb.id, {"resources": {"memory": 8}})
    with pytest.raises(ResponseValidationError):
        await client.sandboxes.update(sb.id, {"resources": {"cpu": 2}, "name": "renamed"})
    await client.aclose()
