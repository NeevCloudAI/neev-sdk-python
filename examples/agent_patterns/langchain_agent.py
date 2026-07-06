"""
LangGraph ReAct agent with ``SandboxCodeExecutor`` as its code-execution tool.

Demonstrates framework integration for tool-calling agents: LangGraph handles the
ReAct loop, tool schema, and retries while a Neev sandbox runs shell commands
in isolation. This is the tier-2 follow-up to ``minimal_agent.py`` — run that
hand-rolled example first, then this one.

Why LangChain
-------------

Use a framework when you want a maintained agent graph, built-in tool wiring, and
retry logic instead of implementing the model → tool → result loop yourself.
``create_react_agent`` builds a ReAct graph; ``ChatOpenAI`` points at the Neev
inference endpoint. Sandbox execution still goes through the shared
``utils/sandbox_tool.py`` helper so commands stay isolated.

Prerequisites
-------------

Required environment variables:

- ``NEEV_API_KEY`` — API key for your organization
- ``NEEV_ORG_ID`` — organization ID
- ``NEEV_PROJECT_ID`` — project ID

Inference (see ``utils/model_config.py`` for key resolution):

- ``NEEV_INFERENCE_API_KEY`` — model API key
  (falls back to ``NEEV_API_KEY``)

Optional overrides:

- ``NEEV_SANDBOX_TEMPLATE_ID`` — template to provision (default:
  ``sb-ubuntu-26-04-minimal``)
- ``NEEV_MODEL`` — inference model name (default: ``gpt-oss-120b``)
- ``NEEV_INFERENCE_BASE_URL`` — OpenAI-compatible
  endpoint (default: ``https://inference.ai.neevcloud.com/v1``)

Extra Python dependencies::

    uv sync --extra agents

Module constants (not env-overridable):

- Demo task — create a small project (3 Python, 2 JavaScript, 1 Markdown file)
  in the sandbox, count source-code files (``.py`` and ``.js`` only), and report
  only the number
- ``recursion_limit`` — ``100`` on ``agent.invoke`` so the first sandbox warmup
  does not hit LangGraph's default step cap

Flow
----

1. **Executor** — ``SandboxCodeExecutor`` provisions a sandbox on first use
2. **Tool** — register ``run_shell`` as a LangChain ``@tool`` backed by the executor
3. **Agent** — ``create_react_agent`` with ``ChatOpenAI`` (Neev inference endpoint)
4. **Invoke** — ``agent.invoke`` runs the ReAct loop until the model answers
5. **Result** — print the final assistant message content on stdout
6. **Cleanup** — ``executor.cleanup()`` deletes the sandbox in a ``finally`` block

Example Output
--------------

::

    [agent] LangChain · gpt-oss-120b — running (first sandbox call waits for warmup)…
    5

Stdout / stderr
---------------

- **stderr** — ``[agent] LangChain · …`` progress notice before invoke; uncaught
  errors on failure
- **stdout** — source-code file count only (``.py`` and ``.js``)

Run::

    uv sync --extra agents

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    uv run --extra agents python examples/agent_patterns/langchain_agent.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from langchain_core.tools import tool  # pyright: ignore[reportUnknownVariableType]
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import (
    create_react_agent,  # pyright: ignore[reportUnknownVariableType, reportDeprecated]
)
from pydantic import SecretStr
from utils.model_config import NEEV_INFERENCE_BASE_URL, NEEV_MODEL, neev_inference_api_key
from utils.sandbox_tool import SandboxCodeExecutor, format_run_result


def main() -> None:
    # --- Executor ---
    executor = SandboxCodeExecutor()

    # --- Tool ---
    @tool
    def run_shell(command: str) -> str:
        """Run a shell command in the Neev sandbox and return its output."""
        return format_run_result(executor.run_shell(command))

    # --- Agent ---
    agent = create_react_agent(  # pyright: ignore[reportUnknownVariableType, reportDeprecated]
        ChatOpenAI(
            model=NEEV_MODEL,
            temperature=0,
            api_key=SecretStr(neev_inference_api_key()),
            timeout=90,
            max_retries=1,
            base_url=NEEV_INFERENCE_BASE_URL,
        ),
        tools=[run_shell],
    )

    print(
        f"[agent] LangChain · {NEEV_MODEL} — running (first sandbox call waits for warmup)…",
        file=sys.stderr,
    )
    try:
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Use the sandbox to create a small project with:\n\n"
                            "- 3 Python files\n"
                            "- 2 JavaScript files\n"
                            "- 1 Markdown file\n\n"
                            "Then determine how many source-code files exist (.py and .js only) "
                            "and report only the number."
                        ),
                    }
                ]
            },
            config={"recursion_limit": 100},
        )
        final = result["messages"][-1]
        print(final.content)
    finally:
        # --- Cleanup ---
        executor.cleanup()


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        print(err, file=sys.stderr)
        sys.exit(1)
