# conftest.py
"""Test fixtures for NeevAI Python SDK.
Provides a mock httpx transport that returns deterministic JSON payloads
for control‑plane and data‑plane endpoints. The fixtures are used across
all test modules.
"""

import json
import re
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

# Simple in‑memory store to simulate backend state for sandbox resources
_FAKE_DB: dict[str, Any] = {
    "sandboxes": {},
    "next_id": 1,
}


def _control_response(
    method: str, path: str, query: dict[str, Any] | None, body: Any
) -> httpx.Response:
    """Return a mocked control‑plane response.
    Only a subset of endpoints required for the test suite are handled.
    """

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
                sid = str(_FAKE_DB["next_id"])
                _FAKE_DB["next_id"] += 1
                sandbox = {
                    "id": sid,
                    "org_id": org_id,
                    "project_id": project_id,
                    "name": (body or {}).get("name", "test-sandbox"),
                    "namespace": (body or {}).get("namespace", "default"),
                    "region": (body or {}).get("region", "us-east-1"),
                    "image": (body or {}).get("image", "ubuntu:22.04"),
                    "command": (body or {}).get("command"),
                    "env": (body or {}).get("env"),
                    "phase": "Pending",
                    "replicas": 0,
                    "created_at": now,
                    "updated_at": now,
                }
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
                    "from": (query or {}).get("from", ""),
                    "to": (query or {}).get("to", ""),
                    "step": (query or {}).get("step", ""),
                    "series": [],
                },
            )

        return json_resp(400, {"message": "bad request"})

    # ---- Fallback: simple /v1/sandboxes paths (backward compat) -----------------
    if path == "/v1/sandboxes" and method == "GET":
        items = list(_FAKE_DB["sandboxes"].values())
        return json_resp(200, {"items": items})

    if path == "/v1/sandboxes" and method == "POST":
        sid = str(_FAKE_DB["next_id"])
        _FAKE_DB["next_id"] += 1
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        sandbox = {
            "id": sid,
            "org_id": "",
            "project_id": "",
            "name": (body or {}).get("name", "test-sandbox"),
            "namespace": "default",
            "region": "us-east-1",
            "image": (body or {}).get("image", "ubuntu:22.04"),
            "phase": "Pending",
            "replicas": 0,
            "created_at": now,
            "updated_at": now,
        }
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
    _FAKE_DB["next_id"] = 1
    return httpx.Client(transport=MockControlTransport())


@pytest.fixture
def dataplane_transport() -> httpx.Client:
    """Provides a mock data‑plane httpx Client used by sandboxd tests."""
    return httpx.Client(transport=MockDataPlaneTransport())


@pytest.fixture
def mock_transport() -> httpx.Client:
    """Alias for `control_transport` – a fresh mock control‑plane httpx Client per test."""
    _FAKE_DB["sandboxes"].clear()
    _FAKE_DB["next_id"] = 1
    return httpx.Client(transport=MockControlTransport())
