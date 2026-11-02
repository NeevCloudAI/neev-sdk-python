"""Tests for agent snapshots and fork, and the 409/425 errors they surface."""

import json

import httpx
import pytest

from neevai.client import AsyncNeevAI, NeevAI
from neevai.errors import ConflictError, NeevAIError, TooEarlyError

AGENT_ID = "11111111-1111-1111-1111-111111111111"
FORK_ID = "44444444-4444-4444-4444-444444444444"
SNAPSHOT_ID = "33333333-3333-3333-3333-333333333333"
PROJECT = "/api/v1beta1/orgs/org1/projects/proj1"
BASE = f"{PROJECT}/agents/{AGENT_ID}"

AGENT = {
    "id": AGENT_ID,
    "org_id": "org1",
    "project_id": "proj1",
    "name": "web",
    "agent_template_id": "ag-claude-code",
    "drive_mode": "http",
    "sandbox_id": "22222222-2222-2222-2222-222222222222",
    "status": "Ready",
    "metrics_url": "https://metrics.example/agents/1",
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}
FORKED = {
    **AGENT,
    "id": FORK_ID,
    "name": "web-fork",
    "sandbox_id": "55555555-5555-5555-5555-555555555555",
    "status": "Provisioning",
}


def _snapshot(status: str) -> dict:
    return {
        "id": SNAPSHOT_ID,
        "sandbox_id": AGENT["sandbox_id"],
        "org_id": "org1",
        "project_id": "proj1",
        "name": "before-change",
        "status": status,
        "snapshot_type": "full",
        "trigger": "manual",
        "sandbox_format_version": 1,
        "restorability": "restorable",
        "source_region": "as-south-1",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }


def _handler(captured: list[tuple[str, str, dict | None, dict]]):
    """Records (method, path, json body, query) and answers each route with a canned body."""

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        path = request.url.path
        captured.append((request.method, path, body, dict(request.url.params)))
        if path == f"{BASE}/snapshots" and request.method == "POST":
            return httpx.Response(202, json=_snapshot("Pending"))
        if path == f"{BASE}/snapshots":
            snaps = [_snapshot("Ready")]
            return httpx.Response(200, json={"items": snaps, "total": 1, "page": 2, "limit": 5})
        if path == f"{PROJECT}/snapshots/{SNAPSHOT_ID}":
            return httpx.Response(200, json=_snapshot("Ready"))
        if path == f"{BASE}/fork":
            return httpx.Response(201, json=FORKED)
        return httpx.Response(200, json=AGENT)

    return handle


def _client(captured) -> NeevAI:
    return NeevAI(
        api_key="k",
        base_url="https://api.example.com",
        org_id="org1",
        project_id="proj1",
        client=httpx.Client(transport=httpx.MockTransport(_handler(captured))),
    )


def _async_client(captured) -> AsyncNeevAI:
    return AsyncNeevAI(
        api_key="k",
        base_url="https://api.example.com",
        org_id="org1",
        project_id="proj1",
        client=httpx.AsyncClient(transport=httpx.MockTransport(_handler(captured))),
    )


def test_agents_create_and_list_snapshots():
    captured: list = []
    client = _client(captured)
    snap = client.agents.create_snapshot(AGENT_ID, {"name": "before-change", "retain_for": "24h"})
    assert str(snap.id) == SNAPSHOT_ID and snap.status == "Pending"
    snaps = client.agents.list_snapshots(AGENT_ID, page=2, limit=5)
    assert [str(s.id) for s in snaps] == [SNAPSHOT_ID]
    client.agents.create_snapshot(AGENT_ID)
    assert captured == [
        ("POST", f"{BASE}/snapshots", {"name": "before-change", "retain_for": "24h"}, {}),
        ("GET", f"{BASE}/snapshots", None, {"page": "2", "limit": "5"}),
        ("POST", f"{BASE}/snapshots", {}, {}),
    ]
    client.close()


def test_agents_fork_returns_the_new_agent():
    captured: list = []
    client = _client(captured)
    forked = client.agents.fork(AGENT_ID, "web-fork")
    assert forked.id == FORK_ID and forked.status == "Provisioning"
    assert forked.agents is client.agents
    assert captured == [("POST", f"{BASE}/fork", {"name": "web-fork"}, {})]
    client.close()


def test_agent_handle_snapshot_snapshots_and_fork():
    captured: list = []
    client = _client(captured)
    agent = client.agents.get(AGENT_ID)
    assert agent.snapshot({"name": "before-change"}).status == "Pending"
    assert agent.snapshot(wait_until_ready=True, poll_interval_ms=1).status == "Ready"
    assert [str(s.id) for s in agent.snapshots()] == [SNAPSHOT_ID]
    forked = agent.fork("web-fork")
    assert forked is not agent and forked.id == FORK_ID
    assert agent.id == AGENT_ID and agent.status == "Ready"
    assert [(m, p) for m, p, _, _ in captured[1:]] == [
        ("POST", f"{BASE}/snapshots"),
        ("POST", f"{BASE}/snapshots"),
        ("GET", f"{PROJECT}/snapshots/{SNAPSHOT_ID}"),
        ("GET", f"{BASE}/snapshots"),
        ("POST", f"{BASE}/fork"),
    ]
    client.close()


def test_agent_handle_snapshot_rejects_bad_timing_before_creating():
    captured: list = []
    client = _client(captured)
    agent = client.agents.get(AGENT_ID)
    with pytest.raises(NeevAIError, match="timeout_ms must be a positive number"):
        agent.snapshot(wait_until_ready=True, timeout_ms=0)
    assert [m for m, _, _, _ in captured] == ["GET"]
    client.close()


@pytest.mark.parametrize("status, error", [(409, ConflictError), (425, TooEarlyError)])
def test_agent_fork_and_snapshot_surface_409_and_425(status: int, error: type):
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"code": "agent_not_ready", "message": "not ready"})

    client = NeevAI(
        api_key="k",
        base_url="https://api.example.com",
        org_id="org1",
        project_id="proj1",
        client=httpx.Client(transport=httpx.MockTransport(handle)),
    )
    with pytest.raises(error) as fork_err:
        client.agents.fork(AGENT_ID, "web-fork")
    assert fork_err.value.status_code == status and fork_err.value.code == "agent_not_ready"
    with pytest.raises(error):
        client.agents.create_snapshot(AGENT_ID)
    client.close()


@pytest.mark.asyncio
async def test_async_agent_snapshots_and_fork():
    captured: list = []
    client = _async_client(captured)
    snap = await client.agents.create_snapshot(AGENT_ID, {"name": "before-change"})
    assert snap.status == "Pending"
    assert len(await client.agents.list_snapshots(AGENT_ID, limit=5)) == 1
    assert (await client.agents.fork(AGENT_ID, "web-fork")).id == FORK_ID
    agent = await client.agents.get(AGENT_ID)
    ready = await agent.snapshot(wait_until_ready=True, poll_interval_ms=1)
    assert ready.status == "Ready"
    assert len(await agent.snapshots()) == 1
    forked = await agent.fork("web-fork")
    assert forked is not agent and forked.status == "Provisioning"
    assert [(m, p) for m, p, _, _ in captured] == [
        ("POST", f"{BASE}/snapshots"),
        ("GET", f"{BASE}/snapshots"),
        ("POST", f"{BASE}/fork"),
        ("GET", BASE),
        ("POST", f"{BASE}/snapshots"),
        ("GET", f"{PROJECT}/snapshots/{SNAPSHOT_ID}"),
        ("GET", f"{BASE}/snapshots"),
        ("POST", f"{BASE}/fork"),
    ]
    await client.aclose()
