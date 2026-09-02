"""
Bring-your-own-image (BYOI): create a sandbox from a public OCI image and run a
command in it, instead of a catalogue template.

`create()` accepts `image` (a public OCI reference with an explicit tag or
digest) and an optional `command`, as an alternative to `sandbox_template_id`.
Set exactly one of the two.

Prerequisites
-------------

Required environment variables:

- ``NEEV_API_KEY`` — API key for your organization
- ``NEEV_ORG_ID`` — organization ID
- ``NEEV_PROJECT_ID`` — project ID

Optional overrides:

- ``NEEV_SANDBOX_IMAGE`` — OCI image reference (default:
  ``docker.io/library/python:3.12-slim``)
- ``NEEVAI_WAIT_TIMEOUT_MS`` — max time to wait for ready state (default: ``300000``)

Flow
----

1. **Create** — ``client.sandboxes.create({"image": ..., "command": [...]})`` (BYOI).
2. **Wait** — block on ``wait_until_ready``.
3. **Exec** — run a command to prove the image booted.
4. **Cleanup** — delete the sandbox.

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    uv run python examples/byoi_create.py
"""

from __future__ import annotations

import os
import sys

from neevai import NeevAI
from neevai.errors import NeevAIError

IMAGE = os.environ.get("NEEV_SANDBOX_IMAGE", "docker.io/library/python:3.12-slim")
WAIT_TIMEOUT_MS = int(os.environ.get("NEEVAI_WAIT_TIMEOUT_MS", "300000"))


def main() -> None:
    with NeevAI(
        api_key=os.environ.get("NEEV_API_KEY"),
        org_id=os.environ.get("NEEV_ORG_ID"),
        project_id=os.environ.get("NEEV_PROJECT_ID"),
    ) as client:
        sandbox = None
        try:
            # BYOI: `image` (+ optional `command`) instead of `sandbox_template_id`.
            sandbox = client.sandboxes.create({"image": IMAGE, "command": ["sleep", "infinity"]})
            sandbox.wait_until_ready(timeout_ms=WAIT_TIMEOUT_MS)
            print(f"ready {sandbox.id} from image {IMAGE}")

            result = sandbox.exec(["python", "--version"])
            print(f"exec exit={result.exit_code} out={(result.stdout or result.stderr).strip()}")
        except NeevAIError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            if sandbox is not None:
                sandbox.delete()
                print("deleted")


if __name__ == "__main__":
    main()
