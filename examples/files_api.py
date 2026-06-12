"""
Write, read, and list files in a sandbox workspace.

Demonstrates ``sandbox.files.write``, ``read_text``, and ``list(recursive=True)``.
Provisions a sandbox, writes nested workspace files, reads one back, lists the
tree, and deletes the sandbox.

Workspace paths
---------------

All file paths are **workspace-relative** (for example ``demo/hello.txt``).
The sandbox daemon rejects absolute paths — use paths relative to the workspace
root, not ``/tmp/...`` or ``/home/...``.

Prerequisites
-------------

Required environment variables:

- ``NEEVCLOUD_API_KEY`` — API key for your organization
- ``NEEVCLOUD_ORG_ID`` — organization ID
- ``NEEVCLOUD_PROJECT_ID`` — project ID

Optional overrides:

- ``NEEVCLOUD_SANDBOX_TEMPLATE_ID`` — template to provision (default:
  ``sb-ubuntu-26-04-minimal``)
- ``NEEVCLOUD_REGION`` — deployment region (default: ``as-south-1``)

Flow
----

1. **Create & wait** — provision a sandbox and block on ``wait_until_ready``
2. **Write** — create ``demo/hello.txt`` and ``demo/nested/world.txt``
3. **Read** — fetch ``demo/hello.txt`` with ``read_text``
4. **List** — walk ``demo/`` recursively with ``files.list``
5. **Delete** — remove the sandbox in a ``finally`` block

Example Output
--------------

::

    [files] creating sandbox (sb-ubuntu-26-04-minimal, as-south-1)…
    [files] ready: sb-abc123
    read_text: Hello from files API
      file: demo/hello.txt (23 bytes)
      file: demo/nested/world.txt (12 bytes)
    [files] deleting sandbox sb-abc123

Stdout / stderr
---------------

- **stdout** — ``read_text`` result and indented ``file:`` / ``dir:`` listing lines
- **stderr** — ``[files]`` progress lines and any ``NeevAIError`` on failure

Run::

    NEEVCLOUD_API_KEY=... NEEVCLOUD_ORG_ID=... NEEVCLOUD_PROJECT_ID=... \\
    NEEVCLOUD_SANDBOX_TEMPLATE_ID=sb-ubuntu-26-04-minimal \\
    uv run python examples/files_api.py
"""

from __future__ import annotations

import os
import random
import string
import sys

from neevai import NeevAI
from neevai.errors import NeevAIError

# Tunable defaults — override via environment variables listed in the docstring.
REGION = os.environ.get("NEEVCLOUD_REGION", "as-south-1")
TEMPLATE = os.environ.get("NEEVCLOUD_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")


def log(message: str) -> None:
    """Print a ``[files]`` progress line to stderr."""
    print(f"[files] {message}", file=sys.stderr)


def _rand_suffix() -> str:
    """Return a short random suffix for unique sandbox names."""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


def main() -> None:
    with NeevAI() as client:
        sandbox = None
        try:
            # --- Create & wait ---
            log(f"creating sandbox ({TEMPLATE}, {REGION})…")
            sandbox = client.sandboxes.create(
                {
                    "name": f"files-demo-{_rand_suffix()}",
                    "sandbox_template_id": TEMPLATE,
                    "region": REGION,
                }
            )
            sandbox.wait_until_ready()
            log(f"ready: {sandbox.id}")

            # --- Write ---
            sandbox.files.write("demo/hello.txt", "Hello from files API\n")
            sandbox.files.write("demo/nested/world.txt", "Nested file\n")

            # --- Read ---
            text = sandbox.files.read_text("demo/hello.txt")
            print(f"read_text: {text.strip()}")

            # --- List ---
            entries = sandbox.files.list("demo", recursive=True)
            for entry in entries:
                print(f"  {entry.type}: {entry.path} ({entry.size} bytes)")
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
