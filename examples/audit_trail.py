"""
Read a sandbox's audit trail: the calls made to it, every program that ran
inside it, and every connection those programs opened, newest first.

Runs a script through exec, then reads ``sandbox.audit()`` and ties each program
back to the call that started it through its parent chain. Only the program name
is recorded, never its arguments.

Events come in three OCSF classes: API Activity (``class_uid`` 6003) for a call,
Process Activity (1007) for a program starting or ending, and Network Activity
(4001) for a connection. ``status`` filters every class; ``operation``,
``actor_type``, ``actor_uid`` and ``credential_uid`` return calls only.

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    uv run python examples/audit_trail.py
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone

from neevai import AuditEvent, AuditTrail, NeevAI
from neevai.errors import NeevAIError

TEMPLATE = os.environ.get("NEEV_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-dev")

API_ACTIVITY = 6003
PROCESS_ACTIVITY = 1007
NETWORK_ACTIVITY = 4001


def describe(e: AuditEvent) -> str:
    if e.class_uid == API_ACTIVITY:
        who = e.actor.user.name or e.actor.user.uid
        return f"{e.api.operation if e.api else '?'} by {who}"
    if e.class_uid == PROCESS_ACTIVITY and e.process is not None:
        p = e.process
        parent = p.parent_process.pid if p.parent_process else "-"
        if e.exit_code is not None:
            ended = f" exit {e.exit_code}"
        elif e.status_detail:
            ended = f" {e.status_detail}"
        else:
            ended = ""
        return f"{p.name} pid {p.pid} (parent {parent}){ended}"
    if e.class_uid == NETWORK_ACTIVITY and e.actor.process is not None:
        d = e.dst_endpoint
        where = (d.name or f"{d.ip}:{d.port}") if d else "?"
        return f"{e.actor.process.name} pid {e.actor.process.pid} -> {where}"
    return e.type_name


def started_by(pid: int | None, events: Sequence[AuditEvent]) -> AuditEvent | None:
    """The call that started a program: its own pid, or an ancestor's, is a call's pid."""
    calls: dict[int, AuditEvent] = {}
    parent: dict[int, int] = {}
    for e in events:
        for r in e.resources or []:
            if r.data is not None and r.data.pid is not None:
                calls[r.data.pid] = e
        launch = e.class_uid == PROCESS_ACTIVITY and e.activity_id == 1
        if launch and e.process is not None and e.process.pid is not None:
            pp = e.process.parent_process
            if pp is not None and pp.pid is not None:
                parent[e.process.pid] = pp.pid
    seen: set[int] = set()
    while pid is not None and pid not in seen:
        seen.add(pid)
        if pid in calls:
            return calls[pid]
        pid = parent.get(pid)
    return None


def page_with_programs(read: Callable[[], AuditTrail]) -> AuditTrail:
    """Programs and connections can take about a minute to appear, so poll until they do."""
    deadline = time.monotonic() + 120
    while True:
        trail = read()
        has_programs = any(e.class_uid == PROCESS_ACTIVITY for e in trail.data)
        if has_programs or time.monotonic() >= deadline:
            return trail
        time.sleep(5)


def main() -> None:
    with NeevAI() as client:
        sandbox = None
        try:
            sandbox = client.sandboxes.create(
                {"sandbox_template_id": TEMPLATE}, allow_internet=True
            )
            sandbox.wait_until_ready()
            print(f"ready: {sandbox.id}", file=sys.stderr)

            # A script that starts programs of its own: none of them is a call you made.
            sandbox.files.write(
                "work.sh", "#!/bin/sh\nls /workspace\ncurl -s -o /dev/null https://example.com\n"
            )
            sandbox.exec(["sh", "work.sh"])

            trail = page_with_programs(lambda: sandbox.audit(limit=200))
            for e in trail.data:
                at = datetime.fromtimestamp(e.time / 1000, tz=timezone.utc)
                pid = (e.process.pid if e.process else None) or (
                    e.actor.process.pid if e.actor.process else None
                )
                call = None if e.class_uid == API_ACTIVITY else started_by(pid, trail.data)
                via = ""
                if call is not None and call.api is not None:
                    via = f"  <- {call.api.operation} by {call.actor.user.name or call.actor.user.uid}"
                print(f"{at:%H:%M:%S} {e.type_name:<28} {describe(e)}{via}")

            failed = sandbox.audit(status="failure")
            print(f"{len(failed.data)} events ended in failure")
        except NeevAIError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            if sandbox is not None:
                sandbox.delete()


if __name__ == "__main__":
    main()
