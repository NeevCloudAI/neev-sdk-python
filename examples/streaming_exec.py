"""
Stream a command's output from a sandbox as it is produced.

``sandbox.exec_stream(...)`` yields stdout/stderr text chunks the moment the
daemon flushes them, then a terminal exit event.

Run::

    NEEVCLOUD_API_KEY=... NEEVCLOUD_ORG_ID=... NEEVCLOUD_PROJECT_ID=... \\
    uv run python examples/streaming_exec.py
"""

from __future__ import annotations

import os
import random
import string
import sys
import time

from neevai import NeevAI

REGION = os.environ.get("NEEVCLOUD_REGION", "as-south-1")
TEMPLATE = os.environ.get("NEEVCLOUD_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")

start = time.time() * 1000


def log(message: str) -> None:
    elapsed = int(time.time() * 1000 - start)
    print(f"[+{elapsed:5d}ms] {message}", file=sys.stderr)


def _rand_suffix() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


def main() -> None:
    with NeevAI() as client:
        log("creating sandbox…")
        sandbox = client.sandboxes.create(
            {
                "name": f"stream-{_rand_suffix()}",
                "sandbox_template_id": TEMPLATE,
                "region": REGION,
            }
        )

        try:
            sandbox.wait_until_ready()

            command = [
                "sh",
                "-c",
                'i=1; while [ $i -le 5 ]; do echo "line $i"; sleep 1; i=$((i+1)); done; echo "(done)" >&2',
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
            log("deleting sandbox…")
            sandbox.delete()


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        print(err, file=sys.stderr)
        sys.exit(1)
