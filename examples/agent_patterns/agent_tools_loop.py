"""
Agent loop on the sandbox tool contract: ``neevai.agent_tools`` with no framework.

``SandboxTools`` gives the model the contract's tools (``run_command``,
``write_file``, ``read_file``, plus background processes here) with ready-made
descriptions and JSON Schemas. This script turns them into OpenAI-compatible
function specs, sends them to ``gpt-oss-120b``, and runs each tool call with
``tools.call(name, args)``, which returns a JSON-serializable dict for the model,
including ``{"error": ...}`` for mistakes it can fix on its next call.

Prerequisites
-------------

Required environment variables:

- ``NEEV_API_KEY`` — API key for your organization
- ``NEEV_ORG_ID`` — organization ID
- ``NEEV_PROJECT_ID`` — project ID

Inference (see ``utils/model_config.py``):

- ``NEEV_INFERENCE_API_KEY`` — model API key (falls back to ``NEEV_API_KEY``)
- ``NEEV_MODEL`` / ``NEEV_INFERENCE_BASE_URL`` — optional overrides

Flow
----

1. **Create** — a sandbox, then ``wait_until_ready``
2. **Specs** — one function spec per ``tools.names()`` from ``DESCRIPTIONS`` and ``PARAMETERS``
3. **Loop** — ask the model; run every tool call with ``tools.call``; append the results
4. **Answer** — print the model's final reply
5. **Delete** — remove the sandbox in a ``finally`` block

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    uv run python examples/agent_patterns/agent_tools_loop.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx
from utils.model_config import NEEV_INFERENCE_BASE_URL, NEEV_MODEL, neev_inference_api_key

from neevai import NeevAI
from neevai.agent_tools import DESCRIPTIONS, PARAMETERS, SandboxTools

TASK = (
    "Write fib.py in the workspace that prints the first 15 Fibonacci numbers on one line, "
    "run it, and tell me the last number."
)
MAX_STEPS = 8


def chat(messages: list[dict[str, Any]], specs: list[dict[str, Any]]) -> dict[str, Any]:
    response = httpx.post(
        f"{NEEV_INFERENCE_BASE_URL}/chat/completions",
        headers={"authorization": f"Bearer {neev_inference_api_key()}"},
        json={"model": NEEV_MODEL, "messages": messages, "tools": specs, "temperature": 0},
        timeout=120.0,
    )
    response.raise_for_status()
    message: dict[str, Any] = response.json()["choices"][0]["message"]
    return message


def main() -> None:
    with NeevAI() as client:
        sandbox = client.sandboxes.create({})
        print(f"[sandbox] {sandbox.id}")
        try:
            sandbox.wait_until_ready()
            tools = SandboxTools(sandbox, allow_processes=True)
            specs = [
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": DESCRIPTIONS[name],
                        "parameters": PARAMETERS[name],
                    },
                }
                for name in tools.names()
            ]
            messages: list[dict[str, Any]] = [{"role": "user", "content": TASK}]

            for _ in range(MAX_STEPS):
                message = chat(messages, specs)
                messages.append(message)
                calls: list[dict[str, Any]] = message.get("tool_calls") or []
                if not calls:
                    print(f"\n[answer] {message.get('content')}")
                    return
                for call in calls:
                    name = call["function"]["name"]
                    args = json.loads(call["function"].get("arguments") or "{}")
                    result = tools.call(name, args)
                    print(f"[tool] {name}({json.dumps(args)[:120]}) -> {json.dumps(result)[:200]}")
                    messages.append(
                        {"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)}
                    )
            print(f"\nstopped after {MAX_STEPS} steps")
        finally:
            sandbox.delete()
            print(f"[sandbox] deleted {sandbox.id}")


if __name__ == "__main__":
    main()
