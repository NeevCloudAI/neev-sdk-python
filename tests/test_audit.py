"""Tests for the sandbox and agent audit trail."""

import httpx
import pytest

from neevai.client import AsyncNeevAI, NeevAI
from neevai.handles.agent import Agent, AsyncAgent
from neevai.handles.sandbox import AsyncSandbox, Sandbox
from neevai.types import AuditTrail

SANDBOX_ID = "00000000-0000-0000-0000-000000000001"
AGENT_ID = "11111111-1111-1111-1111-111111111111"
BACKING_ID = "22222222-2222-2222-2222-222222222222"
BASE = "/api/v1beta1/orgs/org1/projects/proj1"

SANDBOX_DATA = {
    "id": SANDBOX_ID,
    "org_id": "org1",
    "project_id": "proj1",
    "name": "s1",
    "region": "as-south-1",
    "image": "ubuntu:24.04",
    "phase": "Ready",
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}
AGENT_DATA = {
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
}


def _event(uid: str, operation: str, status_id: int, actor: dict, **extra) -> dict:
    status = "Success" if status_id == 1 else "Failure"
    return {
        "class_uid": 6003,
        "class_name": "API Activity",
        "category_uid": 6,
        "category_name": "Application Activity",
        "activity_id": 1,
        "activity_name": "Create",
        "type_uid": 600301,
        "type_name": "API Activity: Create",
        "time": 1767268800000,
        "severity_id": 1,
        "severity": "Informational",
        "status_id": status_id,
        "status": status,
        "actor": actor,
        "api": {"operation": operation, "request": {"uid": f"req-{uid}"}},
        "cloud": {"provider": "NeevCloud", "account": {"uid": "org1"}, "project_uid": "proj1"},
        "src_endpoint": {"name": "unknown"},
        "osint": [],
        "metadata": {
            "version": "1.9.0",
            "product": {"name": "Sandbox Audit", "vendor_name": "NeevCloud"},
            "uid": uid,
        },
        **extra,
    }


TRAIL = {
    "from": "2026-01-01T00:00:00Z",
    "to": "2026-01-02T00:00:00Z",
    "retention_days": 30,
    "window_truncated": False,
    "next_cursor": "c2",
    "data": [
        _event(
            "e1",
            "exec",
            1,
            {
                "user": {
                    "type": "api_key",
                    "type_id": 99,
                    "uid": "key-1",
                    "name": "ci",
                    "credential_uid": "key-1",
                }
            },
            duration=120,
            status_code="ok",
            resources=[{"type": "sandbox", "uid": SANDBOX_ID}, {"type": "process", "name": "psql"}],
        ),
        _event(
            "e2",
            "fs.read",
            2,
            {"user": {"type": "user", "type_id": 1, "uid": "user-1"}, "session": {"uid": "s1"}},
            status_code="permission_denied",
            resources=[{"type": "file", "name": "notes.txt"}],
        ),
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
    assert trail.retention_days == 30
    assert trail.next_cursor == "c2"
    assert [e.metadata.uid for e in trail.data] == ["e1", "e2"]
    first, second = trail.data
    assert first.api.operation == "exec"
    assert first.status == "Success"
    assert first.time == 1767268800000
    assert first.actor.user.type == "api_key"
    assert first.actor.user.name == "ci"
    assert first.actor.user.credential_uid == "key-1"
    assert second.status_code == "permission_denied"
    assert second.actor.user.name is None
    assert second.actor.session is not None and second.actor.session.uid == "s1"
    assert second.resources is not None and second.resources[0].name == "notes.txt"


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
    sb = Sandbox(client.sandboxes, SANDBOX_DATA)
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
    agent = Agent(client.agents, AGENT_DATA)
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


def test_sandboxes_audit_sends_filters():
    captured: list[httpx.Request] = []
    client = NeevAI(
        api_key="k",
        base_url="https://api.example.com",
        org_id="org1",
        project_id="proj1",
        client=httpx.Client(transport=_recorder(captured)),
    )
    client.sandboxes.audit(
        SANDBOX_ID,
        operation=["exec", "pty_command"],
        status="failure",
        actor_type=["user", "api_key"],
        actor_uid="user-1",
        credential_uid="key-1",
    )
    assert dict(captured[0].url.params) == {
        "operation": "exec,pty_command",
        "status": "failure",
        "actor_type": "user,api_key",
        "actor_uid": "user-1",
        "credential_uid": "key-1",
    }
    client.close()


def test_audit_single_string_filter_is_not_split():
    captured: list[httpx.Request] = []
    client = NeevAI(
        api_key="k",
        base_url="https://api.example.com",
        org_id="org1",
        project_id="proj1",
        client=httpx.Client(transport=_recorder(captured)),
    )
    client.agents.audit(AGENT_ID, operation="exec", actor_type="system")
    assert dict(captured[0].url.params) == {"operation": "exec", "actor_type": "system"}
    client.close()


@pytest.mark.asyncio
async def test_async_handles_pass_filters():
    captured: list[httpx.Request] = []
    client = AsyncNeevAI(
        api_key="k",
        base_url="https://api.example.com",
        org_id="org1",
        project_id="proj1",
        client=httpx.AsyncClient(transport=_recorder(captured)),
    )
    sb = AsyncSandbox(client.sandboxes, SANDBOX_DATA)
    agent = AsyncAgent(client.agents, AGENT_DATA)
    _assert_trail(await sb.audit(status="success"))
    _assert_trail(await agent.audit(credential_uid="key-1"))
    assert dict(captured[0].url.params) == {"status": "success"}
    assert dict(captured[1].url.params) == {"credential_uid": "key-1"}
    await client.aclose()
