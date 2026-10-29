"""
Use a paused agent without resuming it first.

Pausing an agent pauses its backing sandbox. Where the platform's automatic
wake-up is enabled, a request to that sandbox wakes it and is delivered once it is
ready: one slow response instead of an error. This pauses an agent, reads a file
back through ``agent.sandbox().exec`` without calling ``agent.resume()``, and
prints ``RESULT: woke automatically``, ``resumed explicitly`` or ``failed``.

If ``exec`` gets a 429 and the agent is still ``Paused``, it calls
``agent.resume()`` and runs the read-only command once more. In the current backend
a 429 on this path is sent before the command runs; that is not an API guarantee,
so don't replay commands that change state. A 503 is not replayed.

Set NEEV_AGENT_TEMPLATE to pick a template (default "claude-code").

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    uv run python examples/agent_auto_resume.py
"""

from __future__ import annotations

import os
import sys
import time

from neevai import NeevAI
from neevai.errors import APIError, NeevAIError

AGENT_TEMPLATE = os.environ.get("NEEV_AGENT_TEMPLATE", "claude-code")
MARKER_FILE = "auto-resume-marker.txt"
MARKER_TEXT = "written before the pause"
PHASE_TIMEOUT_SEC = 120


def wait_for(agent, done, expected: str) -> None:
    """Polls until done(agent) holds, or raises after PHASE_TIMEOUT_SEC."""
    deadline = time.monotonic() + PHASE_TIMEOUT_SEC
    while not done(agent):
        if time.monotonic() > deadline:
            raise NeevAIError(f"agent still {agent.status}; expected {expected}")
        time.sleep(2)
        agent.refresh()


def read_marker(sandbox) -> str:
    """Reads the marker back; a different text means the files did not survive."""
    result = sandbox.exec(["cat", MARKER_FILE], timeout_ms=PHASE_TIMEOUT_SEC * 1000)
    text = result.stdout.strip()
    if result.exit_code != 0 or text != MARKER_TEXT:
        raise NeevAIError(f"marker not intact: {text!r} {result.stderr}")
    return text


def use_paused_agent(agent, sandbox) -> str:
    """Reads the marker without resuming; returns which path made it work."""
    print(f"reading {MARKER_FILE} from the paused agent, without calling resume()...")
    started = time.monotonic()
    try:
        read_marker(sandbox)
        print(f"file read back intact after {time.monotonic() - started:.1f}s")
        return "woke automatically"
    except APIError as e:
        if e.status_code != 429:
            raise
        agent.refresh()
        if agent.status != "Paused":
            raise
        print(f"the read was refused with 429 and the agent is still Paused ({e})")
        print("calling resume() and reading the file again...")

    agent.resume()
    # wait_until_ready() gives up at once on Paused, so first wait for resume to take effect.
    wait_for(agent, lambda a: a.status != "Paused", "to leave Paused")
    agent.wait_until_ready()
    read_marker(sandbox)
    print(f"file read back intact after {time.monotonic() - started:.1f}s")
    return "resumed explicitly"


def main() -> None:
    with NeevAI() as client:
        agent = None
        try:
            agent = client.agents.create(
                {"name": "auto-resume-demo", "agent_template": AGENT_TEMPLATE}
            )
            print(f"created agent {agent.id}, waiting for it to be Ready...")
            agent.wait_until_ready()
            sandbox = agent.sandbox()
            sandbox.wait_until_ready()
            sandbox.files.write(MARKER_FILE, MARKER_TEXT)
            print(f"agent is Ready; wrote {MARKER_FILE} into its sandbox {agent.sandbox_id}")

            agent.pause()
            wait_for(agent, lambda a: a.status == "Paused", "Paused")
            print(f"agent paused (status: {agent.status})")

            result = use_paused_agent(agent, sandbox)
            agent.refresh()
            print(f"agent status now: {agent.status}")
            print(f"RESULT: {result}")
        except NeevAIError as e:
            print(f"Error: {e}", file=sys.stderr)
            print("RESULT: failed")
            sys.exit(1)
        finally:
            if agent is not None:
                try:
                    agent.delete()
                    print(f"deleted agent {agent.id}")
                except NeevAIError as e:
                    print(f"cleanup failed, delete {agent.id} by hand: {e}", file=sys.stderr)
                    sys.exit(1)


if __name__ == "__main__":
    main()
