"""
AI code-interpreter with live output.

NeevCloud ``gpt-oss-120b`` is given a ``run_shell`` tool backed by a Neev sandbox.
When the model calls it, stdout/stderr stream to your terminal as they are
produced via ``sandbox.exec_stream``.

Run::

    NEEVCLOUD_API_KEY=... NEEVCLOUD_ORG_ID=... NEEVCLOUD_PROJECT_ID=... \\
    uv run python examples/agents/ai_interpreter.py
"""

from __future__ import annotations

import json
import os
import random
import string
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx

from neevai import NeevAI

from utils.model_config import NEEV_INFERENCE_BASE_URL, NEEV_MODEL, neev_inference_api_key

TASK = (
    "Print every prime number below 50, one per line, then on the last line print "
    "'count: N' with how many there were. Use the run_shell tool; the sandbox has "
    "busybox sh only (no bash, no python)."
)

REGION = os.environ.get("NEEVCLOUD_REGION", "as-south-1")
TEMPLATE = os.environ.get("NEEVCLOUD_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")
MAX_STEPS = 6

TOOLS = [
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


def chat(messages: list[dict]) -> tuple[dict, dict | None]:
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
    data = response.json()
    message = data.get("choices", [{}])[0].get("message", {"role": "assistant", "content": ""})
    return message, data.get("usage")


def _rand_suffix() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


def main() -> None:
    line(_bold("AI code-interpreter (gpt-oss-120b → Neev sandbox)"))
    line(_dim(f"task: {TASK}"))

    with NeevAI() as client:
        line(_dim(f"\n[sandbox] creating (template={TEMPLATE}, region={REGION})…"))
        sandbox = client.sandboxes.create(
            {
                "name": f"ai-{_rand_suffix()}",
                "sandbox_template_id": TEMPLATE,
                "region": REGION,
            }
        )

        messages: list[dict] = [
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

                tool_calls = message.get("tool_calls") or []
                if tool_calls:
                    line(_dim(f"[model] requested {len(tool_calls)} tool call(s)"))
                    for call in tool_calls:
                        fn = call.get("function", {})
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

                line(_green(_bold("\n✅ final answer:")))
                line(_green((message.get("content") or "").strip()))
                return

            line(_dim(f"\nstopped after {MAX_STEPS} steps"))
        finally:
            line(_dim(f"\n[sandbox] deleting {sandbox.id}"))
            sandbox.delete()


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        print(err, file=sys.stderr)
        sys.exit(1)
