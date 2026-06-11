# Agent framework examples

These examples wire a **Neev sandbox** into popular agentic frameworks as a
secure code-execution tool. Each agent reasons over a task, runs Python or shell
inside a gVisor-isolated Neev sandbox, and uses the captured output to answer.

All examples drive the **same NeevCloud model — `gpt-oss-120b`** — over the
OpenAI-compatible Neev inference endpoint, and share two helpers:

- [`utils/sandbox_tool.py`](./utils/sandbox_tool.py) — a `SandboxCodeExecutor` that
  provisions one sandbox, exposes `run_python` / `run_shell`, and tears it down.
- [`utils/model_config.py`](./utils/model_config.py) — the shared model config (endpoint + `gpt-oss-120b`).

| Example | Framework | Model |
| ------- | --------- | ----- |
| [`langchain_agent.py`](./langchain_agent.py) | LangChain (LangGraph ReAct agent) | NeevCloud `gpt-oss-120b` |
| [`ai_interpreter.py`](./ai_interpreter.py) | none (hand-rolled loop) | NeevCloud `gpt-oss-120b` |

**[`ai_interpreter.py`](./ai_interpreter.py)** is the highlight: the model writes
shell, it runs in the sandbox, and its output **streams to your terminal live**
(via `sandbox.exec_stream`) as it executes — the "AI writes code, watch it run
safely" demo. No framework, no extra deps (just `neevai` + `httpx`):

```sh
uv run python examples/agents/ai_interpreter.py
```

There is no 1:1 Python port of the TS Vercel AI SDK or Genkit examples; use
`ai_interpreter.py` or `langchain_agent.py` instead.

## Setup

First do the one-time setup in [`../README.md`](../README.md). One NeevCloud API
key covers both the sandbox and the model:

```sh
export NEEVCLOUD_API_KEY=...        # sandbox + model (inference)
export NEEVCLOUD_ORG_ID=...
export NEEVCLOUD_PROJECT_ID=...
```

Defaults applied for you:

| Setting | Default | Override |
| ------- | ------- | -------- |
| Platform API base | production | `NEEVCLOUD_BASE_URL` |
| Model | `gpt-oss-120b` | — |
| Inference endpoint | `https://inference.ai.neevcloud.com/v1` | `NEEVCLOUD_INFERENCE_BASE_URL` |
| Inference key | `NEEVCLOUD_API_KEY` | `NEEVCLOUD_INFERENCE_API_KEY` |
| Region | `as-south-1` | `NEEVCLOUD_REGION` |
| Template | `sb-ubuntu-26-04-minimal` | `NEEVCLOUD_SANDBOX_TEMPLATE_ID` |

**Templates and binaries.** Discover templates with `client.templates.list()`
(e.g. `sb-debian-12-minimal`, `sb-ubuntu-26-04-minimal`). The minimal images are
deliberately small: they ship `sh` but **not** `bash`, and **not** `python3`. So
`run_shell` works everywhere, while `run_python` needs a python-capable template.
Sandbox file paths are **workspace-relative**.

## Run

```sh
# AI code-interpreter — no extra deps
uv run python examples/agents/ai_interpreter.py

# LangChain
uv sync --extra agents
uv run --extra agents python examples/agents/langchain_agent.py
```

## Verify

Each SHA-256 example asks the agent to compute the SHA-256 of the string `neev`
inside the sandbox. A successful run prints:

```
3fb3a134aebfd0bf072b02b4096612a39e201593853091c52510d37adc3d98de
```

Right after the sandbox reaches Ready, its data-plane hostname can take a few
seconds to resolve, so the first tool call may need a moment — the agent loop
waits and retries on its own (`recursion_limit: 100` for LangGraph).

## Shared helpers

### `utils/agent_loop.py`

Tool-agnostic ``StreamingAgentLoop`` used by the ``use_cases`` examples. It
drives a chat-completion model, dispatches tool calls to caller-provided
handlers, and streams tool output live.

```python
from utils.agent_loop import (
    RUN_SHELL_TOOL,
    StreamingAgentLoop,
    make_run_shell_handler,
    pull_artifact,
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

``pull_artifact(sandbox, remote_path, output_dir)`` reads a file from the
sandbox and writes it to a local output directory — used by
``data_analysis.py`` (``chart.png``) and ``browser_agent.py`` (``results.json``).

### `utils/model_config.py`

Shared model configuration — endpoint URL, API key resolution, and model name
(overridable via ``NEEV_MODEL``).

### `utils/sandbox_tool.py`

``SandboxCodeExecutor`` — wraps ``NeevAI`` + one sandbox with ``run_python`` /
``run_shell`` convenience methods. Used by ``langchain_agent.py``.
