"""
List sandbox templates, fetch one by id, then create a sandbox from it.

Demonstrates ``client.templates.list()``, ``client.templates.get()``, and
``client.sandboxes.create()`` with ``wait_until_ready`` and cleanup.

Prerequisites
-------------

Required environment variables:

- ``NEEV_API_KEY`` — API key for your organization
- ``NEEV_ORG_ID`` — organization ID
- ``NEEV_PROJECT_ID`` — project ID

Optional overrides:

- ``NEEV_SANDBOX_TEMPLATE_ID`` — template to provision after listing
  (default: first active template in the list, or ``sb-ubuntu-26-04-minimal``)

Flow
----

1. **List** — call ``client.templates.list`` and print each template id/name/status
2. **Get** — fetch full detail for the selected template id
3. **Create** — provision a sandbox from that template
4. **Wait** — block on ``sandbox.wait_until_ready``
5. **Delete** — remove the sandbox in a ``finally`` block

Example Output
--------------

::

    templates: 3 of 10 (page 1)
      sb-ubuntu-26-04-minimal — Ubuntu Minimal [ACTIVE]
      sb-python-3-12 — Python 3.12 [ACTIVE]
    selected: sb-ubuntu-26-04-minimal — Minimal Ubuntu 26.04 image
    [templates] creating sandbox (sb-ubuntu-26-04-minimal)…
    created sb-abc123 (phase: Provisioning)
    [templates] waiting until ready…
    ready at https://connect.example/sb-abc123
    [templates] deleting sandbox sb-abc123

Stdout / stderr
---------------

- **stdout** — template list, selected template detail, created id/phase, connect URL
- **stderr** — ``[templates]`` progress lines and any ``NeevAIError`` on failure

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    NEEV_SANDBOX_TEMPLATE_ID=sb-ubuntu-26-04-minimal \\
    uv run python examples/templates_list.py
"""

from __future__ import annotations

import os
import random
import string
import sys
from typing import cast

from neevai import NeevAI
from neevai.errors import NeevAIError

# Tunable defaults — override via environment variables listed in the docstring.
DEFAULT_TEMPLATE = os.environ.get("NEEV_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")


def log(message: str) -> None:
    """Print a ``[templates]`` progress line to stderr."""
    print(f"[templates] {message}", file=sys.stderr)


def _rand_suffix() -> str:
    """Return a short random suffix for unique sandbox names."""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


def main() -> None:
    with NeevAI() as client:
        sandbox = None
        try:
            # --- List ---
            page = client.templates.list(limit=10)
            print(f"templates: {len(page.items)} of {page.total} (page {page.page})")
            for template in page.items:
                print(f"  {template.id} — {template.name} [{template.status.value}]")

            template_id: str = DEFAULT_TEMPLATE
            if page.items and template_id not in {t.id for t in page.items}:
                template_id = cast(str, page.items[0].id)

            # --- Get ---
            detail = client.templates.get(template_id)
            print(f"selected: {detail.id} — {detail.description}")

            # --- Create ---
            log(f"creating sandbox ({template_id})…")
            sandbox = client.sandboxes.create(
                {
                    "name": f"templates-demo-{_rand_suffix()}",
                    "sandbox_template_id": template_id,
                }
            )
            print(f"created {sandbox.id} (phase: {sandbox.phase})")

            # --- Wait until ready ---
            log("waiting until ready…")
            sandbox.wait_until_ready()
            print(f"ready at {sandbox.connect_url}")
        except NeevAIError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            # --- Cleanup ---
            if sandbox is not None:
                try:
                    log(f"deleting sandbox {sandbox.id}")
                    sandbox.delete()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
