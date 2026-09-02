"""
Create a sandbox scoped to GitHub egress, then update it in place: resize its
cpu/memory and re-scope egress to Google in a single update() call (one PATCH
carrying both), without recreating the sandbox or losing its id.

Python equivalent of examples/update-resize-egress.ts in the JS SDK.

Run with (targets the Neev API from your NEEV_* environment):

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \
        NEEV_BASE_URL=https://aiagent.dev.ai.neevcloud.com \
        uv run python examples/update_resize_egress.py
"""

from __future__ import annotations

import sys

from neevai import NeevAI
from neevai.errors import NeevAIError

# Construct the client from NEEV_* environment variables.
neev = NeevAI()


def main() -> None:
    # Create with egress locked to GitHub only (deny-all otherwise). `allow_egress`
    # is the same convenience `update()` accepts — identical wire JSON.
    sandbox = neev.sandboxes.create({}, allow_egress=["github.com"])
    sandbox.wait_until_ready()
    print(
        f"ready {sandbox.id} — resources: {sandbox.data.get('resources')}, "
        f"egress: {sandbox.data.get('egress')}"
    )

    # Resize cpu/memory AND replace the egress policy (GitHub -> Google) in a single
    # update — the SDK sends one PATCH carrying both `resources` and `egress`, and
    # both take effect together. The sandbox keeps its id, name, and preview URLs;
    # disk_gb is not resizable in place. Egress replaces the policy in full and
    # needs no restart.
    sandbox.update({"resources": {"cpu": 2, "memory_gb": 4}}, allow_egress=["google.com"])
    print(
        f"updated {sandbox.id} in one PATCH — resources: {sandbox.data.get('resources')}, "
        "egress: github.com -> google.com"
    )

    # A fresh get confirms the resize landed and the new egress policy is intact —
    # the exact combined-PATCH path AIPLATFORM-1896 concerns (egress must not revert).
    fresh = neev.sandboxes.get(sandbox.id)
    print(f"confirmed resources: {fresh.data.get('resources')}, egress: {fresh.data.get('egress')}")

    sandbox.delete()
    print("cleaned up")


if __name__ == "__main__":
    try:
        main()
    except NeevAIError as err:
        print(err, file=sys.stderr)
        sys.exit(1)
    finally:
        neev.close()
