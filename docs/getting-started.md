# NeevAI Python SDK — Getting Started

Install the SDK, configure credentials, and run your first synchronous or
asynchronous script. For a shorter overview, see the [README](../README.md).
When you need API lists, method signatures, or example line numbers, use the
[documentation map](#documentation-map) below.

## Prerequisites

Before installing, confirm you have:

- **Python ≥ 3.10** (`python --version` or `python3 --version`)
- A supported OS: **Windows**, **macOS**, or **Linux**
- A NeevCloud API key and org/project/region values (from your NeevCloud account)

The package depends on `httpx` and `pydantic` for HTTP transport and response
validation. These are installed automatically with the SDK.

### Install uv (recommended)

[uv](https://docs.astral.sh/uv/) is the easiest way to install from this repo and
run examples. It creates a local virtual environment and installs the package in
editable mode.

**Linux / macOS:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Or use your system package manager if available.

**Windows (PowerShell):**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

If you prefer not to use `uv`, see the pip + virtual environment fallback in
[Option B](#option-b--install-from-github-recommended-today) below.

---

## Installation and setup

### Option A — PyPI (coming soon; try first)

When the package is published, this is the primary install path:

```bash
pip install neevai
```

When this succeeds, you are done — skip Option B.

If `pip install neevai` fails with **package not found**, use Option B today.

### Option B — Install from GitHub (recommended today)

Clone the repository:

```bash
git clone https://github.com/NeevCloudAI/neev-sdk-python.git
cd neev-sdk-python
```

**Recommended (uv):**

```bash
uv sync
```

`uv sync` creates a local environment and installs the package in editable mode.
Run examples from the repo root with `uv run python ...`.

**Fallback (pip + virtual environment):**

| Platform | Commands |
| -------- | -------- |
| **Linux / macOS** | `python3 -m venv .venv && source .venv/bin/activate && pip install -e .` |
| **Windows PowerShell** | `python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -e .` |
| **Windows CMD** | `python -m venv .venv && .venv\Scripts\activate.bat && pip install -e .` |

### Verify installation

From the repo root (after Option B) or any environment where the package is
installed (after Option A):

```bash
uv run python -c "from neevai import NeevAI; print('ok')"
```

If you used pip and an activated virtual environment instead of `uv`, run:

```bash
python -c "from neevai import NeevAI; print('ok')"
```

You should see `ok`. If the import fails, confirm you ran `uv sync` or
`pip install -e .` from the repo root.

Contributors can run the full test suite without network access — see
[`development.md`](./development.md) for `uv run pytest` and other commands.

### Configure credentials

The SDK reads defaults from environment variables. Set these before running scripts
or pass equivalent constructor kwargs to `NeevAI(...)` / `AsyncNeevAI(...)`.

| Variable | Purpose |
| -------- | ------- |
| `NEEVCLOUD_API_KEY` | Bearer token (**required**) |
| `NEEVCLOUD_ORG_ID` | Default organization ID |
| `NEEVCLOUD_PROJECT_ID` | Default project ID |
| `NEEVCLOUD_REGION` | Default deployment region for sandbox create |
| `NEEVCLOUD_BASE_URL` | Control-plane base URL (default: `https://api.ai.neevcloud.com/agent`) |
| `NEEVCLOUD_SANDBOX_TEMPLATE_ID` | Optional template id (defaults to `sb-ubuntu-26-04-minimal` in examples) |
| `NEEVAI_WAIT_TIMEOUT_MS` | Shared deadline for connect URL, Ready phase, and data-plane probe (default: `300000`) |
| `NEEVAI_POLL_INTERVAL_MS` | Poll interval while waiting for connect URL / data plane (default: `2000`) |

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

**Persistence:** The commands above apply only to your current terminal session.
To keep credentials across restarts, set them as user-level environment variables
in your OS settings (Windows System Properties → Environment Variables, macOS/Linux
shell profile, or your preferred secrets manager). The SDK does not load a
`.env` file automatically.

You can override org, project, or region on individual API calls via `org_id` and
`project_id` keyword arguments without changing the client defaults.

### Imports

```python
from neevai import NeevAI, AsyncNeevAI, Sandbox
from neevai.types import CreateSandboxParams, ExecResult, SandboxPhase
from neevai.errors import NeevAIError, NotFoundError, AuthenticationError
```

The top-level `neevai` package re-exports clients, handles, connection types,
errors, and `Scope`. Control-plane models live in `neevai.types` and should be
imported from there (not from generated modules directly).

---

## From clone to your first sandbox

This section walks through the full path from a fresh clone to a running sandbox.

1. **Clone and install**

   ```bash
   git clone https://github.com/NeevCloudAI/neev-sdk-python.git
   cd neev-sdk-python
   uv sync
   ```

2. **Set credentials** using the [platform-specific blocks](#configure-credentials)
   above. You need at minimum `NEEVCLOUD_API_KEY`, `NEEVCLOUD_ORG_ID`,
   `NEEVCLOUD_PROJECT_ID`, and `NEEVCLOUD_REGION`.

3. **Verify the install** (see [Verify installation](#verify-installation)).

4. **Run the first example:**

   ```bash
   uv run python examples/templates_list.py
   ```

5. **Interpret the output.** The script will:
   - List available sandbox templates (id, name, status)
   - Fetch full detail for one template
   - Create a sandbox from that template and wait until it is ready
   - Delete the sandbox in a `finally` block

   If you see authentication or permission errors, double-check your API key and
   org/project ids. If the package is not found, re-run `uv sync` from the repo
   root.

6. **Continue learning** with the sync quick-start below, or follow the tiered
   path in [`examples/README.md`](../examples/README.md).

---

## Quick start — synchronous

This walkthrough creates a sandbox, waits for it to become ready, runs a command,
writes a file, and cleans up.

Save the script below as `quickstart.py` in the repo root (or any directory where
the `neevai` package is installed), then run:

```bash
uv run python quickstart.py
```

If you use an activated virtual environment instead of `uv`:

```bash
python quickstart.py
```

```python
from neevai import NeevAI

with NeevAI() as client:
    # 1. Pick a template from the catalogue
    templates = client.templates.list(limit=5)
    template_id = templates.items[0].id
    print(f"Using template: {templates.items[0].name} ({template_id})")

    # 2. Create a sandbox (region defaults from NEEVCLOUD_REGION or client)
    sandbox = client.sandboxes.create({
        "name": "quickstart-demo",
        "sandbox_template_id": template_id,
        "region": "as-south-1",
    })
    print(f"Created sandbox {sandbox.id}, phase={sandbox.phase}")

    # 3. Poll until the data plane is reachable
    sandbox.wait_until_ready(timeout_ms=120_000)
    print(f"Ready — connect_url={sandbox.connect_url}")

    # 4. Run a buffered command
    result = sandbox.exec(["sh", "-c", "echo hello from sandbox"])
    print(f"stdout={result.stdout!r}, exit_code={result.exit_code}")

    # 5. Write and read a file (paths are workspace-relative)
    sandbox.files.write("notes.txt", "written by the SDK\n")
    text = sandbox.files.read_text("notes.txt")
    print(f"File contents: {text!r}")

    # 6. Clean up
    sandbox.delete()
    print("Sandbox deleted")
```

Key points:

- Use `sandbox_template_id` in create params (not `template_id`). See
  [`api-inventory.md`](./api-inventory.md#clientsandboxescreateparams-org_idnone-project_idnone)
  for the full parameter table.
- `connect_url` is a property on the handle; it may appear while `phase` is still
  `Pending` or `NotReady`. Wait until `phase == "Ready"` **and** the data plane
  accepts requests before `exec`, `files`, or `processes`.
- `sandbox.pause()` and `sandbox.resume()` return updated `Sandbox` handles (they do
  not return `None`).
- Always call `wait_until_ready()` before data-plane operations; for supervised
  processes, also probe with `sandbox.processes.list()` (see
  [Supervised processes](#supervised-processes)).

**Examples:** [`sandbox_lifecycle.py`](../examples/sandbox_lifecycle.py),
[`files_api.py`](../examples/files_api.py)

For snapshot capture, rollback via `from_snapshot`, and fork workflows, see
[`snapshot_fork_restore.py`](../examples/snapshot_fork_restore.py) and the
[Snapshots](./api-reference.md#snapshots) section in the API reference.

---

## Supervised processes

Detached processes outlive the HTTP request that started them — useful for
long-running workers, log streaming, and process pools. Before calling
`sandbox.processes.start`, complete this sequence (shared deadline via
`NEEVAI_WAIT_TIMEOUT_MS` / `NEEVAI_POLL_INTERVAL_MS`):

1. Poll `sandbox.refresh()` until `connect_url` is set (may appear before
   `phase == "Ready"`).
2. Call `sandbox.wait_until_ready()` until `phase == "Ready"`.
3. Probe the data plane with `sandbox.processes.list()` — retry transient
   `502` / `503` / `504` until the daemon accepts requests.

[`examples/processes.py`](../examples/processes.py) implements the full wait
helpers (`_wait_for_connect_url`, `_wait_for_dataplane`, `_wait_before_processes`).
Use it as the reference for production code.

```python
# Minimal inline version (see processes.py for retry helpers)
while not sandbox.connect_url:
    sandbox.refresh()
sandbox.wait_until_ready(timeout_ms=120_000)
sandbox.processes.list()  # probe data plane

proc = sandbox.processes.start(["sh", "-c", "echo started; sleep 3"])
for event in proc.follow():
    if event["type"] == "stdout":
        print(event["data"], end="")
proc.kill()
proc.wait()
```

Full end-to-end flow (auth headers, raw HTTP, troubleshooting):
[`api-inventory.md` → End-to-end flow](./api-inventory.md#end-to-end-flow).
Runnable examples: [`processes.py`](../examples/processes.py),
[`process_pool.py`](../examples/process_pool.py).

---

## Quick start — asynchronous

The async client mirrors the sync API. Use `async with`, `await`, and `async for`
where appropriate.

Save as `quickstart_async.py` and run with `uv run python quickstart_async.py`
(or `python quickstart_async.py` inside an activated venv).

```python
import asyncio
from neevai import AsyncNeevAI

async def main() -> None:
    async with AsyncNeevAI() as client:
        template_id = (await client.templates.list(limit=1)).items[0].id

        sandbox = await client.sandboxes.create({
            "name": "async-demo",
            "sandbox_template_id": template_id,
            "region": "as-south-1",
        })
        await sandbox.wait_until_ready()

        # Buffered exec
        result = await sandbox.exec(["echo", "async hello"])
        print(result.stdout.strip())

        # Streaming exec
        async for event in sandbox.exec_stream(["sh", "-c", "seq 1 3"]):
            if event["type"] == "stdout":
                print(event["data"], end="")
            elif event["type"] == "exit":
                print(f"\nexit {event['exit_code']}")

        await sandbox.delete()

asyncio.run(main())
```

**Example:** [`async_sandbox.py`](../examples/async_sandbox.py)

---

## Documentation map

| Document | What you'll find |
| -------- | ---------------- |
| [README](../README.md) | Short install overview, clone-to-first-run checklist, examples table |
| **Getting started** (this file) | Full install walkthrough, env vars, first sync/async script, [supervised processes](#supervised-processes) |
| [`api-reference.md`](./api-reference.md) | Control-plane vs data-plane API lists and copy-paste snippets |
| [`api-inventory.md`](./api-inventory.md) | Full method signatures, parameter tables, types, errors, symbol index |
| [`api-inventory.md` → Processes E2E](./api-inventory.md#end-to-end-flow) | connect_url wait, auth, raw HTTP, curl/PowerShell, troubleshooting |
| [`example-coverage.md`](./example-coverage.md) | Example catalog and API → examples lookup |
| [`architecture.md`](./architecture.md) | SDK layout and module responsibilities |
| [`development.md`](./development.md) | Contributor workflow and doc maintenance |
| [`examples/README.md`](../examples/README.md) | Tiered learning path and run commands |
