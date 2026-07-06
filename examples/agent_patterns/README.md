# Agent integration examples

These examples wire a **Neev sandbox** into agent workflows as a secure
code-execution tool. Each agent reasons over a task, runs shell (or Python) inside
a isolated Neev sandbox, and uses the captured output to answer.

All examples drive the **same NeevCloud model — `gpt-oss-120b`** — over the
OpenAI-compatible Neev inference endpoint.

| Example | Framework | SDK features |
| ------- | --------- | ------------ |
| [`minimal_agent.py`](./minimal_agent.py) | none (hand-rolled loop) | `sandboxes.create`, `wait_until_ready`, `exec_stream`, `delete` |
| [`langchain_agent.py`](./langchain_agent.py) | LangChain (LangGraph ReAct) | Same via `SandboxCodeExecutor` (`exec`, `wait_until_ready`, `delete`) |

**[`minimal_agent.py`](./minimal_agent.py)** is the highlight: the model writes
shell, it runs in the sandbox, and its output **streams to your terminal live**
(via `sandbox.exec_stream`) as it executes — the "AI writes code, watch it run
safely" demo. No framework, no extra deps (just `neevai` + `httpx`):

```sh
uv run python examples/agent_patterns/minimal_agent.py
```

There is no 1:1 Python port of the TS Vercel AI SDK or Genkit examples; use
`minimal_agent.py` or `langchain_agent.py` instead.

For end-to-end workflows with local artifacts, continue to
[`../workflow_examples/README.md`](../workflow_examples/README.md).

Platform **agents** (`client.agents`) are documented separately — see Tier 1
[`create_agent.py`](../create_agent.py) and
[`docs/getting-started.md`](../../docs/getting-started.md#create-an-agent).

## Setup

First do the one-time setup in [`../README.md`](../README.md). One NeevCloud API
key often covers both the sandbox and the model:

```sh
export NEEV_API_KEY=...        # sandbox (+ model if keys are shared)
export NEEV_ORG_ID=...
export NEEV_PROJECT_ID=...
```

Defaults applied for you:

| Setting | Default | Override |
| ------- | ------- | -------- |
| Platform API base | production | `NEEV_BASE_URL` |
| Model | `gpt-oss-120b` | `NEEV_MODEL` |
| Inference endpoint | `https://inference.ai.neevcloud.com/v1` | `NEEV_INFERENCE_BASE_URL` |
| Inference key | `NEEV_API_KEY` | `NEEV_INFERENCE_API_KEY` |
| Template | `sb-ubuntu-26-04-minimal` | `NEEV_SANDBOX_TEMPLATE_ID` |

**Templates and binaries.** Discover templates with `client.templates.list()`
(e.g. `sb-debian-12-minimal`, `sb-ubuntu-26-04-minimal`). The minimal images are
deliberately small: they ship `sh` but **not** `bash`, and **not** `python3`. So
`run_shell` works everywhere, while `run_python` needs a python-capable template.
Sandbox file paths are **workspace-relative**.

## Run

```sh
# Minimal agent — no extra deps
uv run python examples/agent_patterns/minimal_agent.py

# LangChain
uv sync --extra agents
uv run --extra agents python examples/agent_patterns/langchain_agent.py
```

## Verify

**`minimal_agent.py`** — on success, stdout ends with a prime listing and a line
like `count: 15` (primes below 50). Progress and streamed tool output appear on
stderr.

**`langchain_agent.py`** — asks the agent to create a small project (3 Python, 2
JavaScript, 1 Markdown file) in the sandbox, then count source-code files
(`.py` and `.js` only). A successful run prints `5` on stdout (after the
warmup notice on stderr):

```
5
```

Right after the sandbox reaches Ready, its runtime hostname can take a few
seconds to resolve, so the first tool call may need a moment — the agent loop
waits and retries on its own (`recursion_limit: 100` for LangGraph).

## Shared helpers

### `utils/agent_loop.py`

Tool-agnostic `StreamingAgentLoop` shared with the
[`workflow_examples`](../workflow_examples/) demos. It drives a chat-completion
model, dispatches tool calls to caller-provided handlers, and streams tool
output live.

```python
from utils.agent_loop import (
    RUN_SHELL_TOOL,
    StreamingAgentLoop,
    make_run_shell_handler,
    pull_artifact,
    pull_artifact_if_exists,
)

loop = StreamingAgentLoop(
    sandbox,
    system_prompt="You are a coding assistant.",
    tools=[RUN_SHELL_TOOL],
    handlers={"run_shell": make_run_shell_handler(sandbox)},
    max_steps=12,
)
final = loop.run("Your task description here.")
```

- `pull_artifact(sandbox, remote_path, output_dir)` — read a sandbox file and
  write it locally (raises if missing).
- `pull_artifact_if_exists(...)` — same, but returns `None` when the file was not
  created (used by `browser_agent.py` for `results.md`).

Used by the workflow examples, not by `minimal_agent.py` or `langchain_agent.py`.

### `utils/model_config.py`

Shared model configuration — endpoint URL, API key resolution, and model name
(overridable via `NEEV_MODEL`). Key resolution order:

1. `NEEV_INFERENCE_API_KEY`
2. `NEEV_API_KEY`

### `utils/sandbox_tool.py`

`SandboxCodeExecutor` — wraps `NeevAI` + one sandbox with `run_python` /
`run_shell` convenience methods. Used by **`langchain_agent.py` only**;
`minimal_agent.py` implements its own inline agent loop and sandbox lifecycle.
