# Examples

Runnable examples for the NeevAI Python SDK (`neevai`). Install the package from
the repo root, set credentials, then run scripts with `uv run`. For an API →
example lookup and minimal snippets per symbol, see
[`docs/example-coverage.md`](../docs/example-coverage.md).

## Quick setup (once)

From the repository root:

```sh
uv sync
```

**Linux / macOS (bash/zsh):**

```sh
export NEEV_API_KEY=...        # sandbox API key (required)
export NEEV_ORG_ID=...
export NEEV_PROJECT_ID=...
```

**Windows PowerShell:**

```powershell
$env:NEEV_API_KEY = "..."
$env:NEEV_ORG_ID = "..."
$env:NEEV_PROJECT_ID = "..."
```

By default examples target the **production** API
(`https://api.ai.neevcloud.com/agent`).

Template id defaults to `sb-ubuntu-26-04-minimal`; override with:

```sh
export NEEV_SANDBOX_TEMPLATE_ID=sb-ubuntu-26-04-minimal
```

For platform agent create (`create_agent.py`), pick a catalogue template name:

```sh
export NEEV_AGENT_TEMPLATE=claude-code   # default when unset
```

Run every command below from the **repo root** unless noted otherwise.

## Platform agents vs model integration

Two different "agent" concepts appear in this repo:

- **Platform agents** (`client.agents`, Tier 1 [`create_agent.py`](./create_agent.py))
  — provision a packaged agent from the catalogue onto its own backing sandbox.
  No inference key required.
- **Model integration** (Tier 2 [`agent_patterns/`](./agent_patterns/)) — wire
  `gpt-oss-120b` (or another model) into a sandbox as a code-execution tool.
  See [`agent_patterns/README.md`](./agent_patterns/README.md).

Tier 3 [`workflow_examples/`](./workflow_examples/) builds on the model
integration helpers for end-to-end demos with local artifacts.

## Learning path

Examples are organized in three tiers — start at Tier 1 and work your way up:

```text
examples/
├── templates_list.py             ← Tier 1: Core Sandbox
├── create_agent.py               ← Tier 1: Agent lifecycle (platform agents API)
├── sandbox_lifecycle.py
├── snapshot_fork_restore.py
├── async_sandbox.py
├── files_api.py
├── streaming_exec.py
├── processes.py
├── process_pool.py
├── sandbox_metrics.py
├── parallel_fanout.py
├── raw_request.py
├── sandbox_lifecycle_controller.py
│
├── agent_patterns/               ← Tier 2: Agent Integration
│   ├── minimal_agent.py          ← start here
│   └── langchain_agent.py
│
└── workflow_examples/            ← Tier 3: Real-World Workflows
    ├── repo_analyzer.py          ← start here
    └── browser_agent.py
```

| Tier | Focus | Start here |
|------|-------|------------|
| **1 — Core Sandbox** | Pure SDK: templates, sandbox lifecycle, **platform agents**, async, files, streaming exec, metrics | [`templates_list.py`](./templates_list.py) |
| **2 — Agent Integration** | Wire a model into a sandbox as a code-execution tool (not `client.agents`) | [`agent_patterns/minimal_agent.py`](./agent_patterns/minimal_agent.py) |
| **3 — Real-World Workflows** | End-to-end model-driven agent workflows with artifacts | [`workflow_examples/repo_analyzer.py`](./workflow_examples/repo_analyzer.py) |

## Tier 1 — Core Sandbox (no model needed)

These scripts only need sandbox credentials (`NEEV_API_KEY`, org, project). Each provisions a real sandbox or platform agent and deletes it in a
`finally` block (or explicit cleanup). [`create_agent.py`](./create_agent.py)
uses the **platform agents API** — not the model-driven patterns in Tier 2.

| File | SDK features | Run |
|------|--------------|-----|
| [`templates_list.py`](./templates_list.py) | `templates.list`, `templates.get`, `sandboxes.create`, `wait_until_ready`, `delete` | `uv run python examples/templates_list.py` |
| [`create_agent.py`](./create_agent.py) | `agent_templates.list`, `agents.create`, `wait_until_ready`, `sandbox()`, `update`, `pause`, `delete` | `uv run python examples/create_agent.py` |
| [`sandbox_lifecycle.py`](./sandbox_lifecycle.py) | `sandboxes.create`, `wait_until_ready`, `metrics`, `pause`, `delete` | `uv run python examples/sandbox_lifecycle.py` |
| [`snapshot_fork_restore.py`](./snapshot_fork_restore.py) | `snapshot`, `get_snapshot`, `create` with `from_snapshot`, `fork`, `delete_snapshot` | `uv run python examples/snapshot_fork_restore.py` |
| [`async_sandbox.py`](./async_sandbox.py) | `AsyncNeevAI`, `sandboxes.create`, `wait_until_ready`, `exec`, `delete` | `uv run python examples/async_sandbox.py` |
| [`files_api.py`](./files_api.py) | `files.write`, `read_text`, `list(recursive=True)` | `uv run python examples/files_api.py` |
| [`preview_ports.py`](./preview_ports.py) | `get_url(port)` — serve on a port, get its preview URL, `list_ports`, `revoke_port` | `uv run python examples/preview_ports.py` |
| [`pty.py`](./pty.py) | `pty.create(...)` — interactive PTY over WebSocket: `on_data`, `send_input`, `wait` | `uv run python examples/pty.py` |
| [`streaming_exec.py`](./streaming_exec.py) | `exec_stream` — stdout/stderr streamed line-by-line | `uv run python examples/streaming_exec.py` |
| [`processes.py`](./processes.py) | `refresh` (connect_url poll), `wait_until_ready`, `processes.list` (runtime probe), `start`, `follow`, `logs`, `kill`, `wait` | `uv run python examples/processes.py` |
| [`process_pool.py`](./process_pool.py) | Same wait pattern as `processes.py`, parallel `start`, `list`, `kill_all`, `wait` | `uv run python examples/process_pool.py` |
| [`parallel_fanout.py`](./parallel_fanout.py) | Multiple `sandboxes.create`, parallel `exec` via `ThreadPoolExecutor` | `uv run python examples/parallel_fanout.py` |
| [`sandbox_metrics.py`](./sandbox_metrics.py) | `metrics()` polled under simulated CPU load | `uv run python examples/sandbox_metrics.py` |
| [`raw_request.py`](./raw_request.py) | `client.raw.request` — untyped API access | `uv run python examples/raw_request.py` |
| [`sandbox_lifecycle_controller.py`](./sandbox_lifecycle_controller.py) | CLI over `client.sandboxes` — create, list, get, pause, resume, delete, metrics | `uv run python examples/sandbox_lifecycle_controller.py --help` |

**Lifecycle controller** — useful for manual testing without writing a script:

```sh
uv run python examples/sandbox_lifecycle_controller.py create --name my-sandbox --wait
uv run python examples/sandbox_lifecycle_controller.py list --limit 20
uv run python examples/sandbox_lifecycle_controller.py metrics <sandbox-id>
```

## Tier 2 — Agent Integration (with an AI model)

These drive NeevCloud `gpt-oss-120b` over the OpenAI-compatible inference
endpoint. Add an inference key (falls back to `NEEV_API_KEY` when sandbox
and inference keys are the same):

```sh
export NEEV_INFERENCE_API_KEY=...          # preferred; falls back to NEEV_API_KEY
# inference endpoint defaults to https://inference.ai.neevcloud.com/v1
```

| File | SDK features | Extra install | Run |
|------|--------------|---------------|-----|
| [`agent_patterns/minimal_agent.py`](./agent_patterns/minimal_agent.py) | `sandboxes.create`, `wait_until_ready`, `exec_stream`, `delete` | none (`neevai` + `httpx`) | `uv run python examples/agent_patterns/minimal_agent.py` |
| [`agent_patterns/langchain_agent.py`](./agent_patterns/langchain_agent.py) | Same sandbox APIs via `SandboxCodeExecutor` | `uv sync --extra agents` | `uv run --extra agents python examples/agent_patterns/langchain_agent.py` |

See [`agent_patterns/README.md`](./agent_patterns/README.md) for helper modules
and framework-specific detail.

## Tier 3 — Real-World Workflows

[`workflow_examples/`](./workflow_examples/) contains two hand-rolled agent demos
backed by a shared [`StreamingAgentLoop`](./agent_patterns/utils/agent_loop.py).
Each registers a `run_shell` tool — the model writes shell, it executes in the
sandbox, and artifacts are saved locally on exit.

| Example | SDK features | Artifact |
|---------|--------------|----------|
| [`repo_analyzer.py`](./workflow_examples/repo_analyzer.py) | `sandboxes.create`, `exec`, `files.write` (bootstrap), `delete` | `workflow_examples/output/repo-analysis.md` |
| [`browser_agent.py`](./workflow_examples/browser_agent.py) | `sandboxes.create`, `exec`, `files.read` (artifact pull), `delete` | `workflow_examples/output/results.md` |

See [`workflow_examples/README.md`](./workflow_examples/README.md) for CLI flags,
template recommendations, and environment variables.

```sh
# Hero example — repo analyzer
uv run python examples/workflow_examples/repo_analyzer.py

# Browser automation (Hacker News scrape)
uv run python examples/workflow_examples/browser_agent.py --query "AI"
```

## Two agent stacks

The agent examples use two complementary integration patterns:

- **`SandboxCodeExecutor`** — used by [`langchain_agent.py`](./agent_patterns/langchain_agent.py).
  Provisions one sandbox and exposes `run_python` / `run_shell` as tool methods.
- **Hand-rolled / `StreamingAgentLoop`** — used by [`minimal_agent.py`](./agent_patterns/minimal_agent.py)
  and the workflow examples. Implements (or wraps) a tool-dispatch loop that
  streams tool output live and pulls artifacts from the sandbox on exit.

Shared helpers live under [`agent_patterns/utils/`](./agent_patterns/utils/):

| Module | Used by |
|--------|---------|
| [`model_config.py`](./agent_patterns/utils/model_config.py) | All model-driven examples |
| [`sandbox_tool.py`](./agent_patterns/utils/sandbox_tool.py) | `langchain_agent.py` |
| [`agent_loop.py`](./agent_patterns/utils/agent_loop.py) | `workflow_examples/*` |

## Step-by-step: run every example

Do the [Quick setup](#quick-setup-once) once, then run each in order. Each
example provisions a real sandbox, so the project needs available credits.

**1. Templates and create**

```sh
uv run python examples/templates_list.py
```

**1b. Platform agent lifecycle**

```sh
uv run python examples/create_agent.py
```

**2. Lifecycle**

```sh
uv run python examples/sandbox_lifecycle.py
```

**3. Snapshot, restore, and fork**

```sh
uv run python examples/snapshot_fork_restore.py
```

**4. Async workflow**

```sh
uv run python examples/async_sandbox.py
```

**5. Files API**

```sh
uv run python examples/files_api.py
```

**6. Streaming exec**

```sh
uv run python examples/streaming_exec.py
```

**7. Supervised processes** — connect_url wait, Ready, runtime probe, then
start / follow / logs / kill

```sh
uv run python examples/processes.py
```

**8. Process pool** — parallel starts and `kill_all`

```sh
uv run python examples/process_pool.py
```

**9. Parallel fan-out** — three sandboxes analyze public repos in parallel and
print aggregated file counts

```sh
uv run python examples/parallel_fanout.py
```

**10. Metrics under load**

```sh
uv run python examples/sandbox_metrics.py
```

**11. Raw request** (optional)

```sh
uv run python examples/raw_request.py
```

The remaining examples need an AI model — set `NEEV_INFERENCE_API_KEY` (see [Tier 2](#tier-2--agent-integration-with-an-ai-model)).

**12. Minimal agent** (no extra deps)

```sh
uv run python examples/agent_patterns/minimal_agent.py
```

**13. LangChain**

```sh
uv sync --extra agents
uv run --extra agents python examples/agent_patterns/langchain_agent.py
```

**14. Repository analyzer**

```sh
uv run python examples/workflow_examples/repo_analyzer.py
```

**15. Browser automation**

```sh
uv run python examples/workflow_examples/browser_agent.py
```

**16. (Optional) Browser with query filter**

```sh
uv run python examples/workflow_examples/browser_agent.py --query "AI"
```

## Environment reference

| Variable | Used by | Default |
|----------|---------|---------|
| `NEEV_API_KEY` | all | — (required) |
| `NEEV_ORG_ID` | all | — (required) |
| `NEEV_PROJECT_ID` | all | — (required) |
| `NEEV_BASE_URL` | all | `https://api.ai.neevcloud.com/agent` |
| `NEEV_SANDBOX_TEMPLATE_ID` | sandbox create | `sb-ubuntu-26-04-minimal` |
| `NEEV_AGENT_TEMPLATE` | `create_agent.py` | `claude-code` |
| `NEEV_INFERENCE_API_KEY` | model examples | falls back to `NEEV_API_KEY` |
| `NEEV_INFERENCE_BASE_URL` | model examples | `https://inference.ai.neevcloud.com/v1` |
| `NEEV_MODEL` | model + workflow_examples | `gpt-oss-120b` |
| `NEEVAI_WORKFLOW_MAX_STEPS` | workflow_examples | `35` (`repo_analyzer`), `70` (`browser_agent`) |
| `NEEVAI_WAIT_TIMEOUT_MS` | `sandbox_lifecycle.py`, `snapshot_fork_restore.py`, `processes.py`, `process_pool.py`, lifecycle controller | `300000` |
| `NEEVAI_POLL_INTERVAL_MS` | `processes.py`, `process_pool.py` | `2000` |
| `NEEVAI_SNAPSHOT_POLL_MS` | `snapshot_fork_restore.py` | `3000` |
| `NEEVAI_STEP_DELAY_SEC` | `sandbox_lifecycle.py` | `3` |
| `NEEV_GIT_STATIC_URL` | `repo_analyzer.py` | — (optional static git binary URL) |

## Notes

- Sandbox file paths are **workspace-relative** — the sandbox rejects absolute paths.
- Standard minimal templates ship `sh` only (no `bash`, no `python3`); `sh -c`
  works on every template. `run_python` needs a python-capable template.
- Python examples call `wait_until_ready()` explicitly before `exec` / `exec_stream`
  (the TS SDK auto-waits on first use).
- `processes.py` and `process_pool.py` poll until `connect_url` is set, call
  `wait_until_ready()`, then probe the sandbox runtime with `sandbox.processes.list()`
  before `processes.start` (tunable via `NEEVAI_WAIT_TIMEOUT_MS` /
  `NEEVAI_POLL_INTERVAL_MS`).
- Progress/transcript output goes to **stderr**; an example's result goes to **stdout**.
