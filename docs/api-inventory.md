# NeevAI Python SDK — API Inventory

Complete, hand-maintained inventory of the public `neevai` package: per-method
reference, type field tables, symbol index, and contract notes. Use this document
when you need exhaustive detail on the entire SDK surface.

For installation, credentials, and first scripts, see
[`getting-started.md`](./getting-started.md). For control-plane vs data-plane API
lists and copy-paste snippets, see [`api-reference.md`](./api-reference.md). For
which examples demonstrate which APIs, see
[`example-coverage.md`](./example-coverage.md).

## Table of contents

- Getting started → [`getting-started.md`](./getting-started.md)
- [Top-level exports](#top-level-exports)
- [Client](#client)
- [Sandboxes resource](#sandboxes-resource)
  - [create](#clientsandboxescreateparams-org_idnone-project_idnone)
  - [list](#clientsandboxeslistpage-none-limit-none-org_idnone-project_idnone)
  - [get](#clientsandboxesgetid-org_idnone-project_idnone)
  - [pause](#clientsandboxespauseid-org_idnone-project_idnone)
  - [resume](#clientsandboxesresumeid-org_idnone-project_idnone)
  - [delete](#clientsandboxesdeleteid-org_idnone-project_idnone)
  - [metrics](#clientsandboxesmetricsid-from_none-to-none-step-none-org_idnone-project_idnone)
- [Templates resource](#templates-resource)
- [Sandbox handle](#sandbox-handle)
- [Exec and streaming](#exec-and-streaming)
- [Files API](#files-api)
- [Data-plane connection](#data-plane-connection)
- [Raw client](#raw-client)
- [Types reference](#types-reference)
- [Errors](#errors)
- [Pagination types](#pagination-types)
- [Sync/async parity](#syncasync-parity)
- [Symbol index by module](#symbol-index-by-module)
- [Contract notes](#contract-notes)
- [Maintaining this inventory](#maintaining-this-inventory)

---

## Top-level exports

Everything in `neevai.__all__`:

| Symbol | Kind | Module |
| ------ | ---- | ------ |
| `NeevAI` | class | `client.py` |
| `AsyncNeevAI` | class | `client.py` |
| `RawClient` | class | `transport/lifecycle.py` |
| `AsyncRawClient` | class | `transport/lifecycle.py` |
| `Sandbox` | class | `handles/sandbox.py` |
| `AsyncSandbox` | class | `handles/sandbox.py` |
| `SandboxConnection` | class | `runtime/sandboxd.py` |
| `AsyncSandboxConnection` | class | `runtime/sandboxd.py` |
| `SandboxFiles` | class | `runtime/sandboxd.py` |
| `AsyncSandboxFiles` | class | `runtime/sandboxd.py` |
| `Scope` | dataclass | `types.py` |
| `NeevAIError` … `InternalServerError` | exceptions | `errors.py` |

Types exported from `neevai.types.__all__`:

| Symbol | Kind | Source |
| ------ | ---- | ------ |
| `CreateSandboxParams` | model alias | `generated/aiagent.py` → `CreateSandboxRequest` |
| `EnvVar` | model | generated |
| `SandboxData` | model alias | generated → `Sandbox` |
| `SandboxListResponse` | model | generated |
| `SandboxTemplate` | model | generated |
| `SandboxTemplateListResponse` | model | generated |
| `SandboxMetricsResponse` | model | generated |
| `MetricSeries` | model | generated |
| `SandboxPhase` | type alias | `Literal["Pending", "Ready", "NotReady", "Unknown", "Paused"]` |
| `SandboxPhaseEnum` | enum | generated → `SandboxPhase` |
| `Scope` | dataclass | `types.py` |
| `FileEntry` | model | `types.py` |
| `ExecResult` | model | `types.py` |
| `ExecStreamEvent` | type alias | union of stream TypedDicts |
| `StdoutStreamEvent` | TypedDict | `types.py` |
| `StderrStreamEvent` | TypedDict | `types.py` |
| `ExitStreamEvent` | TypedDict | `types.py` |

---

## Client

### `NeevAI(...)`

Synchronous platform client. Exposes three resource namespaces:

- `client.sandboxes` — CRUD and metrics for sandboxes in a project
- `client.templates` — read-only template catalogue
- `client.raw` — untyped control-plane HTTP escape hatch

**Parameters:**

| Name | Type | Default | Description |
| ---- | ---- | ------- | ----------- |
| `api_key` | `str \| None` | `NEEVCLOUD_API_KEY` | Bearer token |
| `org_id` | `str \| None` | `NEEVCLOUD_ORG_ID` | Default org scope |
| `project_id` | `str \| None` | `NEEVCLOUD_PROJECT_ID` | Default project scope |
| `region` | `str \| None` | `NEEVCLOUD_REGION` | Default region for create |
| `base_url` | `str \| None` | production gateway | Control-plane URL |
| `timeout_ms` | `int` | `60000` | Per-request timeout |
| `max_retries` | `int` | `2` | Retries on network / 429 / 5xx |
| `client` | `httpx.Client \| None` | new client | Inject custom HTTP client |

**Raises:** `NeevAIError` if `api_key` is missing.

Use as a context manager to ensure the HTTP transport is closed:

```python
with NeevAI(api_key="...", org_id="...", project_id="...", region="...") as client:
    sandbox = client.sandboxes.create({...})
```

### `NeevAI.close()`

Closes the underlying HTTP transport. Called automatically when exiting a `with`
block.

### `AsyncNeevAI(...)` / `AsyncNeevAI.aclose()`

Async variant with identical constructor parameters and resource layout. Use
`async with AsyncNeevAI() as client:` and `await client.aclose()` when not using a
context manager.

---

## Sandboxes resource

Access via `client.sandboxes` (`Sandboxes`) or `await client.sandboxes` on
`AsyncNeevAI` (`AsyncSandboxes`). Unless noted, async variants use `await` with
identical parameters; return types use `AsyncSandbox` / `AsyncSandboxPage` instead
of their sync counterparts.

All sandbox resource methods require a resolved org/project scope. Missing scope
raises `NeevAIError` before any HTTP request is sent.

### `client.sandboxes.create(params, org_id=None, project_id=None)`

Creates a new sandbox in the resolved project context.

**Parameters:**

| Name | Type | Description |
| ---- | ---- | ----------- |
| `params` | `CreateSandboxParams \| Mapping[str, Any]` | Create body; `region` defaults from client if omitted |
| `org_id` | `str \| None` | Override org (else client default) |
| `project_id` | `str \| None` | Override project (else client default) |

**Returns:** `Sandbox` handle with initial control-plane state (`phase` is typically
`Pending` immediately after create).

**Raises:** `NeevAIError` (missing scope/region), `BadRequestError`,
`AuthenticationError`, `PermissionDeniedError`, `ConflictError`, `RateLimitError`,
`InternalServerError`, etc.

```python
sandbox = client.sandboxes.create({
    "name": "my-agent",
    "sandbox_template_id": "tmpl-abc123",
    "region": "as-south-1",
    "env": [{"name": "LOG_LEVEL", "value": "debug"}],
})
sandbox.wait_until_ready()
```

**Async:** `sandbox = await client.sandboxes.create(...)`

**Example:** [`sandbox_lifecycle.py`](../examples/sandbox_lifecycle.py)

### `client.sandboxes.list(page=None, limit=None, org_id=None, project_id=None)`

Lists sandboxes with server-side pagination.

**Returns:** `SandboxPage` with fields `items`, `total`, `page`, `limit`. Each item
is a `Sandbox` handle bound to the client.

```python
page = client.sandboxes.list(page=1, limit=20)
for sb in page.items:
    print(sb.id, sb.name, sb.phase, sb.replicas)
print(f"Showing {len(page.items)} of {page.total}")
```

**Example:** [`sandbox_lifecycle_controller.py`](../examples/sandbox_lifecycle_controller.py)

### `client.sandboxes.get(id, org_id=None, project_id=None)`

Fetches a single sandbox by UUID.

**Returns:** `Sandbox` handle.

**Raises:** `NotFoundError` if the sandbox does not exist.

```python
sandbox = client.sandboxes.get("550e8400-e29b-41d4-a716-446655440000")
print(sandbox.phase, sandbox.connect_url)
```

### `client.sandboxes.pause(id, org_id=None, project_id=None)`

Scales the sandbox to 0 replicas. Control-plane phase becomes `Paused`.

**Returns:** Updated `Sandbox` handle (not `None`).

```python
paused = client.sandboxes.pause(sandbox.id)
assert paused.phase == "Paused"
assert paused.replicas == 0
```

A paused sandbox will not become `Ready` until `resume()` is called. Calling
`wait_until_ready()` on a paused handle raises `NeevAIError`.

### `client.sandboxes.resume(id, org_id=None, project_id=None)`

Scales the sandbox back to 1 replica, moving it toward `Ready`.

**Returns:** Updated `Sandbox` handle (not `None`).

```python
resumed = client.sandboxes.resume(sandbox.id)
resumed.wait_until_ready()
```

**Examples:** [`sandbox_lifecycle.py`](../examples/sandbox_lifecycle.py),
[`sandbox_lifecycle_controller.py`](../examples/sandbox_lifecycle_controller.py)

### `client.sandboxes.delete(id, org_id=None, project_id=None)`

Permanently deletes a sandbox. Returns `None`.

```python
client.sandboxes.delete(sandbox.id)
# or via handle:
sandbox.delete()
```

### `client.sandboxes.metrics(id, from_=None, to=None, step=None, org_id=None, project_id=None)`

Queries live health metrics for a sandbox over a time range.

**Returns:** `SandboxMetricsResponse` with `series: list[MetricSeries]`.

```python
metrics = client.sandboxes.metrics(
    sandbox.id,
    from_="2026-06-01T00:00:00Z",
    to="2026-06-01T01:00:00Z",
    step="1m",
)
for series in metrics.series:
    print(series.metric, series.unit, len(series.points))
```

**Example:** [`sandbox_metrics.py`](../examples/sandbox_metrics.py)

---

## Templates resource

Access via `client.templates`. Read-only catalogue with no org/project scope.

### `client.templates.list(page=None, limit=None)`

**Returns:** `TemplatePage` with `items: list[SandboxTemplate]`.

```python
page = client.templates.list(limit=10)
for tmpl in page.items:
    print(tmpl.id, tmpl.name, tmpl.category, tmpl.status)
```

**Example:** [`templates_list.py`](../examples/templates_list.py)

### `client.templates.get(template_id)`

**Returns:** `SandboxTemplate`.

**Raises:** `NotFoundError` if the template id is unknown.

```python
tmpl = client.templates.get("tmpl-abc123")
print(tmpl.description)
```

---

## Sandbox handle

Returned by `create()`, `get()`, and `list().items`. Holds mutable in-memory state
mirroring the last control-plane response. Call `refresh()` to sync from the server.

### Properties

| Property | Type | Description |
| -------- | ---- | ----------- |
| `id` | `UUID` | Sandbox identifier |
| `name` | `str` | Human-readable name |
| `phase` | `SandboxPhase` | `"Pending"`, `"Ready"`, `"NotReady"`, `"Unknown"`, or `"Paused"` |
| `replicas` | `int` | `0` or `1` |
| `connect_url` | `str \| None` | Regional data-plane URL (available when ready) |
| `data` | `dict[str, Any]` | Full record snapshot |

### `sandbox.refresh()`

Re-fetches the sandbox from the control plane and updates this handle in place.

**Returns:** `self`.

**Raises:** `NeevAIError` if the handle has no client context.

```python
sandbox.refresh()
print(sandbox.phase, sandbox.replicas)
```

### `sandbox.wait_until_ready(timeout_ms=120000, poll_interval_ms=2000, on_poll=None)`

Polls `refresh()` until `phase == "Ready"`.

**Raises:**

- `NeevAIError` on timeout
- `NeevAIError` if sandbox is `Paused` (call `resume()` first)

Optional `on_poll` callback receives the handle on each poll iteration — useful for
progress logging:

```python
def log_progress(sb: Sandbox) -> None:
    print(f"  polling… phase={sb.phase}")

sandbox.wait_until_ready(on_poll=log_progress)
```

### `sandbox.pause()` / `sandbox.resume()` / `sandbox.delete()`

Convenience wrappers that delegate to `client.sandboxes` and update handle state in
place (except `delete`, which removes the remote resource).

Both `pause()` and `resume()` return the updated `Sandbox` handle:

```python
sandbox = sandbox.pause()   # phase → Paused, replicas → 0
sandbox = sandbox.resume()  # scales back, then wait for Ready
sandbox.wait_until_ready()
```

### `sandbox.metrics(from_=None, to=None, step=None)`

Same as `client.sandboxes.metrics(self.id, ...)` using the handle's scope.

### `sandbox.to_json()`

Returns the raw API record as a JSON-compatible `dict` suitable for
`json.dumps(sandbox.to_json())`.

---

## Exec and streaming

Data-plane command execution requires the sandbox to be `Ready` with a populated
`connect_url`. Most callers use `sandbox.exec` / `sandbox.exec_stream` rather than
constructing `SandboxConnection` directly.

### `sandbox.exec(command, args=None, cwd=None, env=None, timeout_ms=None, stdin=None)`

Runs a command and buffers stdout/stderr until completion.

| Parameter | Description |
| --------- | ----------- |
| `command` | Shell string or argv list (`["ls", "-la"]`) |
| `args` | Extra argv when `command` is a string (mutually exclusive with list `command`) |
| `cwd` | Working directory (workspace-relative) |
| `env` | `dict[str, str]` merged into environment |
| `timeout_ms` | Command timeout |
| `stdin` | Optional stdin text |

**Returns:** `ExecResult` with `stdout`, `stderr`, `exit_code`.

```python
# argv form (preferred)
result = sandbox.exec(["python3", "-c", "import sys; print(sys.version)"])

# string + args form
result = sandbox.exec("echo", args=["hello", "world"])

# with environment and working directory
result = sandbox.exec(
    ["sh", "-c", "echo $MY_VAR > out.txt && cat out.txt"],
    cwd="workspace",
    env={"MY_VAR": "test-value"},
    timeout_ms=30_000,
)

if result.exit_code != 0:
    print(f"Command failed: {result.stderr}")
else:
    print(result.stdout)
```

**Async:** `result = await sandbox.exec(...)`

**Example:** [`parallel_fanout.py`](../examples/parallel_fanout.py)

### `sandbox.exec_stream(...)`

Same parameters as `exec`. Yields `ExecStreamEvent` dicts as output arrives.

Event shapes:

| `type` | Fields |
| ------ | ------ |
| `"stdout"` | `data: str` |
| `"stderr"` | `data: str` |
| `"exit"` | `exit_code: int` |

```python
for event in sandbox.exec_stream(
    ["sh", "-c", "for i in 1 2 3; do echo line-$i; sleep 0.5; done"]
):
    if event["type"] == "stdout":
        print(event["data"], end="")
    elif event["type"] == "stderr":
        print(f"[stderr] {event['data']}", end="", file=sys.stderr)
    elif event["type"] == "exit":
        print(f"\nProcess exited with code {event['exit_code']}")
```

Sync: `for event in sandbox.exec_stream(...)`. Async:
`async for event in sandbox.exec_stream(...)`.

**Example:** [`streaming_exec.py`](../examples/streaming_exec.py)

---

## Files API

Access via the `sandbox.files` property (`SandboxFiles` / `AsyncSandboxFiles`).
Paths are **workspace-relative**; absolute paths are rejected by the daemon.

### `sandbox.files.write(path, content, cwd=None)`

Writes string or bytes to a file.

**Returns:** `dict[str, int]` with key `bytes_written`.

```python
info = sandbox.files.write("src/main.py", 'print("hello")\n')
print(f"Wrote {info['bytes_written']} bytes")
```

### `sandbox.files.read(path, cwd=None)` / `read_text(path, cwd=None)`

Read raw bytes or UTF-8 decoded text.

```python
raw = sandbox.files.read("data.bin")
text = sandbox.files.read_text("README.md")
```

### `sandbox.files.list(path, cwd=None, recursive=False, max_count=None)`

**Returns:** `list[FileEntry]` with `name`, `type`, `path`, `size`, `mode`,
`permissions`, `modified_time`, and optional `symlink_target`.

```python
entries = sandbox.files.list(".", recursive=True)
for entry in entries:
    print(f"{entry.type:10} {entry.path} ({entry.size} bytes)")
```

**Examples:** [`files_api.py`](../examples/files_api.py),
[`workflow_examples/repo_analyzer.py`](../examples/workflow_examples/repo_analyzer.py)

---

## Data-plane connection

Low-level connection to the regional sandbox daemon. Constructed internally by
`sandbox.exec` and `sandbox.files`; exposed for advanced use cases.

### `SandboxConnection(connect_url, api_key, timeout_ms=60000, client=None)`

| Method | Returns | Description |
| ------ | ------- | ----------- |
| `exec(...)` | `ExecResult` | Same signature as `sandbox.exec` |
| `exec_stream(...)` | `Iterator[ExecStreamEvent]` | Streaming variant |
| `close()` | `None` | Release HTTP transport |

Async mirror: `AsyncSandboxConnection` with `aclose()` instead of `close()`.

```python
from neevai import SandboxConnection

conn = SandboxConnection(sandbox.connect_url, api_key="...")
try:
    result = conn.exec(["uname", "-a"])
    print(result.stdout)
finally:
    conn.close()
```

---

## Raw client

Untyped escape hatch over the control-plane transport. Same auth, timeout, retry,
and error mapping as typed resources.

### `client.raw.request(method, path, query=None, body=None)`

**Returns:** Parsed JSON (`dict` / `list`) or `None` for HTTP 204.

```python
# List templates via raw HTTP
data = client.raw.request(
    "GET",
    "/api/v1beta1/sandbox-templates",
    query={"limit": 5, "page": 1},
)
for item in data["items"]:
    print(item["name"], item["id"])

# Create with explicit body (prefer typed client.sandboxes.create instead)
body = {
    "name": "raw-demo",
    "sandbox_template_id": template_id,
    "region": "as-south-1",
}
created = client.raw.request(
    "POST",
    f"/api/v1beta1/orgs/{org_id}/projects/{project_id}/sandboxes",
    body=body,
)
```

**Async:** `data = await client.raw.request(...)`

**Example:** [`raw_request.py`](../examples/raw_request.py)

---

## Types reference

Import from `neevai.types`. Control-plane models are generated from
`specs/aiagent.yaml` (regenerate with `scripts/gen_types.py`). After spec changes,
manually verify field tables here and in [`api-reference.md`](./api-reference.md).

### `CreateSandboxParams`

Alias for generated `CreateSandboxRequest`.

| Field | Type | Required |
| ----- | ---- | -------- |
| `name` | `str` | yes |
| `sandbox_template_id` | `str` | yes |
| `region` | `str` | yes (auto-filled from client if omitted at API boundary) |
| `namespace` | `str \| None` | no |
| `image` | `str \| None` | no |
| `command` | `list[str] \| None` | no |
| `env` | `list[EnvVar] \| None` | no |

### `EnvVar`

| Field | Type | Required |
| ----- | ---- | -------- |
| `name` | `str` | yes |
| `value` | `str` | yes |

### `SandboxData`

Full control-plane sandbox record (alias for generated `Sandbox`).

| Field | Type | Required |
| ----- | ---- | -------- |
| `id` | `UUID` | yes |
| `org_id` | `str` | yes |
| `project_id` | `str` | yes |
| `name` | `str` | yes |
| `namespace` | `str \| None` | no |
| `region` | `str` | yes |
| `image` | `str` | yes |
| `command` | `list[str] \| None` | no |
| `env` | `list[EnvVar] \| None` | no |
| `phase` | `SandboxPhaseEnum` | yes |
| `fqdn` | `str \| None` | no |
| `connect_url` | `str \| None` | no |
| `replicas` | `int` (0–1) | yes |
| `k8s_uid` | `str \| None` | no |
| `created_at` | `datetime` | yes |
| `updated_at` | `datetime` | yes |

On handles, `sandbox.phase` returns the string literal (`SandboxPhase`), not the enum.

### `SandboxTemplate`

| Field | Type | Required |
| ----- | ---- | -------- |
| `id` | `str` | yes |
| `name` | `str` | yes |
| `description` | `str` | yes |
| `category` | enum | yes |
| `status` | enum | yes |
| `created_at` | `datetime` | yes |
| `updated_at` | `datetime` | yes |

### `SandboxListResponse` / `SandboxTemplateListResponse`

| Field | Type |
| ----- | ---- |
| `items` | list |
| `total` | `int` |
| `page` | `int` |
| `limit` | `int` |

### `SandboxMetricsResponse`

| Field | Type | Required |
| ----- | ---- | -------- |
| `sandbox_id` | `UUID` | yes |
| `from_` | `datetime` | yes (JSON key `from`) |
| `to` | `datetime` | yes |
| `step` | `str` | yes |
| `series` | `list[MetricSeries]` | yes |

### `MetricSeries`

| Field | Type | Required |
| ----- | ---- | -------- |
| `metric` | `str` | yes |
| `unit` | `str \| None` | no |
| `points` | `list[list[float]]` | yes |

### `Scope`

| Field | Type |
| ----- | ---- |
| `org_id` | `str` |
| `project_id` | `str` |

### `SandboxPhase`

Type alias: `Literal["Pending", "Ready", "NotReady", "Unknown", "Paused"]`.

### `FileEntry`

| Field | Type | Required |
| ----- | ---- | -------- |
| `name` | `str` | yes |
| `type` | `"file" \| "directory" \| "symlink"` | yes |
| `path` | `str` | yes |
| `size` | `int` | yes |
| `mode` | `int` | yes |
| `permissions` | `str` | yes |
| `modified_time` | `str` | yes |
| `symlink_target` | `str \| None` | no |

### `ExecResult`

| Field | Type |
| ----- | ---- |
| `stdout` | `str` |
| `stderr` | `str` |
| `exit_code` | `int` |

### Stream events

| Type | Fields |
| ---- | ------ |
| `StdoutStreamEvent` | `type: "stdout"`, `data: str` |
| `StderrStreamEvent` | `type: "stderr"`, `data: str` |
| `ExitStreamEvent` | `type: "exit"`, `exit_code: int` |

`ExecStreamEvent = StdoutStreamEvent | StderrStreamEvent | ExitStreamEvent`

---

## Errors

All SDK errors inherit from `NeevAIError`. Import from `neevai` or `neevai.errors`.

| Class | When raised |
| ----- | ----------- |
| `APIConnectionError` | DNS, connection reset, unreachable host |
| `APITimeoutError` | Request exceeded `timeout_ms` (subclass of `APIConnectionError`) |
| `APIError` | Any non-2xx HTTP response |
| `BadRequestError` | HTTP 400 |
| `AuthenticationError` | HTTP 401 |
| `PermissionDeniedError` | HTTP 403 |
| `NotFoundError` | HTTP 404 |
| `ConflictError` | HTTP 409 |
| `PreconditionFailedError` | HTTP 412 |
| `RateLimitError` | HTTP 429 |
| `DeadlineExceededError` | HTTP 504 |
| `InternalServerError` | HTTP 5xx |

`APIError` attributes: `status_code`, `body`, `code`, `details`, `request_id`,
`request_method`, `request_url`.

Data-plane exec errors are mapped to the same hierarchy via gRPC-style reason codes.

```python
from neevai import NeevAI
from neevai.errors import NeevAIError, NotFoundError, AuthenticationError

try:
    with NeevAI() as client:
        client.sandboxes.get("00000000-0000-0000-0000-000000000000")
except NotFoundError as e:
    print(f"404 — code={e.code}, request_id={e.request_id}")
except AuthenticationError:
    print("Check NEEVCLOUD_API_KEY")
except NeevAIError as e:
    print(f"SDK error: {e}")
```

---

## Pagination types

Returned from `list()` methods; not exported at package root.

### `SandboxPage` / `AsyncSandboxPage`

| Field | Type |
| ----- | ---- |
| `items` | `list[Sandbox]` or `list[AsyncSandbox]` |
| `total` | `int` |
| `page` | `int` |
| `limit` | `int` |

### `TemplatePage` / `AsyncTemplatePage`

| Field | Type |
| ----- | ---- |
| `items` | `list[SandboxTemplate]` |
| `total` | `int` |
| `page` | `int` |
| `limit` | `int` |

---

## Sync/async parity

Every sync public API has an async equivalent with matching semantics.

| Sync | Async | Notes |
| ---- | ----- | ----- |
| `NeevAI` | `AsyncNeevAI` | |
| `NeevAI.close()` | `AsyncNeevAI.aclose()` | Naming differs by convention |
| `Sandboxes.*` | `AsyncSandboxes.*` | Add `await` |
| `Templates.*` | `AsyncTemplates.*` | Add `await` |
| `Sandbox.*` | `AsyncSandbox.*` | Add `await` on methods |
| `Sandbox.exec_stream` | `AsyncSandbox.exec_stream` | `async for` instead of `for` |
| `SandboxConnection.close()` | `AsyncSandboxConnection.aclose()` | Naming differs |
| `SandboxFiles.*` | `AsyncSandboxFiles.*` | Add `await` |
| `RawClient.request` | `AsyncRawClient.request` | Add `await` |

No sync-only or async-only public methods. Pagination types mirror each other
(`SandboxPage` / `AsyncSandboxPage`, `TemplatePage` / `AsyncTemplatePage`).

---

## Symbol index by module

Compact reviewer index. Each symbol should also appear in
[`example-coverage.md`](./example-coverage.md).

### Client (`client.py`)

| Symbol | Kind | Description |
| ------ | ---- | ----------- |
| `NeevAI` | class | Sync platform client; exposes `.sandboxes`, `.templates`, `.raw` |
| `NeevAI.__init__` | method | `api_key`, `org_id`, `project_id`, `region`, `base_url`, `timeout_ms`, `max_retries`, `client` |
| `NeevAI.close` | method | Release HTTP transport |
| `AsyncNeevAI` | class | Async platform client |
| `AsyncNeevAI.aclose` | method | Release async HTTP transport |

### Sandboxes resource (`resources/sandboxes.py`)

| Symbol | Kind | Returns |
| ------ | ---- | ------- |
| `Sandboxes.create` | method | `Sandbox` |
| `Sandboxes.list` | method | `SandboxPage` |
| `Sandboxes.get` | method | `Sandbox` |
| `Sandboxes.pause` | method | `Sandbox` |
| `Sandboxes.resume` | method | `Sandbox` |
| `Sandboxes.delete` | method | `None` |
| `Sandboxes.metrics` | method | `SandboxMetricsResponse` |
| `AsyncSandboxes.*` | methods | Same as sync with `await`; returns `AsyncSandbox` / `AsyncSandboxPage` |

### Templates resource (`resources/templates.py`)

| Symbol | Kind | Returns |
| ------ | ---- | ------- |
| `Templates.list` | method | `TemplatePage` |
| `Templates.get` | method | `SandboxTemplate` |
| `AsyncTemplates.*` | methods | Same as sync with `await` |

### Sandbox handle (`handles/sandbox.py`)

| Symbol | Kind | Notes |
| ------ | ---- | ----- |
| `Sandbox.id`, `.name`, `.phase`, `.replicas`, `.connect_url` | properties | `phase` is `SandboxPhase` string literal |
| `Sandbox.data` | property | `dict[str, Any]` snapshot |
| `Sandbox.to_json` | method | JSON-serializable dict |
| `Sandbox.refresh` | method | Re-fetch from control plane → `Sandbox` |
| `Sandbox.wait_until_ready` | method | Poll until `Ready` |
| `Sandbox.pause` / `.resume` | methods | Return updated `Sandbox` |
| `Sandbox.delete` | method | `None` |
| `Sandbox.metrics` | method | `SandboxMetricsResponse` |
| `Sandbox.exec` | method | `ExecResult` |
| `Sandbox.exec_stream` | method | `Iterator[ExecStreamEvent]` |
| `Sandbox.files` | property | `SandboxFiles` |
| `AsyncSandbox.*` | mirror | Same surface with `await` / `async for` |

### Data-plane (`runtime/sandboxd.py`)

| Symbol | Kind | Notes |
| ------ | ---- | ----- |
| `SandboxConnection.exec` | method | `ExecResult` |
| `SandboxConnection.exec_stream` | method | `Iterator[ExecStreamEvent]` |
| `SandboxConnection.close` | method | `None` |
| `SandboxFiles.write` | method | `dict[str, int]` (`bytes_written`) |
| `SandboxFiles.read` | method | `bytes` |
| `SandboxFiles.read_text` | method | `str` |
| `SandboxFiles.list` | method | `list[FileEntry]` |
| `AsyncSandboxConnection.*` | mirror | `.aclose()` instead of `.close()` |
| `AsyncSandboxFiles.*` | mirror | Add `await` |

### Raw client (`transport/lifecycle.py`)

| Symbol | Kind | Notes |
| ------ | ---- | ----- |
| `RawClient.request` | method | Untyped control-plane HTTP |
| `AsyncRawClient.request` | method | Async variant |

---

## Contract notes

- `ResponseValidationError` in `neevai._parse` is **internal** — not public API.
- `Scope` is exported from both `neevai` and `neevai.types` intentionally.
- Pagination types are public but not in top-level `__all__`.
- Client env vars: `NEEVCLOUD_API_KEY`, `NEEVCLOUD_ORG_ID`, `NEEVCLOUD_PROJECT_ID`,
  `NEEVCLOUD_REGION`, `NEEVCLOUD_BASE_URL` (not `NEEVAI_API_KEY`).
- Sandbox create uses `sandbox_template_id` in params (not `template_id`).
- `Sandbox.pause()` / `.resume()` return updated handles (not `None`).
- `connect_url` is a property on `Sandbox`, not a method.
- File and exec paths are workspace-relative; absolute paths are rejected.

---

## Maintaining this inventory

Update manually when the public API changes. Cross-check against `src/neevai/`.

On API changes, also update:

- [`docs/getting-started.md`](./getting-started.md) — if install, env vars, or quick-start flows change
- [`docs/api-reference.md`](./api-reference.md) — control-plane/data-plane API lists and inline snippet table
- [`docs/example-coverage.md`](./example-coverage.md) — example catalog and API → examples lookup
- [`examples/`](../examples/) — if a new capability lacks an example

After `scripts/gen_types.py`, verify type field tables **here only** match
`src/neevai/generated/`. Type tables live in this inventory, not in
`api-reference.md`.
