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
    sb = client.sandboxes.create(
        {"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal", "image": "ubuntu:22.04"}
    )
    assert sb.id == _first_sandbox_id()
    assert sb.name == "s1"
    assert sb.phase == "Pending"
    assert sb.data.get("namespace") is None
    client.close()


def test_sandboxes_create_with_model_instance(mock_transport):
    client = _make_client(mock_transport)
    params = CreateSandboxParams(
        name="s1",
        sandbox_template_id="sb-ubuntu-24-04-minimal",
        region="us-east-1",
        image="ubuntu:22.04",
    )
    sb = client.sandboxes.create(params)
    assert sb.name == "s1"
    client.close()


def test_sandboxes_create_injects_default_region(mock_transport):
    client = _make_client(mock_transport, region="eu-central-1")
    sb = client.sandboxes.create(
        {"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal", "image": "ubuntu:22.04"}
    )
    assert sb.data["region"] == "eu-central-1"
    client.close()


def test_sandboxes_create_explicit_region_overrides_default(mock_transport):
    client = _make_client(mock_transport, region="eu-central-1")
    sb = client.sandboxes.create(
        {
            "name": "s1",
            "sandbox_template_id": "sb-ubuntu-24-04-minimal",
            "region": "ap-south-1",
            "image": "ubuntu:22.04",
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
                "image": "ubuntu:22.04",
            }
        )
    client.close()


def test_sandboxes_get(mock_transport):
    client = _make_client(mock_transport)
    created = client.sandboxes.create(
        {"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal", "image": "ubuntu:22.04"}
    )
    fetched = client.sandboxes.get(created.id)
    assert fetched.id == created.id
    assert fetched.name == "s1"
    client.close()


def test_sandboxes_list(mock_transport):
    client = _make_client(mock_transport)
    client.sandboxes.create(
        {"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal", "image": "ubuntu:22.04"}
    )
    client.sandboxes.create(
        {"name": "s2", "sandbox_template_id": "sb-ubuntu-24-04-minimal", "image": "ubuntu:22.04"}
    )

    page = client.sandboxes.list()
    assert len(page.items) == 2
    assert page.total == 2
    assert page.page == 1
    client.close()


def test_sandboxes_delete(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create(
        {"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal", "image": "ubuntu:22.04"}
    )
    client.sandboxes.delete(sb.id)
    with pytest.raises(NotFoundError):
        client.sandboxes.get(sb.id)
    client.close()


def test_sandboxes_pause_resume(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create(
        {"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal", "image": "ubuntu:22.04"}
    )
    paused = client.sandboxes.pause(sb.id)
    assert paused.phase == "Paused"
    resumed = client.sandboxes.resume(sb.id)
    assert resumed.phase == "Pending"
    client.close()


def test_sandboxes_metrics(mock_transport):
    client = _make_client(mock_transport)
    sb = client.sandboxes.create(
        {"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal", "image": "ubuntu:22.04"}
    )
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
    sb = client.sandboxes.create(
        {"name": "s1", "sandbox_template_id": "sb-ubuntu-24-04-minimal", "image": "ubuntu:22.04"}
    )

    original_request = client._transport.request

    def broken_get(method, path, **kwargs):
        if method == "GET" and path.endswith(f"/sandboxes/{sb.id}"):
            return {"id": "not-a-uuid", "name": "broken"}
        return original_request(method, path, **kwargs)

    monkeypatch.setattr(client._transport, "request", broken_get)

    with pytest.raises(ResponseValidationError):
        client.sandboxes.get(sb.id)
    client.close()
