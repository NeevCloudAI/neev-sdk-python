# NeevCloud SDK for Python

The official Python client for NeevCloud, published as `neevai`.

[![PyPI](https://img.shields.io/pypi/v/neevai)](https://pypi.org/project/neevai/)
[![Python](https://img.shields.io/pypi/pyversions/neevai)](https://pypi.org/project/neevai/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![CI](https://github.com/NeevCloudAI/neev-sdk-python/actions/workflows/python-ci.yml/badge.svg)](https://github.com/NeevCloudAI/neev-sdk-python/actions/workflows/python-ci.yml)

One package for the NeevCloud products you build with: Sandboxes, Agents and Agent tools
today, with more to come. It works sync or async, with one client, one API key, and
typed requests, responses and errors.

## Contents

- [Install](#install)
- [Quick start](#quick-start)
- [Products](#products)
- [Sandboxes](#sandboxes)
- [Agents](#agents)
- [Agent tools](#agent-tools)
- [Errors](#errors)
- [Configuration](#configuration)
- [Examples](#examples)
- [Documentation](#documentation)
- [Security](#security)
- [License](#license)

## Install

```bash
pip install neevai
# or
uv add neevai
```

Requires Python 3.10 or later, on Linux, macOS or Windows.

## Quick start

Set your credentials:

```bash
export NEEV_API_KEY="your-api-key"
export NEEV_ORG_ID="your-org-id"
export NEEV_PROJECT_ID="your-project-id"
```

Find your organization and project IDs as described in [Organizations and projects](https://docs.ai.neevcloud.com/getting-started/org-and-project#find-your-organization-id-and-project-id).

Create a sandbox, run a command, read a file, and clean up:

```python
from neevai import NeevAI

with NeevAI() as client:  # reads the NEEV_* variables
    sandbox = client.sandboxes.create({"sandbox_template_id": "sb-ubuntu-26-04-dev"})
    try:
        sandbox.wait_until_ready()
        result = sandbox.exec(["python3", "-c", "print(6 * 7)"])
        print(result.stdout)  # 42

        sandbox.files.write("hello.txt", "hello from NeevCloud\n")
        print(sandbox.files.read_text("hello.txt"))
    finally:
        sandbox.delete()
```

`AsyncNeevAI` offers the same API with `async`/`await`. See
[`async_sandbox.py`](examples/async_sandbox.py).

## Products

| Product | What it is | Entry point | Guide |
| --- | --- | --- | --- |
| Sandboxes | Isolated machines that run your code, commands and servers | `client.sandboxes`, `client.templates` | [Sandboxes](#sandboxes) |
| Agents | Ready-made coding agents, such as Claude Code, each on its own sandbox | `client.agents`, `client.agent_templates` | [Agents](#agents) |
| Agent tools | A sandbox tool set, with model-ready schemas, for the agent you build | `neevai.agent_tools` | [Agent tools](#agent-tools) |

## Sandboxes

A sandbox is an isolated machine for running code, commands and servers. You create it
from a template, work inside it, and pause or delete it when you are done.

| Capability | API | Example |
| --- | --- | --- |
| [Sandbox lifecycle](#sandbox-lifecycle) | `client.sandboxes.create / list / get / update / pause / resume / delete` | [`sandbox_lifecycle.py`](examples/sandbox_lifecycle.py) |
| [Templates](#templates) | `client.templates.list / get` | [`templates_list.py`](examples/templates_list.py) |
| [Files](#files) | `sandbox.files` | [`files_api.py`](examples/files_api.py) |
| [Commands and processes](#commands-and-processes) | `sandbox.exec()`, `sandbox.processes` | [`processes.py`](examples/processes.py) |
| [Terminals and SSH](#terminals-and-ssh) | `sandbox.pty`, `sandbox.ssh()` | [`pty.py`](examples/pty.py) |
| [Preview URLs](#preview-urls) | `sandbox.get_url()`, `sandbox.expose_port()` | [`preview_ports.py`](examples/preview_ports.py) |
| [Snapshots, fork and rollback](#snapshots-fork-and-rollback) | `sandbox.snapshot() / fork() / rollback()` | [`snapshot_fork_restore.py`](examples/snapshot_fork_restore.py) |
| [Network egress](#network-egress) | `allow_internet`, `allow_egress`, `egress` | [`update_resize_egress.py`](examples/update_resize_egress.py) |
| [Labels](#labels) | `labels=` on create and list | [`sandbox_labels.py`](examples/sandbox_labels.py) |
| [Metrics](#metrics) | `sandbox.metrics()` | [`sandbox_metrics.py`](examples/sandbox_metrics.py) |
| [Audit trail](#audit-trail) | `sandbox.audit()` | [`audit_trail.py`](examples/audit_trail.py) |
| [Code interpreter](#code-interpreter) | `sandbox.code` | [`code_interpreter.py`](examples/code_interpreter.py) |

### Sandbox lifecycle

`create`, `get` and `list` return a `Sandbox` handle. Its lifecycle methods act on that
sandbox, and `get` accepts an id or a name.

```python
sandbox = client.sandboxes.create({"name": "build-1", "sandbox_template_id": "sb-ubuntu-26-04-dev"})
sandbox.wait_until_ready()

sandbox.pause()  # release compute; files and running processes are kept
sandbox.resume()
sandbox.update({"resources": {"cpu": 2, "memory_gb": 4}})  # resize in place

page = client.sandboxes.list(status="Paused", limit=50)
sandbox.delete()
```

Lifecycle windows stop a sandbox from running forever. Durations are in seconds.

| Option | Meaning |
| --- | --- |
| `idle_timeout_seconds` | Act after this long with no activity |
| `on_idle` | `"pause"` or `"delete"` |
| `max_lifetime_seconds` | Hard limit on total lifetime |

Set them in `lifecycle` at create time, change them with `sandbox.update_timeout(...)`,
and reset the idle timer with `sandbox.keepalive()`.

See [`sandbox_lifecycle.py`](examples/sandbox_lifecycle.py) · [`sandbox_lifecycle_windows.py`](examples/sandbox_lifecycle_windows.py) · [reference](docs/api-reference.md#clientsandboxes)

### Templates

A template is the image a sandbox starts from. Omit `sandbox_template_id` to use the
default, or pick one from the catalogue.

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
own image instead, pass `image` (a public OCI image with a tag or digest).

Playwright and Chromium come preinstalled on the Playwright template, so a project that
pins the same Playwright version runs its tests with nothing to download:

```python
browser = client.sandboxes.create({"sandbox_template_id": "sb-ubuntu-26-04-playwright"})
browser.wait_until_ready()
run = browser.exec(["npx", "playwright", "test"], cwd="app", timeout_ms=300_000)
```

See [`docker.py`](examples/docker.py) · [`byoi_create.py`](examples/byoi_create.py) · [reference](docs/api-reference.md#templates)

### Files

Paths are relative to the sandbox workspace, or absolute inside it.

```python
sandbox.files.write("main.py", "print('hi')")
text = sandbox.files.read_text("main.py")
entries = sandbox.files.list(".")

sandbox.files.move("main.py", "app.py")
sandbox.files.remove("build", recursive=True)
```

Large writes are sent in resumable chunks automatically. `upload_file` and
`download_file` move files between local disk and the sandbox without buffering them,
and `files.watch` streams changes as they happen.

See [`files_api.py`](examples/files_api.py) · [`upload_download.py`](examples/upload_download.py) · [reference](docs/api-reference.md#files)

### Commands and processes

`exec` runs a command to completion and returns its output. A non-zero exit code is
returned, not raised.

```python
result = sandbox.exec(["ls", "-la"])
print(result.exit_code, result.stdout)

# Stream output as it is produced.
for event in sandbox.exec_stream(["npm", "test"]):
    print(event)
```

For work that should outlive one call, such as a dev server or a watcher, start a
background process instead:

```python
server = sandbox.processes.start(["python3", "-m", "http.server", "8000"])
for event in server.follow():
    if event["type"] == "stdout":
        print(event["data"], end="")
        break
server.kill()
```

See [`processes.py`](examples/processes.py) · [`streaming_exec.py`](examples/streaming_exec.py) · [reference](docs/api-reference.md#commands-and-processes)

### Terminals and SSH

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

See [`pty.py`](examples/pty.py) · [`ssh_tunnel.py`](examples/ssh_tunnel.py) · [reference](docs/api-reference.md#terminals-and-ssh)

### Preview URLs

Expose a port and get a public HTTPS URL for it. `get_url` waits until the URL answers.

```python
sandbox.processes.start(["python3", "-m", "http.server", "3000"])
url = sandbox.get_url(3000)
```

Anyone with the URL can open it, so treat it as a secret. Rotate it with
`sandbox.expose_port(3000, slug=...)`, and close the port with `sandbox.revoke_port(3000)`.

See [`preview_ports.py`](examples/preview_ports.py) · [reference](docs/api-reference.md#clientsandboxes)

### Snapshots, fork and rollback

A snapshot captures a sandbox's full state: its files and the memory of its running
processes. Roll the sandbox back to it later, fork the
sandbox's current state into a new one, or restore a snapshot into a new sandbox.

```python
snap = sandbox.snapshot({"name": "checkpoint"}, wait_until_ready=True)
sandbox.rollback(snap.id)  # back to the snapshot, in place
copy = sandbox.fork("my-fork")  # a new sandbox from the current state
restored = client.sandboxes.create({"restore": snap.id})  # a new sandbox from the snapshot
```

See [`snapshot_fork_restore.py`](examples/snapshot_fork_restore.py) · [reference](docs/api-reference.md#snapshots-fork-and-rollback)

### Network egress

A sandbox has no outbound network unless you allow it, apart from any its template
allows (the Docker template allows Docker Hub and GHCR).

```python
client.sandboxes.create({"sandbox_template_id": "sb-ubuntu-26-04-dev"}, allow_internet=True)
client.sandboxes.create({"sandbox_template_id": "sb-ubuntu-26-04-dev"}, allow_egress=["github.com", "*.pypi.org"])

# Edit a running sandbox's allow-list in place.
sandbox.update({"egress_add": {"allow": [{"host": "pypi.org", "ports": [443]}]}})
```

For ports and protocols, pass a full `egress` policy instead.

See [`update_resize_egress.py`](examples/update_resize_egress.py) · [reference](docs/api-reference.md#clientsandboxes)

### Labels

Tag sandboxes at create time and find them again by label.

```python
client.sandboxes.create({"sandbox_template_id": "sb-ubuntu-26-04-dev"}, labels={"team": "payments"})
page = client.sandboxes.list(labels={"team": "payments"})
```

See [`sandbox_labels.py`](examples/sandbox_labels.py) · [reference](docs/api-reference.md#clientsandboxes)

### Metrics

Read CPU, memory and disk usage over a time window.

```python
metrics = sandbox.metrics(step="60s")
```

See [`sandbox_metrics.py`](examples/sandbox_metrics.py) · [reference](docs/api-reference.md#clientsandboxes)

### Audit trail

Read what happened inside a sandbox, newest first, as OCSF 1.9.0 events in three classes:
calls made to it (API Activity, `class_uid` 6003), every program that ran in it, including
ones no call asked for (Process Activity, 1007), and every connection those programs
opened (Network Activity, 4001). Programs are recorded by name only, never with their arguments.

```python
trail = sandbox.audit(limit=50)
for e in trail.data:
    # A recorded program has no api; its process names it instead.
    proc = e.process or e.actor.process
    what = e.api.operation if e.api else (proc.name if proc else None)
    print(e.time, e.type_name, what, e.status)
```

Filter with `status` (every class), or `operation`, `actor_type`, `actor_uid`,
`credential_uid` (calls only), and page back with `cursor=trail.next_cursor`. Calls take a
few seconds to appear, programs and connections about a minute. Turn program recording off
with `sandbox.update({"execution_trace": False})`.

See [`audit_trail.py`](examples/audit_trail.py) · [reference](docs/api-reference.md#audit-trail)

### Code interpreter

Sandboxes created from `sb-ubuntu-26-04-interpreter` run Python in kernels that keep
their state between runs.

```python
sandbox = client.sandboxes.create({"sandbox_template_id": "sb-ubuntu-26-04-interpreter"})

sandbox.code.run("import pandas as pd\ndf = pd.DataFrame({'x': [1, 2, 3]})")
run = sandbox.code.run("int(df.x.sum())")
print(run.text)  # "6"
```

An exception in your code is returned in `run.error`, not raised. Use
`sandbox.code.create_context()` for separate kernels with their own state.

See [`code_interpreter.py`](examples/code_interpreter.py) · [reference](docs/api-reference.md#code-interpreter)

## Agents

An agent is a ready-made coding agent, such as Claude Code, running on its own sandbox.
You choose an agent template, and the SDK manages the agent's life and gives you its
sandbox to work with.

| Capability | API | Example |
| --- | --- | --- |
| [Agent lifecycle](#agent-lifecycle) | `client.agents.create / list / get / update / pause / resume / delete` | [`create_agent.py`](examples/create_agent.py) |
| [Agent templates](#agent-templates) | `client.agent_templates.list / get` | [`create_agent.py`](examples/create_agent.py) |
| [Preview URLs and audit trail](#preview-urls-and-audit-trail) | `agent.get_url()`, `agent.expose_port()`, `agent.audit()` | [`agent_ports_audit.py`](examples/agent_ports_audit.py) |
| [Working inside the agent's sandbox](#working-inside-the-agents-sandbox) | `agent.sandbox()` | [`create_agent.py`](examples/create_agent.py) |

### Agent lifecycle

`create`, `get` and `list` return an `Agent` handle, and `get` accepts an id or a name.

```python
agent = client.agents.create({"name": "my-coder", "agent_template": "claude-code"})
agent.wait_until_ready()

agent.update({"idle_timeout_seconds": 1800})  # also resources and egress
agent.pause()
agent.resume()
agent.keepalive()  # reset the idle timer
agent.delete()
```

`agent.rollback(snapshot_id)` restores the agent's sandbox to a snapshot in place.

See [`create_agent.py`](examples/create_agent.py) · [reference](docs/api-reference.md#agents)

### Agent templates

An agent template is the agent you run, such as `claude-code`. Pass its name as
`agent_template` when you create an agent.

```python
page = client.agent_templates.list()
```

See [`create_agent.py`](examples/create_agent.py) · [reference](docs/api-reference.md#agent-templates)

### Preview URLs and audit trail

Agents expose ports and keep an audit trail the same way sandboxes do.

```python
url = agent.get_url(3000)
trail = agent.audit(limit=50)
```

See [`agent_ports_audit.py`](examples/agent_ports_audit.py) · [reference](docs/api-reference.md#agents)

### Working inside the agent's sandbox

`agent.sandbox()` returns the agent's sandbox as a `Sandbox` handle, so files, commands
and processes work exactly as they do on any sandbox.

```python
sandbox = agent.sandbox()
sandbox.files.write("task.md", "# scratch\n")
result = sandbox.exec(["ls"])
```

See [`create_agent.py`](examples/create_agent.py) · [reference](docs/api-reference.md#agents)

## Agent tools

`neevai.agent_tools` gives the agent you build a ready-made set of sandbox tools, with
descriptions and JSON schemas written for a model. Use it with any model API, or
through an adapter for your agent framework.

| Capability | API | Example |
| --- | --- | --- |
| [The tool contract](#the-tool-contract) | `SandboxTools`, `DESCRIPTIONS`, `PARAMETERS`, `FatalGuard` | [`agent_tools_loop.py`](examples/agent_patterns/agent_tools_loop.py) |
| [Framework adapters](#framework-adapters) | `to_claude`, `to_openai_agents`, `to_langchain` | [`agent_patterns/`](examples/agent_patterns/README.md) |

### The tool contract

```python
import json

from neevai.agent_tools import DESCRIPTIONS, PARAMETERS, SandboxTools

tools = SandboxTools(sandbox, allow_processes=True)
specs = [
    {"name": n, "description": DESCRIPTIONS[n], "parameters": PARAMETERS[n]}
    for n in tools.names()
]

# For each tool call from the model:
result = tools.call(tool_call.name, json.loads(tool_call.arguments))
```

| Tools | Enabled |
| --- | --- |
| `run_command`, `write_file`, `read_file`, `stat_path`, `move_path`, `delete_path` | Always |
| `expose_port` | `allow_preview=True` |
| `checkpoint`, `rollback` | `allow_rollback=True` |
| `start_process`, `read_process_output`, `stop_process`, `list_processes` | `allow_processes=True` |

Mistakes the model can fix come back as `{"error": ...}`. Authentication, rate-limit,
server and network failures raise. `FatalGuard` turns those into one fixed error for the
model, stops later calls, and re-raises the first failure to you. `AsyncSandboxTools`
works with `AsyncSandbox`.

See [`agent_tools_loop.py`](examples/agent_patterns/agent_tools_loop.py) · [reference](docs/api-reference.md#agent-tools)

### Framework adapters

Adapters turn the tools into a framework's own tools. Install the matching extra.

| Framework | Extra | Adapter |
| --- | --- | --- |
| Claude Agent SDK | `neevai[claude]` | `neevai.agent_tools.claude.to_claude` |
| OpenAI Agents SDK | `neevai[openai-agents]` | `neevai.agent_tools.openai_agents.to_openai_agents` |
| LangChain and LangGraph | `neevai[langchain]` | `neevai.agent_tools.langchain.to_langchain` |

```python
from agents import Agent, Runner

from neevai.agent_tools import SandboxTools
from neevai.agent_tools.openai_agents import to_openai_agents

agent = Agent(name="coder", tools=to_openai_agents(SandboxTools(sandbox)))
result = await Runner.run(agent, prompt)
```

A sandbox failure that the model can't fix stops the run and is raised to you.

See [`agent_patterns/`](examples/agent_patterns/README.md) · [reference](docs/api-reference.md#framework-adapters)

## Errors

Every failure is a `NeevAIError`. API failures are `APIError` subclasses with the HTTP
status (`status_code`), a machine-readable `code` and a `request_id` for support.

```python
from neevai.errors import APIError, NotFoundError

try:
    client.sandboxes.get("missing")
except NotFoundError:
    ...  # handle a missing sandbox
except APIError as e:
    print(e.status_code, e.code, e.request_id)
```

| Error | When |
| --- | --- |
| `BadRequestError` | 400: invalid request |
| `AuthenticationError` | 401: missing or invalid API key |
| `PermissionDeniedError` | 403: not allowed |
| `NotFoundError` | 404: no such resource |
| `ConflictError` | 409: conflicting state |
| `RateLimitError` | 429: too many requests |
| `InternalServerError` | 5xx (`ServiceUnavailableError` for 503) |
| `APIConnectionError`, `APITimeoutError` | The request did not complete |

Branch on `e.code` rather than the message text. Network errors, 429 and 5xx are
retried automatically. Calls inside a sandbox, such as `exec` and `files.write`, are not
retried, because running them twice could repeat their effect.

## Configuration

Pass options to `NeevAI(...)`, or set the matching environment variables. They apply to
every product.

| Option | Environment variable | Default |
| --- | --- | --- |
| `api_key` | `NEEV_API_KEY` | Required |
| `org_id` | `NEEV_ORG_ID` | Required for most calls |
| `project_id` | `NEEV_PROJECT_ID` | Required for most calls |
| `timeout_ms` | | `60000` |
| `max_retries` | | `2` |

Find your organization and project IDs as described in [Organizations and projects](https://docs.ai.neevcloud.com/getting-started/org-and-project#find-your-organization-id-and-project-id).

Every method also accepts `org_id` and `project_id` to override the client's defaults for
one call.

For an endpoint the SDK does not wrap yet, `client.raw.request(method, path)` sends a
request with the same authentication, retries and errors.

## Examples

Runnable scripts live in [`examples/`](examples); see its
[README](examples/README.md) for setup and the full list.

### Sandboxes

| Example | What it shows |
| --- | --- |
| [`sandbox_lifecycle.py`](examples/sandbox_lifecycle.py) | Create, wait, metrics, pause, delete |
| [`templates_list.py`](examples/templates_list.py) | Browse templates and create a sandbox |
| [`files_api.py`](examples/files_api.py) | Write, read and list files |
| [`upload_download.py`](examples/upload_download.py) | Large file upload and download |
| [`processes.py`](examples/processes.py) | Background processes: start, follow, kill |
| [`streaming_exec.py`](examples/streaming_exec.py) | Live command output |
| [`pty.py`](examples/pty.py) | Interactive terminal |
| [`ssh_tunnel.py`](examples/ssh_tunnel.py) | SSH, scp and rsync through a local port |
| [`preview_ports.py`](examples/preview_ports.py) | Serve a port at a public URL |
| [`snapshot_fork_restore.py`](examples/snapshot_fork_restore.py) | Snapshot, restore and fork |
| [`audit_trail.py`](examples/audit_trail.py) | Read and filter the audit trail |
| [`code_interpreter.py`](examples/code_interpreter.py) | Python with state kept between runs |
| [`docker.py`](examples/docker.py) | Docker inside a sandbox |
| [`async_sandbox.py`](examples/async_sandbox.py) | The async client |

### Agents

| Example | What it shows |
| --- | --- |
| [`create_agent.py`](examples/create_agent.py) | Create and drive an agent |
| [`agent_ports_audit.py`](examples/agent_ports_audit.py) | An agent's preview URL, keepalive and audit trail |

### Agent tools

| Example | What it shows |
| --- | --- |
| [`agent_tools_loop.py`](examples/agent_patterns/agent_tools_loop.py) | Sandbox tools for your own agent |
| [`agent_patterns/`](examples/agent_patterns/README.md) | Agents that use a sandbox as a tool, with and without a framework |

## Documentation

| Guide | For |
| --- | --- |
| [Getting started](docs/getting-started.md) | Install, credentials and a first sandbox, step by step |
| [API reference](docs/api-reference.md) | Every product and method, with snippets |
| [API inventory](docs/api-inventory.md) | Full signatures, types and errors |
| [Example coverage](docs/example-coverage.md) | Which example shows which API |
| [Changelog](.github/CHANGELOG.md) | What changed in each release |
| [NeevCloud documentation](https://docs.ai.neevcloud.com) | Platform guides and concepts |

## Security

Report vulnerabilities as described in [SECURITY.md](SECURITY.md). Keep your API key out
of source control and logs. Contributions are welcome; see [docs/development.md](docs/development.md).

## License

[Apache-2.0](LICENSE) © NeevCloud
