# conftest.py
"""Test fixtures for NeevAI Python SDK.
Provides a mock httpx transport that returns deterministic JSON payloads
for control‑plane and data‑plane endpoints. The fixtures are used across
all test modules.
"""

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

# Simple in‑memory store to simulate backend state for sandbox resources
_FAKE_DB: dict[str, Any] = {
    "sandboxes": {},
    "snapshots": {},
    "templates": {
        "sb-ubuntu-26-04-minimal": {
            "id": "sb-ubuntu-26-04-minimal",
            "name": "Ubuntu 26.04 Minimal",
            "description": "Minimal Ubuntu template",
            "category": "standard",
            "status": "active",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    },
    "next_snapshot_id": 1,
    "next_id": 1,
}


def _snapshot_id(n: int) -> str:
    return str(uuid.UUID(int=n + 0x1000))


def _make_snapshot_record(
    *,
    snap_id: str,
    sandbox_id: str,
    org_id: str,
    project_id: str,
    body: dict[str, Any] | None,
    now: str,
) -> dict[str, Any]:
    req = body or {}
    return {
        "id": snap_id,
        "sandbox_id": sandbox_id,
        "org_id": org_id,
        "project_id": project_id,
        "name": req.get("name"),
        "status": "Pending",
        "include_memory": req.get("include_memory", False),
        "source_region": "us-east-1",
        "size_bytes": None,
        "error_message": None,
        "expires_at": None,
        "created_at": now,
        "updated_at": now,
    }


def _sandbox_id(n: int) -> str:
    return str(uuid.UUID(int=n))


def _make_sandbox_record(
    *,
    sid: str,
    org_id: str,
    project_id: str,
    body: dict[str, Any] | None,
    now: str,
) -> dict[str, Any]:
    req = body or {}
    return {
        "id": sid,
        "org_id": org_id,
        "project_id": project_id,
        "name": req.get("name", "test-sandbox"),
        "region": req.get("region", "us-east-1"),
        "image": "ubuntu:22.04",
        "command": None,
        "env": req.get("env"),
        "resources": req.get("resources"),
        "phase": "Pending",
        "connect_url": None,
        "replicas": 0,
        "egress": None,
        "sandbox_template_id": req.get("sandbox_template_id"),
        "created_by": None,
        "created_at": now,
        "updated_at": now,
    }


def _normalize_control_path(path: str) -> str:
    """Strip /agent prefix when base_url is https://.../agent (DEFAULT_BASE_URL)."""
    if path.startswith("/agent/"):
        return path[len("/agent") :]
    return path


def _control_response(
    method: str, path: str, query: dict[str, Any] | None, body: Any
) -> httpx.Response:
    """Return a mocked control‑plane response.
    Only a subset of endpoints required for the test suite are handled.
    """
    path = _normalize_control_path(path)

    def json_resp(
        status: int, data: Any = None, headers: dict[str, str] | None = None
    ) -> httpx.Response:
        content = b"" if data is None else json.dumps(data).encode()
        return httpx.Response(status_code=status, content=content, headers=headers or {})

    # ---- Real API paths: /api/v1beta1/orgs/{org}/projects/{proj}/sandboxes[...] --
    m = re.match(
        r"^/api/v1beta1/orgs/([^/]+)/projects/([^/]+)/sandboxes"
        r"(?:/([^/]+))?(?:/([^/]+))?$",
        path,
    )
    if m:
        org_id = m.group(1)
        project_id = m.group(2)
        sandbox_id = m.group(3)
        action = m.group(4)

        if sandbox_id is None:
            # ---- Collection endpoints ------------------------------------------------
            if method == "GET":
                items = list(_FAKE_DB["sandboxes"].values())
                return json_resp(
                    200,
                    {
                        "items": items,
                        "total": len(items),
                        "page": 1,
                        "limit": 100,
                    },
                )
            if method == "POST":
                now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                sid = _sandbox_id(_FAKE_DB["next_id"])
                _FAKE_DB["next_id"] += 1
                sandbox = _make_sandbox_record(
                    sid=sid,
                    org_id=org_id,
                    project_id=project_id,
                    body=body,
                    now=now,
                )
                _FAKE_DB["sandboxes"][sid] = sandbox
                return json_resp(201, sandbox)
            return json_resp(400, {"message": "bad request"})

        # ---- Individual sandbox ---------------------------------------------------
        sandbox = _FAKE_DB["sandboxes"].get(sandbox_id)
        if not sandbox:
            return json_resp(404, {"message": "not found"})

        if action is None:
            if method == "GET":
                return json_resp(200, sandbox)
            if method == "DELETE":
                del _FAKE_DB["sandboxes"][sandbox_id]
                return json_resp(204)
            if method == "PATCH":
                if isinstance(body, dict):
                    sandbox.update(body)
                    return json_resp(200, sandbox)
            return json_resp(400, {"message": "bad request"})

        if action == "pause":
            sandbox["phase"] = "Paused"
            sandbox["replicas"] = 0
            return json_resp(200, sandbox)
        if action == "resume":
            sandbox["phase"] = "Pending"
            sandbox["replicas"] = 1
            return json_resp(200, sandbox)
        if action == "metrics" and method == "GET":
            return json_resp(
                200,
                {
                    "sandbox_id": sandbox_id,
                    "from": (query or {}).get("from", "2026-01-01T00:00:00Z"),
                    "to": (query or {}).get("to", "2026-01-01T01:00:00Z"),
                    "step": (query or {}).get("step", "1m"),
                    "series": [],
                },
            )

        if action == "snapshots":
            if method == "GET":
                items = [
                    snap
                    for snap in _FAKE_DB["snapshots"].values()
                    if snap["sandbox_id"] == sandbox_id
                ]
                return json_resp(
                    200,
                    {
                        "items": items,
                        "total": len(items),
                        "page": int((query or {}).get("page", 1)),
                        "limit": int((query or {}).get("limit", 100)),
                    },
                )
            if method == "POST":
                now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                snap_id = _snapshot_id(_FAKE_DB["next_snapshot_id"])
                _FAKE_DB["next_snapshot_id"] += 1
                snapshot = _make_snapshot_record(
                    snap_id=snap_id,
                    sandbox_id=sandbox_id,
                    org_id=org_id,
                    project_id=project_id,
                    body=body,
                    now=now,
                )
                _FAKE_DB["snapshots"][snap_id] = snapshot
                return json_resp(202, snapshot)

        if action == "restore" and method == "POST":
            sandbox["phase"] = "Pending"
            sandbox["replicas"] = 1
            return json_resp(200, sandbox)

        if action == "fork" and method == "POST":
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            fork_id = _sandbox_id(_FAKE_DB["next_id"])
            _FAKE_DB["next_id"] += 1
            fork_body = body if isinstance(body, dict) else {}
            forked = _make_sandbox_record(
                sid=fork_id,
                org_id=org_id,
                project_id=project_id,
                body=fork_body,
                now=now,
            )
            forked["phase"] = "Pending"
            forked["replicas"] = 1
            _FAKE_DB["sandboxes"][fork_id] = forked
            return json_resp(201, forked)

        return json_resp(400, {"message": "bad request"})

    # ---- Project-scoped snapshots ---------------------------------------------
    m_snapshot = re.match(
        r"^/api/v1beta1/orgs/([^/]+)/projects/([^/]+)/snapshots/([^/]+)$",
        path,
    )
    if m_snapshot:
        snapshot_id = m_snapshot.group(3)
        snapshot = _FAKE_DB["snapshots"].get(snapshot_id)
        if not snapshot:
            return json_resp(404, {"message": "not found"})
        if method == "GET":
            return json_resp(200, snapshot)
        if method == "DELETE":
            del _FAKE_DB["snapshots"][snapshot_id]
            return json_resp(204)
        return json_resp(400, {"message": "bad request"})

    # ---- Sandbox templates ----------------------------------------------------
    if path == "/api/v1beta1/sandbox-templates" and method == "GET":
        items = list(_FAKE_DB["templates"].values())
        return json_resp(
            200,
            {
                "items": items,
                "total": len(items),
                "page": int((query or {}).get("page", 1)),
                "limit": int((query or {}).get("limit", 20)),
            },
        )

    m_template = re.match(r"^/api/v1beta1/sandbox-templates/([^/]+)$", path)
    if m_template and method == "GET":
        template_id = m_template.group(1)
        template = _FAKE_DB["templates"].get(template_id)
        if not template:
            return json_resp(404, {"message": "not found"})
        return json_resp(200, template)

    if path == "/api/v1beta1/sandbox-templates" and method == "GET":
        return json_resp(
            200,
            {
                "items": [
                    {
                        "id": "sb-ubuntu-26-04-minimal",
                        "name": "Ubuntu 26.04 Minimal",
                        "description": "Minimal Ubuntu template",
                        "category": "standard",
                        "status": "active",
                        "created_at": "2026-01-01T00:00:00Z",
                        "updated_at": "2026-01-01T00:00:00Z",
                    }
                ],
                "total": 1,
                "page": 1,
                "limit": 20,
            },
        )

    if path.startswith("/api/v1beta1/sandbox-templates/"):
        template_id = path.rsplit("/", 1)[-1]
        if method == "GET":
            return json_resp(
                200,
                {
                    "id": template_id,
                    "name": "Ubuntu 26.04 Minimal",
                    "description": "Minimal Ubuntu template",
                    "category": "standard",
                    "status": "active",
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                },
            )
        return json_resp(400, {"message": "bad request"})

    # ---- Fallback: simple /v1/sandboxes paths (backward compat) -----------------
    if path == "/v1/sandboxes" and method == "GET":
        items = list(_FAKE_DB["sandboxes"].values())
        return json_resp(200, {"items": items})

    if path == "/v1/sandboxes" and method == "POST":
        sid = _sandbox_id(_FAKE_DB["next_id"])
        _FAKE_DB["next_id"] += 1
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        sandbox = _make_sandbox_record(
            sid=sid,
            org_id="",
            project_id="",
            body=body,
            now=now,
        )
        _FAKE_DB["sandboxes"][sid] = sandbox
        return json_resp(201, sandbox)

    if path.startswith("/v1/sandboxes/"):
        sid = path.split("/")[-1]
        sandbox = _FAKE_DB["sandboxes"].get(sid)
        if not sandbox:
            return json_resp(404, {"message": "not found"})
        if method == "GET":
            return json_resp(200, sandbox)
        if method == "DELETE":
            del _FAKE_DB["sandboxes"][sid]
            return json_resp(204)
        if method == "PATCH":
            if isinstance(body, dict):
                sandbox.update(body)
                return json_resp(200, sandbox)
        return json_resp(400, {"message": "bad request"})

    return json_resp(404, {"message": "unknown endpoint"})


def _dataplane_response(
    method: str, path: str, query: dict[str, Any] | None, body: Any
) -> httpx.Response:
    """Mock data‑plane (sandboxd) responses.
    Only the minimal subset needed for the current tests is implemented.
    """

    def json_resp(status: int, data: Any = None) -> httpx.Response:
        content = b"" if data is None else json.dumps(data).encode()
        return httpx.Response(status_code=status, content=content)

    # Exec endpoint – returns a streamed NDJSON payload with a single result
    if path.endswith("/exec") and method == "POST":
        # In a real service this would be a streaming response. For simplicity we return a
        # single JSON object that mimics the final decoded output.
        payload = {"status": "ok", "output": "hello world"}
        return json_resp(200, payload)

    # Files endpoint – placeholder returning empty list
    if path.endswith("/files") and method == "GET":
        return json_resp(200, {"files": []})

    return json_resp(404, {"message": "unknown dataplane endpoint"})


class MockControlTransport(httpx.MockTransport):
    """httpx.MockTransport that routes requests to our simple control handler."""

    def __init__(self):
        super().__init__(self.handler)

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        return _control_response(
            method=request.method,
            path=request.url.path,
            query=dict(request.url.params),
            body=body,
        )


class MockDataPlaneTransport(httpx.MockTransport):
    """httpx.MockTransport for the sandboxd (data‑plane) API."""

    def __init__(self):
        super().__init__(self.handler)

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        return _dataplane_response(
            method=request.method,
            path=request.url.path,
            query=dict(request.url.params),
            body=body,
        )


@pytest.fixture
def control_transport() -> httpx.Client:
    """Provides a fresh mock control‑plane httpx Client for each test."""
    _FAKE_DB["sandboxes"].clear()
    _FAKE_DB["snapshots"].clear()
    _FAKE_DB["next_id"] = 1
    _FAKE_DB["next_snapshot_id"] = 1
    return httpx.Client(transport=MockControlTransport())


@pytest.fixture
def dataplane_transport() -> httpx.Client:
    """Provides a mock data‑plane httpx Client used by sandboxd tests."""
    return httpx.Client(transport=MockDataPlaneTransport())


@pytest.fixture
def mock_transport() -> httpx.Client:
    """Alias for `control_transport` – a fresh mock control‑plane httpx Client per test."""
    _FAKE_DB["sandboxes"].clear()
    _FAKE_DB["snapshots"].clear()
    _FAKE_DB["next_id"] = 1
    _FAKE_DB["next_snapshot_id"] = 1
    return httpx.Client(transport=MockControlTransport())
