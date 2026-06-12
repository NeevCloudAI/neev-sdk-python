"""Basic sanity tests for the Sandboxes resource (control plane, sync)."""

import uuid

import pytest

from neevai._parse import ResponseValidationError
from neevai.client import NeevAI
from neevai.errors import NeevAIError, NotFoundError
from neevai.types import CreateSandboxParams


def _make_client(mock_transport, region: str = "us-east-1") -> NeevAI:
    return NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        region=region,
        client=mock_transport,
    )


def _first_sandbox_id() -> str:
    return str(uuid.UUID(int=1))


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
        region="us-east-1",
    )
    sb = client.sandboxes.create(params)
    assert sb.name == "s1"
    client.close()


def test_sandboxes_create_injects_default_region(mock_transport):
    client = _make_client(mock_transport, region="eu-central-1")
    sb = client.sandboxes.create({"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal"})
    assert sb.data["region"] == "eu-central-1"
    client.close()


def test_sandboxes_create_explicit_region_overrides_default(mock_transport):
    client = _make_client(mock_transport, region="eu-central-1")
    sb = client.sandboxes.create(
        {
            "name": "s1",
            "sandbox_template_id": "sb-ubuntu-24-04-minimal",
            "region": "ap-south-1",
        }
    )
    assert sb.data["region"] == "ap-south-1"
    client.close()


def test_sandboxes_create_raises_when_region_missing(mock_transport, monkeypatch):
    monkeypatch.delenv("NEEVCLOUD_REGION", raising=False)
    client = NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        client=mock_transport,
    )
    with pytest.raises(NeevAIError, match="Missing region"):
        client.sandboxes.create(
            {
                "name": "s1",
                "sandbox_template_id": "sb-ubuntu-24-04-minimal",
            }
        )
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
