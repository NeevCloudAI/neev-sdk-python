"""
End-to-end async workflow with AsyncNeevAI.

Creates a sandbox, waits until ready, runs a command, and deletes it — all with
``async with AsyncNeevAI()`` and ``await``. Demonstrates the async client for
create, wait, exec, and cleanup without blocking the event loop.

Why async
---------

Use ``AsyncNeevAI`` when your application is already async — for example FastAPI
or Starlette handlers, asyncio task groups, or any code that needs to run
multiple sandbox operations concurrently without blocking a thread. The sync
``NeevAI`` client is simpler for scripts; ``AsyncNeevAI`` fits async web
servers and concurrent I/O workloads.

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

1. **Create** — ``await client.sandboxes.create`` with the template
2. **Wait** — ``await sandbox.wait_until_ready``
3. **Exec** — ``await sandbox.exec`` and print stdout and exit code
4. **Delete** — ``await sandbox.delete`` in a ``finally`` block

Example Output
--------------

::

    [async] creating sandbox (sb-ubuntu-26-04-minimal)…
    created sb-abc123 (phase: Provisioning)
    [async] waiting until ready…
    ready at https://connect.example/sb-abc123
    exec stdout: hello from async (exit 0)
    [async] deleting sandbox sb-abc123

Stdout / stderr
---------------

- **stdout** — sandbox id/phase, connect URL, exec stdout and exit code
- **stderr** — ``[async]`` progress lines and any ``NeevAIError`` on failure

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    NEEV_SANDBOX_TEMPLATE_ID=sb-ubuntu-26-04-minimal \\
    uv run python examples/async_sandbox.py
"""

from __future__ import annotations

import asyncio
import os
import random
import string
import sys

from neevai import AsyncNeevAI
from neevai.errors import NeevAIError

# Tunable defaults — override via environment variables listed in the docstring.
TEMPLATE = os.environ.get("NEEV_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")


def log(message: str) -> None:
    """Print a ``[async]`` progress line to stderr."""
    print(f"[async] {message}", file=sys.stderr)


def _rand_suffix() -> str:
    """Return a short random suffix for unique sandbox names."""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


async def main() -> None:
    async with AsyncNeevAI() as client:
        sandbox = None
        try:
            # --- Create ---
            log(f"creating sandbox ({TEMPLATE})…")
            sandbox = await client.sandboxes.create(
                {
                    "name": f"async-demo-{_rand_suffix()}",
                    "sandbox_template_id": TEMPLATE,
                }
            )
            print(f"created {sandbox.id} (phase: {sandbox.phase})")

            # --- Wait until ready ---
            log("waiting until ready…")
            await sandbox.wait_until_ready()
            print(f"ready at {sandbox.connect_url}")

            # --- Exec ---
            result = await sandbox.exec(["echo", "hello from async"])
            print(f"exec stdout: {result.stdout.strip()} (exit {result.exit_code})")
        except NeevAIError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            # --- Cleanup ---
            if sandbox is not None:
                try:
                    log(f"deleting sandbox {sandbox.id}")
                    await sandbox.delete()
                except Exception:
                    pass


if __name__ == "__main__":
    asyncio.run(main())
