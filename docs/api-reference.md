# API reference

Every public method in `neevai`, grouped by product, with short snippets. For a guided
tour, see the product guides ([Sandboxes](./sandboxes.md), [Agents](./agents.md),
[Agent tools](./agent-tools.md)); to get set up, see
[Getting started](./getting-started.md). For full signatures and type fields, see the
[API inventory](./api-inventory.md).

Every sync class has an async twin (`AsyncNeevAI`, `AsyncSandbox`, `AsyncAgent`,
`AsyncSandboxTools` and so on) with the same methods: add `await`, and use `async for`
where a method streams. Each product ends with a table of sync and async one-liners.

## Contents

- [Client](#client): [`NeevAI` and `AsyncNeevAI`](#neevai-and-asyncneevai), [`client.raw`](#clientraw)
- [Sandboxes](#sandboxes)
  - [`client.sandboxes`](#clientsandboxes), [Snapshots, fork and rollback](#snapshots-fork-and-rollback), [Audit trail](#audit-trail)
  - [`client.templates`](#clienttemplates)
  - [Sandbox handle](#sandbox-handle)
  - [Commands and processes](#commands-and-processes), [Files](#files), [Code interpreter](#code-interpreter), [Terminals and SSH](#terminals-and-ssh)
  - [Low-level connection types](#low-level-connection-types)
  - [Sandbox snippets](#sandbox-snippets)
- [Agents](#agents): [`client.agents`](#clientagents), [`client.agent_templates`](#clientagent_templates), [`Agent` handle](#agent-handle), [Agent snippets](#agent-snippets)
- [Agent tools](#agent-tools): [`SandboxTools` and `AsyncSandboxTools`](#sandboxtools-and-asyncsandboxtools), [Framework adapters](#framework-adapters), [Agent tools snippets](#agent-tools-snippets)
- [Errors](#errors)

---

## Client

### `NeevAI` and `AsyncNeevAI`

```python
NeevAI(api_key=None, org_id=None, project_id=None, base_url=None,
       timeout_ms=60000, max_retries=2, client=None)
```

| Option | Environment variable | Default |
| --- | --- | --- |
| `api_key` | `NEEV_API_KEY` | Required |
| `org_id` | `NEEV_ORG_ID` | None; needed by most calls |
| `project_id` | `NEEV_PROJECT_ID` | None; needed by most calls |
| `base_url` | `NEEV_BASE_URL` | `https://api.ai.neevcloud.com/agent` |
| `timeout_ms` | | `60000` |
| `max_retries` | | `2` |
| `client` | | A new `httpx.Client` (`httpx.AsyncClient` for `AsyncNeevAI`) |

| API | Sync | Async |
| --- | ---- | ----- |
| Root client | `NeevAI(...)` | `AsyncNeevAI(...)` |
| Close transport | `client.close()` (or `with`) | `await client.aclose()` (or `async with`) |
| Products | `client.sandboxes`, `client.templates`, `client.agents`, `client.agent_templates` | same |

Every method that acts in a project takes `org_id` and `project_id` to override the
client's defaults for one call. See [Configuration](./configuration.md).

Details: [`api-inventory.md` → Client](./api-inventory.md#client)

### `client.raw`

| Method | Returns | Summary |
| ------ | ------- | ------- |
| `request(method, path, query=None, body=None)` | JSON dict/list or `None` | Untyped API call with the client's authentication, retries and errors; `None` for HTTP 204. |

Details: [`api-inventory.md` → Raw client](./api-inventory.md#raw-client)

---

## Sandboxes

A sandbox is an isolated machine for your code. `client.sandboxes` and `client.templates`
manage sandboxes; the `Sandbox` handle and its runtime properties work inside one. Guide:
[Sandboxes](./sandboxes.md).

### `client.sandboxes`

| Method | Returns | Summary |
| ------ | ------- | ------- |
| `create(params, org_id=None, project_id=None, *, allow_internet=None, allow_egress=None, labels=None)` | `Sandbox` | Creates a new sandbox. `allow_internet=True` / `allow_egress=[...]` open egress (deny-all by default; explicit `egress` wins). `labels={...}` tags it with key-value labels. Optional `restore` in params provisions from a snapshot; `image` and `command` start your own image. |
| `list(page=None, limit=None, name=None, status=None, sandbox_id=None, org_id=None, project_id=None, *, labels=None)` | `SandboxPage` | Lists sandboxes with pagination in the resolved org/project scope. `labels={...}` keeps only sandboxes carrying every given label. |
| `get(id, org_id=None, project_id=None)` | `Sandbox` | Fetches the current record for a sandbox by ID or name. |
| `update(id, params, org_id=None, project_id=None, *, allow_internet=None, allow_egress=None)` | `Sandbox` | In-place update of `resources` (cpu/memory) and/or `egress`. Resize keeps the ID/name/preview URLs and does not restart; `disk_gb` is not resizable and the server rejects a change. `allow_internet` / `allow_egress` are the same egress convenience as `create`. `egress_add` / `egress_remove` edit the allow-list in place (not combinable with `egress`). `{"execution_trace": False}` stops recording programs, `True` turns it back on. Rejects `{}` locally, naming every field. |
| `pause(id, org_id=None, project_id=None)` | `Sandbox` | Stops a sandbox and keeps its state (Paused). A pause always captures full state, so a resume picks up where it left off. |
| `resume(id, org_id=None, project_id=None)` | `Sandbox` | Starts a paused sandbox again, toward Ready. |
| `keepalive(id, org_id=None, project_id=None)` | `Sandbox` | Resets the sandbox's idle timer. |
| `update_timeout(id, params, org_id=None, project_id=None)` | `Sandbox` | Changes idle/lifetime windows; only the windows passed change, `0` turns one off. |
| `delete(id, org_id=None, project_id=None)` | `None` | Permanently deletes a sandbox. |
| `metrics(id, from_=None, to=None, step=None, ...)` | `SandboxMetricsResponse` | Queries live health metrics over an optional time range. |
| `audit(id, *, from_=None, to=None, cursor=None, limit=None, ...)` | `AuditTrail` | One page of the audit trail, newest first: calls, programs and connections. See [Audit trail](#audit-trail). |
| `expose_port(id, port, ..., *, slug=None)` / `list_ports(id)` / `revoke_port(id, port)` | `SandboxPort` / `list[SandboxPort]` / `None` | Preview ports. A new `slug` on an exposed port rotates its URL. |
| `get_port_url(id, port, wait_until_ready=True, timeout_ms=60000, poll_interval_ms=2000, ..., *, slug=None)` | `str` | Exposes a port and returns its preview URL once routable. |
| `create_snapshot(id, params=None, ...)` | `Snapshot` | Creates a snapshot of the sandbox: process memory and filesystem by default, or `/workspace` only with `snapshot_type="filesystem"` (returns immediately with status Pending). |
| `list_snapshots(id, page=None, limit=None, ...)` | `list[Snapshot]` | Lists snapshots for a sandbox (unwraps pagination items). |
| `get_snapshot(snapshot_id, ...)` | `Snapshot` | Fetches snapshot metadata by project-scoped ID. |
| `wait_for_snapshot(snapshot_id, timeout_ms=300000, poll_interval_ms=2000, ...)` | `Snapshot` | Waits until a snapshot is `Ready`. |
| `delete_snapshot(snapshot_id, ...)` | `None` | Deletes a snapshot permanently. |
| `rollback(id, snapshot_id, ...)` | `Sandbox` | Rolls a sandbox back in place to a previous snapshot. Prefer `create({..., "restore": ...})` to recover into a new sandbox; see [Snapshots](#snapshots-fork-and-rollback). |
| `fork(id, name, ...)` | `Sandbox` | Forks a sandbox into a new sandbox from its current state. |

### Snapshots, fork and rollback

A snapshot captures a sandbox's full state: its files and the memory of its running
processes. Restore it into a new sandbox, roll back in place, or fork. Snapshots are
asynchronous: `create_snapshot` returns `status=Pending`; `wait_for_snapshot` (or
`sandbox.snapshot(..., wait_until_ready=True)`) waits until it is `Ready`.

**Recommended restore pattern:** create a new sandbox from a snapshot, which does not
change the original sandbox.

```python
snap = sandbox.snapshot({"name": "checkpoint"}, wait_until_ready=True)
restored = client.sandboxes.create({"name": "restored", "restore": snap.id})
restored.wait_until_ready()
```

In-place `sandbox.rollback(snapshot_id)` is also available but can come back with an
empty workspace. See [`snapshot_fork_restore.py`](../examples/snapshot_fork_restore.py).

### Audit trail

`audit()` returns an `AuditTrail` (`from_`, `to`, `retention_days`, `window_truncated`,
`next_cursor`, `data: list[AuditEvent]`), newest first. Each event is an
[OCSF 1.9.0](https://schema.ocsf.io/1.9.0/) event, so it can go straight into a SIEM.

| `class_uid` | `class_name` | What it records | `activity_name` |
| --- | --- | --- | --- |
| `6003` | API Activity | A call made to the sandbox: `exec`, a terminal command, a file operation, a process start, SSH, a code-interpreter cell | Create, Read, Update, Delete, Other |
| `1007` | Process Activity | A program that ran inside the sandbox, whether or not a call asked for it: scripts, generated code, child processes | Launch, Terminate, Sandbox Start |
| `4001` | Network Activity | A connection a program opened | Open |

Every event has `time` (milliseconds since the Unix epoch), `type_name` (such as
`Process Activity: Launch`), `status` (`Success` or `Failure`), `device.uid` (the sandbox
id) and `metadata.uid` (a stable event id).

| Class | Key fields |
| --- | --- |
| API Activity | `api.operation`, `api.request.uid`, `actor.user` (`type` is `User`, `API Key`, `System` or `Unknown`; an API key also has `programmatic_credentials[].uid`), `resources`, `duration`, `status_code` |
| Process Activity | `process.pid`, `process.name` (no arguments), `process.file.path` (what actually executed), `process.working_directory`, `process.parent_process.pid`. On Launch, `actor.process` is the parent. On Terminate, `exit_code`, or `status_detail` such as `signal 9` when a signal stopped it |
| Network Activity | `actor.process` (the program), `dst_endpoint.ip` and `dst_endpoint.port`, or `dst_endpoint.name` (`unix:<path>`) for a local socket |

`api` and `resources` are `None` on program and connection events, which don't name who
acted, so check `e.api` before reading `e.api.operation`. To find the call that started a
program, take the API Activity event whose `resources[].data.pid` equals the program's
pid, or the pid of an ancestor reached through `parent_process.pid` (each ancestor's own
Launch event names its parent). A terminal command's programs lead back to the terminal's
shell pid.

| Filter | Applies to |
| --- | --- |
| `from_`, `to` (RFC 3339), `limit` (1–200, default 50), `cursor` | Every event |
| `status` (`"success"` or `"failure"`) | Every event |
| `operation` (one name or a list) | API Activity only; programs and connections are left out |
| `actor_type` (`"user"`, `"api_key"` or `"system"`, or a list), `actor_uid`, `credential_uid` | API Activity only |

- Program names are recorded without their arguments, the environment is never recorded,
  and input typed at a hidden password prompt is never recorded.
- Programs and connections can take about a minute to appear. The first programs a newly
  started sandbox runs may be missing.
- `update(id, {"execution_trace": False})` stops recording programs and connections;
  calls are still recorded. `sandbox.execution_trace` reports the current setting.
- The trail covers the last `retention_days` days; `window_truncated` is `True` when
  `from_` reaches further back.

[`audit_trail.py`](../examples/audit_trail.py) prints all three classes and ties each
program to the call that started it.

### `client.templates`

| Method | Returns | Summary |
| ------ | ------- | ------- |
| `list(page=None, limit=None)` | `TemplatePage` | Lists available sandbox templates with pagination. |
| `get(template_id)` | `SandboxTemplate` | Fetches a single sandbox template by ID. Templates carry an optional display `icon`. |

Templates you can start from:

| Template | Use it for |
| --- | --- |
| `sb-ubuntu-26-04-dev` | General development: git, gh, Python 3, Node 24 LTS |
| `sb-ubuntu-26-04-docker` | Docker, Compose and Buildx, with Docker started at boot; run containers with `--network=host` |
| `sb-ubuntu-26-04-interpreter` | The [code interpreter](#code-interpreter): Python kernels that keep their state |
| `sb-ubuntu-26-04-playwright` | Browser testing: a desktop with Node 24, Playwright and Chromium, headless or headed (`DISPLAY=:1`) |

The catalogue grows over time, so `templates.list()` is the source of truth.

### Sandbox handle

`Sandbox` is returned by `create()`, `get()`, `list().items` and `fork()`. Its methods
update the handle in place.

| API | Kind |
| --- | ---- |
| `id`, `name`, `phase`, `connect_url`, `addressable`, `execution_trace`, `labels`, `last_crash`, `data` | properties |
| `refresh()` | method |
| `update(params, *, allow_internet=None, allow_egress=None)` | method: in-place resize / egress re-scope (`egress_add` / `egress_remove` edit the allow-list) / `execution_trace` |
| `wait_until_ready(timeout_ms=120000, poll_interval_ms=2000, on_poll=None)` | method: polls the API until `Ready` and addressable; raises at once if `Paused` |
| `pause()` / `resume()` | methods |
| `keepalive()` / `update_timeout(params)` | methods: reset idle timer / change lifecycle windows |
| `snapshot(params=None, *, wait_until_ready=False, timeout_ms=300000, poll_interval_ms=2000)` / `snapshots()` | methods |
| `rollback(snapshot_id)` / `fork(name)` | methods |
| `delete()` | method |
| `metrics(from_=None, to=None, step=None)` | method |
| `audit(*, from_=None, to=None, cursor=None, limit=None, operation=None, status=None, actor_type=None, actor_uid=None, credential_uid=None)` | method |
| `expose_port(port, *, slug=None)` / `list_ports()` / `revoke_port(port)` / `get_url(port, wait_until_ready=True, timeout_ms=60000, poll_interval_ms=2000, *, slug=None)` | methods: preview ports |
| `exec(...)` / `exec_stream(...)` | methods: [Commands and processes](#commands-and-processes) |
| `files` / `processes` / `code` / `pty` | properties: [Files](#files), [Commands and processes](#commands-and-processes), [Code interpreter](#code-interpreter), [Terminals and SSH](#terminals-and-ssh) |
| `ssh(port=None, host="127.0.0.1")` | method: [Terminals and SSH](#terminals-and-ssh) |
| `to_json()` | method |

`pause()`, `resume()` and `rollback()` drop the handle's cached runtime connection. Runtime
calls on a `Paused` sandbox that still has a `connect_url` are sent, and wake it where the
platform's automatic wake-up is enabled; see [Pause and wake](./sandboxes.md#pause-and-wake).

### Commands and processes

Runtime calls run commands, access files and manage processes inside a sandbox once it is
ready (after `wait_until_ready()`). Most callers use `sandbox.exec`, `sandbox.files` and
`sandbox.processes` on the handle rather than constructing `SandboxConnection` directly.

#### Exec

| Method | Returns | Summary |
| ------ | ------- | ------- |
| `exec(command, args=None, cwd=None, env=None, timeout_ms=None, stdin=None)` | `ExecResult` (`stdout`, `stderr`, `exit_code`) | Runs a command to completion. A non-zero exit code is returned, not raised. `command` is an argv list, or a program name with `args`. |
| `exec_stream(command, args=None, cwd=None, env=None, timeout_ms=None, stdin=None)` | `Iterator[ExecStreamEvent]` | Yields `stdout` / `stderr` chunks as they arrive, then an `exit` event. |

| API | Sync | Async |
| --- | ---- | ----- |
| `sandbox.exec(command, ...)` | returns `ExecResult` | `await sandbox.exec(...)` |
| `sandbox.exec_stream(command, ...)` | `for event in ...` | `async for event in ...` |

Details: [`api-inventory.md` → Exec and streaming](./api-inventory.md#exec-and-streaming)

#### `sandbox.processes`

Supervised detached processes, whose lifetime outlives the start request. They
complement request-scoped `sandbox.exec`.

**Prerequisites:** wait for `connect_url`, `phase == "Ready"`, and a successful runtime
probe before calling these methods. See
[`api-inventory.md` → End-to-end flow](./api-inventory.md#end-to-end-flow).

| Method | Returns | Summary |
| ------ | ------- | ------- |
| `start(program, args=None, cwd=None, env=None, stdin=None)` | `Process` | Starts a detached process; `program` is a string or argv list. |
| `get(process_id, *, wait=False)` | `ProcessStatus` | Fetches status; `wait=True` blocks until exit. |
| `list()` | `list[ProcessInfo]` | Lists running and recently-exited processes. |
| `kill(process_id, signal=None)` | `bool` | Signals one process (default SIGTERM). |
| `kill_all(signal=None)` | `int` | Signals all processes; returns `signalled_count`. |
| `logs(process_id, cursor=None)` | `ProcessLogsPage` | Poll-mode UTF-8 log lines with cursor. |
| `follow(process_id, cursor=None)` | `Iterator[ProcessLogEvent]` | Streams output as `{"type": "stdout" or "stderr", "data": str}` events, then `{"type": "exit", "exit_code": int}`. |

`Process` handle: `id`, `state`, `exit_code`, `started_at`, plus `status()`, `wait()`,
`kill()`, `logs()`, `follow()`.

| API | Sync | Async |
| --- | ---- | ----- |
| `sandbox.processes.*` | direct calls | `await sandbox.processes.*` |
| `proc.follow()` | `for event in proc.follow():` | `async for event in proc.follow():` |

Details: [`api-inventory.md` → Processes API](./api-inventory.md#processes-api)

### Files

`sandbox.files`:

| Method | Returns | Summary |
| ------ | ------- | ------- |
| `write(path, content, cwd=None)` | `dict` (`bytes_written`) | Writes string or bytes to a sandbox file path; over 1 MiB goes through `upload`. |
| `upload(path, data, *, chunk_size=None, cwd=None, on_progress=None)` | `dict` (`bytes_written`) | Chunked, resumable upload of bytes, str, or a seekable file object. |
| `upload_file(local_path, remote_path, *, chunk_size=None, cwd=None, on_progress=None)` | `dict` (`bytes_written`) | Uploads a local file with `upload`. |
| `download_file(remote_path, local_path, *, cwd=None)` | `{"bytes_written": int}` | Streams a sandbox file to disk; no partial file on failure. |
| `read(path, cwd=None, offset=None, length=None)` | `bytes` | Reads a sandbox file and returns raw binary content, or only `length` bytes from `offset`. |
| `read_text(path, cwd=None, offset=None, length=None)` | `str` | Reads a sandbox file (or a byte range of it) and decodes it as UTF-8 text. |
| `list(path, cwd=None, recursive=False, max_count=None)` | `list[FileEntry]` | Lists directory entries at a path, optionally recursive. |
| `stat(path, cwd=None)` / `exists(path, cwd=None)` | `FileEntry` / `bool` | Metadata for one path / whether it exists. |
| `mkdir(path, cwd=None)` / `move(source, destination, cwd=None)` / `remove(path, cwd=None, recursive=False)` | `FileEntry` / `FileEntry` / `None` | Create a directory, move or rename, delete. |
| `watch(path, cwd=None, recursive=False, timeout_ms=None)` | `Iterator[WatchEvent]` | Streams filesystem change events. |

Paths are relative to the workspace or absolute within it; a path outside the workspace
is refused.

Details: [`api-inventory.md` → Files API](./api-inventory.md#files-api)

### Code interpreter

Sandboxes created from `sb-ubuntu-26-04-interpreter` run Python in kernels that keep
their state between runs. `sandbox.code` runs code in them.

| Method | Returns | Summary |
| ------ | ------- | ------- |
| `run(code, *, context=None, language=None, envs=None, timeout_ms=None, request_timeout_ms=None, on_stdout=None, on_stderr=None, on_result=None, on_error=None)` | `Execution` | Runs code in a context (the `default` one unless `context` is set) and returns its output, results and how it ended. An exception in the code is returned in `error`, not raised. A refused run raises an `APIError` whose `reason` says why. |
| `create_context(*, language=None, cwd=None, request_timeout_ms=None)` | `CreatedCodeContext` | Starts a separate kernel with its own state. |
| `list_contexts(*, request_timeout_ms=None)` | `list[CodeContext]` | Lists contexts with their `state`, `generation` and memory use (`rss_mib`). |
| `restart_context(context, *, request_timeout_ms=None)` | `str` | Restarts a context's kernel, dropping its state; returns the new `generation`. |
| `delete_context(context, *, request_timeout_ms=None)` | `None` | Stops a context and frees its kernel; deleting `default` restarts it instead. |

An `Execution` has `stdout`, `stderr`, `logs`, `results`, `text` (the last expression's
value), `error`, `end_reason`, `execution_count`, `generation` and `truncated`; a changed
`generation` means the context's state was lost. `AsyncSandbox` has the same methods with
`await`.

```python
sandbox.code.run("import pandas as pd\ndf = pd.DataFrame({'x': [1, 2, 3]})")
run = sandbox.code.run("int(df.x.sum())")
print(run.text, run.end_reason)  # 6 ok

ctx = sandbox.code.create_context(cwd="project")
sandbox.code.run("import os; print(os.getcwd())", context=ctx)
```

### Terminals and SSH

#### `sandbox.pty`

| Method | Returns | Summary |
| ------ | ------- | ------- |
| `create(program=None, args=None, cols=0, rows=0, id=None, on_data=None)` | `PtyHandle` | Opens an interactive terminal; `on_data` receives output bytes. Pass `id` to reattach to an existing terminal. |

`PtyHandle`: `id`, plus `send_input(data)`, `resize(cols, rows)`, `wait()`, `kill()` and
`disconnect()`.

```python
term = sandbox.pty.create(program="bash", cols=80, rows=24,
                          on_data=lambda data: print(data.decode(), end=""))
term.send_input("ls -la\n")
```

Details: [`api-inventory.md` → Interactive PTY](./api-inventory.md#interactive-pty--sandboxpty)

#### `sandbox.ssh`

| Method | Returns | Summary |
| ------ | ------- | ------- |
| `ssh(port=None, host="127.0.0.1")` | `SshTunnel` | Opens a local port that forwards to the sandbox, for `ssh`, `scp`, `rsync` and IDE remote development. Use it as a context manager, or call `close()`. |

```python
with sandbox.ssh() as tunnel:
    print(f"ssh -p {tunnel.port} neev@localhost")
```

Details: [`api-inventory.md` → SSH tunnel](./api-inventory.md#ssh-tunnel--sandboxssh)

### Low-level connection types

Listed for completeness; prefer the handle methods above.

| Type | Sync | Async |
| ---- | ---- | ----- |
| Connection | `SandboxConnection(connect_url, api_key, ...)` | `AsyncSandboxConnection` |
| Files helper | `SandboxFiles` | `AsyncSandboxFiles` |
| Processes helper | `SandboxProcesses` | `AsyncSandboxProcesses` |
| Code helper | `SandboxCode` | `AsyncSandboxCode` |
| Close | `connection.close()` | `await connection.aclose()` |

Details: [`api-inventory.md` → Runtime connection](./api-inventory.md#runtime-connection)

### Sandbox snippets

Minimal one-liners for each sandbox API, sync and async, with the example that shows it.

| API | Sync snippet | Async snippet | Runnable example |
| --- | ------------ | ------------- | ---------------- |
| `NeevAI(...)` | `with NeevAI() as client:` | `async with AsyncNeevAI() as client:` | [templates_list.py](../examples/templates_list.py), [async_sandbox.py](../examples/async_sandbox.py) |
| `client.close()` / `aclose()` | `with NeevAI() as client:` (auto) | `async with AsyncNeevAI() as client:` (auto) | all tier-1 examples |
| `client.sandboxes.create(...)` | `sandbox = client.sandboxes.create({...})` | `sandbox = await client.sandboxes.create({...})` | [sandbox_lifecycle.py](../examples/sandbox_lifecycle.py), [snapshot_fork_restore.py](../examples/snapshot_fork_restore.py) (`restore`) |
| `client.sandboxes.list(...)` | `page = client.sandboxes.list(name="web", status="Paused")` | `page = await client.sandboxes.list(name="web", status="Paused")` | [sandbox_lifecycle_controller.py](../examples/sandbox_lifecycle_controller.py) |
| `client.sandboxes.list(labels=...)` | `page = client.sandboxes.list(labels={"team": "payments"})` | `page = await client.sandboxes.list(labels={"team": "payments"})` | [sandbox_labels.py](../examples/sandbox_labels.py) |
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
| `client.sandboxes.wait_for_snapshot(id)` | `snap = client.sandboxes.wait_for_snapshot(snap.id)` | `snap = await client.sandboxes.wait_for_snapshot(snap.id)` | — |
| `client.sandboxes.delete_snapshot(id)` | `client.sandboxes.delete_snapshot(snap_id)` | `await client.sandboxes.delete_snapshot(snap_id)` | [snapshot_fork_restore.py](../examples/snapshot_fork_restore.py) |
| `client.sandboxes.rollback(id, snapshot_id)` | `sb = client.sandboxes.rollback(sb.id, snap_id)` | `sb = await client.sandboxes.rollback(sb.id, snap_id)` | — (prefer `restore` create; see [Snapshots](#snapshots-fork-and-rollback)) |
| `client.sandboxes.fork(id, name)` | `fork = client.sandboxes.fork(sb.id, "fork-name")` | `fork = await client.sandboxes.fork(sb.id, "fork-name")` | [snapshot_fork_restore.py](../examples/snapshot_fork_restore.py) (via `sandbox.fork`) |
| `client.templates.list(...)` | `page = client.templates.list(limit=10)` | `page = await client.templates.list(limit=10)` | [templates_list.py](../examples/templates_list.py) |
| `client.templates.get(id)` | `tpl = client.templates.get(template_id)` | `tpl = await client.templates.get(template_id)` | [templates_list.py](../examples/templates_list.py) |
| `client.raw.request(...)` | `data = client.raw.request("GET", path, query={...})` | `data = await client.raw.request("GET", path, query={...})` | [raw_request.py](../examples/raw_request.py) |
| `sandbox.id` / `.name` / `.phase` | `print(sandbox.phase)` | same after `await create` | [sandbox_lifecycle.py](../examples/sandbox_lifecycle.py) |
| `sandbox.connect_url` | `print(sandbox.connect_url)` | `print(sandbox.connect_url)` | [templates_list.py](../examples/templates_list.py) |
| `sandbox.data` | `record = sandbox.data` | `record = sandbox.data` | — |
| `sandbox.refresh()` | `sandbox.refresh()` | `await sandbox.refresh()` | [auto_resume.py](../examples/auto_resume.py) |
| `sandbox.update(params, *, allow_internet, allow_egress)` | `sandbox.update({"resources": {"cpu": 2}}, allow_egress=["api.github.com"])` | `await sandbox.update({"resources": {"cpu": 2}})` | [sandbox_update.py](../examples/sandbox_update.py) |
| `sandbox.wait_until_ready(...)` | `sandbox.wait_until_ready(timeout_ms=120_000)` | `await sandbox.wait_until_ready()` | [sandbox_lifecycle.py](../examples/sandbox_lifecycle.py) |
| `sandbox.pause()` | `sandbox.pause()` | `await sandbox.pause()` | [sandbox_lifecycle.py](../examples/sandbox_lifecycle.py) |
| `sandbox.resume()` | `sandbox.resume()` | `await sandbox.resume()` | [auto_resume.py](../examples/auto_resume.py) |
| `sandbox.keepalive()` | `sandbox.keepalive()` | `await sandbox.keepalive()` | [sandbox_lifecycle_windows.py](../examples/sandbox_lifecycle_windows.py) |
| `sandbox.update_timeout(params)` | `sandbox.update_timeout({"idle_timeout_seconds": 300, "max_lifetime_seconds": 0})` | `await sandbox.update_timeout({"idle_timeout_seconds": 300})` | [sandbox_lifecycle_windows.py](../examples/sandbox_lifecycle_windows.py) |
| `sandbox.snapshot(params=None, ...)` | `pending = sandbox.snapshot({"name": "demo-snap"})` | `pending = await sandbox.snapshot({"name": "demo-snap"})` | [snapshot_fork_restore.py](../examples/snapshot_fork_restore.py) |
| `sandbox.snapshots()` | `snaps = sandbox.snapshots()` | `snaps = await sandbox.snapshots()` | — |
| `sandbox.rollback(snapshot_id)` | `sandbox.rollback(snapshot_id)` | `await sandbox.rollback(snapshot_id)` | — (prefer `restore` create; see [Snapshots](#snapshots-fork-and-rollback)) |
| `sandbox.fork(name)` | `fork = sandbox.fork("fork-name")` | `fork = await sandbox.fork("fork-name")` | [snapshot_fork_restore.py](../examples/snapshot_fork_restore.py) |
| `sandbox.delete()` | `sandbox.delete()` | `await sandbox.delete()` | [sandbox_lifecycle.py](../examples/sandbox_lifecycle.py) |
| `sandbox.metrics(...)` | `metrics = sandbox.metrics()` | `metrics = await sandbox.metrics()` | [sandbox_metrics.py](../examples/sandbox_metrics.py) |
| `sandbox.audit(...)` | `trail = sandbox.audit(limit=50, operation="exec")` | `trail = await sandbox.audit(limit=50)` | [audit_trail.py](../examples/audit_trail.py) |
| `sandbox.addressable` | `print(sandbox.addressable)` | `print(sandbox.addressable)` | — |
| `sandbox.labels` | `print(sandbox.labels)` | `print(sandbox.labels)` | [sandbox_labels.py](../examples/sandbox_labels.py) |
| `sandbox.last_crash` | `crash = sandbox.last_crash` | `crash = sandbox.last_crash` | [last_crash.py](../examples/last_crash.py) |
| `sandbox.expose_port(port)` | `p = sandbox.expose_port(8080)` | `p = await sandbox.expose_port(8080)` | [preview_ports.py](../examples/preview_ports.py) |
| `sandbox.expose_port(port, slug=...)` | `p = sandbox.expose_port(8080, slug="k3x9q2ab")` (rotates the URL) | `p = await sandbox.expose_port(8080, slug="k3x9q2ab")` | [preview_ports.py](../examples/preview_ports.py) |
| `sandbox.list_ports()` | `ports = sandbox.list_ports()` | `ports = await sandbox.list_ports()` | [preview_ports.py](../examples/preview_ports.py) |
| `sandbox.revoke_port(port)` | `sandbox.revoke_port(8080)` | `await sandbox.revoke_port(8080)` | [preview_ports.py](../examples/preview_ports.py) |
| `sandbox.get_url(port, ...)` | `url = sandbox.get_url(8080)` | `url = await sandbox.get_url(8080)` | [preview_ports.py](../examples/preview_ports.py) |
| `sandbox.pty.create(...)` | `pty = sandbox.pty.create(program="sh", on_data=cb)` | `pty = await sandbox.pty.create(program="sh", on_data=cb)` | [pty.py](../examples/pty.py) |
| `sandbox.ssh(...)` | `t = sandbox.ssh()` | `t = await sandbox.ssh()` | [ssh_tunnel.py](../examples/ssh_tunnel.py) |
| `sandbox.code.run(...)` | `run = sandbox.code.run("1 + 1")` | `run = await sandbox.code.run("1 + 1")` | [code_interpreter.py](../examples/code_interpreter.py) |
| `sandbox.code.create_context(...)` | `ctx = sandbox.code.create_context()` | `ctx = await sandbox.code.create_context()` | [code_interpreter.py](../examples/code_interpreter.py) |
| `sandbox.to_json()` | `sandbox.to_json()` | `sandbox.to_json()` | [sandbox_lifecycle_controller.py](../examples/sandbox_lifecycle_controller.py) |
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
| `workflow_examples/*` | Model-driven sandboxes via `StreamingAgentLoop`, not `client.agents` | same | [repo_analyzer.py](../examples/workflow_examples/repo_analyzer.py) |
| `SandboxConnection` (low-level) | via `sandbox.exec` on handle | via `await sandbox.exec` on handle | — |
| `SandboxFiles` (low-level) | via `sandbox.files` property | via `sandbox.files` property | [files_api.py](../examples/files_api.py) |
| `SandboxProcesses` (low-level) | via `sandbox.processes` property | via `sandbox.processes` property | [processes.py](../examples/processes.py) |

---

## Agents

An agent is a catalogue template (such as `"claude-code"`) running on its own sandbox.
Manage it through `client.agents`; reach its files, `exec` and processes through
`agent.sandbox()`. Every method that takes an `id` accepts the agent's name too. Guide:
[Agents](./agents.md).

### `client.agents`

| Method | Returns | Summary |
| ------ | ------- | ------- |
| `create(params, org_id=None, project_id=None, *, allow_internet=None, allow_egress=None)` | `Agent` | Creates an agent from a catalogue template name (`agent_template`). The agent starts with its template's egress rules; `allow_internet=True` / `allow_egress=[...]` replace them, and an explicit `egress` wins over both. |
| `list(page=None, limit=None, org_id=None, project_id=None)` | `AgentPage` | Lists agents with pagination in the resolved org/project scope. |
| `get(id, org_id=None, project_id=None)` | `Agent` | Fetches the current record for an agent by ID or name. |
| `update(id, params, org_id=None, project_id=None, *, allow_internet=None, allow_egress=None)` | `Agent` | In-place update of egress, cpu/memory (`resources`; defaults and bounds in [Agent resources](./api-inventory.md#agent-resources)) and `idle_timeout_seconds`. `allow_internet` / `allow_egress` are the same egress convenience as `create`; `egress_add` / `egress_remove` edit the allow-list in place. Rejects `{}` locally, naming every field. |
| `pause(id, org_id=None, project_id=None)` | `Agent` | Pauses the agent and its backing sandbox. |
| `resume(id, org_id=None, project_id=None)` | `Agent` | Resumes a paused agent. |
| `delete(id, org_id=None, project_id=None)` | `None` | Permanently deletes an agent. |
| `keepalive(id, ...)` / `rollback(id, snapshot_id, ...)` | `Agent` | Resets the idle timer / rolls the backing sandbox back to a snapshot. |
| `create_snapshot(id, params=None, ...)` / `list_snapshots(id, page=None, limit=None, ...)` | `Snapshot` / `list[Snapshot]` | Snapshots the backing sandbox (starts `Pending`) / lists its snapshots. |
| `fork(id, name, ...)` | `Agent` | Forks into a new agent, `Provisioning` until ready; the source keeps running. |
| `expose_port` / `list_ports` / `revoke_port` / `get_port_url` | as on `client.sandboxes` | Agent preview ports, same signatures. |
| `audit(id, *, from_=None, to=None, cursor=None, limit=None, ...)` | `AuditTrail` | The agent's audit trail: the same events and filters as the [sandbox one](#audit-trail). An agent has no `execution_trace` setting. |
| `get_sandbox(sandbox_id, scope)` | `Sandbox` | Fetches an agent's backing sandbox by id; `agent.sandbox()` calls it for you. |

### `client.agent_templates`

| Method | Returns | Summary |
| ------ | ------- | ------- |
| `list(page=None, limit=None)` | `AgentTemplatePage` | Lists available agent templates (global catalogue, no org scope). |
| `get(template_id)` | `AgentTemplate` | Fetches a single agent template by ID. |

### `Agent` handle

`Agent` is returned by `client.agents.create()`, `get()`, `list().items` and `fork()`.

| API | Kind |
| --- | ---- |
| `id`, `name`, `status`, `sandbox_id`, `agent_template_id`, `config`, `last_crash`, `idle_timeout_seconds`, `created_at`, `updated_at`, `data` | properties |
| `refresh()` / `update(params, *, allow_internet=None, allow_egress=None)` | methods |
| `wait_until_ready(timeout_ms=120000, poll_interval_ms=2000, on_poll=None)` | method: polls until `Ready`; fails fast on `Failed` / `Paused` |
| `pause()` / `resume()` / `delete()` | methods |
| `keepalive()` / `rollback(snapshot_id)` / `audit(...)` | methods |
| `snapshot(params=None, *, wait_until_ready=False, timeout_ms=300000, poll_interval_ms=2000)` / `snapshots()` / `fork(name)` | methods: `fork` returns a new `Agent` handle |
| `expose_port(port, *, slug=None)` / `list_ports()` / `revoke_port(port)` / `get_url(port, ..., *, slug=None)` | methods: preview ports |
| `sandbox()` | method: backing `Sandbox` handle for runtime `exec`, `files` and `processes` |
| `to_json()` | method |

### Agent snippets

| API | Sync snippet | Async snippet | Runnable example |
| --- | ------------ | ------------- | ---------------- |
| `client.agents.create(...)` | `agent = client.agents.create({...})` | `agent = await client.agents.create({...})` | [create_agent.py](../examples/create_agent.py) |
| `client.agents.list(...)` | `page = client.agents.list(page=1, limit=20)` | `page = await client.agents.list(page=1, limit=20)` | — |
| `client.agents.get(id)` | `agent = client.agents.get(agent_id)` | `agent = await client.agents.get(agent_id)` | — |
| `client.agents.update(id, params)` | `agent = client.agents.update(id, {"resources": {...}})` | `agent = await client.agents.update(id, {...})` | [create_agent.py](../examples/create_agent.py) |
| `client.agents.pause(id)` / `.resume(id)` | `agent = client.agents.pause(agent_id)` / `client.agents.resume(agent_id)` | `agent = await client.agents.pause(agent_id)` / `await client.agents.resume(agent_id)` | [create_agent.py](../examples/create_agent.py) (pause via handle) |
| `client.agents.delete(id)` | `client.agents.delete(agent_id)` | `await client.agents.delete(agent_id)` | [create_agent.py](../examples/create_agent.py) |
| `client.agents.keepalive(id)` | `client.agents.keepalive(agent_id)` | `await client.agents.keepalive(agent_id)` | [agent_ports_audit.py](../examples/agent_ports_audit.py) |
| `client.agents.rollback(id, snapshot_id)` | `client.agents.rollback(agent_id, snap_id)` | `await client.agents.rollback(agent_id, snap_id)` | [agent_snapshot_fork_rollback.py](../examples/agent_snapshot_fork_rollback.py) (via `agent.rollback`) |
| `client.agents.create_snapshot(id, ...)` | `snap = client.agents.create_snapshot(agent_id, {"name": "demo"})` | `snap = await client.agents.create_snapshot(agent_id, {"name": "demo"})` | [agent_snapshot_fork_rollback.py](../examples/agent_snapshot_fork_rollback.py) (via `agent.snapshot`) |
| `client.agents.list_snapshots(id)` | `snaps = client.agents.list_snapshots(agent_id)` | `snaps = await client.agents.list_snapshots(agent_id)` | [agent_snapshot_fork_rollback.py](../examples/agent_snapshot_fork_rollback.py) (via `agent.snapshots`) |
| `client.agents.fork(id, name)` | `fork = client.agents.fork(agent_id, "fork-name")` | `fork = await client.agents.fork(agent_id, "fork-name")` | [agent_snapshot_fork_rollback.py](../examples/agent_snapshot_fork_rollback.py) (via `agent.fork`) |
| `client.agents.expose_port(id, port, ..., *, slug)` | `p = client.agents.expose_port(agent_id, 3000)` | `p = await client.agents.expose_port(agent_id, 3000)` | [agent_ports_audit.py](../examples/agent_ports_audit.py) |
| `client.agents.audit(id, ...)` | `trail = client.agents.audit(agent_id, limit=50)` | `trail = await client.agents.audit(agent_id, limit=50)` | [agent_ports_audit.py](../examples/agent_ports_audit.py) |
| `client.agent_templates.list(...)` | `page = client.agent_templates.list()` | `page = await client.agent_templates.list()` | [create_agent.py](../examples/create_agent.py) |
| `client.agent_templates.get(id)` | `tpl = client.agent_templates.get(template_id)` | `tpl = await client.agent_templates.get(template_id)` | — |
| `agent.id` / `.status` / `.sandbox_id` | `print(agent.status, agent.sandbox_id)` | same after `await create` | [create_agent.py](../examples/create_agent.py) |
| `agent.wait_until_ready(...)` | `agent.wait_until_ready(timeout_ms=120_000)` | `await agent.wait_until_ready()` | [create_agent.py](../examples/create_agent.py) |
| `agent.refresh()` | `agent.refresh()` | `await agent.refresh()` | [agent_auto_resume.py](../examples/agent_auto_resume.py) |
| `agent.sandbox()` | `sandbox = agent.sandbox()`, then `exec` / `files` / `processes` | `sandbox = await agent.sandbox()` | [create_agent.py](../examples/create_agent.py) |
| `agent.update(params)` | `agent.update({"resources": {...}})` | `await agent.update({...})` | [create_agent.py](../examples/create_agent.py) |
| `agent.pause()` / `.resume()` / `.delete()` | `agent.pause(); agent.resume(); agent.delete()` | `await agent.pause(); await agent.resume(); await agent.delete()` | [create_agent.py](../examples/create_agent.py), [agent_auto_resume.py](../examples/agent_auto_resume.py) (resume) |
| `agent.keepalive()` / `.rollback(snapshot_id)` | `agent.keepalive()` | `await agent.keepalive()` | [agent_ports_audit.py](../examples/agent_ports_audit.py), [agent_snapshot_fork_rollback.py](../examples/agent_snapshot_fork_rollback.py) (rollback) |
| `agent.snapshot(...)` / `.snapshots()` | `snap = agent.snapshot(wait_until_ready=True)` | `snap = await agent.snapshot(wait_until_ready=True)` | [agent_snapshot_fork_rollback.py](../examples/agent_snapshot_fork_rollback.py) |
| `agent.fork(name)` | `fork = agent.fork("fork-name"); fork.wait_until_ready()` | `fork = await agent.fork("fork-name")` | [agent_snapshot_fork_rollback.py](../examples/agent_snapshot_fork_rollback.py) |
| `agent.expose_port(port, *, slug)` / `.list_ports()` / `.revoke_port(port)` / `.get_url(port)` | `p = agent.expose_port(3000)` | `p = await agent.expose_port(3000)` | [agent_ports_audit.py](../examples/agent_ports_audit.py) |
| `agent.audit(...)` | `trail = agent.audit(limit=50)` | `trail = await agent.audit(limit=50)` | [agent_ports_audit.py](../examples/agent_ports_audit.py) |
| `agent.idle_timeout_seconds` | `print(agent.idle_timeout_seconds)` | same | [agent_ports_audit.py](../examples/agent_ports_audit.py) |
| `agent.to_json()` | `agent.to_json()` | `agent.to_json()` | — |

---

## Agent tools

`neevai.agent_tools` binds the sandbox tool contract to one sandbox for your own agent,
with model-ready descriptions and JSON Schemas. No framework dependency. Guide:
[Agent tools](./agent-tools.md).

### `SandboxTools` and `AsyncSandboxTools`

| API | Sync | Async |
| --- | ---- | ----- |
| Tools | `SandboxTools(sandbox, *, allow_preview=False, allow_rollback=False, allow_processes=False)` | `AsyncSandboxTools(sandbox, ...)` |
| Enabled tool names | `tools.names()` | `tools.names()` |
| Run a model tool call | `tools.call(name, args)` | `await tools.call(name, args)` |
| Tool methods | `run_command`, `write_file`, `read_file`, `stat_path`, `move_path`, `delete_path`, `expose_port`, `checkpoint`, `rollback`, `start_process`, `read_process_output`, `stop_process`, `list_processes` | same, with `await` |
| Descriptions / schemas / titles | `DESCRIPTIONS[name]`, `PARAMETERS[name]`, `TITLES[name]` | same |
| Specs for a framework | `tools.specs()` (`spec.call(args)` returns the result) | `tools.specs()` (`await spec.call(args)`) |
| Stop a run on a fatal error | `FatalGuard().call(spec, args)`, then `guard.raise_if_failed()` | `await guard.acall(spec, args)` |
| Fatal result | `FATAL_RESULT`, `FATAL_ERROR` | same |

`SandboxTools` raises `ValueError` if `allow_preview` or `allow_rollback` is set on a
handle with no client context. Every tool returns a JSON-serializable `TypedDict`;
errors the model can fix come back as `{"error": ...}`. `FatalGuard` has `failed`,
`error`, `call`, `acall` and `raise_if_failed`.

Details: [`api-inventory.md` → Agent tools](./api-inventory.md#agent-tools)

### Framework adapters

| Framework | Extra | Adapter | Returns |
| --- | --- | --- | --- |
| Claude Agent SDK | `neevai[claude]` | `neevai.agent_tools.claude.to_claude(tools)` | `ClaudeTools`: `.options()` for `ClaudeAgentOptions`, `.watch(messages)`, `.guard` |
| OpenAI Agents SDK | `neevai[openai-agents]` | `neevai.agent_tools.openai_agents.to_openai_agents(tools)` | `list[FunctionTool]` |
| LangChain / LangGraph | `neevai[langchain]` | `neevai.agent_tools.langchain.to_langchain(tools)` | `list[StructuredTool]` |

Each adapter takes a sync `SandboxTools`. A sandbox error such as an expired key stops the
run instead of being handed back to the model; see
[Stopping on fatal errors](./agent-tools.md#stopping-on-fatal-errors).

### Agent tools snippets

| API | Sync snippet | Async snippet | Runnable example |
| --- | ------------ | ------------- | ---------------- |
| `SandboxTools(...)` | `tools = SandboxTools(sandbox, allow_processes=True)` | `tools = AsyncSandboxTools(sandbox, allow_processes=True)` | [agent_tools_loop.py](../examples/agent_patterns/agent_tools_loop.py) |
| `tools.names()` / `DESCRIPTIONS` / `PARAMETERS` | `specs = [(n, DESCRIPTIONS[n], PARAMETERS[n]) for n in tools.names()]` | same | [agent_tools_loop.py](../examples/agent_patterns/agent_tools_loop.py) |
| `tools.call(name, args)` | `result = tools.call("run_command", {"command": "ls"})` | `result = await tools.call("run_command", {"command": "ls"})` | [agent_tools_loop.py](../examples/agent_patterns/agent_tools_loop.py) |
| `tools.read_process_output(...)` | `tools.read_process_output(pid, wait_s=30)` | `await tools.read_process_output(pid, wait_s=30)` | — |
| `tools.specs()` + `FatalGuard` | `guard.call(spec, args)` | `await guard.acall(spec, args)` | — |

---

## Errors

Every failure is a `NeevAIError`. API failures are `APIError` subclasses with
`status_code`, a machine-readable `code` and a `request_id` for support. Branch on `code`
rather than the message text. Import them from `neevai` or `neevai.errors`. Guide:
[Errors](./errors.md).

| Error | When |
| --- | --- |
| `BadRequestError` | 400: invalid request |
| `AuthenticationError` | 401: missing or invalid API key |
| `PermissionDeniedError` | 403: not allowed |
| `NotFoundError` | 404: no such resource |
| `ConflictError` | 409: conflicting state |
| `PreconditionFailedError` | 412: a precondition of the call failed |
| `TooEarlyError` | 425: not ready yet, such as an agent still provisioning; retry later |
| `RateLimitError` | 429: too many requests |
| `DeadlineExceededError` | 504: the call ran past its deadline |
| `InternalServerError` | Other 5xx (`ServiceUnavailableError` for 503) |
| `APIConnectionError`, `APITimeoutError` | The request did not complete |
| `NeevAIError` | Base class; also raised for client-side failures such as a missing key or a wait that timed out |

`APIError` attributes: `status_code`, `code`, `reason`, `scope`, `details`, `body`,
`request_id`, `request_method`, `request_url`.

Network errors, 429 and 5xx are retried automatically on API calls. Calls inside a
sandbox, such as `exec` and `files.write`, are not retried, because running them twice
could repeat their effect.

Details: [`api-inventory.md` → Errors](./api-inventory.md#errors)
