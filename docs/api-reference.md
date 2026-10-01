# NeevAI Python SDK — API Reference

Task-oriented API lists and copy-paste snippets for the public `neevai` package.
For method parameters, type field tables, errors, and the symbol index, see
[`api-inventory.md`](./api-inventory.md). For which runnable examples call which
APIs are demonstrated, see [`example-coverage.md`](./example-coverage.md).
For install and first scripts, see [`getting-started.md`](./getting-started.md).

## Table of contents

- [Lifecycle](#lifecycle)
- [Snapshots](#snapshots)
- [Runtime](#runtime)
- [Inline example snippets](#inline-example-snippets)
- [Maintaining this reference](#maintaining-this-reference)

---

## Lifecycle

Lifecycle APIs manage sandboxes, agents, agent templates, and sandbox
templates through the Neev API. All sync symbols have async counterparts
(`AsyncNeevAI`, `AsyncSandboxes`, `AsyncAgents`, etc.) — add `await` and use
`async with` / `aclose()` where noted.

### Client

| API | Sync | Async |
| --- | ---- | ----- |
| Root client | `NeevAI(...)` | `AsyncNeevAI(...)` |
| Close transport | `client.close()` (via `with`) | `await client.aclose()` |

Details: [`api-inventory.md` → Client](./api-inventory.md#client)

### `client.sandboxes`

| Method | Returns | Summary |
| ------ | ------- | ------- |
| `create(params, org_id=None, project_id=None, *, allow_internet=None, allow_egress=None)` | `Sandbox` | Creates a new sandbox. `allow_internet=True` / `allow_egress=[...]` open egress (deny-all by default; explicit `egress` wins). Optional `restore` in params provisions from a snapshot. |
| `list(page=None, limit=None, org_id=None, project_id=None)` | `SandboxPage` | Lists sandboxes with pagination in the resolved org/project scope. |
| `get(id, org_id=None, project_id=None)` | `Sandbox` | Fetches the current record for a sandbox by ID or name. |
| `update(id, params, org_id=None, project_id=None, *, allow_internet=None, allow_egress=None)` | `Sandbox` | In-place update of `resources` (cpu/memory) and/or `egress`. Resize keeps the ID/name/preview URLs and does not restart; `disk_gb` is not resizable and the server rejects a change. `allow_internet` / `allow_egress` are the same egress convenience as `create`. `egress_add` / `egress_remove` edit the allow-list in place (not combinable with `egress`). Rejects `{}` locally, naming every field. |
| `pause(id, org_id=None, project_id=None)` | `Sandbox` | Stops a sandbox and keeps its state (Paused). Sends an empty body; a pause always captures full state, so a resume picks up where it left off. |
| `resume(id, org_id=None, project_id=None)` | `Sandbox` | Starts a paused sandbox again, toward Ready. |
| `keepalive(id, org_id=None, project_id=None)` | `Sandbox` | Resets the sandbox's idle timer (POST `.../keepalive`). |
| `update_timeout(id, params, org_id=None, project_id=None)` | `Sandbox` | Changes idle/lifetime windows (PUT `.../timeout`); only the windows passed change, `0` turns one off. |
| `delete(id, org_id=None, project_id=None)` | `None` | Permanently deletes a sandbox. |
| `metrics(id, from_=None, to=None, step=None, ...)` | `SandboxMetricsResponse` | Queries live health metrics over an optional time range. |
| `audit(id, *, from_=None, to=None, cursor=None, limit=None, ...)` | `AuditTrail` | One page of the command audit trail, newest first; page with `next_cursor`. |
| `expose_port(id, port, ..., *, slug=None)` / `list_ports(id)` / `revoke_port(id, port)` | `SandboxPort` / `list[SandboxPort]` / `None` | Preview ports. A new `slug` on an exposed port rotates its URL. |
| `get_port_url(id, port, wait_until_ready=True, ..., *, slug=None)` | `str` | Exposes a port and returns its preview URL once routable. |
| `create_snapshot(id, params=None, ...)` | `Snapshot` | Creates a filesystem snapshot (returns immediately with status Pending). |
| `list_snapshots(id, page=None, limit=None, ...)` | `list[Snapshot]` | Lists snapshots for a sandbox (unwraps pagination items). |
| `get_snapshot(snapshot_id, ...)` | `Snapshot` | Fetches snapshot metadata by project-scoped ID. |
| `delete_snapshot(snapshot_id, ...)` | `None` | Deletes a snapshot permanently. |
| `rollback(id, snapshot_id, ...)` | `Sandbox` | Rolls a sandbox back in place to a previous snapshot. Prefer `create({..., "restore": ...})` to recover into a new sandbox — see [Snapshots](#snapshots). |
| `fork(id, name, ...)` | `Sandbox` | Forks a sandbox into a new sandbox from its current state. |

### Snapshots

Snapshot workflows capture filesystem state, restore into a new sandbox, or fork
inherited state. Snapshots are asynchronous: `create_snapshot` returns
`status=Pending`; poll `get_snapshot` until `Ready`.

**Recommended restore pattern** — create a new sandbox from a snapshot (does not
mutate the original sandbox):

```python
pending = sandbox.snapshot({"name": "checkpoint"})
# poll until Ready …
restored = client.sandboxes.create({
    "name": "restored",
    "sandbox_template_id": template_id,
    "restore": str(pending.id),
})
restored.wait_until_ready()
```

In-place `sandbox.rollback(snapshot_id)` is also available but can come back with an
empty workspace. See
[`snapshot_fork_restore.py`](../examples/snapshot_fork_restore.py).

### `client.templates`

| Method | Returns | Summary |
| ------ | ------- | ------- |
| `list(page=None, limit=None)` | `TemplatePage` | Lists available sandbox templates with pagination. |
| `get(template_id)` | `SandboxTemplate` | Fetches a single sandbox template by ID. Templates carry an optional display `icon`. |

### `client.agents`

| Method | Returns | Summary |
| ------ | ------- | ------- |
| `create(params, org_id=None, project_id=None, *, allow_internet=None, allow_egress=None)` | `Agent` | Creates an agent from a catalogue template name (`agent_template`). `allow_internet=True` / `allow_egress=[...]` open egress (deny-all by default; explicit `egress` wins). |
| `list(page=None, limit=None, org_id=None, project_id=None)` | `AgentPage` | Lists agents with pagination in the resolved org/project scope. |
| `get(id, org_id=None, project_id=None)` | `Agent` | Fetches the current record for an agent by ID or name. |
| `update(id, params, org_id=None, project_id=None, *, allow_internet=None, allow_egress=None)` | `Agent` | In-place update of egress, cpu/memory (`resources`; defaults & bounds in [Agent resources](./api-inventory.md#agent-resources)) and `idle_timeout_seconds`. `allow_internet` / `allow_egress` are the same egress convenience as `create`; `egress_add` / `egress_remove` edit the allow-list in place. Rejects `{}` locally, naming every field. |
| `keepalive(id, ...)` / `rollback(id, snapshot_id, ...)` | `Agent` | Resets the idle timer / rolls the backing sandbox back to a snapshot. |
| `expose_port` / `list_ports` / `revoke_port` / `get_port_url` | as on `client.sandboxes` | Agent preview ports, same signatures. |
| `audit(id, *, from_=None, to=None, cursor=None, limit=None, ...)` | `AuditTrail` | The agent's command audit trail. |
| `pause(id, org_id=None, project_id=None)` | `Agent` | Pauses the agent and its backing sandbox. |
| `resume(id, org_id=None, project_id=None)` | `Agent` | Resumes a paused agent. |
| `delete(id, org_id=None, project_id=None)` | `None` | Permanently deletes an agent (HTTP 204, no body). |

### `client.agent_templates`

| Method | Returns | Summary |
| ------ | ------- | ------- |
| `list(page=None, limit=None)` | `AgentTemplatePage` | Lists available agent templates (global catalogue, no org scope). |
| `get(template_id)` | `AgentTemplate` | Fetches a single agent template by ID. |

### `client.raw`

| Method | Returns | Summary |
| ------ | ------- | ------- |
| `request(method, path, query=None, body=None)` | JSON dict/list or `None` | Untyped API call; returns parsed JSON or `None` for HTTP 204. |

### Sandbox handle (lifecycle)

Returned by `create()`, `get()`, `list().items`, etc.

| API | Kind |
| --- | ---- |
| `id`, `name`, `phase`, `replicas`, `connect_url`, `addressable`, `last_crash`, `data` | properties |
| `refresh()` | method |
| `update(params, *, allow_internet=None, allow_egress=None)` | method — in-place resize / egress re-scope (`egress_add` / `egress_remove` edit the allow-list); updates state in place |
| `wait_until_ready(timeout_ms=120000, ...)` | method — polls the API until `Ready` and addressable |
| `pause()` / `resume()` | methods |
| `keepalive()` / `update_timeout(params)` | methods — reset idle timer / change lifecycle windows |
| `snapshot(params=None)` / `snapshots()` | methods |
| `rollback(snapshot_id)` / `fork(name)` | methods |
| `delete()` | method |
| `metrics(from_=None, to=None, step=None)` | method |
| `audit(*, from_=None, to=None, cursor=None, limit=None)` | method |
| `expose_port(port, *, slug=None)` / `list_ports()` / `revoke_port(port)` / `get_url(port, ..., *, slug=None)` | methods — preview ports |
| `to_json()` | method |

### Agent handle (lifecycle)

Returned by `client.agents.create()`, `get()`, `list().items`, etc.

| API | Kind |
| --- | ---- |
| `id`, `name`, `status`, `sandbox_id`, `agent_template_id`, `config`, `last_crash`, `idle_timeout_seconds`, `data` | properties |
| `refresh()` / `update(params, *, allow_internet=None, allow_egress=None)` | methods |
| `wait_until_ready(timeout_ms=120000, poll_interval_ms=2000, on_poll=None)` | method — polls until `Ready`; fails fast on `Failed` / `Paused` |
| `pause()` / `resume()` / `delete()` | methods |
| `keepalive()` / `rollback(snapshot_id)` / `audit(...)` | methods |
| `expose_port(port, *, slug=None)` / `list_ports()` / `revoke_port(port)` / `get_url(port, ..., *, slug=None)` | methods — preview ports |
| `sandbox()` | method — backing `Sandbox` handle for runtime `exec`, `files`, and `processes` |
| `to_json()` | method |

---

## Runtime

Sandbox runtime APIs run commands, access files, and manage supervised processes
inside a **ready** sandbox (after `wait_until_ready()`). Most callers use
`sandbox.exec` / `sandbox.files` / `sandbox.processes` on the handle rather than
constructing `SandboxConnection` directly.

### Exec

| API | Sync | Async |
| --- | ---- | ----- |
| `sandbox.exec(command, ...)` | returns `ExecResult` | `await sandbox.exec(...)` |
| `sandbox.exec_stream(command, ...)` | `for event in ...` | `async for event in ...` |

Details: [`api-inventory.md` → Exec and streaming](./api-inventory.md#exec-and-streaming)

### `sandbox.processes`

Supervised detached processes (lifetime outlives the start request). Complements
request-scoped `sandbox.exec`.

**Prerequisites:** Wait for `connect_url`, `phase == "Ready"`, and a successful
runtime probe before calling these methods. See
[`api-inventory.md` → End-to-end flow](./api-inventory.md#end-to-end-flow).

| Method | Returns | Summary |
| ------ | ------- | ------- |
| `start(program, args=None, cwd=None, env=None, stdin=None)` | `Process` | Starts a detached process; `program` is a string or argv list. |
| `get(process_id, wait=False)` | `ProcessStatus` | Fetches status; `wait=True` blocks until exit. |
| `list()` | `list[ProcessInfo]` | Lists running and recently-exited processes. |
| `kill(process_id, signal=None)` | `bool` | Signals one process (default SIGTERM). |
| `kill_all(signal=None)` | `int` | Signals all processes; returns `signalled_count`. |
| `logs(process_id, cursor=None)` | `ProcessLogsPage` | Poll-mode UTF-8 log lines with cursor. |
| `follow(process_id, cursor=None)` | `Iterator[ProcessLogEvent]` | NDJSON stream with base64 chunks + optional exit event. |

`Process` handle: `id`, `state`, `exit_code`, `started_at`, plus `status()`, `wait()`,
`kill()`, `logs()`, `follow()`.

| API | Sync | Async |
| --- | ---- | ----- |
| `sandbox.processes.*` | direct calls | `await sandbox.processes.*` |
| `proc.follow()` | `for event in proc.follow():` | `async for event in proc.follow():` |

Details: [`api-inventory.md` → Processes API](./api-inventory.md#processes-api)

### `sandbox.files`

| Method | Returns | Summary |
| ------ | ------- | ------- |
| `write(path, content, cwd=None)` | `dict` (`bytes_written`) | Writes string or bytes to a sandbox file path; over 1 MiB goes through `upload`. |
| `upload(path, data, *, chunk_size=None, cwd=None, on_progress=None)` | `dict` (`bytes_written`) | Chunked, resumable upload of bytes, str, or a seekable file object. |
| `upload_file(local_path, remote_path, *, chunk_size=None, cwd=None, on_progress=None)` | `dict` (`bytes_written`) | Uploads a local file with `upload`. |
| `download_file(remote_path, local_path, *, cwd=None)` | `{"bytes_written": int}` | Streams a sandbox file to disk; no partial file on failure. |
| `read(path, cwd=None)` | `bytes` | Reads a sandbox file and returns raw binary content. |
| `read_text(path, cwd=None)` | `str` | Reads a sandbox file and decodes it as UTF-8 text. |
| `list(path, cwd=None, recursive=False, max_count=None)` | `list[FileEntry]` | Lists directory entries at a path, optionally recursive. |
| `stat(path, cwd=None)` / `exists(path, cwd=None)` | `FileEntry` / `bool` | Metadata for one path / whether it exists. |
| `mkdir(path, cwd=None)` / `move(source, destination, cwd=None)` / `remove(path, cwd=None, recursive=False)` | `FileEntry` / `FileEntry` / `None` | Create a directory, move or rename, delete. |
| `watch(path, cwd=None, recursive=False, timeout_ms=None)` | `Iterator[WatchEvent]` | Streams filesystem change events. |

Paths are relative to the workspace or absolute within it; a path outside the
workspace is refused.

### Low-level connection types

Listed for completeness; prefer handle methods above.

| Type | Sync | Async |
| ---- | ---- | ----- |
| Connection | `SandboxConnection(connect_url, api_key, ...)` | `AsyncSandboxConnection` |
| Files helper | `SandboxFiles` | `AsyncSandboxFiles` |
| Processes helper | `SandboxProcesses` | `AsyncSandboxProcesses` |
| Close | `connection.close()` | `await connection.aclose()` |

Details: [`api-inventory.md` → Runtime connection](./api-inventory.md#runtime-connection)

---

## Inline example snippets

Minimal one-liners for each public API. Runnable examples link to repo paths.

### Lifecycle

| API | Sync snippet | Async snippet | Runnable example |
| --- | ------------ | ------------- | ---------------- |
| `NeevAI(...)` | `with NeevAI() as client:` | `async with AsyncNeevAI() as client:` | [templates_list.py](../examples/templates_list.py), [async_sandbox.py](../examples/async_sandbox.py) |
| `client.close()` / `aclose()` | `with NeevAI() as client:` (auto) | `async with AsyncNeevAI() as client:` (auto) | all tier-1 examples |
| `client.sandboxes.create(...)` | `sandbox = client.sandboxes.create({...})` | `sandbox = await client.sandboxes.create({...})` | [sandbox_lifecycle.py](../examples/sandbox_lifecycle.py), [snapshot_fork_restore.py](../examples/snapshot_fork_restore.py) (`restore`) |
| `client.sandboxes.list(...)` | `page = client.sandboxes.list(name="web", status="Paused")` | `page = await client.sandboxes.list(name="web", status="Paused")` | [sandbox_lifecycle_controller.py](../examples/sandbox_lifecycle_controller.py) |
| `client.sandboxes.get(id)` | `sandbox = client.sandboxes.get(sandbox_id)` | `sandbox = await client.sandboxes.get(sandbox_id)` | [sandbox_lifecycle_controller.py](../examples/sandbox_lifecycle_controller.py) |
| `client.sandboxes.update(id, params, *, allow_internet, allow_egress)` | `client.sandboxes.update(id, {"resources": {"cpu": 2}})` | `await client.sandboxes.update(id, {"resources": {"cpu": 2}})` | [sandbox_update.py](../examples/sandbox_update.py) |
| `client.sandboxes.update(id, {"egress_add": ...})` | `client.sandboxes.update(id, {"egress_add": {"allow": [{"host": "pypi.org"}]}})` | `await client.sandboxes.update(id, {"egress_remove": {"allow": [{"host": "pypi.org"}]}})` | [update_resize_egress.py](../examples/update_resize_egress.py) |
| `client.sandboxes.pause(id)` | `sandbox = client.sandboxes.pause(sandbox_id)` | `sandbox = await client.sandboxes.pause(sandbox_id)` | [sandbox_lifecycle_controller.py](../examples/sandbox_lifecycle_controller.py) |
| `client.sandboxes.resume(id)` | `sandbox = client.sandboxes.resume(sandbox_id)` | `sandbox = await client.sandboxes.resume(sandbox_id)` | [sandbox_lifecycle_controller.py](../examples/sandbox_lifecycle_controller.py) |
| `client.sandboxes.keepalive(id)` | `client.sandboxes.keepalive(sandbox_id)` | `await client.sandboxes.keepalive(sandbox_id)` | [sandbox_lifecycle_windows.py](../examples/sandbox_lifecycle_windows.py) |
| `client.sandboxes.update_timeout(id, params)` | `client.sandboxes.update_timeout(sandbox_id, {"idle_timeout_seconds": 300})` | `await client.sandboxes.update_timeout(sandbox_id, {"idle_timeout_seconds": 300})` | [sandbox_lifecycle_windows.py](../examples/sandbox_lifecycle_windows.py) |
| `client.sandboxes.delete(id)` | `client.sandboxes.delete(sandbox_id)` | `await client.sandboxes.delete(sandbox_id)` | [sandbox_lifecycle_controller.py](../examples/sandbox_lifecycle_controller.py) |
| `client.sandboxes.metrics(id, ...)` | `metrics = client.sandboxes.metrics(sandbox_id)` | `metrics = await client.sandboxes.metrics(sandbox_id)` | [sandbox_lifecycle_controller.py](../examples/sandbox_lifecycle_controller.py) |
| `client.sandboxes.audit(id, ...)` | `trail = client.sandboxes.audit(sandbox_id, limit=50)` | `trail = await client.sandboxes.audit(sandbox_id, limit=50)` | [audit_trail.py](../examples/audit_trail.py) |
| `client.sandboxes.expose_port(id, port, ..., *, slug)` | `p = client.sandboxes.expose_port(sandbox_id, 3000)` | `p = await client.sandboxes.expose_port(sandbox_id, 3000)` | [preview_ports.py](../examples/preview_ports.py) |
| `client.sandboxes.create_snapshot(id, ...)` | `snap = client.sandboxes.create_snapshot(sb.id, {"name": "demo"})` | `snap = await client.sandboxes.create_snapshot(sb.id, {"name": "demo"})` | [snapshot_fork_restore.py](../examples/snapshot_fork_restore.py) (via `sandbox.snapshot`) |
| `client.sandboxes.list_snapshots(id)` | `snaps = client.sandboxes.list_snapshots(sb.id)` | `snaps = await client.sandboxes.list_snapshots(sb.id)` | — |
| `client.sandboxes.get_snapshot(id)` | `snap = client.sandboxes.get_snapshot(snap_id)` | `snap = await client.sandboxes.get_snapshot(snap_id)` | [snapshot_fork_restore.py](../examples/snapshot_fork_restore.py) |
| `client.sandboxes.delete_snapshot(id)` | `client.sandboxes.delete_snapshot(snap_id)` | `await client.sandboxes.delete_snapshot(snap_id)` | [snapshot_fork_restore.py](../examples/snapshot_fork_restore.py) |
| `client.sandboxes.rollback(id, snapshot_id)` | `sb = client.sandboxes.rollback(sb.id, snap_id)` | `sb = await client.sandboxes.rollback(sb.id, snap_id)` | — (prefer `restore` create; see [Snapshots](#snapshots)) |
| `client.sandboxes.fork(id, name)` | `fork = client.sandboxes.fork(sb.id, "fork-name")` | `fork = await client.sandboxes.fork(sb.id, "fork-name")` | [snapshot_fork_restore.py](../examples/snapshot_fork_restore.py) (via `sandbox.fork`) |
| `client.templates.list(...)` | `page = client.templates.list(limit=10)` | `page = await client.templates.list(limit=10)` | [templates_list.py](../examples/templates_list.py) |
| `client.templates.get(id)` | `tpl = client.templates.get(template_id)` | `tpl = await client.templates.get(template_id)` | [templates_list.py](../examples/templates_list.py) |
| `client.agents.create(...)` | `agent = client.agents.create({...})` | `agent = await client.agents.create({...})` | [create_agent.py](../examples/create_agent.py) |
| `client.agents.list(...)` | `page = client.agents.list(page=1, limit=20)` | `page = await client.agents.list(page=1, limit=20)` | — |
| `client.agents.get(id)` | `agent = client.agents.get(agent_id)` | `agent = await client.agents.get(agent_id)` | — |
| `client.agents.update(id, params)` | `agent = client.agents.update(id, {"resources": {...}})` | `agent = await client.agents.update(id, {...})` | [create_agent.py](../examples/create_agent.py) |
| `client.agents.pause(id)` / `.resume(id)` | `agent = client.agents.pause(agent_id)` / `client.agents.resume(agent_id)` | `agent = await client.agents.pause(agent_id)` / `await client.agents.resume(agent_id)` | [create_agent.py](../examples/create_agent.py) (pause via handle) |
| `client.agents.delete(id)` | `client.agents.delete(agent_id)` | `await client.agents.delete(agent_id)` | [create_agent.py](../examples/create_agent.py) |
| `client.agents.keepalive(id)` | `client.agents.keepalive(agent_id)` | `await client.agents.keepalive(agent_id)` | [agent_ports_audit.py](../examples/agent_ports_audit.py) |
| `client.agents.rollback(id, snapshot_id)` | `client.agents.rollback(agent_id, snap_id)` | `await client.agents.rollback(agent_id, snap_id)` | — |
| `client.agents.expose_port(id, port, ..., *, slug)` | `p = client.agents.expose_port(agent_id, 3000)` | `p = await client.agents.expose_port(agent_id, 3000)` | [agent_ports_audit.py](../examples/agent_ports_audit.py) |
| `client.agents.audit(id, ...)` | `trail = client.agents.audit(agent_id, limit=50)` | `trail = await client.agents.audit(agent_id, limit=50)` | [agent_ports_audit.py](../examples/agent_ports_audit.py) |
| `client.agent_templates.list(...)` | `page = client.agent_templates.list()` | `page = await client.agent_templates.list()` | [create_agent.py](../examples/create_agent.py) |
| `client.agent_templates.get(id)` | `tpl = client.agent_templates.get(template_id)` | `tpl = await client.agent_templates.get(template_id)` | — |
| `client.raw.request(...)` | `data = client.raw.request("GET", path, query={...})` | `data = await client.raw.request("GET", path, query={...})` | [raw_request.py](../examples/raw_request.py) |
| `sandbox.id` / `.name` / `.phase` / `.replicas` | `print(sandbox.phase, sandbox.replicas)` | same after `await create` | [sandbox_lifecycle.py](../examples/sandbox_lifecycle.py) |
| `sandbox.connect_url` | `print(sandbox.connect_url)` | `print(sandbox.connect_url)` | [templates_list.py](../examples/templates_list.py) |
| `sandbox.data` | `record = sandbox.data` | `record = sandbox.data` | — |
| `sandbox.refresh()` | `sandbox.refresh()` | `await sandbox.refresh()` | — |
| `sandbox.update(params, *, allow_internet, allow_egress)` | `sandbox.update({"resources": {"cpu": 2}}, allow_egress=["api.github.com"])` | `await sandbox.update({"resources": {"cpu": 2}})` | [sandbox_update.py](../examples/sandbox_update.py) |
| `sandbox.wait_until_ready(...)` | `sandbox.wait_until_ready(timeout_ms=120_000)` | `await sandbox.wait_until_ready()` | [sandbox_lifecycle.py](../examples/sandbox_lifecycle.py) |
| `sandbox.pause()` | `sandbox.pause()` | `await sandbox.pause()` | [sandbox_lifecycle.py](../examples/sandbox_lifecycle.py) |
| `sandbox.resume()` | `sandbox.resume()` | `await sandbox.resume()` | — |
| `sandbox.keepalive()` | `sandbox.keepalive()` | `await sandbox.keepalive()` | [sandbox_lifecycle_windows.py](../examples/sandbox_lifecycle_windows.py) |
| `sandbox.update_timeout(params)` | `sandbox.update_timeout({"idle_timeout_seconds": 300, "max_lifetime_seconds": 0})` | `await sandbox.update_timeout({"idle_timeout_seconds": 300})` | [sandbox_lifecycle_windows.py](../examples/sandbox_lifecycle_windows.py) |
| `sandbox.snapshot(params=None)` | `pending = sandbox.snapshot({"name": "demo-snap"})` | `pending = await sandbox.snapshot({"name": "demo-snap"})` | [snapshot_fork_restore.py](../examples/snapshot_fork_restore.py) |
| `sandbox.snapshots()` | `snaps = sandbox.snapshots()` | `snaps = await sandbox.snapshots()` | — |
| `sandbox.rollback(snapshot_id)` | `sandbox.rollback(snapshot_id)` | `await sandbox.rollback(snapshot_id)` | — (prefer `restore` create; see [Snapshots](#snapshots)) |
| `sandbox.fork(name)` | `fork = sandbox.fork("fork-name")` | `fork = await sandbox.fork("fork-name")` | [snapshot_fork_restore.py](../examples/snapshot_fork_restore.py) |
| `sandbox.delete()` | `sandbox.delete()` | `await sandbox.delete()` | [sandbox_lifecycle.py](../examples/sandbox_lifecycle.py) |
| `sandbox.metrics(...)` | `metrics = sandbox.metrics()` | `metrics = await sandbox.metrics()` | [sandbox_metrics.py](../examples/sandbox_metrics.py) |
| `sandbox.audit(...)` | `trail = sandbox.audit(limit=50)` | `trail = await sandbox.audit(limit=50)` | [audit_trail.py](../examples/audit_trail.py) |
| `sandbox.addressable` | `print(sandbox.addressable)` | `print(sandbox.addressable)` | — |
| `sandbox.expose_port(port)` | `p = sandbox.expose_port(8080)` | `p = await sandbox.expose_port(8080)` | [preview_ports.py](../examples/preview_ports.py) |
| `sandbox.expose_port(port, slug=...)` | `p = sandbox.expose_port(8080, slug="k3x9q2ab")` (rotates the URL) | `p = await sandbox.expose_port(8080, slug="k3x9q2ab")` | [preview_ports.py](../examples/preview_ports.py) |
| `sandbox.list_ports()` | `ports = sandbox.list_ports()` | `ports = await sandbox.list_ports()` | [preview_ports.py](../examples/preview_ports.py) |
| `sandbox.revoke_port(port)` | `sandbox.revoke_port(8080)` | `await sandbox.revoke_port(8080)` | [preview_ports.py](../examples/preview_ports.py) |
| `sandbox.get_url(port, ...)` | `url = sandbox.get_url(8080)` | `url = await sandbox.get_url(8080)` | [preview_ports.py](../examples/preview_ports.py) |
| `sandbox.pty.create(...)` | `pty = sandbox.pty.create(program="sh", on_data=cb)` | `pty = await sandbox.pty.create(program="sh", on_data=cb)` | [pty.py](../examples/pty.py) |
| `sandbox.ssh(...)` | `t = sandbox.ssh()` | `t = await sandbox.ssh()` | [ssh_tunnel.py](../examples/ssh_tunnel.py) |
| `sandbox.to_json()` | `sandbox.to_json()` | `sandbox.to_json()` | [sandbox_lifecycle_controller.py](../examples/sandbox_lifecycle_controller.py) |
| `agent.id` / `.status` / `.sandbox_id` | `print(agent.status, agent.sandbox_id)` | same after `await create` | [create_agent.py](../examples/create_agent.py) |
| `agent.wait_until_ready(...)` | `agent.wait_until_ready(timeout_ms=120_000)` | `await agent.wait_until_ready()` | [create_agent.py](../examples/create_agent.py) |
| `agent.refresh()` | `agent.refresh()` | `await agent.refresh()` | — |
| `agent.sandbox()` | `sandbox = agent.sandbox()` — then `exec` / `files` / `processes` | `sandbox = await agent.sandbox()` | [create_agent.py](../examples/create_agent.py) |
| `agent.update(params)` | `agent.update({"resources": {...}})` | `await agent.update({...})` | [create_agent.py](../examples/create_agent.py) |
| `agent.pause()` / `.resume()` / `.delete()` | `agent.pause(); agent.resume(); agent.delete()` | `await agent.pause(); await agent.resume(); await agent.delete()` | [create_agent.py](../examples/create_agent.py) (pause/delete; resume via handle API) |
| `agent.keepalive()` / `.rollback(snapshot_id)` | `agent.keepalive()` | `await agent.keepalive()` | [agent_ports_audit.py](../examples/agent_ports_audit.py) |
| `agent.expose_port(port, *, slug)` / `.list_ports()` / `.revoke_port(port)` / `.get_url(port)` | `p = agent.expose_port(3000)` | `p = await agent.expose_port(3000)` | [agent_ports_audit.py](../examples/agent_ports_audit.py) |
| `agent.audit(...)` | `trail = agent.audit(limit=50)` | `trail = await agent.audit(limit=50)` | [agent_ports_audit.py](../examples/agent_ports_audit.py) |
| `agent.idle_timeout_seconds` | `print(agent.idle_timeout_seconds)` | same | — |
| `agent.to_json()` | `agent.to_json()` | `agent.to_json()` | — |

### Runtime

| API | Sync snippet | Async snippet | Runnable example |
| --- | ------------ | ------------- | ---------------- |
| `sandbox.exec(...)` | `result = sandbox.exec(["echo", "hi"])` | `result = await sandbox.exec(["echo", "hi"])` | [parallel_fanout.py](../examples/parallel_fanout.py), [async_sandbox.py](../examples/async_sandbox.py) |
| `sandbox.exec_stream(...)` | `for event in sandbox.exec_stream(cmd):` | `async for event in sandbox.exec_stream(cmd):` | [streaming_exec.py](../examples/streaming_exec.py) |
| `sandbox.processes.list(...)` | `sandbox.processes.list()` | `await sandbox.processes.list()` | [processes.py](../examples/processes.py), [process_pool.py](../examples/process_pool.py) |
| `sandbox.processes.start(...)` | `proc = sandbox.processes.start(["sleep", "30"])` | `proc = await sandbox.processes.start(["sleep", "30"])` | [processes.py](../examples/processes.py), [process_pool.py](../examples/process_pool.py) |
| `sandbox.processes.get(...)` | `status = sandbox.processes.get(proc.id)` | `status = await sandbox.processes.get(proc.id)` | — (`proc.wait()` / `proc.status()` call `get` internally; see [processes.py](../examples/processes.py)) |
| `Process.status()` | `status = proc.status()` | `status = await proc.status()` | — (no dedicated example) |
| `Process.wait()` | `final = proc.wait()` | `final = await proc.wait()` | [processes.py](../examples/processes.py), [process_pool.py](../examples/process_pool.py) |
| `sandbox.processes.follow(...)` | `for event in proc.follow():` | `async for event in proc.follow():` | [processes.py](../examples/processes.py) |
| `sandbox.processes.logs(...)` | `page = proc.logs()` | `page = await proc.logs()` | [processes.py](../examples/processes.py) |
| `sandbox.processes.kill(...)` | `proc.kill(signal=Signal.TERM)` | `await proc.kill(signal=Signal.TERM)` | [processes.py](../examples/processes.py) |
| `sandbox.processes.kill_all(...)` | `count = sandbox.processes.kill_all()` | `count = await sandbox.processes.kill_all()` | [process_pool.py](../examples/process_pool.py) |
| `sandbox.files.write(...)` | `sandbox.files.write("path.txt", "content")` | `await sandbox.files.write("path.txt", "content")` | [files_api.py](../examples/files_api.py), [snapshot_fork_restore.py](../examples/snapshot_fork_restore.py) |
| `sandbox.files.upload(...)` | `sandbox.files.upload("big.bin", data, on_progress=cb)` | `await sandbox.files.upload("big.bin", data)` | [upload_download.py](../examples/upload_download.py) |
| `sandbox.files.upload_file(...)` | `sandbox.files.upload_file("local.bin", "remote.bin")` | `await sandbox.files.upload_file("local.bin", "remote.bin")` | [upload_download.py](../examples/upload_download.py) |
| `sandbox.files.download_file(...)` | `sandbox.files.download_file("remote.bin", "copy.bin")` | `await sandbox.files.download_file("remote.bin", "copy.bin")` | [upload_download.py](../examples/upload_download.py) |
| `sandbox.files.read(...)` | `data = sandbox.files.read("path.txt")` | `data = await sandbox.files.read("path.txt")` | [agent_loop.py](../examples/agent_patterns/utils/agent_loop.py) |
| `sandbox.files.read_text(...)` | `text = sandbox.files.read_text("path.txt")` | `text = await sandbox.files.read_text("path.txt")` | [files_api.py](../examples/files_api.py), [snapshot_fork_restore.py](../examples/snapshot_fork_restore.py) |
| `sandbox.files.list(...)` | `entries = sandbox.files.list("dir", recursive=True)` | `entries = await sandbox.files.list("dir", recursive=True)` | [files_api.py](../examples/files_api.py) |
| `sandbox.files.stat(...)` | `entry = sandbox.files.stat("path.txt")` | `entry = await sandbox.files.stat("path.txt")` | [files_api.py](../examples/files_api.py) |
| `sandbox.files.exists(...)` | `ok = sandbox.files.exists("path.txt")` | `ok = await sandbox.files.exists("path.txt")` | [files_api.py](../examples/files_api.py) |
| `sandbox.files.mkdir(...)` | `sandbox.files.mkdir("dir")` | `await sandbox.files.mkdir("dir")` | [files_api.py](../examples/files_api.py) |
| `sandbox.files.move(...)` | `sandbox.files.move("a.txt", "b.txt")` | `await sandbox.files.move("a.txt", "b.txt")` | [files_api.py](../examples/files_api.py) |
| `sandbox.files.remove(...)` | `sandbox.files.remove("dir", recursive=True)` | `await sandbox.files.remove("dir", recursive=True)` | [files_api.py](../examples/files_api.py) |
| `sandbox.files.watch(...)` | `for ev in sandbox.files.watch("."): ...` | `async for ev in sandbox.files.watch("."): ...` | [files_api.py](../examples/files_api.py) |
| `workflow_examples/*` | Model-driven sandboxes via `StreamingAgentLoop` — not `client.agents` | same | [repo_analyzer.py](../examples/workflow_examples/repo_analyzer.py) |
| `SandboxConnection` (low-level) | via `sandbox.exec` on handle | via `await sandbox.exec` on handle | — |
| `SandboxFiles` (low-level) | via `sandbox.files` property | via `sandbox.files` property | [files_api.py](../examples/files_api.py) |
| `SandboxProcesses` (low-level) | via `sandbox.processes` property | via `sandbox.processes` property | [processes.py](../examples/processes.py) |

---

## Maintaining this reference

Any PR that modifies public SDK exports must update:

- [`docs/api-reference.md`](./api-reference.md) — API lists and inline snippet table (this file)
- [`docs/api-inventory.md`](./api-inventory.md) — method signatures, type field tables, symbol index
- [`docs/example-coverage.md`](./example-coverage.md) — example catalog and API → examples lookup
- [`docs/getting-started.md`](./getting-started.md) — if install, env vars, or quick-start flows change
- [`examples/`](../examples/) — if a new capability lacks a runnable example

Type field tables live in [`api-inventory.md`](./api-inventory.md) only — not here.
After `scripts/gen_types.py`, verify type tables in the inventory against
`src/neevai/generated/`.
