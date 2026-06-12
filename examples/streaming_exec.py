"""
Stream live output from a sandbox while a simulated download task runs.

Provisions a sandbox, runs a shell script that prints download progress every
second, and prints each ``exec_stream`` event as it arrives. Demonstrates
create, wait, stream stdout, exit code, and cleanup.

Streaming output
----------------

Output from a long-running sandbox command can arrive in two ways. With

``sandbox.exec()``, you wait until the command finishes and receive all stdout (Standard Output) and stderr (Standard Error) in one result (i.e. `{ stdout, stderr, exit_code }`). With streaming, output appears incrementally while the command is still running — useful for progress logs, build output, or any task that takes more than a moment.

``sandbox.exec_stream(command)`` runs a command in the sandbox and yields a Python
iterator of events. Each event is a dict:

- ``type`` ``"stdout"`` or ``"stderr"`` — includes ``data``, a text chunk as it
  arrives
- ``type`` ``"exit"`` — final event; includes ``exit_code``

As the SDK puts it: runs a command and yields stdout/stderr chunks as they arrive,
then an exit event.

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

1. **Create** — call ``client.sandboxes.create`` with the template and region
2. **Wait** — block on ``sandbox.wait_until_ready``
3. **Stream exec** — iterate ``sandbox.exec_stream(...)``; log each stdout/stderr
   chunk and the final exit code
4. **Delete** — remove the sandbox in a ``finally`` block

Example Output
--------------

::

    [+  123ms] creating sandbox…
    [+ 4567ms] stdout: Starting download...
    [+ 5678ms] stdout: Download progress: 20%
    [+ 6789ms] stdout: Download progress: 40%
    [+ 7890ms] stdout: Download progress: 60%
    [+ 8901ms] stdout: Download progress: 80%
    [+ 9012ms] stdout: Download progress: 100%
    [+10023ms] stdout: Download completed
    [+10134ms] exit 0
    [+10245ms] deleting sandbox…

Run::

    NEEVCLOUD_API_KEY=... NEEVCLOUD_ORG_ID=... NEEVCLOUD_PROJECT_ID=... \\
    NEEVCLOUD_SANDBOX_TEMPLATE_ID=sb-ubuntu-26-04-minimal \\
    uv run python examples/streaming_exec.py
"""

from __future__ import annotations

import os
import random
import string
import sys
import time

from neevai import NeevAI

# Tunable defaults — override via environment variables listed in the docstring.
REGION = os.environ.get("NEEVCLOUD_REGION", "as-south-1")
TEMPLATE = os.environ.get("NEEVCLOUD_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")

start = time.time() * 1000


def log(message: str) -> None:
    """Print a timestamped line to stderr (milliseconds since script start)."""
    elapsed = int(time.time() * 1000 - start)
    print(f"[+{elapsed:5d}ms] {message}", file=sys.stderr)


def _rand_suffix() -> str:
    """Return a short random suffix for unique sandbox names."""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


def main() -> None:
    with NeevAI() as client:
        # --- Create ---
        log("creating sandbox…")
        sandbox = client.sandboxes.create(
            {
                "name": f"stream-{_rand_suffix()}",
                "sandbox_template_id": TEMPLATE,
                "region": REGION,
            }
        )

        try:
            # --- Wait until ready ---
            sandbox.wait_until_ready()

            # --- Stream exec ---
            command = [
                "sh",
                "-c",
                """
                echo "Starting download..."
                for p in 20 40 60 80 100; do
                    sleep 1
                    echo "Download progress: ${p}%"
                done
                echo "Download completed"
                """,
            ]

            exit_code = 0
            for event in sandbox.exec_stream(command, timeout_ms=30_000):
                if event["type"] == "stdout":
                    log(f"stdout: {event['data'].rstrip()}")
                elif event["type"] == "stderr":
                    log(f"stderr: {event['data'].rstrip()}")
                else:
                    exit_code = event["exit_code"]
            log(f"exit {exit_code}")
        finally:
            # --- Cleanup ---
            log("deleting sandbox…")
            sandbox.delete()


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        print(err, file=sys.stderr)
        sys.exit(1)
