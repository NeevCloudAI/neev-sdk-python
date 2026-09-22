"""
Detect that a sandbox crashed and lost its filesystem.

A sandbox that hits an OOM kill (or another unexpected stop) is restarted for
you, so it reads back as ``Ready`` — nothing in ``phase`` says anything went
wrong. ``sandbox.last_crash`` is the only way to find out, and its
``storage_reset`` flag says whether the sandbox came back with its files or
with an empty ``/workspace``.

This example forces an OOM inside a small sandbox, polls until the crash is
reported, then checks a marker file written before the crash to confirm that
``storage_reset`` told the truth.

Prerequisites
-------------

Required environment variables:

- ``NEEV_API_KEY`` — API key for your organization
- ``NEEV_ORG_ID`` — organization ID
- ``NEEV_PROJECT_ID`` — project ID

Optional overrides:

- ``NEEV_SANDBOX_TEMPLATE_ID`` — template to provision (default:
  ``sb-ubuntu-26-04-minimal``)
- ``NEEVAI_WAIT_TIMEOUT_MS`` — max time to wait for ready state (default: ``300000``)
- ``NEEVAI_CRASH_POLL_ITERS`` — how many times to poll for the crash (default: ``30``)
- ``NEEVAI_CRASH_POLL_INTERVAL_SEC`` — seconds between polls (default: ``5``)

Flow
----

1. **Create** — 1 GB of memory, so an OOM is easy to provoke.
2. **Mark** — write ``/workspace/marker.txt``; its survival is the ground truth
   ``storage_reset`` is checked against.
3. **Crash** — allocate far more memory than the sandbox has. The exec call
   itself is expected to fail or hang up; that is the point.
4. **Poll** — ``sandbox.refresh()`` until ``last_crash`` is populated. It stays
   ``None`` on a sandbox that has never crashed.
5. **Compare** — read ``reason`` / ``at`` / ``storage_reset``, then look for the
   marker file and confirm the two agree.
6. **Cleanup** — delete the sandbox.

Note that ``last_crash`` records a *past* event: it is not cleared when the
sandbox recovers, so read ``at`` before reacting to it.

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \
    uv run python examples/last_crash.py
"""

from __future__ import annotations

import os
import sys
import time

from neevai import NeevAI
from neevai.errors import NeevAIError

WAIT_TIMEOUT_MS = int(os.environ.get("NEEVAI_WAIT_TIMEOUT_MS", "300000"))
SANDBOX_TEMPLATE_ID = os.environ.get("NEEV_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")
POLL_ITERS = int(os.environ.get("NEEVAI_CRASH_POLL_ITERS", "30"))
POLL_INTERVAL_SEC = float(os.environ.get("NEEVAI_CRASH_POLL_INTERVAL_SEC", "5"))

MARKER = "/workspace/marker.txt"


def _marker_survived(sandbox) -> bool:
    """True when the pre-crash marker file is still on disk.

    A non-zero exit means the file is gone; ``exec`` does not raise for that. Any
    NeevAIError here is a failed *check*, not a missing file, so it propagates
    rather than being reported as agreement with ``storage_reset``.
    """
    return sandbox.exec(["sh", "-c", f"test -f {MARKER}"]).exit_code == 0


def main() -> None:
    """Force an OOM, then confirm ``storage_reset`` matches the real filesystem."""
    with NeevAI(
        api_key=os.environ.get("NEEV_API_KEY"),
        org_id=os.environ.get("NEEV_ORG_ID"),
        project_id=os.environ.get("NEEV_PROJECT_ID"),
    ) as client:
        sandbox = None
        try:
            # --- Create a memory-starved sandbox so an OOM is easy to provoke ---
            sandbox = client.sandboxes.create(
                {
                    "sandbox_template_id": SANDBOX_TEMPLATE_ID,
                    "resources": {"cpu": 1, "memory_gb": 1},
                }
            )
            sandbox.wait_until_ready(timeout_ms=WAIT_TIMEOUT_MS)
            # A sandbox that has never crashed reports None.
            print(f"ready {sandbox.id} — last_crash={sandbox.last_crash}")

            # --- Marker file: ground truth for whether storage survived ---
            sandbox.files.write(MARKER, "written before the crash")
            print(f"wrote {MARKER}")

            # --- Force the OOM. This exec is expected to die with the sandbox. ---
            print("allocating past the memory limit...")
            try:
                sandbox.exec(["sh", "-c", "head -c 4G /dev/zero | tail -c 4G"], timeout_ms=60_000)
            except NeevAIError as e:
                print(f"  exec died as expected: {type(e).__name__}")

            # --- Poll until the platform reports the stop ---
            crash = None
            for i in range(POLL_ITERS):
                time.sleep(POLL_INTERVAL_SEC)
                sandbox.refresh()
                crash = sandbox.last_crash
                if crash is not None:
                    break
                print(f"  poll {i + 1}/{POLL_ITERS} — phase={sandbox.phase}, no crash yet")

            if crash is None:
                print(
                    f"No crash reported after {POLL_ITERS * POLL_INTERVAL_SEC:.0f}s. "
                    "The sandbox may have absorbed the allocation; try a larger one.",
                    file=sys.stderr,
                )
                sandbox.delete()
                sys.exit(1)

            print(f"crash: reason={crash.reason} at={crash.at.isoformat()}")
            print(f"  storage_reset={crash.storage_reset}")

            # --- Did storage_reset tell the truth? ---
            sandbox.wait_until_ready(timeout_ms=WAIT_TIMEOUT_MS)
            survived = _marker_survived(sandbox)
            print(f"  marker file present: {survived}")
            if crash.storage_reset == survived:
                print(
                    "MISMATCH: storage_reset says "
                    f"{'wiped' if crash.storage_reset else 'intact'} "
                    f"but the marker is {'present' if survived else 'gone'}",
                    file=sys.stderr,
                )
                sandbox.delete()
                sys.exit(1)
            print(
                "storage_reset agrees with the filesystem: "
                + (
                    "/workspace was wiped, re-provision before reusing this sandbox"
                    if crash.storage_reset
                    else "files survived the restart"
                )
            )

            sandbox.delete()
            print("deleted")
        except NeevAIError as e:
            print(f"Error: {e}", file=sys.stderr)
            if sandbox is not None:
                try:
                    sandbox.delete()
                except NeevAIError:
                    pass
            sys.exit(1)


if __name__ == "__main__":
    main()
