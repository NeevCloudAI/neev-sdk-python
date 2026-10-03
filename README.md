# NeevAI Python SDK

Official Python client for the [NeevCloud](https://neevcloud.com) AI platform. Use it to
provision sandboxes, run commands, manage files, and integrate with agent workflows.

## Prerequisites

- **Python ≥ 3.10**
- **Supported OS:** Windows, macOS, Linux
- **[uv](https://docs.astral.sh/uv/)** (recommended for running examples from this repo; optional if you use pip and a virtual environment)

See [`docs/getting-started.md`](docs/getting-started.md) for per-OS `uv` install commands and a full walkthrough.

## Installation

```bash
pip install neevai
```

### Install from source (contributors)

Clone the repository and install in editable mode with [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/NeevCloudAI/neev-sdk-python.git
cd neev-sdk-python
uv sync
```

`uv sync` creates a local environment and installs the package in editable mode. Run examples from the repo root with `uv run python ...`.

## Configure credentials

Set these environment variables before running scripts, or pass equivalent kwargs to `NeevAI(...)` / `AsyncNeevAI(...)`.

| Variable | Purpose |
| -------- | ------- |
| `NEEV_API_KEY` | Bearer token (**required**) |
| `NEEV_ORG_ID` | Default organization ID |
| `NEEV_PROJECT_ID` | Default project ID |
| `NEEV_BASE_URL` | Base URL (default: `https://api.ai.neevcloud.com/agent`) |
| `NEEV_SANDBOX_TEMPLATE_ID` | Optional sandbox template id (defaults to `sb-ubuntu-26-04-minimal` in examples) |
| `NEEV_AGENT_TEMPLATE` | Optional agent template **name** for `create_agent.py` (default: `claude-code`) |

**Linux / macOS (bash/zsh)** — current session:

```bash
export NEEV_API_KEY="your-api-key"
export NEEV_ORG_ID="org-abc123"
export NEEV_PROJECT_ID="proj-xyz789"
```

**Windows PowerShell** — current session:

```powershell
$env:NEEV_API_KEY = "your-api-key"
$env:NEEV_ORG_ID = "org-abc123"
$env:NEEV_PROJECT_ID = "proj-xyz789"
```

**Windows CMD** — current session:

```cmd
set NEEV_API_KEY=your-api-key
set NEEV_ORG_ID=org-abc123
set NEEV_PROJECT_ID=proj-xyz789
```

You can also pass credentials directly when creating the client:

```python
from neevai import NeevAI

with NeevAI(api_key="...", org_id="...", project_id="...") as client:
    ...
```

## Quick start (from clone)

If you just cloned the repo, follow these steps to reach your first successful run:

1. Clone and enter the repo (see [Install from source (contributors)](#install-from-source-contributors) above if you have not already).
2. Install dependencies: `uv sync`.
4. Verify the install:

   ```bash
   uv run python -c "from neevai import NeevAI; print('ok')"
   ```

5. Run your first example:

   ```bash
   uv run python examples/templates_list.py
   ```

6. **Expected outcome:** the script lists available sandbox templates, fetches one by id, creates a sandbox from it, waits until it is ready, then deletes it.
7. **Next:** read [`docs/getting-started.md`](docs/getting-started.md) for full sync/async quick-start scripts and the documentation map.

## Minimal code example

```python
from neevai import NeevAI

with NeevAI(api_key="...", org_id="...", project_id="...") as client:
    sandbox = client.sandboxes.create({})
    sandbox.wait_until_ready()
    result = sandbox.exec("echo Hello World")
    print(result.stdout)
    client.sandboxes.delete(sandbox.id)
```

## Detecting a crash

A sandbox that hits an OOM kill or another unexpected stop is restarted for you, so it
reads back as `Ready` — but its filesystem may be gone. `last_crash` is how you tell:

```python
crash = sandbox.last_crash  # None if this sandbox has never crashed
if crash and crash.storage_reset:
    # The sandbox restarted with an empty filesystem: files under /workspace,
    # and anything installed since create, are gone. Re-provision before using it.
    print(f"{crash.reason} at {crash.at}")
```

`crash.storage_reset is False` means it restarted with its files intact. The field records
a past event and is **not** cleared when the sandbox recovers, so check `crash.at` before
reacting to it. Restoring from a snapshot taken before a stop that reset storage brings
the files back and clears `last_crash` once the restore completes. Agents expose the same
`agent.last_crash`. See [`last_crash.py`](examples/last_crash.py).

## Files

Paths are relative to the workspace or absolute within it. `files.write` sends content
up to 1 MiB in one request and anything larger in chunks automatically. For large files
on disk, `upload_file` / `download_file` stream without holding the file in memory:

```python
sandbox.files.write("notes.txt", "hello\n")

# Chunked and resumable: a chunk lost to a dropped connection continues from the
# last byte the sandbox received. chunk_size is 1 MiB by default (64 KiB-1 MiB).
sandbox.files.upload_file("dataset.parquet", "data/dataset.parquet",
                          on_progress=lambda sent, total: print(f"{sent}/{total}"))

# Written beside the target and moved into place when complete: no partial file.
sandbox.files.download_file("data/dataset.parquet", "copy.parquet")
```

`files.upload(path, data)` takes bytes, str, or a seekable binary file object. See
[`upload_download.py`](examples/upload_download.py).

## Preview URLs

Ports are private until exposed. `get_url(port)` exposes one and returns its public,
credential-free URL. The slug in the URL is the only thing gating it, so treat the URL
as a secret; if it leaks, expose the port again with a new `slug` to rotate it:

```python
url = sandbox.get_url(3000)
sandbox.expose_port(3000, slug="k3x9q2mz")  # replaces the slug; the old URL stops working
sandbox.revoke_port(3000)
```

Agents have the same `expose_port` / `list_ports` / `revoke_port` / `get_url`.

## Audit trail

`sandbox.audit()` (and `agent.audit()`) reads what ran inside, newest first — terminal
commands, SSH, process and file operations — with the credential each ran under and how it
ended. Program names are recorded without their arguments. Page with `next_cursor`:

```python
trail = sandbox.audit(limit=50)
for r in trail.records:
    print(r.at, r.tool, r.command or "", r.outcome.value)
older = sandbox.audit(limit=50, cursor=trail.next_cursor) if trail.next_cursor else None
```

See [`audit_trail.py`](examples/audit_trail.py).

## Network egress

Sandboxes (and agents) are **deny-all by default** — no outbound network. Open egress at
create time with the convenience keyword args, on either `sandboxes.create` or
`agents.create`:

```python
# allow the whole internet
client.sandboxes.create({"name": "web", "sandbox_template_id": "..."}, allow_internet=True)

# allow only specific hosts (FQDN or CIDR; wildcards supported)
client.sandboxes.create({"name": "ci", "sandbox_template_id": "..."}, allow_egress=["github.com", "*.npmjs.org"])

# same on agents
client.agents.create({"name": "coder", "agent_template": "claude-code"}, allow_internet=True)
```

`allow_internet=True` opens all outbound traffic (`0.0.0.0/0` and `::/0`). For finer control
(ports, protocols, a mix of rules) pass a full `egress` object in `params` instead — it
takes precedence over the convenience args.

On a running sandbox or agent, `update` either replaces the policy (`egress`) or edits the
allow-list in place, leaving every other rule untouched:

```python
sandbox.update({
    "egress_add": {"allow": [{"host": "pypi.org", "ports": [443]}]},
    "egress_remove": {"allow": [{"host": "github.com"}]},
})
```

## Errors

Every failure raises a `NeevAIError` subclass: `NotFoundError` (404), `ConflictError`
(409), `RateLimitError` (429), `ServiceUnavailableError` (503, worth retrying shortly; a
subclass of `InternalServerError`), and so on. `APIError.code` is a machine-readable
classification such as `not_found` or `sandbox_quota_exceeded` — branch on it rather than
on the message text — and `APIError.scope` names the limit a quota refusal hit:

```python
from neevai.errors import APIError

try:
    client.sandboxes.create({"sandbox_template_id": "sb-ubuntu-26-04-minimal"})
except APIError as e:
    if e.code == "sandbox_quota_exceeded":
        print(f"quota reached for this {e.scope}")
    else:
        raise
```

## Long-running processes

For detached workloads that outlive a single HTTP request, use `sandbox.processes`
(unlike request-scoped `sandbox.exec`). Before `processes.start`, wait for
`connect_url` (it may appear before `phase == "Ready"`), then
`sandbox.wait_until_ready()`, then probe the sandbox runtime with
`sandbox.processes.list()` (retry transient 502/503/504). Tune polling with
`NEEVAI_WAIT_TIMEOUT_MS` and `NEEVAI_POLL_INTERVAL_MS`. See
[Processes API — end-to-end flow](docs/api-inventory.md#processes-api) for auth,
raw endpoints, and troubleshooting.

```python
proc = sandbox.processes.start(["sh", "-c", "echo started; sleep 30"])
for event in proc.follow():
    if event["type"] == "stdout":
        print(event["data"], end="")
    elif event["type"] == "exit":
        print(f"exit {event['exit_code']}")
        break
final = proc.wait()
```

See [`examples/processes.py`](examples/processes.py) and
[`examples/process_pool.py`](examples/process_pool.py).

## Code interpreter

A sandbox created from the interpreter template runs Python in persistent kernels.
Variables, imports and loaded data stay between runs in the same context, so each run
builds on the last:

```python
sandbox = client.sandboxes.create({"sandbox_template_id": "sb-ubuntu-26-04-interpreter"})
sandbox.wait_until_ready()

sandbox.code.run("import pandas as pd\ndf = pd.DataFrame({'x': [1, 2, 3]})")
run = sandbox.code.run(
    "print(df.x.sum())\ndf.describe()",
    on_stdout=lambda out: print(out.line, end=""),  # OutputMessage(line, timestamp, error)
)
run.stdout            # "6\n"
run.text              # the last expression's text, here the describe() table
run.results[0].html   # text, html, markdown, svg, png, jpeg, pdf, latex, json; formats()
run.execution_count   # 2
run.end_reason        # "ok"
```

Code that raises is returned, not raised: `end_reason` is `"error"` and `run.error`
holds `name`, `value` and `traceback`. A run that outlives `timeout_ms` is interrupted
with `end_reason == "deadline_exceeded"` and the context keeps its state;
`"kernel_restarted"` and `"memory_exceeded"` mean the state was lost, which a change in
`run.generation` also tells you. A run on a context that is still busy raises an
`APIError` with `reason == "context_busy"`.

Run options: `context` (a context or its id), `language` (`"python"`, the default
context's language), `envs` (environment variables for this run only, seen by
subprocesses too), `timeout_ms` (the cell's timeout; the sandbox's ceiling is the
default), `request_timeout_ms` (a bound on the whole request), and the `on_stdout` /
`on_stderr` / `on_result` / `on_error` callbacks. `run.logs` holds the output pieces as
they arrived.

```python
sandbox.code.run("import os\nprint(os.environ['STAGE'])", envs={"STAGE": "test"})
```

Each context is a separate kernel with its own state, started in its own working
directory; a run sent while its kernel is still starting waits for it. Runs without a
`context` use the `default` context:

```python
ctx = sandbox.code.create_context(cwd="project")  # CreatedCodeContext(context_id, generation, language, cwd)
sandbox.code.run("import os\nprint(os.getcwd())", context=ctx)
sandbox.code.list_contexts()       # [CodeContext(context_id, state, generation, language, cwd, rss_mib)]
sandbox.code.restart_context(ctx)  # drops its state, returns the new generation
sandbox.code.delete_context(ctx)
```

See [`examples/code_interpreter.py`](examples/code_interpreter.py).

## Agents

Provision a packaged agent from the catalogue template (`agent_template` is the
template **name**, e.g. `"claude-code"`), wait for it to become `Ready`, then
reach its environment through the backing sandbox:

```python
from neevai import NeevAI

with NeevAI(api_key="...", org_id="...", project_id="...") as client:
    agent = client.agents.create({
        "name": "my-agent",
        "agent_template": "claude-code",
    })
    agent.wait_until_ready()
    sandbox = agent.sandbox()
    sandbox.files.write("notes.md", "# scratch\n")
    agent.update({"resources": {"cpu": 2, "memory_gb": 4}, "idle_timeout_seconds": 1800})
    agent.keepalive()  # reset the idle timer while work is in progress
    agent.pause()
    agent.delete()
```

Agents can also be fetched by name (`client.agents.get("my-agent")`), rolled back to a
snapshot (`agent.rollback(snapshot_id)`), serve preview URLs (`agent.expose_port(port)`),
and read their audit trail (`agent.audit()`). See
[`agent_ports_audit.py`](examples/agent_ports_audit.py).

Browse templates with `client.agent_templates.list()` / `.get(id)`. `region` is
optional on agent create. See [`examples/create_agent.py`](examples/create_agent.py).

## Examples

Runnable examples live under [`examples/`](examples/). From the repo root, run any example with:

```bash
uv run python examples/<script>.py
```

See [`examples/README.md`](examples/README.md) for the full catalogue and learning path.

| Example | What it shows |
| ------- | ------------- |
| [`templates_list.py`](examples/templates_list.py) | List templates → get by id → create sandbox |
| [`create_agent.py`](examples/create_agent.py) | Agent templates → create agent → sandbox → update/pause/delete |
| [`sandbox_lifecycle.py`](examples/sandbox_lifecycle.py) | Create → wait → metrics → pause → delete |
| [`last_crash.py`](examples/last_crash.py) | Force an OOM kill → read `last_crash` → check `storage_reset` |
| [`snapshot_fork_restore.py`](examples/snapshot_fork_restore.py) | Snapshot → `restore` → fork |
| [`async_sandbox.py`](examples/async_sandbox.py) | End-to-end `AsyncNeevAI` workflow |
| [`files_api.py`](examples/files_api.py) | `files.write` / `read_text` / `list` |
| [`update_resize_egress.py`](examples/update_resize_egress.py) | Resize + re-scope egress in one update → `egress_add` / `egress_remove` |
| [`upload_download.py`](examples/upload_download.py) | Chunked `upload_file` with progress → `download_file` → compare sizes |
| [`preview_ports.py`](examples/preview_ports.py) | Serve a port → preview URL → rotate the slug → revoke |
| [`audit_trail.py`](examples/audit_trail.py) | Run commands → page through the sandbox audit trail |
| [`agent_ports_audit.py`](examples/agent_ports_audit.py) | Agent preview URL with a slug, keepalive, audit trail |
| [`streaming_exec.py`](examples/streaming_exec.py) | Live `sandbox.exec_stream()` output |
| [`processes.py`](examples/processes.py) | Supervised process lifecycle (start, follow, logs, kill) |
| [`code_interpreter.py`](examples/code_interpreter.py) | `sandbox.code` — state kept between runs, an exception as a result, a second context |
| [`process_pool.py`](examples/process_pool.py) | Parallel processes with `kill_all` |
| [`parallel_fanout.py`](examples/parallel_fanout.py) | 3 sandboxes, parallel repo analysis, aggregated file counts |
| [`sandbox_metrics.py`](examples/sandbox_metrics.py) | Metrics under CPU load |
| [`raw_request.py`](examples/raw_request.py) | Untyped `client.raw.request()` |
| [`agent_patterns/minimal_agent.py`](examples/agent_patterns/minimal_agent.py) | Hand-rolled agent with streaming tool output |
| [`agent_patterns/langchain_agent.py`](examples/agent_patterns/langchain_agent.py) | LangGraph ReAct agent (`uv sync --extra agents`) |
| [`workflow_examples/repo_analyzer.py`](examples/workflow_examples/repo_analyzer.py) | Clone & audit untrusted repos in a sandbox |
| [`sandbox_lifecycle_controller.py`](examples/sandbox_lifecycle_controller.py) | CLI for individual sandbox CRUD ops |

## Documentation

Start with [`docs/getting-started.md`](docs/getting-started.md) for installation, credentials, and your first sync/async script.

| Doc | Purpose |
| --- | ------- |
| [`getting-started.md`](docs/getting-started.md) | Install, env vars, quick starts, doc map |
| [`api-reference.md`](docs/api-reference.md) | Lifecycle vs sandbox runtime lists + copy-paste snippets |
| [`api-inventory.md`](docs/api-inventory.md) | Full method signatures, types, errors, symbol index |
| [`example-coverage.md`](docs/example-coverage.md) | Example catalog and API → examples lookup |

Contributors: update docs when the public API changes. See [`docs/development.md`](docs/development.md) for the contributor workflow, typing notes, and test commands.

## License

[Apache 2.0](LICENSE)
