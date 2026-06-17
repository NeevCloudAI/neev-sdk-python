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
| `NEEVCLOUD_API_KEY` | Bearer token (**required**) |
| `NEEVCLOUD_ORG_ID` | Default organization ID |
| `NEEVCLOUD_PROJECT_ID` | Default project ID |
| `NEEVCLOUD_REGION` | Default deployment region for sandbox create |
| `NEEVCLOUD_BASE_URL` | Control-plane base URL (default: `https://api.ai.neevcloud.com/agent`) |
| `NEEVCLOUD_SANDBOX_TEMPLATE_ID` | Optional sandbox template id (defaults to `sb-ubuntu-26-04-minimal` in examples) |
| `NEEV_AGENT_TEMPLATE` | Optional agent template **name** for `create_agent.py` (default: `claude-code`) |

**Linux / macOS (bash/zsh)** — current session:

```bash
export NEEVCLOUD_API_KEY="your-api-key"
export NEEVCLOUD_ORG_ID="org-abc123"
export NEEVCLOUD_PROJECT_ID="proj-xyz789"
export NEEVCLOUD_REGION="as-south-1"
```

**Windows PowerShell** — current session:

```powershell
$env:NEEVCLOUD_API_KEY = "your-api-key"
$env:NEEVCLOUD_ORG_ID = "org-abc123"
$env:NEEVCLOUD_PROJECT_ID = "proj-xyz789"
$env:NEEVCLOUD_REGION = "as-south-1"
```

**Windows CMD** — current session:

```cmd
set NEEVCLOUD_API_KEY=your-api-key
set NEEVCLOUD_ORG_ID=org-abc123
set NEEVCLOUD_PROJECT_ID=proj-xyz789
set NEEVCLOUD_REGION=as-south-1
```

You can also pass credentials directly when creating the client:

```python
from neevai import NeevAI

with NeevAI(api_key="...", org_id="...", project_id="...", region="...") as client:
    ...
```

## Quick start (from clone)

If you just cloned the repo, follow these steps to reach your first successful run:

1. Clone and enter the repo (see [Install from source (contributors)](#install-from-source-contributors) above if you have not already).
2. Install dependencies: `uv sync`.
3. Set the four required environment variables (`NEEVCLOUD_API_KEY`, `NEEVCLOUD_ORG_ID`, `NEEVCLOUD_PROJECT_ID`, `NEEVCLOUD_REGION`) using the [platform-specific blocks](#configure-credentials) above.
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

with NeevAI(api_key="...", org_id="...", project_id="...", region="...") as client:
    sandbox = client.sandboxes.create({
        "name": "my-sandbox",
        "sandbox_template_id": "<your-sandbox-template-id>",
    })
    sandbox.wait_until_ready()
    result = sandbox.exec("echo Hello World")
    print(result.stdout)
    client.sandboxes.delete(sandbox.id)
```

## Long-running processes

For detached workloads that outlive a single HTTP request, use `sandbox.processes`
(unlike request-scoped `sandbox.exec`). Before `processes.start`, wait for
`connect_url` (it may appear before `phase == "Ready"`), then
`sandbox.wait_until_ready()`, then probe the data plane with
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
    agent.update({"resources": {"cpu": 2, "memory_gb": 4}})
    agent.pause()
    agent.delete()
```

Browse templates with `client.agent_templates.list()` / `.get(id)`. Region is
optional on create — the client injects `default_region` only when set (unlike
sandbox create, which requires a region). See [`examples/create_agent.py`](examples/create_agent.py).

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
| [`snapshot_fork_restore.py`](examples/snapshot_fork_restore.py) | Snapshot → `from_snapshot` rollback → fork |
| [`async_sandbox.py`](examples/async_sandbox.py) | End-to-end `AsyncNeevAI` workflow |
| [`files_api.py`](examples/files_api.py) | `files.write` / `read_text` / `list` |
| [`streaming_exec.py`](examples/streaming_exec.py) | Live `sandbox.exec_stream()` output |
| [`processes.py`](examples/processes.py) | Supervised process lifecycle (start, follow, logs, kill) |
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
| [`api-reference.md`](docs/api-reference.md) | Control-plane vs data-plane API lists + copy-paste snippets |
| [`api-inventory.md`](docs/api-inventory.md) | Full method signatures, types, errors, symbol index |
| [`example-coverage.md`](docs/example-coverage.md) | Example catalog and API → examples lookup |
| [`architecture.md`](docs/architecture.md) | SDK layout and module responsibilities |

Contributors: update docs when the public API changes. See [`docs/development.md`](docs/development.md) for the contributor workflow, typing notes, and test commands.

## License

[Apache 2.0](LICENSE)
