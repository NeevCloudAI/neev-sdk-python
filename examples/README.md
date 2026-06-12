# Examples

Runnable examples for the NeevAI Python SDK (`neevai`). Install the package in
editable mode from the repo root, then run scripts with `uv run`.

## Quick setup (once)

```sh
# from neev-sdk-python/
uv sync --extra dev

# sandbox credentials
export NEEVCLOUD_API_KEY=...        # your sandbox API key
export NEEVCLOUD_ORG_ID=...
export NEEVCLOUD_PROJECT_ID=...
export NEEVCLOUD_REGION=as-south-1  # or your deployment region
```

By default examples target the **production** API (`https://agent.ai.neevcloud.com`)
and region `as-south-1`. To target another environment, also set:

```sh
export NEEVCLOUD_BASE_URL=https://api.dev.ai.neevcloud.com/agent
export NEEVCLOUD_REGION=as-dev-1
```

Template id defaults to `sb-ubuntu-26-04-minimal`; override with:

```sh
export NEEVCLOUD_SANDBOX_TEMPLATE_ID=sb-ubuntu-26-04-minimal
```

## Examples — no model needed (pure SDK)

| File | What it shows | Run |
|------|---------------|-----|
| [`sandbox_lifecycle.py`](./sandbox_lifecycle.py) | Lifecycle: list templates → create → wait → metrics → pause → delete | `uv run python examples/sandbox_lifecycle.py` |
| [`streaming_exec.py`](./streaming_exec.py) | `sandbox.exec_stream` — output streamed line-by-line | `uv run python examples/streaming_exec.py` |
| [`parallel_fanout.py`](./parallel_fanout.py) | Concurrent sandboxes, map/reduce via `exec`, metrics | `uv run python examples/parallel_fanout.py` |
| [`sandbox_metrics.py`](./sandbox_metrics.py) | `sandbox.metrics()` polled under CPU load | `uv run python examples/sandbox_metrics.py` |

Extra utility (no TS counterpart): [`sandbox_lifecycle_controller.py`](./sandbox_lifecycle_controller.py) — CLI for individual sandbox operations.

## Examples — with an AI model

These drive NeevCloud `gpt-oss-120b` over the OpenAI-compatible inference
endpoint. Add an inference key (falls back to `NEEVCLOUD_API_KEY` if your sandbox
and inference keys are the same):

```sh
export NEEVCLOUD_INFERENCE_API_KEY=...   # inference key
# inference endpoint defaults to https://inference.ai.neevcloud.com/v1
```

| File | Extra install | Run |
|------|---------------|-----|
| [`agents/ai_interpreter.py`](./agents/ai_interpreter.py) | none (only `neevai` + `httpx`) | `uv run python examples/agents/ai_interpreter.py` |
| [`agents/langchain_agent.py`](./agents/langchain_agent.py) | `uv sync --extra agents` | `uv run --extra agents python examples/agents/langchain_agent.py` |

`ai_interpreter.py` is the highlight: the model writes shell, it runs in the
sandbox, and its output streams to your terminal live. See
[`agents/README.md`](./agents/README.md) for framework-by-framework detail.

## Step-by-step: run every example

Do the [Quick setup](#quick-setup-once) once, then run each in order. Each
example provisions a real sandbox, so the project needs available credits.

**1. Lifecycle**
```sh
uv run python examples/sandbox_lifecycle.py
```

**2. Streaming exec**
```sh
uv run python examples/streaming_exec.py
```

**3. Parallel fan-out + metrics**
```sh
uv run python examples/parallel_fanout.py
```

**4. Metrics under load**
```sh
uv run python examples/sandbox_metrics.py
```

The remaining examples need an AI model — set `NEEVCLOUD_INFERENCE_API_KEY` (see above).

**5. AI code-interpreter** (no extra deps)
```sh
uv run python examples/agents/ai_interpreter.py
```

**6. LangChain**
```sh
uv sync --extra agents
uv run --extra agents python examples/agents/langchain_agent.py
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
| `NEEVCLOUD_INFERENCE_API_KEY` | model examples | falls back to `NEEVCLOUD_API_KEY` |
| `NEEVCLOUD_INFERENCE_BASE_URL` | model examples | production inference endpoint |

## Notes

- Sandbox file paths are **workspace-relative** — the daemon rejects absolute paths.
- The standard templates ship `sh` only (no `bash`, no `python3`); `sh -c` works
  on every template. `run_python` needs a python-capable template.
- Python examples call `wait_until_ready()` explicitly before `exec` / `exec_stream`
  (the TS SDK auto-waits on first use).
- Progress/transcript output goes to **stderr**; an example's result goes to **stdout**.
