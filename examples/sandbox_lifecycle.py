"""
Walk through a sandbox's full lifecycle from creation to deletion.

Provisions a sandbox from ``NEEV_SANDBOX_TEMPLATE_ID``, waits for it to
become ready, reads live metrics, pauses it, and tears it down. Each step is
separated by a configurable delay so you can follow progress in the console or
watch the sandbox in the NeevCloud dashboard.

Prerequisites
-------------

Required environment variables:

- ``NEEV_API_KEY`` — API key for your organization
- ``NEEV_ORG_ID`` — organization ID
- ``NEEV_PROJECT_ID`` — project ID

Optional overrides:

- ``NEEV_SANDBOX_TEMPLATE_ID`` — template to provision (default:
  ``sb-ubuntu-26-04-minimal``)
- ``NEEVAI_WAIT_TIMEOUT_MS`` — max time to wait for ready state in ms
  (default: ``300000``)
- ``NEEVAI_STEP_DELAY_SEC`` — pause between lifecycle steps in seconds
  (default: ``3``; set to ``0`` to disable)

Flow
----

1. **Create** — call ``client.sandboxes.create`` with the template
2. **Wait** — block on ``sandbox.wait_until_ready``, printing phase/replica
   updates on each poll
3. **Metrics** — call ``sandbox.metrics()`` and list available metric series
4. **Pause** — scale the sandbox to zero replicas via ``sandbox.pause()``
5. **Delete** — remove the sandbox with ``sandbox.delete()``

Stdout / stderr
---------------

- **stdout** — lifecycle milestones (created ID, ready URL, metric names,
  pause confirmation, deleted)
- **stderr** — inter-step delay notices (``waiting Ns before …``) and any
  ``NeevAIError`` message on failure

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    NEEV_SANDBOX_TEMPLATE_ID=sb-ubuntu-26-04-minimal \\
    uv run python examples/sandbox_lifecycle.py
"""

from __future__ import annotations

import os
import sys
import time

from neevai import NeevAI
from neevai.errors import NeevAIError

# Tunable defaults — override via environment variables listed in the docstring.
WAIT_TIMEOUT_MS = int(os.environ.get("NEEVAI_WAIT_TIMEOUT_MS", "300000"))
STEP_DELAY_SEC = float(os.environ.get("NEEVAI_STEP_DELAY_SEC", "3"))
SANDBOX_TEMPLATE_ID = os.environ.get("NEEV_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")


def _pause_between_steps(label: str) -> None:
    """Sleep between lifecycle steps so progress is easy to follow live."""
    if STEP_DELAY_SEC <= 0:
        return
    print(f"waiting {STEP_DELAY_SEC}s before {label}…", file=sys.stderr)
    time.sleep(STEP_DELAY_SEC)


def main() -> None:
    with NeevAI(
        api_key=os.environ.get("NEEV_API_KEY"),
        org_id=os.environ.get("NEEV_ORG_ID"),
        project_id=os.environ.get("NEEV_PROJECT_ID"),
    ) as client:
        try:
            # --- Create ---
            # Egress is deny-all by default. Pass allow_internet=True, or
            # allow_egress=["github.com"], to open outbound network at create time.
            sandbox = client.sandboxes.create(
                {
                    "sandbox_template_id": SANDBOX_TEMPLATE_ID,
                }
            )
            print(f"created {sandbox.id} from {SANDBOX_TEMPLATE_ID} (phase: {sandbox.phase})")

            # --- Wait until ready ---
            _pause_between_steps("wait_until_ready")
            sandbox.wait_until_ready(
                timeout_ms=WAIT_TIMEOUT_MS,
                on_poll=lambda s: print(f"  phase={s.phase} replicas={s.replicas}"),
            )
            print(f"ready at {sandbox.connect_url}")

            # --- Metrics ---
            _pause_between_steps("metrics")
            metrics = sandbox.metrics()
            print(f"metric series: {[s.metric for s in metrics.series]}")

            # --- Pause ---
            _pause_between_steps("pause")
            sandbox.pause()
            print(f"paused (replicas: {sandbox.replicas})")

            # --- Delete ---
            _pause_between_steps("delete")
            sandbox.delete()
            print("deleted")
        except NeevAIError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
