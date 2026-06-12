"""
Tool-agnostic streaming agent loop used by the ``workflow_examples``.

``StreamingAgentLoop`` drives a chat-completion model, dispatches tool calls
to caller-provided handlers, and streams tool output live to the terminal.

``pull_artifact`` reads a file from the sandbox and saves it to a local
output directory — the visual payoff for browser_agent.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from utils.model_config import NEEV_INFERENCE_BASE_URL, NEEV_MODEL, neev_inference_api_key

from neevai.handles.sandbox import Sandbox

RUN_SHELL_TOOL: dict[str, Any] = {
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

SYSTEM_DEFAULT = (
    "You are a helpful coding assistant. You have a run_shell tool that executes "
    "POSIX sh in a secure Neev sandbox. Use as few commands as possible — never "
    "re-run a command that already succeeded — then reply with a single concise "
    "final answer."
)


def make_run_shell_handler(sandbox: Sandbox) -> Callable[[dict[str, Any]], str]:
    """Return a handler that executes a shell command and streams output live."""

    def handle(tool_call: dict[str, Any]) -> str:
        command = tool_call.get("command", "")
        print(f"  $ {command}", file=sys.stderr)

        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        exit_code = 0

        print("  ┌─ live output ───────────────────────", file=sys.stderr)
        for event in sandbox.exec_stream(["sh", "-c", command], timeout_ms=60_000):
            if event["type"] == "stdout":
                sys.stdout.write(event["data"])
                sys.stdout.flush()
                stdout_chunks.append(event["data"])
            elif event["type"] == "stderr":
                sys.stdout.write(event["data"])
                sys.stdout.flush()
                stderr_chunks.append(event["data"])
            else:
                exit_code = event["exit_code"]
        print(file=sys.stderr)
        print(f"  └─ exit {exit_code} ────────────────────────", file=sys.stderr)

        result = f"exit_code: {exit_code}\nstdout:\n{''.join(stdout_chunks)}\nstderr:\n{''.join(stderr_chunks)}"
        return result[:4000]

    return handle


def pull_artifact(
    sandbox: Sandbox,
    remote_path: str,
    output_dir: str | Path,
) -> Path:
    """Read a file from the sandbox and write it to *output_dir*.

    Returns the local ``Path`` of the saved file.  Creates *output_dir* if
    missing.  Raises ``FileNotFoundError`` if the remote file does not exist.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        data = sandbox.files.read(remote_path)
    except Exception as exc:
        raise FileNotFoundError(f"Artifact {remote_path} not found in sandbox: {exc}") from exc

    local_path = output_dir / Path(remote_path).name
    local_path.write_bytes(data)
    print(f"[artifact] saved {len(data)} bytes -> {local_path}", file=sys.stderr)
    return local_path


def pull_artifact_if_exists(
    sandbox: Sandbox,
    remote_path: str,
    output_dir: str | Path,
) -> Path | None:
    """Like :func:`pull_artifact`, but returns ``None`` when the remote file is missing."""
    try:
        return pull_artifact(sandbox, remote_path, output_dir)
    except FileNotFoundError:
        return None


class StreamingAgentLoop:
    """Drive a chat-completion model with tool-calling support.

    Parameters
    ----------
    sandbox:
        A ready-to-use Neev sandbox handle (used only for tool execution).
    system_prompt:
        System message sent to the model.
    tools:
        List of tool definitions (OpenAI function-calling schema).
    handlers:
        Mapping from tool name to callable that accepts the parsed-argument
        dict and returns a result string.
    max_steps:
        Maximum number of model-tool cycles before giving up.
    """

    def __init__(
        self,
        sandbox: Sandbox,
        *,
        system_prompt: str = SYSTEM_DEFAULT,
        tools: list[dict[str, Any]] | None = None,
        handlers: dict[str, Callable[[dict[str, Any]], str]] | None = None,
        max_steps: int = 12,
    ):
        self._sandbox = sandbox
        self._system_prompt = system_prompt
        self._tools = tools or []
        self._handlers = handlers or {}
        self._max_steps = max_steps

    def run(self, task: str) -> str:
        """Run the agent loop for the given *task*.

        Returns the final assistant answer text.
        """
        messages: list[dict] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": task},
        ]

        for step in range(1, self._max_steps + 1):
            print(f"\n[model] calling {NEEV_MODEL} (step {step})…", file=sys.stderr)
            message, usage = self._chat(messages)
            messages.append(message)

            if usage:
                print(
                    f"  tokens: prompt={usage.get('prompt_tokens', '?')} "
                    f"completion={usage.get('completion_tokens', '?')} "
                    f"total={usage.get('total_tokens', '?')}",
                    file=sys.stderr,
                )

            tool_calls = message.get("tool_calls") or []
            if tool_calls:
                for call in tool_calls:
                    fn = call.get("function", {})
                    name = fn.get("name", "")
                    args = json.loads(fn.get("arguments") or "{}")
                    handler = self._handlers.get(name)
                    if handler:
                        result = handler(args)
                    else:
                        result = f"Unknown tool: {name}"

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": result,
                        }
                    )
                continue

            return (message.get("content") or "").strip()

        print(f"[agent] stopped after {self._max_steps} steps", file=sys.stderr)
        return ""

    def _chat(self, messages: list[dict]) -> tuple[dict, dict | None]:
        response = httpx.post(
            f"{NEEV_INFERENCE_BASE_URL}/chat/completions",
            headers={
                "authorization": f"Bearer {neev_inference_api_key()}",
                "content-type": "application/json",
            },
            json={
                "model": NEEV_MODEL,
                "messages": messages,
                "tools": self._tools or None,
                "temperature": 0,
            },
            timeout=120.0,
        )
        if not response.is_success:
            raise RuntimeError(f"inference {response.status_code}: {response.text[:300]}")
        data = response.json()
        message = data.get("choices", [{}])[0].get("message", {"role": "assistant", "content": ""})
        return message, data.get("usage")
