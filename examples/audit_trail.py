"""
Run a few commands in a sandbox, then read back its audit trail.

Events are OCSF, newest first: each call made to the sandbox — terminal commands,
SSH, process and file operations — with who made it, plus every program the
sandbox ran and every connection it opened, whether or not anything asked for
them. Only the program name is recorded, never its arguments. Filter by
``operation``, ``status``, ``actor_type``, ``actor_uid`` or ``credential_uid``.

Pages are read with ``cursor``: pass the previous page's ``next_cursor`` until it
is empty.

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    uv run python examples/audit_trail.py
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone

from neevai import AuditEvent, NeevAI
from neevai.errors import NeevAIError

TEMPLATE = os.environ.get("NEEV_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-dev")


def describe(e: AuditEvent) -> str:
    """One line per event: the API call, or the program and what it did."""
    if e.api is not None:
        return f"{e.api.operation} by {e.actor.user.name or e.actor.user.uid}"
    if e.dst_endpoint is not None:
        d = e.dst_endpoint
        dst = d.name or f"{d.ip}:{d.port}"
        proc = e.actor.process.name if e.actor.process else "?"
        return f"{proc} connect {dst}"
    name = e.process.name if e.process else "?"
    exit_code = f" exit {e.exit_code}" if e.exit_code is not None else ""
    return f"{name} {e.activity_name.lower()}{exit_code}"


def show(e: AuditEvent) -> None:
    at = datetime.fromtimestamp(e.time / 1000, tz=timezone.utc)
    print(f"{at:%H:%M:%S} {describe(e):<40} {e.status}")


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

            # Events take a few seconds to reach the trail.
            trail = sandbox.audit(limit=20)
            deadline = time.monotonic() + 30
            while not trail.data and time.monotonic() < deadline:
                time.sleep(2)
                trail = sandbox.audit(limit=20)

            # Read the trail one page at a time, newest first.
            print(f"retention: {trail.retention_days} days, truncated: {trail.window_truncated}")
            while True:
                for e in trail.data:
                    show(e)
                if not trail.next_cursor:
                    break
                trail = sandbox.audit(limit=20, cursor=trail.next_cursor)

            # Exec calls and program launches.
            print("exec:")
            for e in sandbox.audit(operation="exec").data:
                show(e)
        except NeevAIError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            if sandbox is not None:
                sandbox.delete()


if __name__ == "__main__":
    main()
