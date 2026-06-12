"""
Call the control-plane API through the untyped raw client escape hatch.

Demonstrates ``client.raw.request("GET", path)`` for endpoints that do not yet
have a typed resource wrapper. The response is parsed JSON (or ``None`` for 204).

When to use raw.request
-----------------------

``client.raw.request(method, path)`` is an escape hatch for control-plane
endpoints without typed SDK wrappers. It returns parsed JSON (or ``None`` for
204 No Content). Prefer typed resources such as ``client.templates`` or
``client.sandboxes`` when they exist; use ``raw.request`` for new or internal
API paths, custom query parameters, or prototyping before wrappers land.

Prerequisites
-------------

Required environment variables:

- ``NEEVCLOUD_API_KEY`` — API key for your organization
- ``NEEVCLOUD_ORG_ID`` — organization ID
- ``NEEVCLOUD_PROJECT_ID`` — project ID

Flow
----

1. **List templates** — ``GET /api/v1beta1/sandbox-templates`` with ``limit=3``
2. **List sandboxes** — ``GET /api/v1beta1/orgs/{org}/projects/{project}/sandboxes``
   with ``limit=5``

Example Output
--------------

::

    raw templates: 3 item(s)
      sb-ubuntu-26-04-minimal — Ubuntu Minimal
      sb-python-3-12 — Python 3.12
      sb-node-22 — Node.js 22
    raw sandboxes: 12 total in project

Stdout / stderr
---------------

- **stdout** — template id/name lines and sandboxes total count
- **stderr** — any ``NeevAIError`` message on failure

Run::

    NEEVCLOUD_API_KEY=... NEEVCLOUD_ORG_ID=... NEEVCLOUD_PROJECT_ID=... \\
    uv run python examples/raw_request.py
"""

from __future__ import annotations

import os
import sys
from typing import Any, cast

from neevai import NeevAI
from neevai.errors import NeevAIError


def main() -> None:
    # Org and project IDs come from the environment (see Prerequisites).
    org_id = os.environ.get("NEEVCLOUD_ORG_ID", "")
    project_id = os.environ.get("NEEVCLOUD_PROJECT_ID", "")

    with NeevAI() as client:
        try:
            # --- List templates ---
            templates_path = "/api/v1beta1/sandbox-templates"
            templates = client.raw.request("GET", templates_path, query={"limit": 3})
            items: list[Any] = (
                cast(list[Any], templates.get("items", []))
                if isinstance(templates, dict)
                else []
            )
            print(f"raw templates: {len(items)} item(s)")
            for item in items:
                print(f"  {item.get('id')} — {item.get('name')}")

            # --- List sandboxes ---
            sandboxes_path = (
                f"/api/v1beta1/orgs/{org_id}/projects/{project_id}/sandboxes"
            )
            sandboxes = client.raw.request("GET", sandboxes_path, query={"limit": 5})
            total: int = (
                cast(int, sandboxes.get("total", 0))
                if isinstance(sandboxes, dict)
                else 0
            )
            print(f"raw sandboxes: {total} total in project")
        except NeevAIError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
