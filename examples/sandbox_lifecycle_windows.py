"""
Cap a sandbox's lifetime, hold it alive past its idle deadline, then re-scope
the windows — all without recreating the sandbox.

Provisions a sandbox with an idle timeout and a maximum lifetime set at create
time, runs a short ``keepalive`` loop that holds it running past its original
idle deadline, then uses ``update_timeout`` to change one window and clear
another.

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
- ``NEEVAI_IDLE_TIMEOUT_SEC`` — idle window to set at create (default: ``60``)
- ``NEEVAI_KEEPALIVE_ITERS`` — number of keepalive pings (default: ``5``)
- ``NEEVAI_KEEPALIVE_INTERVAL_SEC`` — seconds between pings (default: ``20``)

Flow
----

1. **Create** — ``lifecycle`` sets ``idle_timeout_seconds`` + ``max_lifetime_seconds``.
   Omit ``lifecycle`` entirely and account defaults apply instead.
2. **Wait** — block on ``wait_until_ready``.
3. **Keepalive loop** — ``sandbox.keepalive()`` on an interval shorter than the idle
   window, holding the sandbox running past its original idle deadline.
4. **Retune** — ``sandbox.update_timeout(...)`` raises the idle window and clears the
   lifetime cap (``None``). Only the windows passed change; the rest are untouched.
5. **Cleanup** — delete the sandbox.

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    uv run python examples/sandbox_lifecycle_windows.py
"""

from __future__ import annotations

import os
import sys
import time

from neevai import NeevAI
from neevai.errors import NeevAIError

WAIT_TIMEOUT_MS = int(os.environ.get("NEEVAI_WAIT_TIMEOUT_MS", "300000"))
SANDBOX_TEMPLATE_ID = os.environ.get("NEEV_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")
IDLE_TIMEOUT_SEC = int(os.environ.get("NEEVAI_IDLE_TIMEOUT_SEC", "60"))
KEEPALIVE_ITERS = int(os.environ.get("NEEVAI_KEEPALIVE_ITERS", "5"))
KEEPALIVE_INTERVAL_SEC = float(os.environ.get("NEEVAI_KEEPALIVE_INTERVAL_SEC", "20"))


def _windows(sandbox) -> dict:
    return {
        "idle_timeout_seconds": sandbox.data.get("idle_timeout_seconds"),
        "max_lifetime_seconds": sandbox.data.get("max_lifetime_seconds"),
        "on_idle": sandbox.data.get("on_idle"),
    }


def main() -> None:
    with NeevAI(
        api_key=os.environ.get("NEEV_API_KEY"),
        org_id=os.environ.get("NEEV_ORG_ID"),
        project_id=os.environ.get("NEEV_PROJECT_ID"),
    ) as client:
        try:
            # --- Create with a capped lifetime + idle window ---
            sandbox = client.sandboxes.create(
                {
                    "sandbox_template_id": SANDBOX_TEMPLATE_ID,
                    "lifecycle": {
                        "idle_timeout_seconds": IDLE_TIMEOUT_SEC,
                        "max_lifetime_seconds": 3600,
                        "on_idle": "pause",
                    },
                }
            )
            sandbox.wait_until_ready(timeout_ms=WAIT_TIMEOUT_MS)
            print(f"ready {sandbox.id} — windows: {_windows(sandbox)}")

            # --- Keepalive loop: reset the idle timer on an interval shorter than
            #     the idle window, holding the sandbox past its original deadline ---
            for i in range(KEEPALIVE_ITERS):
                sandbox.keepalive()
                print(f"keepalive {i + 1}/{KEEPALIVE_ITERS} — phase={sandbox.phase}")
                if i < KEEPALIVE_ITERS - 1:
                    time.sleep(KEEPALIVE_INTERVAL_SEC)

            # --- Retune windows in place: raise idle, clear the lifetime cap ---
            sandbox.update_timeout({"idle_timeout_seconds": 300, "max_lifetime_seconds": None})
            print(f"retuned — windows: {_windows(sandbox)}")

            sandbox.delete()
            print("deleted")
        except NeevAIError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
