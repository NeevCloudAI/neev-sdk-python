"""
Resize a running sandbox in place, then re-scope its egress — no restart.

Provisions a sandbox, waits for it to become ready, then resizes its CPU/memory
and replaces its egress policy in a single ``client.sandboxes.update`` call —
one PATCH carrying both ``resources`` and ``egress``. The update keeps the
sandbox's ID, name, and preview URLs and takes effect without a restart.

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

Flow
----

1. **Create & wait** — provision a sandbox and block on ``wait_until_ready``
2. **Resize + re-scope egress in one call** — a single
   ``update(resources=…, allow_egress=…)`` bumps cpu/memory and swaps the
   egress policy in one PATCH (``disk_gb`` is not resizable in place)
3. **Verify** — a fresh ``get`` reflects the new shape; the ID is unchanged
4. **Cleanup** — delete the sandbox

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    uv run python examples/sandbox_update.py
"""

from __future__ import annotations

import os
import sys

from neevai import NeevAI
from neevai.errors import NeevAIError

WAIT_TIMEOUT_MS = int(os.environ.get("NEEVAI_WAIT_TIMEOUT_MS", "300000"))
SANDBOX_TEMPLATE_ID = os.environ.get("NEEV_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")


def main() -> None:
    with NeevAI(
        api_key=os.environ.get("NEEV_API_KEY"),
        org_id=os.environ.get("NEEV_ORG_ID"),
        project_id=os.environ.get("NEEV_PROJECT_ID"),
    ) as client:
        try:
            sandbox = client.sandboxes.create({"sandbox_template_id": SANDBOX_TEMPLATE_ID})
            sandbox.wait_until_ready(timeout_ms=WAIT_TIMEOUT_MS)
            print(f"ready {sandbox.id} at {sandbox.connect_url}")

            # --- Resize AND re-scope egress in a single PATCH (no restart;
            #     keeps ID, name, preview URLs) ---
            sandbox.update(
                {"resources": {"cpu": 2, "memory_gb": 4}},
                allow_egress=["api.github.com"],
            )
            print(f"resized: {sandbox.data.get('resources')}")
            print(f"egress now allows: {[r['host'] for r in sandbox.data['egress']['allow']]}")

            # --- Verify the new shape survives a round-trip; ID is unchanged ---
            fresh = client.sandboxes.get(sandbox.id)
            assert fresh.id == sandbox.id
            print(f"verified via get: resources={fresh.data.get('resources')}")

            sandbox.delete()
            print("deleted")
        except NeevAIError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
