"""Tests for the sandbox and agent command audit trail."""

import httpx
import pytest

from neevai.client import AsyncNeevAI, NeevAI
from neevai.handles.agent import Agent
from neevai.handles.sandbox import Sandbox
from neevai.types import AuditTrail

SANDBOX_ID = "00000000-0000-0000-0000-000000000001"
AGENT_ID = "11111111-1111-1111-1111-111111111111"
BACKING_ID = "22222222-2222-2222-2222-222222222222"
BASE = "/api/v1beta1/orgs/org1/projects/proj1"

TRAIL = {
    "sandbox_id": BACKING_ID,
    "from": "2026-01-01T00:00:00Z",
    "to": "2026-01-02T00:00:00Z",
    "retention_days": 30,
    "window_truncated": False,
    "next_cursor": "c2",
    "records": [
        {
            "at": "2026-01-01T12:00:00Z",
            "id": "r1",
            "tool": "pty_command",
            "command": "psql",
            "outcome": "success",
            "reason_code": "ok",
            "caller_source": "api_key",
            "pty_id": "p1",
            "seq": 3,
            "duration_ms": 120,
        },
        {
            "at": "2026-01-01T11:00:00Z",
            "id": "r2",
            "tool": "fs.read",
            "target": "notes.txt",
            "outcome": "error",
            "reason_code": "permission_denied",
        },
    ],
}


def _recorder(captured: list[httpx.Request]) -> httpx.MockTransport:
    """Records each request and answers with the canned audit trail."""

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=TRAIL)

    return httpx.MockTransport(handler)


def _assert_trail(trail: AuditTrail) -> None:
    assert isinstance(trail, AuditTrail)
    assert str(trail.sandbox_id) == BACKING_ID
    assert trail.retention_days == 30
    assert trail.next_cursor == "c2"
    assert [r.id for r in trail.records] == ["r1", "r2"]
    assert trail.records[0].command == "psql"
    assert trail.records[0].outcome.value == "success"
    assert trail.records[1].target == "notes.txt"
    assert trail.records[1].command is None


def test_sandboxes_audit_sends_window_cursor_and_limit():
    captured: list[httpx.Request] = []
    client = NeevAI(
        api_key="k",
        base_url="https://api.example.com",
        org_id="org1",
        project_id="proj1",
        client=httpx.Client(transport=_recorder(captured)),
    )
    trail = client.sandboxes.audit(
        SANDBOX_ID,
        from_="2026-01-01T00:00:00Z",
        to="2026-01-02T00:00:00Z",
        cursor="c1",
        limit=50,
    )
    _assert_trail(trail)
    (req,) = captured
    assert req.method == "GET"
    assert req.url.path == f"{BASE}/sandboxes/{SANDBOX_ID}/audit"
    assert dict(req.url.params) == {
        "from": "2026-01-01T00:00:00Z",
        "to": "2026-01-02T00:00:00Z",
        "cursor": "c1",
        "limit": "50",
    }
    client.close()


def test_sandboxes_audit_omits_unset_query():
    captured: list[httpx.Request] = []
    client = NeevAI(
        api_key="k",
        base_url="https://api.example.com",
        org_id="org1",
        project_id="proj1",
        client=httpx.Client(transport=_recorder(captured)),
    )
    client.sandboxes.audit(SANDBOX_ID)
    assert dict(captured[0].url.params) == {}
    client.close()


def test_sandbox_handle_audit_uses_its_id_and_scope():
    captured: list[httpx.Request] = []
    client = NeevAI(
        api_key="k",
        base_url="https://api.example.com",
        org_id="org1",
        project_id="proj1",
        client=httpx.Client(transport=_recorder(captured)),
    )
    sb = Sandbox(
        client.sandboxes,
        {
            "id": SANDBOX_ID,
            "org_id": "org1",
            "project_id": "proj1",
            "name": "s1",
            "region": "as-south-1",
            "image": "ubuntu:24.04",
            "phase": "Ready",
            "replicas": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )
    _assert_trail(sb.audit(cursor="c2"))
    assert captured[0].url.path == f"{BASE}/sandboxes/{SANDBOX_ID}/audit"
    assert dict(captured[0].url.params) == {"cursor": "c2"}
    client.close()


def test_agents_audit_path_and_query():
    captured: list[httpx.Request] = []
    client = NeevAI(
        api_key="k",
        base_url="https://api.example.com",
        org_id="org1",
        project_id="proj1",
        client=httpx.Client(transport=_recorder(captured)),
    )
    trail = client.agents.audit(AGENT_ID, limit=10)
    _assert_trail(trail)
    (req,) = captured
    assert req.method == "GET"
    assert req.url.path == f"{BASE}/agents/{AGENT_ID}/audit"
    assert dict(req.url.params) == {"limit": "10"}
    client.close()


def test_agent_handle_audit():
    captured: list[httpx.Request] = []
    client = NeevAI(
        api_key="k",
        base_url="https://api.example.com",
        org_id="org1",
        project_id="proj1",
        client=httpx.Client(transport=_recorder(captured)),
    )
    agent = Agent(
        client.agents,
        {
            "id": AGENT_ID,
            "org_id": "org1",
            "project_id": "proj1",
            "name": "web",
            "agent_template_id": "ag-claude-code",
            "drive_mode": "http",
            "sandbox_id": BACKING_ID,
            "status": "Ready",
            "metrics_url": "https://metrics.example/agents/1",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )
    _assert_trail(agent.audit(from_="2026-01-01T00:00:00Z"))
    assert captured[0].url.path == f"{BASE}/agents/{AGENT_ID}/audit"
    assert dict(captured[0].url.params) == {"from": "2026-01-01T00:00:00Z"}
    client.close()


@pytest.mark.asyncio
async def test_async_sandboxes_and_agents_audit():
    captured: list[httpx.Request] = []
    client = AsyncNeevAI(
        api_key="k",
        base_url="https://api.example.com",
        org_id="org1",
        project_id="proj1",
        client=httpx.AsyncClient(transport=_recorder(captured)),
    )
    _assert_trail(await client.sandboxes.audit(SANDBOX_ID, to="2026-01-02T00:00:00Z", limit=5))
    _assert_trail(await client.agents.audit(AGENT_ID, cursor="c1"))
    assert [r.url.path for r in captured] == [
        f"{BASE}/sandboxes/{SANDBOX_ID}/audit",
        f"{BASE}/agents/{AGENT_ID}/audit",
    ]
    assert dict(captured[0].url.params) == {"to": "2026-01-02T00:00:00Z", "limit": "5"}
    assert dict(captured[1].url.params) == {"cursor": "c1"}
    await client.aclose()
