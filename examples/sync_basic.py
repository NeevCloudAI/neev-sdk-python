"""
Minimum synchronous example: create a sandbox, wait until ready, hold, delete.

Requires ``NEEVCLOUD_SANDBOX_TEMPLATE_ID``. Set ``NEEVCLOUD_REGION`` for the
deployment region (or pass ``region`` on the client / in create params).
Optional ``NEEVAI_HOLD_SECONDS`` (default 60) controls how long to keep the
sandbox alive after it becomes ready.

Usage::

    NEEVCLOUD_API_KEY=... NEEVCLOUD_ORG_ID=... NEEVCLOUD_PROJECT_ID=... \\
    NEEVCLOUD_REGION=... NEEVCLOUD_SANDBOX_TEMPLATE_ID=... python examples/sync_basic.py
"""

import os
import sys
import time

from neevai import NeevAI
from neevai.errors import NeevAIError

SANDBOX_TEMPLATE_ID = os.environ["NEEVCLOUD_SANDBOX_TEMPLATE_ID"]
WAIT_TIMEOUT_MS = int(os.environ.get("NEEVAI_WAIT_TIMEOUT_MS", "300000"))
HOLD_SECONDS = int(os.environ.get("NEEVAI_HOLD_SECONDS", "60"))


def main() -> None:
    client = NeevAI(
        api_key=os.environ.get("NEEVCLOUD_API_KEY"),
        org_id=os.environ.get("NEEVCLOUD_ORG_ID"),
        project_id=os.environ.get("NEEVCLOUD_PROJECT_ID"),
    )

    try:
        sandbox = client.sandboxes.create(
            {
                "name": "sync-demo",
                "sandbox_template_id": SANDBOX_TEMPLATE_ID,
                "image": "ubuntu:22.04",
            }
        )
        print(f"Created {sandbox.id} (phase={sandbox.phase})")

        print(f"Waiting for Ready (timeout={WAIT_TIMEOUT_MS}ms)...")
        sandbox.wait_until_ready(
            timeout_ms=WAIT_TIMEOUT_MS,
            on_poll=lambda s: print(f"  phase={s.phase} replicas={s.replicas}"),
        )
        print(f"Ready at {sandbox.connect_url}")

        print(f"Holding for {HOLD_SECONDS}s...")
        time.sleep(HOLD_SECONDS)

        client.sandboxes.delete(sandbox.id)
        print("Deleted")
    except NeevAIError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    main()
