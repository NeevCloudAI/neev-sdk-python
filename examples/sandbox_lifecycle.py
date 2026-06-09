"""
Linear sandbox lifecycle: create, wait, metrics, pause, delete.

Requires ``NEEVCLOUD_SANDBOX_TEMPLATE_ID``. Set ``NEEVCLOUD_REGION`` for the
deployment region (or pass ``region`` on the client / in create params).

Usage::

    NEEVCLOUD_API_KEY=... NEEVCLOUD_ORG_ID=... NEEVCLOUD_PROJECT_ID=... \\
    NEEVCLOUD_REGION=... NEEVCLOUD_SANDBOX_TEMPLATE_ID=... \\
    python examples/sandbox_lifecycle.py
"""

import os
import sys

from neevai import NeevAI
from neevai.errors import NeevAIError

SANDBOX_TEMPLATE_ID = os.environ["NEEVCLOUD_SANDBOX_TEMPLATE_ID"]
WAIT_TIMEOUT_MS = int(os.environ.get("NEEVAI_WAIT_TIMEOUT_MS", "300000"))


def main() -> None:
    with NeevAI(
        api_key=os.environ.get("NEEVCLOUD_API_KEY"),
        org_id=os.environ.get("NEEVCLOUD_ORG_ID"),
        project_id=os.environ.get("NEEVCLOUD_PROJECT_ID"),
    ) as client:
        try:
            sandbox = client.sandboxes.create(
                {
                    "name": "example-agent",
                    "sandbox_template_id": SANDBOX_TEMPLATE_ID,
                    "image": "ghcr.io/neevcloud/sandbox-python:3.12",
                }
            )
            print(f"created {sandbox.id} (phase: {sandbox.phase})")

            sandbox.wait_until_ready(
                timeout_ms=WAIT_TIMEOUT_MS,
                on_poll=lambda s: print(f"  phase={s.phase} replicas={s.replicas}"),
            )
            print(f"ready at {sandbox.connect_url}")

            metrics = sandbox.metrics()
            print(f"metric series: {[s.metric for s in metrics.series]}")

            sandbox.pause()
            print(f"paused (replicas: {sandbox.replicas})")

            client.sandboxes.delete(sandbox.id)
            print("deleted")
        except NeevAIError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
