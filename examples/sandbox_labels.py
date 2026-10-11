"""
Labels: tag sandboxes with key-value labels at create time, then find them by label.

`create()` takes `labels={...}`; `list(labels={...})` returns only the sandboxes
carrying every given label, and each handle exposes its labels as `sandbox.labels`.

Prerequisites
-------------

Required environment variables:

- ``NEEV_API_KEY`` — API key for your organization
- ``NEEV_ORG_ID`` — organization ID
- ``NEEV_PROJECT_ID`` — project ID

Optional overrides:

- ``NEEV_SANDBOX_TEMPLATE_ID`` — template to create from (default: first in the catalogue)

Flow
----

1. **Create** — two sandboxes sharing a ``team`` label, each with its own ``run`` label.
2. **List** — by ``team`` (both match), then by ``team`` + ``run`` (one matches).
3. **Cleanup** — delete both sandboxes.

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    uv run python examples/sandbox_labels.py
"""

from __future__ import annotations

import os
import sys
import uuid

from neevai import NeevAI
from neevai.errors import NeevAIError


def main() -> None:
    with NeevAI(
        api_key=os.environ.get("NEEV_API_KEY"),
        org_id=os.environ.get("NEEV_ORG_ID"),
        project_id=os.environ.get("NEEV_PROJECT_ID"),
    ) as client:
        template_id = (
            os.environ.get("NEEV_SANDBOX_TEMPLATE_ID") or client.templates.list(limit=1).items[0].id
        )
        # A per-run team value keeps this run's sandboxes apart from any others.
        team = f"labels-demo-{uuid.uuid4().hex[:8]}"
        created = []
        try:
            for run in ("1", "2"):
                sandbox = client.sandboxes.create(
                    {"sandbox_template_id": template_id},
                    labels={"team": team, "run": run},
                )
                created.append(sandbox)
                print(f"created {sandbox.id} labels={sandbox.labels}")

            by_team = client.sandboxes.list(labels={"team": team})
            print(f"team={team}: {sorted(s.id for s in by_team.items)}")

            # Every given label must match, so adding `run` narrows to one sandbox.
            by_run = client.sandboxes.list(labels={"team": team, "run": "2"})
            print(f"team={team}, run=2: {[s.id for s in by_run.items]}")
        except NeevAIError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            for sandbox in created:
                sandbox.delete()
                print(f"deleted {sandbox.id}")


if __name__ == "__main__":
    main()
