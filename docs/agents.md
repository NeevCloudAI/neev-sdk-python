# Agents

An agent is a ready-made coding agent, such as Claude Code, running on its own sandbox.
You choose an agent template, and the SDK manages the agent's life and gives you its
sandbox to work with. Every method that takes an agent id also accepts its name.

An agent's sandbox is an ordinary `Sandbox` handle, so the [Sandboxes guide](./sandboxes.md)
applies to it too; this page covers what is specific to agents. The snippets use the sync
client; `AsyncNeevAI` has the same methods with `await`.

| Capability | API | Example |
| --- | --- | --- |
| [Create and manage agents](#create-and-manage-agents) | `client.agents.create / list / get / update / pause / resume / delete` | [`create_agent.py`](../examples/create_agent.py) |
| [Agent templates](#agent-templates) | `client.agent_templates.list / get` | [`create_agent.py`](../examples/create_agent.py) |
| [Work inside an agent](#work-inside-an-agent) | `agent.sandbox()` | [`create_agent.py`](../examples/create_agent.py) |
| [Network access](#network-access) | `agent.update()` with `egress_add` / `egress_remove` | [`create_agent.py`](../examples/create_agent.py) |
| [Preview URLs](#preview-urls) | `agent.get_url()`, `agent.expose_port()` | [`agent_ports_audit.py`](../examples/agent_ports_audit.py) |
| [Snapshots and fork](#snapshots-and-fork) | `agent.snapshot() / snapshots() / fork() / rollback()` | [`agent_snapshot_fork_rollback.py`](../examples/agent_snapshot_fork_rollback.py) |
| [Audit trail](#audit-trail) | `agent.audit()` | [`agent_ports_audit.py`](../examples/agent_ports_audit.py) |

## Create and manage agents

`create`, `get` and `list` return an `Agent` handle.

```python
agent = client.agents.create({"name": "my-coder", "agent_template": "claude-code"})
agent.wait_until_ready()

agent.update({"resources": {"cpu": 2, "memory_gb": 4}, "idle_timeout_seconds": 1800})
agent.pause()
agent.resume()
agent.keepalive()  # reset the idle timer
agent.delete()
```

`wait_until_ready()` polls until the agent is `Ready`, and raises `NeevAIError` at once
if it is `Failed` or `Paused`. Forking an agent that is still provisioning raises
`TooEarlyError` (425), so wait and retry; forking a paused one raises `ConflictError`. `idle_timeout_seconds` sets the idle window, and
`0` removes it. Resources take the same values as a sandbox's.

Pausing an agent pauses its sandbox. As with a sandbox, calls that run inside a paused
agent's sandbox wake it where automatic wake-up is enabled; see
[Pause and wake](./sandboxes.md#pause-and-wake) and
[`agent_auto_resume.py`](../examples/agent_auto_resume.py).

See [`create_agent.py`](../examples/create_agent.py) · [reference](./api-reference.md#clientagents)

## Agent templates

An agent template is the agent you run, such as `claude-code`. Pass its name as
`agent_template` when you create an agent.

```python
page = client.agent_templates.list()
print([t.name for t in page.items])
template = client.agent_templates.get(page.items[0].id)
```

The catalogue grows over time, so `agent_templates.list()` is the source of truth.

See [`create_agent.py`](../examples/create_agent.py) · [reference](./api-reference.md#clientagent_templates)

## Work inside an agent

`agent.sandbox()` returns the agent's sandbox as a `Sandbox` handle, so files, commands,
processes and terminals work exactly as they do on any sandbox.

```python
sandbox = agent.sandbox()
sandbox.wait_until_ready()
sandbox.files.write("task.md", "# scratch\n")
result = sandbox.exec(["git", "clone", "https://github.com/acme/app"])
```

See [Commands and processes](./sandboxes.md#commands-and-processes) and
[Files](./sandboxes.md#files) for the full set.

Agents here are different from the [agent examples](../examples/agent_patterns/README.md),
which connect your own model to a sandbox through [Agent tools](./agent-tools.md).

See [`create_agent.py`](../examples/create_agent.py) · [reference](./api-reference.md#agent-handle)

## Network access

An agent starts with its template's egress rules, which allow what the agent needs.
`allow_internet` and `allow_egress` on `create` replace those rules rather than add to
them, so to allow one more host, create the agent first and then add it in place:

```python
agent.update({"egress_add": {"allow": [{"host": "api.example.com", "ports": [443]}]}})
agent.update({"egress_remove": {"allow": [{"host": "api.example.com"}]}})
```

This needs the agent to have an allow-list; if its template allows nothing, open it with
`allow_egress` or `egress` first. `egress_add` and `egress_remove` can't be combined with a full `egress` policy or with
`allow_internet` / `allow_egress` in the same call. See
[Network egress](./sandboxes.md#network-egress) for the rule format.

See [`create_agent.py`](../examples/create_agent.py) · [reference](./api-reference.md#clientagents)

## Preview URLs

When the agent builds a web app, expose its port to try it in a browser. `get_url` waits
until the URL answers.

```python
url = agent.get_url(3000)
port = agent.expose_port(3000, slug="k3x9q2ab")  # a new slug rotates the URL
agent.revoke_port(3000)
```

Anyone with the URL can open it, so treat it as a secret. See
[Preview URLs](./sandboxes.md#preview-urls).

See [`agent_ports_audit.py`](../examples/agent_ports_audit.py) · [reference](./api-reference.md#clientagents)

## Snapshots and fork

Snapshot an agent before a risky change, roll it back in place if the change goes wrong,
or fork it into a new agent to try something in parallel.

```python
snap = agent.snapshot({"name": "before-change"}, wait_until_ready=True)
print([s.name for s in agent.snapshots()])

fork = agent.fork("my-coder-alt")  # a new agent from the current state
fork.wait_until_ready()

agent.rollback(snap.id)  # back to the snapshot, in place
```

A snapshot starts `Pending`; `wait_until_ready=True` waits until it is `Ready`. The
fork is a new `Agent` that is `Provisioning` until it is ready, and the source agent keeps
running. `client.agents.create_snapshot`, `list_snapshots` and `fork` do the same by
agent id.

See [`agent_snapshot_fork_rollback.py`](../examples/agent_snapshot_fork_rollback.py) · [reference](./api-reference.md#clientagents)

## Audit trail

An agent keeps the same audit trail as a sandbox: calls, programs and connections, as
OCSF events in `trail.data`, with the same filters.

```python
trail = agent.audit(limit=50)
for e in trail.data:
    if e.api:  # only API Activity events have api
        print(e.time, e.api.operation, e.status)
```

An agent has no `execution_trace` setting. See [Audit trail](./sandboxes.md#audit-trail)
for the event classes.

See [`agent_ports_audit.py`](../examples/agent_ports_audit.py) · [reference](./api-reference.md#clientagents)
