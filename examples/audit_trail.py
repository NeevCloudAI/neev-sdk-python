"""
Run a few commands in a sandbox, then read back its command audit trail.

The trail records what ran inside the sandbox — terminal commands, SSH, process
and file operations — newest first, with the credential each ran under and how it
ended. Only the program name is recorded, never its arguments.

Pages are read with ``cursor``: pass the previous page's ``next_cursor`` until it
is empty.

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    uv run python examples/audit_trail.py
"""

from __future__ import annotations

import os
import sys

from neevai import NeevAI
from neevai.errors import NeevAIError

TEMPLATE = os.environ.get("NEEV_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")


def main() -> None:
    with NeevAI() as client:
        sandbox = None
        try:
            sandbox = client.sandboxes.create({"sandbox_template_id": TEMPLATE})
            sandbox.wait_until_ready()
            print(f"ready: {sandbox.id}", file=sys.stderr)

            # Generate some activity: a process and a couple of file operations.
            sandbox.exec(["sh", "-c", "echo hello > greeting.txt"])
            sandbox.files.read_text("greeting.txt")
            sandbox.files.list(".")

            # Read the trail one page at a time, newest first.
            trail = sandbox.audit(limit=20)
            print(f"retention: {trail.retention_days} days, truncated: {trail.window_truncated}")
            while True:
                for r in trail.records:
                    print(
                        f"{r.at:%H:%M:%S} {r.tool:<14} {r.command or r.target or '':<20} {r.outcome.value}"
                    )
                if not trail.next_cursor:
                    break
                trail = sandbox.audit(limit=20, cursor=trail.next_cursor)
        except NeevAIError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            if sandbox is not None:
                sandbox.delete()


if __name__ == "__main__":
    main()
