"""Basic sanity tests for the Sandboxes resource (control plane, sync)."""

import pytest

from neevai.client import NeevAI
from neevai.errors import NotFoundError


def test_sandboxes_create(mock_transport):
    client = NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        client=mock_transport,
    )
    sb = client.sandboxes.create({"name": "s1", "image": "ubuntu:22.04"})
    assert sb.id == "1"
    assert sb.name == "s1"
    assert sb.phase == "Pending"
    client.close()


def test_sandboxes_get(mock_transport):
    client = NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        client=mock_transport,
    )
    created = client.sandboxes.create({"name": "s1", "image": "ubuntu:22.04"})
    fetched = client.sandboxes.get(created.id)
    assert fetched.id == created.id
    assert fetched.name == "s1"
    client.close()


def test_sandboxes_list(mock_transport):
    client = NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        client=mock_transport,
    )
    client.sandboxes.create({"name": "s1", "image": "ubuntu:22.04"})
    client.sandboxes.create({"name": "s2", "image": "ubuntu:22.04"})

    page = client.sandboxes.list()
    assert len(page["items"]) == 2
    assert page["total"] == 2
    assert page["page"] == 1
    client.close()


def test_sandboxes_delete(mock_transport):
    client = NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        client=mock_transport,
    )
    sb = client.sandboxes.create({"name": "s1", "image": "ubuntu:22.04"})
    client.sandboxes.delete(sb.id)
    with pytest.raises(NotFoundError):
        client.sandboxes.get(sb.id)
    client.close()


def test_sandboxes_pause_resume(mock_transport):
    client = NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        client=mock_transport,
    )
    sb = client.sandboxes.create({"name": "s1", "image": "ubuntu:22.04"})
    paused = client.sandboxes.pause(sb.id)
    assert paused.phase == "Paused"
    resumed = client.sandboxes.resume(sb.id)
    assert resumed.phase == "Pending"
    client.close()


def test_sandboxes_metrics(mock_transport):
    client = NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        client=mock_transport,
    )
    sb = client.sandboxes.create({"name": "s1", "image": "ubuntu:22.04"})
    metrics = client.sandboxes.metrics(sb.id)
    assert metrics["sandbox_id"] == sb.id
    assert metrics["series"] == []
    client.close()


def test_sandboxes_get_not_found(mock_transport):
    client = NeevAI(
        api_key="test",
        org_id="org1",
        project_id="proj1",
        client=mock_transport,
    )
    with pytest.raises(NotFoundError):
        client.sandboxes.get("nonexistent")
    client.close()
