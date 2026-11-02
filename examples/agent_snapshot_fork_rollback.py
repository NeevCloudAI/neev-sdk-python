"""
Snapshot a running agent, fork it, and roll it back.

- ``agent.snapshot(wait_until_ready=True)`` snapshots the sandbox backing the agent
  and waits until the snapshot is Ready.
- ``agent.fork(name)`` creates a **new agent** from the agent's current state. The
  source keeps running; the fork is Provisioning until ``wait_until_ready()``.
- ``agent.rollback(snapshot_id)`` returns the agent's sandbox to the snapshot in
  place. The agent keeps its id and name.

A paused or still-provisioning agent raises ``ConflictError`` (409) or
``TooEarlyError`` (425) instead.

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    uv run python examples/agent_snapshot_fork_rollback.py
"""

from __future__ import annotations

import os
import sys

from neevai import NeevAI
from neevai.errors import NeevAIError

AGENT_TEMPLATE = os.environ.get("NEEV_AGENT_TEMPLATE", "claude-code")
MESSAGE_PATH = "demo/message.txt"


def read_message(agent) -> str:
    """Reads the marker file from the agent's backing sandbox."""
    sandbox = agent.sandbox()
    sandbox.wait_until_ready()
    return sandbox.files.read_text(MESSAGE_PATH).strip()


def main() -> None:
    with NeevAI() as client:
        agent = fork = snapshot = None
        try:
            agent = client.agents.create(
                {"name": "snapshot-demo", "agent_template": AGENT_TEMPLATE}
            )
            agent.wait_until_ready()
            print(f"ready: {agent.id}", file=sys.stderr)

            sandbox = agent.sandbox()
            sandbox.wait_until_ready()
            sandbox.files.write(MESSAGE_PATH, "original state")

            snapshot = agent.snapshot({"name": "before-change"}, wait_until_ready=True)
            print(f"snapshot {snapshot.id} is {snapshot.status.value}", file=sys.stderr)
            print(f"agent snapshots: {[s.name for s in agent.snapshots()]}")

            sandbox.files.write(MESSAGE_PATH, "modified state")

            fork = agent.fork("snapshot-demo-fork")
            print(f"forked: {fork.id} ({fork.status})", file=sys.stderr)
            fork.wait_until_ready()
            print(f"fork has: {read_message(fork)}")

            agent.rollback(snapshot.id)
            agent.wait_until_ready()
            print(f"after rollback, {agent.name} ({agent.id}) has: {read_message(agent)}")
        except NeevAIError as exc:
            print(f"error: {exc}", file=sys.stderr)
            raise
        finally:
            # The snapshot goes before the agent it was taken from.
            if snapshot is not None:
                client.sandboxes.delete_snapshot(snapshot.id)
            if fork is not None:
                fork.delete()
            if agent is not None:
                agent.delete()


if __name__ == "__main__":
    main()
