# Getting started

This guide takes you from install to a running sandbox, step by step. For a shorter
overview, see the [README](../README.md).

## Contents

1. [Before you begin](#before-you-begin)
2. [Install](#install)
3. [Set your credentials](#set-your-credentials)
4. [Your first sandbox](#your-first-sandbox)
5. [Choose a template](#choose-a-template)
6. [Long-running processes](#long-running-processes)
7. [The async client](#the-async-client)
8. [Other products](#other-products)
9. [Next steps](#next-steps)

## Before you begin

You need:

- Python 3.10 or later, on Linux, macOS or Windows
- A NeevCloud API key, organization id and project id, from your NeevCloud account

## Install

```bash
pip install neevai
```

Or, with [uv](https://docs.astral.sh/uv/):

```bash
uv add neevai
```

Check that it worked:

```bash
python -c "from neevai import NeevAI; print('ok')"
```

### Run the examples from a clone

The [examples](../examples/README.md) run straight from the repository:

```bash
git clone https://github.com/NeevCloudAI/neev-sdk-python.git
cd neev-sdk-python
uv sync
uv run python examples/templates_list.py
```

Without uv, create a virtual environment and run `pip install -e .` from the
repository root instead.

## Set your credentials

The client reads these environment variables:

| Variable | Purpose |
| --- | --- |
| `NEEV_API_KEY` | Your API key (required) |
| `NEEV_ORG_ID` | Default organization id |
| `NEEV_PROJECT_ID` | Default project id |

Find your organization and project IDs as described in [Organizations and projects](https://docs.ai.neevcloud.com/getting-started/org-and-project#find-your-organization-id-and-project-id).

**Linux and macOS**

```bash
export NEEV_API_KEY="your-api-key"
export NEEV_ORG_ID="your-org-id"
export NEEV_PROJECT_ID="your-project-id"
```

**Windows PowerShell**

```powershell
$env:NEEV_API_KEY = "your-api-key"
$env:NEEV_ORG_ID = "your-org-id"
$env:NEEV_PROJECT_ID = "your-project-id"
```

**Windows Command Prompt**

```cmd
set NEEV_API_KEY=your-api-key
set NEEV_ORG_ID=your-org-id
set NEEV_PROJECT_ID=your-project-id
```

These last for the current terminal session. To keep them, add them to your shell
profile or your system's environment settings. The SDK does not read `.env` files.

You can also pass credentials to the client directly:

```python
from neevai import NeevAI

client = NeevAI(api_key="...", org_id="...", project_id="...")
```

Most methods take `org_id` and `project_id` to override the defaults for one call.

## Your first sandbox

Save this as `quickstart.py` and run it with `python quickstart.py`:

```python
from neevai import NeevAI

with NeevAI() as client:
    sandbox = client.sandboxes.create({"sandbox_template_id": "sb-ubuntu-26-04-dev"})
    print("created", sandbox.id)

    try:
        sandbox.wait_until_ready()

        result = sandbox.exec(["sh", "-c", "echo hello from the sandbox"])
        print(result.stdout, "exit code", result.exit_code)

        sandbox.files.write("notes.txt", "written by the SDK\n")
        print(sandbox.files.read_text("notes.txt"))
    finally:
        sandbox.delete()
```

Good to know:

| Topic | Detail |
| --- | --- |
| Templates | Pass `sandbox_template_id`. Find ids with `client.templates.list()`. |
| Size | Without `resources`, a sandbox gets 1 vCPU, 2 GB memory and 10 GB disk. You can ask for 0.5–8 vCPU (steps of 0.5), 1–16 GB memory and 10–100 GB disk (steps of 10). See [`SandboxResources`](api-inventory.md#sandboxresources). |
| Readiness | Call `wait_until_ready()` before running commands or using files. |
| Names | `client.sandboxes.get()` accepts a sandbox's id or its name. |
| Handles | `pause()` and `resume()` return an updated `Sandbox`. |
| Files | `files.write` handles any size. For large files on disk, use `files.upload_file` and `files.download_file`. |
| Errors | Errors carry a `code` such as `not_found`; branch on it. See [Errors](api-inventory.md#errors). |

Next, try [`sandbox_lifecycle.py`](../examples/sandbox_lifecycle.py) and
[`files_api.py`](../examples/files_api.py), or snapshots with
[`snapshot_fork_restore.py`](../examples/snapshot_fork_restore.py).

## Choose a template

A template is the image a sandbox starts from. `sb-ubuntu-26-04-dev` is a good default;
the others add something specific.

| Template | Use it for |
| --- | --- |
| `sb-ubuntu-26-04-dev` | General development: git, gh, Python 3, Node 24 LTS |
| `sb-ubuntu-26-04-docker` | Docker, Compose and Buildx, with Docker started at boot; run containers with `--network=host` |
| `sb-ubuntu-26-04-interpreter` | The code interpreter: Python kernels that keep their state (`sandbox.code`) |
| `sb-ubuntu-26-04-playwright` | Browser testing: a desktop with Node 24, Playwright and Chromium, headless or headed (`DISPLAY=:1`) |

The catalogue grows over time, so `client.templates.list()` is the source of truth.

```python
browser = client.sandboxes.create({"sandbox_template_id": "sb-ubuntu-26-04-playwright"})
browser.wait_until_ready()
run = browser.exec(["npx", "playwright", "test"], cwd="app", timeout_ms=300_000)
```

## Long-running processes

`exec` waits for a command to finish. For a server or a worker that keeps running, use
`sandbox.processes`: the process keeps going after your request ends, and you can
follow its output, read its logs or stop it later.

```python
sandbox.wait_until_ready()

proc = sandbox.processes.start(["sh", "-c", "echo started; sleep 3"])
for event in proc.follow():
    if event["type"] == "stdout":
        print(event["data"], end="")
proc.wait()
```

Right after a sandbox becomes ready, the first call can briefly fail with a 502, 503 or
504. [`processes.py`](../examples/processes.py) shows a small retry helper for that;
[`process_pool.py`](../examples/process_pool.py) runs several processes at once.

## The async client

`AsyncNeevAI` has the same API. Use `async with` and `await`:

```python
import asyncio

from neevai import AsyncNeevAI

async def main() -> None:
    async with AsyncNeevAI() as client:
        sandbox = await client.sandboxes.create({"sandbox_template_id": "sb-ubuntu-26-04-dev"})
        try:
            await sandbox.wait_until_ready()
            result = await sandbox.exec(["echo", "async hello"])
            print(result.stdout.strip())

            async for event in sandbox.exec_stream(["sh", "-c", "seq 1 3"]):
                if event["type"] == "stdout":
                    print(event["data"], end="")
        finally:
            await sandbox.delete()

asyncio.run(main())
```

See [`async_sandbox.py`](../examples/async_sandbox.py).

## Other products

The same client covers every NeevCloud product in this SDK.

| Product | Start here |
| --- | --- |
| Agents: ready-made coding agents, each on its own sandbox | [Create an agent](#create-an-agent), then [README: Agents](../README.md#agents) |
| Agent tools: sandbox tools for the agent you build | [README: Agent tools](../README.md#agent-tools) |

### Create an agent

An agent is a packaged AI assistant, such as Claude Code, running in its own sandbox.
Pick one from the agent template catalogue and pass its **name** as `agent_template`:

```python
from neevai import NeevAI

with NeevAI() as client:
    print([t.name for t in client.agent_templates.list().items])

    agent = client.agents.create({"name": "my-agent", "agent_template": "claude-code"})
    agent.wait_until_ready()

    sandbox = agent.sandbox()
    print(sandbox.exec(["ls", "-la"]).stdout)

    agent.update({"resources": {"cpu": 2, "memory_gb": 4}})
    agent.pause()
    agent.resume()
    agent.wait_until_ready()
    agent.delete()
```

Agents are different from the [agent examples](../examples/agent_patterns/README.md),
which connect your own model to a sandbox. See
[`create_agent.py`](../examples/create_agent.py).

## Next steps

| Guide | For |
| --- | --- |
| [README](../README.md) | An overview of every feature |
| [API reference](api-reference.md) | Every product and method, grouped by product, with snippets |
| [API inventory](api-inventory.md) | Full signatures, parameter tables, types and errors |
| [Example coverage](example-coverage.md) | Which example shows which API |
| [Examples](../examples/README.md) | Runnable scripts, from basics to complete workflows |
| [Development](development.md) | Contributing to this SDK |
