"""
Write, read, and list files in a sandbox workspace.

Demonstrates the full sandbox.files surface: write, read_text, list, stat, exists, mkdir, move, remove, and watch.
Provisions a sandbox, writes nested workspace files, reads one back, lists the
tree, and deletes the sandbox.

Workspace paths
---------------

All file paths are **workspace-relative** (for example ``demo/hello.txt``).
The sandbox runtime rejects absolute paths — use paths relative to the workspace
root, not ``/tmp/...`` or ``/home/...``.

Prerequisites
-------------

Required environment variables:

- ``NEEV_API_KEY`` — API key for your organization
- ``NEEV_ORG_ID`` — organization ID
- ``NEEV_PROJECT_ID`` — project ID

Optional overrides:

- ``NEEV_SANDBOX_TEMPLATE_ID`` — template to provision (default:
  ``sb-ubuntu-26-04-minimal``)

Flow
----

1. **Create & wait** — provision a sandbox and block on ``wait_until_ready``
2. **Write** — create ``demo/hello.txt`` and ``demo/nested/world.txt``
3. **Read** — fetch ``demo/hello.txt`` with ``read_text``
4. **List** — walk ``demo/`` recursively with ``files.list``
5. **Control** — ``stat`` / ``exists``, then ``mkdir`` / ``move`` / ``remove``, and a short ``watch``
6. **Delete** — remove the sandbox in a ``finally`` block

Example Output
--------------

::

    [files] creating sandbox (sb-ubuntu-26-04-minimal)…
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

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    NEEV_SANDBOX_TEMPLATE_ID=sb-ubuntu-26-04-minimal \\
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
TEMPLATE = os.environ.get("NEEV_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")


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
            log(f"creating sandbox ({TEMPLATE})…")
            sandbox = client.sandboxes.create(
                {
                    "name": f"files-demo-{_rand_suffix()}",
                    "sandbox_template_id": TEMPLATE,
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

            # --- Stat / exists ---
            info = sandbox.files.stat("demo/hello.txt")
            print(f"stat: {info.path} is a {info.type} of {info.size} bytes")
            print(f"exists demo/hello.txt: {sandbox.files.exists('demo/hello.txt')}")
            print(f"exists demo/missing: {sandbox.files.exists('demo/missing')}")

            # --- mkdir / move / remove ---
            sandbox.files.mkdir("demo/archive")
            sandbox.files.move("demo/hello.txt", "demo/archive/hello.txt")
            print(f"moved: exists archive copy = {sandbox.files.exists('demo/archive/hello.txt')}")
            sandbox.files.remove("demo/nested", recursive=True)
            print(f"removed demo/nested: exists = {sandbox.files.exists('demo/nested')}")

            # --- Watch (short-lived) ---
            # Start a watch that stops after 2s, then trigger a change from another call.
            for event in sandbox.files.watch("demo", recursive=True, timeout_ms=2_000):
                print(f"watch: {event.type} {event.path}")
        except NeevAIError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            # --- Cleanup ---
            if sandbox is not None:
                try:
                    log(f"deleting sandbox {sandbox.id}")
                    sandbox.delete()
                except NeevAIError as e:
                    log(f"cleanup failed — sandbox {sandbox.id} may still be running: {e}")


if __name__ == "__main__":
    main()
