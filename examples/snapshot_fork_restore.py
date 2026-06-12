"""
Snapshot, restore, and fork a sandbox's filesystem state.

Writes a marker file, captures it with ``sandbox.snapshot``, modifies the file
to prove live state changed, then provisions a **new** sandbox from the snapshot
via ``from_snapshot`` (the recommended rollback pattern). Finally forks the
restored sandbox to show inherited state.

Restore pattern
---------------

This example rolls back by creating a new sandbox with ``from_snapshot`` rather
than calling ``sandbox.restore()`` in place. In-place restore is available on the
SDK but may leave an empty workspace on some backends; ``from_snapshot`` create
is the reliable pattern demonstrated here.

Prerequisites
-------------

Required environment variables:

- ``NEEVCLOUD_API_KEY`` — API key for your organization
- ``NEEVCLOUD_ORG_ID`` — organization ID
- ``NEEVCLOUD_PROJECT_ID`` — project ID

Optional overrides:

- ``NEEVCLOUD_SANDBOX_TEMPLATE_ID`` — template to provision (default:
  ``sb-ubuntu-26-04-minimal``)
- ``NEEVCLOUD_REGION`` — deployment region (default: ``as-south-1``)
- ``NEEVAI_WAIT_TIMEOUT_MS`` — max time to wait for sandbox ready (default:
  ``300000``)
- ``NEEVAI_SNAPSHOT_POLL_MS`` — interval between snapshot status polls (default:
  ``3000``)

Flow
----

1. **Create & wait** — provision a sandbox and block on ``wait_until_ready``
2. **Write state** — write ``demo/message.txt`` with ``original state``
3. **Snapshot** — call ``sandbox.snapshot({"name": "demo-snap"})`` (returns Pending)
4. **Poll** — ``wait_for_snapshot`` until status is Ready
5. **Modify** — overwrite the file with ``modified state`` (source sandbox keeps this)
6. **Restore** — ``client.sandboxes.create({..., "from_snapshot": snapshot_id})``
7. **Verify** — print file contents from source (modified) vs restored (original)
8. **Fork** — ``restored.fork("snapshot-fork")`` and read inherited file contents
9. **Cleanup** — delete source sandbox, restored sandbox, fork, and snapshot

Example Output
--------------

::

    [snapshot] created sandbox sb-abc123
    [snapshot] ready: https://…
    [snapshot] wrote original state
    [snapshot] snapshot pending: snap-xyz (status=Pending)
    [snapshot] snapshot ready
  before restore:
  modified state
  after restore:
  original state
    [snapshot] restored sandbox sb-restored789 from snapshot
    [snapshot] forked sandbox sb-fork456 (snapshot-fork)
    [snapshot] fork inherited: original state
    [snapshot] deleting fork sb-fork456
    [snapshot] deleting restored sandbox sb-restored789
    [snapshot] deleting sandbox sb-abc123
    [snapshot] deleting snapshot snap-xyz

Stdout / stderr
---------------

- **stdout** — ``before restore:`` / ``after restore:`` labels and file contents
- **stderr** — ``[snapshot]`` progress lines and any ``NeevAIError`` on failure

Run::

    NEEVCLOUD_API_KEY=... NEEVCLOUD_ORG_ID=... NEEVCLOUD_PROJECT_ID=... \\
    NEEVCLOUD_SANDBOX_TEMPLATE_ID=sb-ubuntu-26-04-minimal \\
    uv run python examples/snapshot_fork_restore.py
"""

from __future__ import annotations

import os
import sys
import time

from neevai import NeevAI, NeevAIError, Snapshot, SnapshotStatus

# Tunable defaults — override via environment variables listed in the docstring.
REGION = os.environ.get("NEEVCLOUD_REGION", "as-south-1")
TEMPLATE = os.environ.get("NEEVCLOUD_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")
WAIT_TIMEOUT_MS = int(os.environ.get("NEEVAI_WAIT_TIMEOUT_MS", "300000"))
SNAPSHOT_POLL_MS = int(os.environ.get("NEEVAI_SNAPSHOT_POLL_MS", "3000"))

MESSAGE_PATH = "demo/message.txt"
ORIGINAL_STATE = "original state"
MODIFIED_STATE = "modified state"


def log(message: str) -> None:
    """Print a ``[snapshot]`` progress line to stderr."""
    print(f"[snapshot] {message}", file=sys.stderr)


def wait_for_snapshot(
    client: NeevAI,
    snapshot: Snapshot,
    *,
    timeout_ms: int = WAIT_TIMEOUT_MS,
    poll_interval_ms: int = SNAPSHOT_POLL_MS,
) -> Snapshot:
    """Poll ``get_snapshot`` until the snapshot reaches Ready or Failed."""
    deadline = (time.time() * 1000.0) + timeout_ms
    snap_id = str(snapshot.id)
    while True:
        current = client.sandboxes.get_snapshot(snap_id)
        if current.status == SnapshotStatus.Ready:
            return current
        if current.status == SnapshotStatus.Failed:
            detail = current.error_message or "unknown error"
            raise NeevAIError(f"Snapshot {snap_id} failed: {detail}")

        remaining = deadline - (time.time() * 1000.0)
        if remaining <= 0:
            raise NeevAIError(
                f"Snapshot {snap_id} did not become Ready within {timeout_ms}ms "
                f"(status: {current.status})."
            )
        time.sleep(min(poll_interval_ms, remaining) / 1000.0)


def main() -> None:
    fork = None
    snapshot = None
    restored = None

    with NeevAI(
        api_key=os.environ.get("NEEVCLOUD_API_KEY"),
        org_id=os.environ.get("NEEVCLOUD_ORG_ID"),
        project_id=os.environ.get("NEEVCLOUD_PROJECT_ID"),
        region=REGION,
    ) as client:
        # --- Create source sandbox ---
        sandbox = client.sandboxes.create(
            {
                "name": "snapshot-demo",
                "sandbox_template_id": TEMPLATE,
                "region": REGION,
            }
        )
        log(f"created sandbox {sandbox.id}")

        try:
            # --- Wait until data plane is reachable ---
            sandbox.wait_until_ready(timeout_ms=WAIT_TIMEOUT_MS)
            log(f"ready: {sandbox.connect_url}")

            # --- Write baseline filesystem state ---
            sandbox.files.write(MESSAGE_PATH, ORIGINAL_STATE)
            log("wrote original state")

            # --- Capture snapshot (returns immediately as Pending) ---
            pending = sandbox.snapshot({"name": "demo-snap"})
            log(f"snapshot pending: {pending.id} (status={pending.status})")

            # --- Poll get_snapshot until Ready ---
            snapshot = wait_for_snapshot(client, pending)
            log("snapshot ready")

            # --- Mutate live sandbox to prove rollback is needed ---
            sandbox.files.write(MESSAGE_PATH, MODIFIED_STATE)

            print("before restore:")
            print(sandbox.files.read_text(MESSAGE_PATH).strip())

            # --- Roll back by creating a new sandbox from the snapshot ---
            restored = client.sandboxes.create(
                {
                    "name": "snapshot-restored",
                    "sandbox_template_id": TEMPLATE,
                    "region": REGION,
                    "from_snapshot": str(snapshot.id),
                }
            )
            log(f"restored sandbox {restored.id} from snapshot")
            restored.wait_until_ready(timeout_ms=WAIT_TIMEOUT_MS)

            print("after restore:")
            print(restored.files.read_text(MESSAGE_PATH).strip())

            # --- Fork restored sandbox; fork inherits its filesystem ---
            fork = restored.fork("snapshot-fork")
            log(f"forked sandbox {fork.id} ({fork.name})")

            fork.wait_until_ready(timeout_ms=WAIT_TIMEOUT_MS)
            inherited = fork.files.read_text(MESSAGE_PATH).strip()
            log(f"fork inherited: {inherited}")

        except NeevAIError as exc:
            print(f"error: {exc}", file=sys.stderr)
            raise
        finally:
            # --- Cleanup: fork, restored sandbox, source sandbox, snapshot ---
            if fork is not None:
                log(f"deleting fork {fork.id}")
                fork.delete()
            if restored is not None:
                log(f"deleting restored sandbox {restored.id}")
                restored.delete()
            log(f"deleting sandbox {sandbox.id}")
            sandbox.delete()
            if snapshot is not None:
                log(f"deleting snapshot {snapshot.id}")
                client.sandboxes.delete_snapshot(str(snapshot.id))


if __name__ == "__main__":
    main()
