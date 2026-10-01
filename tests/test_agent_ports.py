"""Tests for agent preview ports, keepalive, rollback and the idle window."""

import json

import httpx
import pytest

from neevai.client import AsyncNeevAI, NeevAI
from neevai.errors import NeevAIError

AGENT_ID = "11111111-1111-1111-1111-111111111111"
SNAPSHOT_ID = "33333333-3333-3333-3333-333333333333"
BASE = f"/api/v1beta1/orgs/org1/projects/proj1/agents/{AGENT_ID}"

AGENT = {
    "id": AGENT_ID,
    "org_id": "org1",
    "project_id": "proj1",
    "name": "web",
    "agent_template_id": "ag-claude-code",
    "drive_mode": "http",
    "sandbox_id": "22222222-2222-2222-2222-222222222222",
    "status": "Ready",
    "idle_timeout_seconds": 900,
    "metrics_url": "https://metrics.example/agents/1",
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}
PORT = {
    "port": 3000,
    "slug": "abcd1234",
    "preview_url": "https://3000-abcd1234.preview.example.com",
}


def _handler(captured: list[tuple[str, str, dict | None]]):
    """Records (method, path, json body) and answers each agent route with a canned body."""

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        captured.append((request.method, request.url.path, body))
        path = request.url.path
        if path.endswith("/ports") and request.method == "GET":
            return httpx.Response(200, json={"ports": [PORT]})
        if path.endswith("/ports"):
            return httpx.Response(200, json=PORT)
        if "/ports/" in path:
            return httpx.Response(204)
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


def test_agents_expose_port_with_and_without_slug():
    captured: list = []
    client = _client(captured)
    port = client.agents.expose_port(AGENT_ID, 3000, slug="abcd1234")
    assert port.slug == "abcd1234"
    client.agents.expose_port(AGENT_ID, 3000)
    assert captured == [
        ("POST", f"{BASE}/ports", {"port": 3000, "slug": "abcd1234"}),
        ("POST", f"{BASE}/ports", {"port": 3000}),
    ]
    client.close()


def test_agents_list_and_revoke_port():
    captured: list = []
    client = _client(captured)
    ports = client.agents.list_ports(AGENT_ID)
    assert [p.port for p in ports] == [3000]
    client.agents.revoke_port(AGENT_ID, 3000)
    assert captured == [("GET", f"{BASE}/ports", None), ("DELETE", f"{BASE}/ports/3000", None)]
    client.close()


def test_agent_handle_ports_and_get_url():
    captured: list = []
    client = _client(captured)
    agent = client.agents.get(AGENT_ID)
    assert agent.expose_port(3000, slug="abcd1234").preview_url == PORT["preview_url"]
    assert agent.get_url(3000, wait_until_ready=False, slug="abcd1234") == PORT["preview_url"]
    assert [p.slug for p in agent.list_ports()] == ["abcd1234"]
    agent.revoke_port(3000)
    assert captured[1:] == [
        ("POST", f"{BASE}/ports", {"port": 3000, "slug": "abcd1234"}),
        ("POST", f"{BASE}/ports", {"port": 3000, "slug": "abcd1234"}),
        ("GET", f"{BASE}/ports", None),
        ("DELETE", f"{BASE}/ports/3000", None),
    ]
    client.close()


def test_agent_get_url_waits_until_reachable(monkeypatch):
    probed: list[str] = []
    monkeypatch.setattr(
        "neevai.resources.sandboxes._preview_url_reachable",
        lambda url, timeout_ms: probed.append(url) or True,
    )
    client = _client([])
    assert client.agents.get_port_url(AGENT_ID, 3000) == PORT["preview_url"]
    assert probed == [PORT["preview_url"]]
    client.close()


def test_agent_keepalive_and_rollback():
    captured: list = []
    client = _client(captured)
    agent = client.agents.get(AGENT_ID)
    assert agent.keepalive() is agent
    assert agent.rollback(SNAPSHOT_ID) is agent
    client.agents.keepalive(AGENT_ID)
    client.agents.rollback(AGENT_ID, SNAPSHOT_ID)
    assert captured[1:] == [
        ("POST", f"{BASE}/keepalive", None),
        ("POST", f"{BASE}/rollback", {"snapshot_id": SNAPSHOT_ID}),
        ("POST", f"{BASE}/keepalive", None),
        ("POST", f"{BASE}/rollback", {"snapshot_id": SNAPSHOT_ID}),
    ]
    client.close()


def test_agent_idle_timeout_seconds_property():
    client = _client([])
    assert client.agents.get(AGENT_ID).idle_timeout_seconds == 900
    client.close()


def test_agents_create_passes_idle_timeout_seconds():
    captured: list = []
    client = _client(captured)
    client.agents.create(
        {"name": "web", "agent_template": "claude-code", "idle_timeout_seconds": 0}
    )
    assert captured[0][2] == {
        "name": "web",
        "agent_template": "claude-code",
        "idle_timeout_seconds": 0,
    }
    client.close()


def test_agents_update_idle_window_and_egress_edits():
    captured: list = []
    client = _client(captured)
    client.agents.update(AGENT_ID, {"idle_timeout_seconds": 600})
    client.agents.update(
        AGENT_ID,
        {
            "egress_add": {"allow": [{"host": "api.github.com", "ports": [443]}]},
            "egress_remove": {"allow": [{"host": "old.example.com"}]},
        },
    )
    assert captured == [
        ("PATCH", BASE, {"idle_timeout_seconds": 600}),
        (
            "PATCH",
            BASE,
            {
                "egress_add": {"allow": [{"host": "api.github.com", "ports": [443]}]},
                "egress_remove": {"allow": [{"host": "old.example.com"}]},
            },
        ),
    ]
    client.close()


@pytest.mark.parametrize(
    "params, kwargs",
    [
        ({"egress": {"mode": "deny_all"}, "egress_add": {"allow": [{"host": "a.com"}]}}, {}),
        ({"egress_remove": {"allow": [{"host": "a.com"}]}}, {"allow_egress": ["b.com"]}),
    ],
)
def test_agents_update_rejects_full_egress_with_edits(params, kwargs):
    captured: list = []
    client = _client(captured)
    with pytest.raises(NeevAIError, match="egress_add"):
        client.agents.update(AGENT_ID, params, **kwargs)
    assert captured == []
    client.close()


def test_agents_update_empty_lists_every_field():
    client = _client([])
    with pytest.raises(NeevAIError, match="idle_timeout_seconds"):
        client.agents.update(AGENT_ID, {})
    client.close()


@pytest.mark.asyncio
async def test_async_agent_ports_keepalive_rollback():
    captured: list = []
    client = _async_client(captured)
    agent = await client.agents.get(AGENT_ID)
    assert (await agent.expose_port(3000, slug="abcd1234")).slug == "abcd1234"
    assert await agent.get_url(3000, wait_until_ready=False) == PORT["preview_url"]
    assert [p.port for p in await agent.list_ports()] == [3000]
    await agent.revoke_port(3000)
    assert await agent.keepalive() is agent
    assert await agent.rollback(SNAPSHOT_ID) is agent
    await client.agents.update(AGENT_ID, {"idle_timeout_seconds": 0})
    assert captured[1:] == [
        ("POST", f"{BASE}/ports", {"port": 3000, "slug": "abcd1234"}),
        ("POST", f"{BASE}/ports", {"port": 3000}),
        ("GET", f"{BASE}/ports", None),
        ("DELETE", f"{BASE}/ports/3000", None),
        ("POST", f"{BASE}/keepalive", None),
        ("POST", f"{BASE}/rollback", {"snapshot_id": SNAPSHOT_ID}),
        ("PATCH", BASE, {"idle_timeout_seconds": 0}),
    ]
    await client.aclose()
