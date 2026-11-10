# Sandboxes

A sandbox is an isolated machine for running code, commands and servers. You create it
from a template, work inside it, and pause or delete it when you are done. Every method
that takes a sandbox id also accepts its name.

The snippets use the sync client, `NeevAI`. `AsyncNeevAI` has the same methods: add
`await`, and use `async for` where a method streams. See
[`async_sandbox.py`](../examples/async_sandbox.py).

| Capability | API | Example |
| --- | --- | --- |
| [Sandbox lifecycle](#sandbox-lifecycle) | `client.sandboxes.create / list / get / update / delete`, `sandbox.metrics()` | [`sandbox_lifecycle.py`](../examples/sandbox_lifecycle.py) |
| [Templates](#templates) | `client.templates.list / get` | [`templates_list.py`](../examples/templates_list.py) |
| [Commands and processes](#commands-and-processes) | `sandbox.exec()`, `sandbox.exec_stream()`, `sandbox.processes` | [`processes.py`](../examples/processes.py) |
| [Files](#files) | `sandbox.files` | [`files_api.py`](../examples/files_api.py) |
| [Code interpreter](#code-interpreter) | `sandbox.code` | [`code_interpreter.py`](../examples/code_interpreter.py) |
| [Terminals and SSH](#terminals-and-ssh) | `sandbox.pty`, `sandbox.ssh()` | [`pty.py`](../examples/pty.py) |
| [Preview URLs](#preview-urls) | `sandbox.get_url()`, `sandbox.expose_port()` | [`preview_ports.py`](../examples/preview_ports.py) |
| [Network egress](#network-egress) | `allow_internet`, `allow_egress`, `egress_add`, `egress_remove` | [`update_resize_egress.py`](../examples/update_resize_egress.py) |
| [Snapshots, fork and rollback](#snapshots-fork-and-rollback) | `sandbox.snapshot() / fork() / rollback()` | [`snapshot_fork_restore.py`](../examples/snapshot_fork_restore.py) |
| [Labels](#labels) | `labels=` on create and list | [`sandbox_labels.py`](../examples/sandbox_labels.py) |
| [Audit trail](#audit-trail) | `sandbox.audit()` | [`audit_trail.py`](../examples/audit_trail.py) |
| [Pause and wake](#pause-and-wake) | `sandbox.pause() / resume()` | [`auto_resume.py`](../examples/auto_resume.py) |

## Sandbox lifecycle

`create`, `get` and `list` return a `Sandbox` handle. Its methods act on that sandbox and
update the handle in place.

```python
sandbox = client.sandboxes.create({"name": "build-1", "sandbox_template_id": "sb-ubuntu-26-04-dev"})
sandbox.wait_until_ready()

sandbox.update({"resources": {"cpu": 2, "memory_gb": 4}})  # resize in place, no restart
page = client.sandboxes.list(status="Ready", limit=50)
same = client.sandboxes.get("build-1")
sandbox.delete()
```

Without `resources`, a sandbox gets 1 vCPU, 2 GB memory and 10 GB disk. You can ask for
0.5 to 8 vCPU (steps of 0.5), 1 to 16 GB memory and 10 to 100 GB disk (steps of 10).
`update` resizes CPU and memory; disk size is fixed at create time. `list` filters by
`name` (a substring), `status` and `labels`.

Call `wait_until_ready()` before running commands or using files. It polls until the
sandbox is `Ready` and can be reached, and raises `NeevAIError` if the sandbox is
`Paused` or the timeout (120 s by default) runs out.

Lifecycle windows stop a sandbox from running forever. Durations are in seconds, and `0`
turns a limit off.

| Option | Meaning |
| --- | --- |
| `idle_timeout_seconds` | Act after this long with no activity |
| `on_idle` | `"pause"` (the default) or `"delete"` |
| `max_lifetime_seconds` | Act this long after create, whatever the activity |
| `paused_retention_seconds` | Delete the sandbox once it has stayed paused this long |

Omit an option to use your account's default.

Set them in `lifecycle` at create time, change them with `sandbox.update_timeout(...)`,
and reset the idle timer with `sandbox.keepalive()`.

```python
sandbox = client.sandboxes.create({
    "sandbox_template_id": "sb-ubuntu-26-04-dev",
    "lifecycle": {"idle_timeout_seconds": 600, "on_idle": "pause"},
})
sandbox.update_timeout({"idle_timeout_seconds": 1800, "max_lifetime_seconds": 0})
sandbox.keepalive()
```

Read CPU, memory and disk usage over a time window with `metrics`, and the most recent
unexpected stop with `last_crash` (`None` if there has been none; `storage_reset` is
`True` when the sandbox came back with an empty workspace).

```python
metrics = sandbox.metrics(step="60s")
crash = sandbox.last_crash
```

See [`sandbox_lifecycle.py`](../examples/sandbox_lifecycle.py) · [`sandbox_lifecycle_windows.py`](../examples/sandbox_lifecycle_windows.py) · [`sandbox_metrics.py`](../examples/sandbox_metrics.py) · [`last_crash.py`](../examples/last_crash.py) · [reference](./api-reference.md#clientsandboxes)

## Templates

A template is the image a sandbox starts from. Omit `sandbox_template_id` to use the
platform default, or pick one from the catalogue.

```python
page = client.templates.list()
template = client.templates.get("sb-ubuntu-26-04-dev")
```

Templates you can start from:

| Template | Use it for |
| --- | --- |
| `sb-ubuntu-26-04-dev` | General development: git, gh, Python 3, Node 24 LTS |
| `sb-ubuntu-26-04-docker` | Docker, Compose and Buildx, with Docker started at boot; run containers with `--network=host` |
| `sb-ubuntu-26-04-interpreter` | The [code interpreter](#code-interpreter): Python kernels that keep their state |
| `sb-ubuntu-26-04-playwright` | Browser testing: a desktop with Node 24, Playwright and Chromium, headless or headed (`DISPLAY=:1`) |

The catalogue grows over time, so `templates.list()` is the source of truth. To use your
own image instead, pass `image` (a public OCI image with a tag or digest) and, if it
needs one, `command`.

```python
sandbox = client.sandboxes.create({"image": "docker.io/library/python:3.12", "command": ["sleep", "infinity"]})
```

Playwright and Chromium come preinstalled on the Playwright template, so a project that
pins the same Playwright version runs its tests with nothing to download:

```python
browser = client.sandboxes.create({"sandbox_template_id": "sb-ubuntu-26-04-playwright"})
browser.wait_until_ready()
run = browser.exec(["npx", "playwright", "test"], cwd="app", timeout_ms=300_000)
```

See [`templates_list.py`](../examples/templates_list.py) · [`docker.py`](../examples/docker.py) · [`byoi_create.py`](../examples/byoi_create.py) · [reference](./api-reference.md#clienttemplates)

## Commands and processes

`exec` runs a command to completion and returns its output. A non-zero exit code is
returned, not raised.

```python
result = sandbox.exec(["ls", "-la"])
print(result.exit_code, result.stdout)

result = sandbox.exec(["npm", "test"], cwd="app", env={"CI": "1"}, timeout_ms=300_000)

# Stream output as it is produced.
for event in sandbox.exec_stream(["npm", "test"]):
    print(event)
```

A command that prints nothing for about 2 minutes is cut off by the network in front of
the sandbox, whatever its `timeout_ms`, and may keep running. Start quiet or long jobs
with `sandbox.processes.start(...)` instead.

A list runs the program directly, without a shell; use `["sh", "-c", "..."]` for pipes,
`&&` and redirects.

For work that should outlive one call, such as a dev server or a watcher, start a
background process instead. It keeps running after your request ends, and you can follow
its output, read its logs or stop it later.

```python
server = sandbox.processes.start(["python3", "-m", "http.server", "8000"])
for event in server.follow():
    if event["type"] == "stdout":
        print(event["data"], end="")
        break
server.kill()
```

`sandbox.processes.list()` shows running and recently exited processes, and
`kill_all()` stops every one. Right after a sandbox becomes ready, the first call can
briefly fail with a 502, 503 or 504; [`processes.py`](../examples/processes.py) shows a
small retry helper for that.

See [`processes.py`](../examples/processes.py) · [`process_pool.py`](../examples/process_pool.py) · [`streaming_exec.py`](../examples/streaming_exec.py) · [reference](./api-reference.md#commands-and-processes)

## Files

Paths are relative to the sandbox workspace, or absolute inside it; a path outside the
workspace is refused.

```python
sandbox.files.write("main.py", "print('hi')")
text = sandbox.files.read_text("main.py")
entries = sandbox.files.list(".", recursive=True)

sandbox.files.move("main.py", "app.py")
sandbox.files.remove("build", recursive=True)
```

Large writes are sent in resumable chunks automatically. `upload_file` and
`download_file` move files between local disk and the sandbox without buffering them,
`read` and `read_text` take `offset` and `length` to read part of a file, and
`files.watch` streams changes as they happen.

```python
sandbox.files.upload_file("dataset.bin", "data/dataset.bin")
sandbox.files.download_file("out/report.pdf", "report.pdf")
head = sandbox.files.read_text("server.log", length=4096)
```

See [`files_api.py`](../examples/files_api.py) · [`upload_download.py`](../examples/upload_download.py) · [reference](./api-reference.md#files)

## Code interpreter

Sandboxes created from `sb-ubuntu-26-04-interpreter` run Python in kernels that keep
their state between runs.

```python
sandbox = client.sandboxes.create({"sandbox_template_id": "sb-ubuntu-26-04-interpreter"})
sandbox.wait_until_ready()

sandbox.code.run("import pandas as pd\ndf = pd.DataFrame({'x': [1, 2, 3]})")
run = sandbox.code.run("int(df.x.sum())")
print(run.text)  # "6"
```

An exception in your code is returned in `run.error`, with `run.end_reason` set to
`"error"`, not raised. Use `sandbox.code.create_context()` for separate kernels with
their own state, and pass `on_stdout` to see output as it arrives.

```python
ctx = sandbox.code.create_context(cwd="project")
sandbox.code.run("import os; print(os.getcwd())", context=ctx,
                 on_stdout=lambda out: print(out.line, end=""))
```

See [`code_interpreter.py`](../examples/code_interpreter.py) · [reference](./api-reference.md#code-interpreter)

## Terminals and SSH

`sandbox.pty` opens an interactive terminal. You send keystrokes and receive output
through a callback.

```python
term = sandbox.pty.create(program="bash", cols=80, rows=24,
                          on_data=lambda data: print(data.decode(), end=""))
term.send_input("ls -la\n")
```

`sandbox.ssh()` opens a local port that forwards to the sandbox, so `ssh`, `scp`,
`rsync` and IDE remote development work with no keys to manage.

```python
with sandbox.ssh() as tunnel:
    print(f"ssh -p {tunnel.port} neev@localhost")
```

See [`pty.py`](../examples/pty.py) · [`ssh_tunnel.py`](../examples/ssh_tunnel.py) · [reference](./api-reference.md#terminals-and-ssh)

## Preview URLs

Expose a port and get a public HTTPS URL for it. `get_url` waits until the URL answers.

```python
sandbox.processes.start(["python3", "-m", "http.server", "3000"])
url = sandbox.get_url(3000)
```

Anyone with the URL can open it, so treat it as a secret. Rotate it with
`sandbox.expose_port(3000, slug=...)`, list exposed ports with `sandbox.list_ports()`,
and close one with `sandbox.revoke_port(3000)`.

See [`preview_ports.py`](../examples/preview_ports.py) · [reference](./api-reference.md#clientsandboxes)

## Network egress

A sandbox has no outbound network unless you allow it, apart from any its template
allows (the Docker template allows Docker Hub and GHCR).

```python
client.sandboxes.create({"sandbox_template_id": "sb-ubuntu-26-04-dev"}, allow_internet=True)
client.sandboxes.create({"sandbox_template_id": "sb-ubuntu-26-04-dev"}, allow_egress=["github.com", "pypi.org", "files.pythonhosted.org"])

# Edit a running sandbox's allow-list in place.
sandbox.update({"egress_add": {"allow": [{"host": "pypi.org", "ports": [443]}]}})
sandbox.update({"egress_remove": {"allow": [{"host": "github.com"}]}})
```

`allow_internet` and `allow_egress` work on `create` and `update`, and replace the whole
policy. `egress_add` and `egress_remove` edit the existing allow-list without restating
it, and can't be combined with a full policy in the same call. They need an allow-list to
edit: on a sandbox that still has no outbound network, open it with `allow_egress` or
`egress` first. To set ports or a protocol for a host, use an `egress_add` or `egress`
rule; `allow_egress` takes host names only.

See [`update_resize_egress.py`](../examples/update_resize_egress.py) · [`sandbox_update.py`](../examples/sandbox_update.py) · [reference](./api-reference.md#clientsandboxes)

## Snapshots, fork and rollback

A snapshot captures a sandbox's full state: its files and the memory of its running
processes. Roll the sandbox back to it later, fork the sandbox's current state into a
new one, or restore a snapshot into a new sandbox.

```python
snap = sandbox.snapshot({"name": "checkpoint"}, wait_until_ready=True)
sandbox.rollback(snap.id)  # back to the snapshot, in place
copy = sandbox.fork("my-fork")  # a new sandbox from the current state
restored = client.sandboxes.create({"restore": snap.id})  # a new sandbox from the snapshot
```

A snapshot starts `Pending`; `wait_until_ready=True`, or
`client.sandboxes.wait_for_snapshot(snap.id)`, waits until it is `Ready`. Pass
`"snapshot_type": "filesystem"` to capture `/workspace` only, which restores onto any
sandbox image, and `"retain_for": "720h"` to let it expire. To recover, prefer
`create({"restore": ...})`, which leaves the original sandbox untouched, over an
in-place `rollback`.

See [`snapshot_fork_restore.py`](../examples/snapshot_fork_restore.py) · [reference](./api-reference.md#snapshots-fork-and-rollback)

## Labels

Tag sandboxes at create time and find them again by label.

```python
client.sandboxes.create({"sandbox_template_id": "sb-ubuntu-26-04-dev"}, labels={"team": "payments"})
page = client.sandboxes.list(labels={"team": "payments"})
print(page.items[0].labels)
```

A sandbox takes up to 16 labels. `list(labels=...)` keeps only sandboxes that carry
every label you give, and `sandbox.labels` is `{}` when a sandbox has none.

See [`sandbox_labels.py`](../examples/sandbox_labels.py) · [reference](./api-reference.md#clientsandboxes)

## Audit trail

Read what happened inside a sandbox, newest first, as OCSF 1.9.0 events in `trail.data`,
in three classes: calls made to it (API Activity, `class_uid` 6003), every program that
ran in it, including ones no call asked for (Process Activity, 1007), and every
connection those programs opened (Network Activity, 4001). Programs are recorded by name
only, never with their arguments.

```python
trail = sandbox.audit(limit=50)
for e in trail.data:
    # Only API Activity events have api; a program's process names it instead.
    proc = e.process or e.actor.process
    what = e.api.operation if e.api else (proc.name if proc else None)
    print(e.time, e.type_name, what, e.status)
```

Filter with `status` (every class), or `operation`, `actor_type`, `actor_uid`,
`credential_uid` (calls only), and page back with `cursor=trail.next_cursor`. Calls take
a few seconds to appear, programs and connections about a minute. Turn program and
connection recording off with `sandbox.update({"execution_trace": False})`; calls are
still recorded, and `sandbox.execution_trace` reports the setting.

See [`audit_trail.py`](../examples/audit_trail.py) · [reference](./api-reference.md#audit-trail)

## Pause and wake

`pause()` stops a sandbox's compute and keeps its state: files and the memory of running
processes. `resume()` brings it back where it left off. Set `on_idle` to `"pause"` to
have this happen on its own after an idle window.

```python
sandbox.pause()
sandbox.resume()
```

You don't always have to resume first. Calls that run inside the sandbox (`exec`,
`files`, `processes`, `code` and `pty`) on a `Paused` sandbox that still has a
`connect_url` are sent as usual, and where the platform's automatic wake-up is enabled
they wake it: one slow response instead of an error. If such a call raises
`RateLimitError` (429) and the sandbox is still `Paused`, call `resume()` and retry.

```python
import time

from neevai.errors import RateLimitError

try:
    result = sandbox.exec(["cat", "notes.txt"])  # wakes the sandbox where wake-up is enabled
except RateLimitError:
    if sandbox.refresh().phase != "Paused":
        raise
    sandbox.resume()
    while sandbox.refresh().phase == "Paused":  # wait_until_ready() raises while Paused
        time.sleep(2)
    sandbox.wait_until_ready()
    result = sandbox.exec(["cat", "notes.txt"])
```

Only retry a command that is safe to run twice. `wait_until_ready()` on a handle that is
still `Paused` raises at once rather than waiting, so wait for the phase to change after
`resume()` as above.

See [`auto_resume.py`](../examples/auto_resume.py) · [`sandbox_lifecycle.py`](../examples/sandbox_lifecycle.py) · [reference](./api-reference.md#sandbox-handle)
