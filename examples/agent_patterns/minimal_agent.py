"""
Hand-rolled agent loop with a sandbox-backed ``run_shell`` tool and live output.

NeevCloud ``gpt-oss-120b`` is given a ``run_shell`` tool backed by a Neev sandbox.
When the model calls it, stdout and stderr stream to your terminal as they are
produced via ``sandbox.exec_stream``. This is the tier-2 entry point in the
agent examples — run it before framework integrations or workflow examples.

Why a minimal agent
-------------------

A tool-calling agent is a loop: the model proposes a tool call, you execute it,
append the result to the conversation, and ask the model again until it replies
with a final answer. This script implements that loop directly (no LangChain or
LangGraph) so you can see every step.

Sandbox commands can run in two ways. With ``sandbox.exec()``, you wait until the
command finishes and receive all stdout and stderr in one result. With
``sandbox.exec_stream()``, output appears incrementally while the command is still
running — useful when the model runs multi-line shell scripts and you want to
watch progress live.

Prerequisites
-------------

Required environment variables:

- ``NEEVCLOUD_API_KEY`` — API key for your organization
- ``NEEVCLOUD_ORG_ID`` — organization ID
- ``NEEVCLOUD_PROJECT_ID`` — project ID

Inference (see ``utils/model_config.py`` for key resolution):

- ``NEEV_INFERENCE_API_KEY`` or ``NEEVCLOUD_INFERENCE_API_KEY`` — model API key
  (falls back to ``NEEVCLOUD_API_KEY``)

Optional overrides:

- ``NEEVCLOUD_SANDBOX_TEMPLATE_ID`` — template to provision (default:
  ``sb-ubuntu-26-04-minimal``)
- ``NEEVCLOUD_REGION`` — deployment region (default: ``as-south-1``)
- ``NEEV_MODEL`` — inference model name (default: ``gpt-oss-120b``)
- ``NEEV_INFERENCE_BASE_URL`` or ``NEEVCLOUD_INFERENCE_BASE_URL`` — OpenAI-compatible
  endpoint (default: ``https://inference.ai.neevcloud.com/v1``)

Module constants (not env-overridable):

- ``MAX_STEPS`` — maximum agent loop iterations (default: ``6``)
- ``TASK`` — fixed demo prompt: print every prime below 50, then ``count: N``

Flow
----

1. **Create** — call ``client.sandboxes.create`` with the template and region
2. **Wait** — block on ``sandbox.wait_until_ready``
3. **Agent loop** — POST ``/chat/completions`` with the ``run_shell`` tool schema
4. **Tool call** — on each tool request, run ``sandbox.exec_stream`` and append
   stdout/stderr/exit code as a tool result message
5. **Final answer** — when the model replies with text (no tool calls), print it
   and exit the loop
6. **Delete** — remove the sandbox in a ``finally`` block

Example Output
--------------

::

    AI code-interpreter (gpt-oss-120b → Neev sandbox)
    task: Print every prime number below 50…

    [sandbox] creating (template=sb-ubuntu-26-04-minimal, region=as-south-1)…

    ━━━━━ step 1 ━━━━━
    [model] calling gpt-oss-120b with 2 messages…
    [model] requested 1 tool call(s)
    [tool] run_shell
      $ for n in 2 3 5 7 …; do echo $n; done; echo "count: 15"
      ┌─ live output ───────────────────────
    2
    3
    5
    …
    count: 15
      └─ exit 0 ────────────────────────
    [tool] returned 142 bytes to the model

    ━━━━━ step 2 ━━━━━
    …

    ✅ final answer:
    There are 15 primes below 50.

    [sandbox] deleting sb-abc123

Stdout / stderr
---------------

- **stdout** — step banners, model/token notices, live tool output, final answer
- **stderr** — uncaught exception message on failure

Run::

    NEEVCLOUD_API_KEY=... NEEVCLOUD_ORG_ID=... NEEVCLOUD_PROJECT_ID=... \\
    uv run python examples/agent_patterns/minimal_agent.py
"""

from __future__ import annotations

import json
import os
import random
import string
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx
from utils.model_config import NEEV_INFERENCE_BASE_URL, NEEV_MODEL, neev_inference_api_key

from neevai import NeevAI

TASK = (
    "Print every prime number below 50, one per line, then on the last line print "
    "'count: N' with how many there were. Use the run_shell tool; the sandbox has "
    "busybox sh only (no bash, no python)."
)

# Tunable defaults — override via environment variables listed in the docstring.
REGION = os.environ.get("NEEVCLOUD_REGION", "as-south-1")
TEMPLATE = os.environ.get("NEEVCLOUD_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")
MAX_STEPS = 6

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "Run a POSIX sh command in the secure sandbox and return its output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to run"}
                },
                "required": ["command"],
            },
        },
    }
]


def _dim(text: str) -> str:
    return f"\x1b[2m{text}\x1b[0m"


def _cyan(text: str) -> str:
    return f"\x1b[36m{text}\x1b[0m"


def _green(text: str) -> str:
    return f"\x1b[32m{text}\x1b[0m"


def _bold(text: str) -> str:
    return f"\x1b[1m{text}\x1b[0m"


def line(text: str = "") -> None:
    print(text)


def chat(messages: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    response = httpx.post(
        f"{NEEV_INFERENCE_BASE_URL}/chat/completions",
        headers={
            "authorization": f"Bearer {neev_inference_api_key()}",
            "content-type": "application/json",
        },
        json={"model": NEEV_MODEL, "messages": messages, "tools": TOOLS, "temperature": 0},
        timeout=120.0,
    )
    if not response.is_success:
        raise RuntimeError(f"inference {response.status_code}: {response.text[:300]}")
    data: dict[str, Any] = response.json()
    message: dict[str, Any] = data.get("choices", [{}])[0].get(
        "message", {"role": "assistant", "content": ""}
    )
    return message, data.get("usage")


def _rand_suffix() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


def main() -> None:
    line(_bold("AI code-interpreter (gpt-oss-120b → Neev sandbox)"))
    line(_dim(f"task: {TASK}"))

    with NeevAI() as client:
        # --- Create ---
        line(_dim(f"\n[sandbox] creating (template={TEMPLATE}, region={REGION})…"))
        sandbox = client.sandboxes.create(
            {
                "name": f"ai-{_rand_suffix()}",
                "sandbox_template_id": TEMPLATE,
                "region": REGION,
            }
        )

        # --- Build messages ---
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are a coding assistant. You have a run_shell tool that executes POSIX sh "
                    "in a secure sandbox (busybox sh; no bash, no python). Use as few commands as "
                    "possible — never re-run a command that already succeeded — then reply with a "
                    "single concise final line."
                ),
            },
            {"role": "user", "content": TASK},
        ]

        try:
            sandbox.wait_until_ready()

            # --- Agent loop ---
            for step in range(1, MAX_STEPS + 1):
                line(_bold(f"\n━━━━━ step {step} ━━━━━"))
                line(_dim(f"[model] calling {NEEV_MODEL} with {len(messages)} messages…"))
                message, usage = chat(messages)
                messages.append(message)
                if usage:
                    line(
                        _dim(
                            "[model] tokens: "
                            f"prompt={usage.get('prompt_tokens', '?')} "
                            f"completion={usage.get('completion_tokens', '?')} "
                            f"total={usage.get('total_tokens', '?')}"
                        )
                    )

                tool_calls: list[dict[str, Any]] = message.get("tool_calls") or []
                if tool_calls:
                    line(_dim(f"[model] requested {len(tool_calls)} tool call(s)"))
                    for call in tool_calls:
                        fn: dict[str, Any] = call.get("function", {})
                        args = json.loads(fn.get("arguments") or "{}")
                        command = args.get("command", "")
                        line(f"{_dim('[tool] run_shell')}\n  {_cyan(f'$ {command}')}")
                        line(_dim("  ┌─ live output ───────────────────────"))

                        stdout = ""
                        stderr = ""
                        exit_code = 0
                        for event in sandbox.exec_stream(["sh", "-c", command], timeout_ms=60_000):
                            if event["type"] == "stdout":
                                sys.stdout.write(event["data"])
                                stdout += event["data"]
                            elif event["type"] == "stderr":
                                sys.stdout.write(event["data"])
                                stderr += event["data"]
                            else:
                                exit_code = event["exit_code"]
                        line(_dim(f"  └─ exit {exit_code} ────────────────────────"))

                        result = f"exit_code: {exit_code}\nstdout:\n{stdout}\nstderr:\n{stderr}"
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call["id"],
                                "content": result[:4000],
                            }
                        )
                        line(_dim(f"[tool] returned {len(result)} bytes to the model"))
                    continue

                # --- Final answer ---
                line(_green(_bold("\n✅ final answer:")))
                content = str(message.get("content") or "").strip()
                line(_green(content))
                return

            line(_dim(f"\nstopped after {MAX_STEPS} steps"))
        finally:
            # --- Delete ---
            line(_dim(f"\n[sandbox] deleting {sandbox.id}"))
            sandbox.delete()


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        print(err, file=sys.stderr)
        sys.exit(1)
