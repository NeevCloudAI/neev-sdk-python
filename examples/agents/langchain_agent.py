"""
LangChain agent with a Neev sandbox as its code-execution tool.

Install agent deps first::

    uv sync --extra agents

Run::

    NEEVCLOUD_API_KEY=... NEEVCLOUD_ORG_ID=... NEEVCLOUD_PROJECT_ID=... \\
    uv run --extra agents python examples/agents/langchain_agent.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from utils.model_config import NEEV_INFERENCE_BASE_URL, NEEV_MODEL, neev_inference_api_key
from utils.sandbox_tool import SandboxCodeExecutor, format_run_result


def main() -> None:
    executor = SandboxCodeExecutor()

    @tool
    def run_shell(command: str) -> str:
        """Run a shell command in the Neev sandbox and return its output."""
        return format_run_result(executor.run_shell(command))

    agent = create_react_agent(
        ChatOpenAI(
            model=NEEV_MODEL,
            temperature=0,
            api_key=neev_inference_api_key(),
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
                            "Use the sandbox to compute the SHA-256 hex digest of the exact "
                            "string 'neev' (no trailing newline), then report only the "
                            "64-character digest."
                        ),
                    }
                ]
            },
            config={"recursion_limit": 100},
        )
        final = result["messages"][-1]
        print(final.content)
    finally:
        executor.cleanup()


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        print(err, file=sys.stderr)
        sys.exit(1)
