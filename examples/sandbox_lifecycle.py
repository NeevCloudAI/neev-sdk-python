"""
Linear sandbox lifecycle: list templates, create, wait, metrics, pause, delete.

Run::

    NEEVCLOUD_API_KEY=... NEEVCLOUD_ORG_ID=... NEEVCLOUD_PROJECT_ID=... \\
    uv run python examples/sandbox_lifecycle.py
"""

from __future__ import annotations

import os
import sys

from neevai import NeevAI
from neevai.errors import NeevAIError

REGION = os.environ.get("NEEVCLOUD_REGION", "as-south-1")
WAIT_TIMEOUT_MS = int(os.environ.get("NEEVAI_WAIT_TIMEOUT_MS", "300000"))


def main() -> None:
    with NeevAI(
        api_key=os.environ.get("NEEVCLOUD_API_KEY"),
        org_id=os.environ.get("NEEVCLOUD_ORG_ID"),
        project_id=os.environ.get("NEEVCLOUD_PROJECT_ID"),
    ) as client:
        try:
            templates = client.templates.list()
            template = next(
                (t for t in templates.items if t.status.value == "active"),
                templates.items[0] if templates.items else None,
            )
            if template is None:
                raise NeevAIError("no sandbox templates available")

            sandbox = client.sandboxes.create(
                {
                    "name": "example-agent",
                    "sandbox_template_id": template.id,
                    "region": REGION,
                }
            )
            print(f"created {sandbox.id} from {template.id} (phase: {sandbox.phase})")

            sandbox.wait_until_ready(
                timeout_ms=WAIT_TIMEOUT_MS,
                on_poll=lambda s: print(f"  phase={s.phase} replicas={s.replicas}"),
            )
            print(f"ready at {sandbox.connect_url}")

            metrics = sandbox.metrics()
            print(f"metric series: {[s.metric for s in metrics.series]}")

            sandbox.pause()
            print(f"paused (replicas: {sandbox.replicas})")

            sandbox.delete()
            print("deleted")
        except NeevAIError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
