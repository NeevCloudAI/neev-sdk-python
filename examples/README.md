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
export NEEVCLOUD_API_KEY=...        # sandbox API key (required)
export NEEVCLOUD_ORG_ID=...
export NEEVCLOUD_PROJECT_ID=...
export NEEVCLOUD_REGION=as-south-1  # or your deployment region
```

**Windows PowerShell:**

```powershell
$env:NEEVCLOUD_API_KEY = "..."
$env:NEEVCLOUD_ORG_ID = "..."
$env:NEEVCLOUD_PROJECT_ID = "..."
$env:NEEVCLOUD_REGION = "as-south-1"
```

By default examples target the **production** control plane
(`https://agent.ai.neevcloud.com`) and region `as-south-1`. To target another
environment:

```sh
export NEEVCLOUD_BASE_URL=https://api.dev.ai.neevcloud.com/agent
export NEEVCLOUD_REGION=as-dev-1
```

Template id defaults to `sb-ubuntu-26-04-minimal`; override with:

```sh
export NEEVCLOUD_SANDBOX_TEMPLATE_ID=sb-ubuntu-26-04-minimal
```

Run every command below from the **repo root** unless noted otherwise.

## Learning path

Examples are organized in three tiers — start at Tier 1 and work your way up:

```text
examples/
├── templates_list.py             ← Tier 1: Core Sandbox
├── sandbox_lifecycle.py
├── async_sandbox.py
├── files_api.py
├── streaming_exec.py
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
| **1 — Core Sandbox** | Pure SDK: templates, lifecycle, async, files, streaming exec, metrics | [`templates_list.py`](./templates_list.py) |
| **2 — Agent Integration** | Wire a model into a sandbox as a code-execution tool | [`agent_patterns/minimal_agent.py`](./agent_patterns/minimal_agent.py) |
| **3 — Real-World Workflows** | End-to-end agent workflows with artifacts | [`workflow_examples/repo_analyzer.py`](./workflow_examples/repo_analyzer.py) |

## Tier 1 — Core Sandbox (no model needed)

These scripts only need sandbox credentials (`NEEVCLOUD_API_KEY`, org, project,
region). Each provisions a real sandbox and deletes it in a `finally` block.

| File | SDK features | Run |
|------|--------------|-----|
| [`templates_list.py`](./templates_list.py) | `templates.list`, `templates.get`, `sandboxes.create`, `wait_until_ready`, `delete` | `uv run python examples/templates_list.py` |
| [`sandbox_lifecycle.py`](./sandbox_lifecycle.py) | `sandboxes.create`, `wait_until_ready`, `metrics`, `pause`, `delete` | `uv run python examples/sandbox_lifecycle.py` |
| [`async_sandbox.py`](./async_sandbox.py) | `AsyncNeevAI`, `sandboxes.create`, `wait_until_ready`, `exec`, `delete` | `uv run python examples/async_sandbox.py` |
| [`files_api.py`](./files_api.py) | `files.write`, `read_text`, `list(recursive=True)` | `uv run python examples/files_api.py` |
| [`streaming_exec.py`](./streaming_exec.py) | `exec_stream` — stdout/stderr streamed line-by-line | `uv run python examples/streaming_exec.py` |
| [`parallel_fanout.py`](./parallel_fanout.py) | Multiple `sandboxes.create`, parallel `exec` via `ThreadPoolExecutor` | `uv run python examples/parallel_fanout.py` |
| [`sandbox_metrics.py`](./sandbox_metrics.py) | `metrics()` polled under simulated CPU load | `uv run python examples/sandbox_metrics.py` |
| [`raw_request.py`](./raw_request.py) | `client.raw.request` — untyped control-plane access | `uv run python examples/raw_request.py` |
| [`sandbox_lifecycle_controller.py`](./sandbox_lifecycle_controller.py) | CLI over `client.sandboxes` — create, list, get, pause, resume, delete, metrics | `uv run python examples/sandbox_lifecycle_controller.py --help` |

**Lifecycle controller** — useful for manual testing without writing a script:

```sh
uv run python examples/sandbox_lifecycle_controller.py create --name my-sandbox --wait
uv run python examples/sandbox_lifecycle_controller.py list --limit 20
uv run python examples/sandbox_lifecycle_controller.py metrics <sandbox-id>
```

## Tier 2 — Agent Integration (with an AI model)

These drive NeevCloud `gpt-oss-120b` over the OpenAI-compatible inference
endpoint. Add an inference key (falls back to `NEEVCLOUD_API_KEY` when sandbox
and inference keys are the same):

```sh
export NEEV_INFERENCE_API_KEY=...          # preferred
# or: export NEEVCLOUD_INFERENCE_API_KEY=...
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

**2. Lifecycle**

```sh
uv run python examples/sandbox_lifecycle.py
```

**3. Async workflow**

```sh
uv run python examples/async_sandbox.py
```

**4. Files API**

```sh
uv run python examples/files_api.py
```

**5. Streaming exec**

```sh
uv run python examples/streaming_exec.py
```

**6. Parallel fan-out** — three sandboxes analyze public repos in parallel and
print aggregated file counts

```sh
uv run python examples/parallel_fanout.py
```

**7. Metrics under load**

```sh
uv run python examples/sandbox_metrics.py
```

**8. Raw request** (optional)

```sh
uv run python examples/raw_request.py
```

The remaining examples need an AI model — set `NEEV_INFERENCE_API_KEY` or
`NEEVCLOUD_INFERENCE_API_KEY` (see [Tier 2](#tier-2--agent-integration-with-an-ai-model)).

**9. Minimal agent** (no extra deps)

```sh
uv run python examples/agent_patterns/minimal_agent.py
```

**10. LangChain**

```sh
uv sync --extra agents
uv run --extra agents python examples/agent_patterns/langchain_agent.py
```

**11. Repository analyzer**

```sh
uv run python examples/workflow_examples/repo_analyzer.py
```

**12. Browser automation**

```sh
uv run python examples/workflow_examples/browser_agent.py
```

**13. (Optional) Browser with query filter**

```sh
uv run python examples/workflow_examples/browser_agent.py --query "AI"
```

## Environment reference

| Variable | Used by | Default |
|----------|---------|---------|
| `NEEVCLOUD_API_KEY` | all | — (required) |
| `NEEVCLOUD_ORG_ID` | all | — (required) |
| `NEEVCLOUD_PROJECT_ID` | all | — (required) |
| `NEEVCLOUD_BASE_URL` | all | production gateway |
| `NEEVCLOUD_REGION` | sandbox create | `as-south-1` |
| `NEEVCLOUD_SANDBOX_TEMPLATE_ID` | sandbox create | `sb-ubuntu-26-04-minimal` |
| `NEEV_INFERENCE_API_KEY` | model examples | falls back to `NEEVCLOUD_INFERENCE_API_KEY`, then `NEEVCLOUD_API_KEY` |
| `NEEVCLOUD_INFERENCE_API_KEY` | model examples | alias for inference key |
| `NEEV_INFERENCE_BASE_URL` | model examples | `https://inference.ai.neevcloud.com/v1` |
| `NEEVCLOUD_INFERENCE_BASE_URL` | model examples | alias for inference base URL |
| `NEEV_MODEL` | model + workflow_examples | `gpt-oss-120b` |
| `NEEVAI_WORKFLOW_MAX_STEPS` | workflow_examples | `35` (`repo_analyzer`), `70` (`browser_agent`) |
| `NEEVAI_WAIT_TIMEOUT_MS` | `sandbox_lifecycle.py`, lifecycle controller | `300000` |
| `NEEVAI_STEP_DELAY_SEC` | `sandbox_lifecycle.py` | `3` |
| `NEEV_GIT_STATIC_URL` | `repo_analyzer.py` | — (optional static git binary URL) |

## Notes

- Sandbox file paths are **workspace-relative** — the daemon rejects absolute paths.
- Standard minimal templates ship `sh` only (no `bash`, no `python3`); `sh -c`
  works on every template. `run_python` needs a python-capable template.
- Python examples call `wait_until_ready()` explicitly before `exec` / `exec_stream`
  (the TS SDK auto-waits on first use).
- Progress/transcript output goes to **stderr**; an example's result goes to **stdout**.
