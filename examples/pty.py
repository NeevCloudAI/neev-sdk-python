"""
Open an interactive PTY (pseudo-terminal) in a sandbox.

``sandbox.pty.create`` opens a terminal over a WebSocket: output streams to the
``on_data`` callback, and you drive it with ``send_input`` / ``resize`` / ``kill``,
blocking on ``wait()`` for the exit code. This example runs a short shell session
non-interactively (sends a command, prints the output, then exits); a real TUI
would instead pipe your terminal's stdin/stdout and forward window-size changes
to ``resize``.

Reattach to a previous terminal with ``sandbox.pty.create(id=handle.id)``.

Prerequisites
-------------

Required environment variables:

- ``NEEV_API_KEY`` — API key for your organization
- ``NEEV_ORG_ID`` — organization ID
- ``NEEV_PROJECT_ID`` — project ID

Optional overrides:

- ``NEEV_SANDBOX_TEMPLATE_ID`` — template to provision (default:
  ``sb-ubuntu-26-04-minimal``)

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    uv run python examples/pty.py
"""

from __future__ import annotations

import os
import random
import string
import sys

from neevai import NeevAI
from neevai.errors import NeevAIError

TEMPLATE = os.environ.get("NEEV_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")


def log(message: str) -> None:
    """Print a ``[pty]`` progress line to stderr."""
    print(f"[pty] {message}", file=sys.stderr)


def _rand_suffix() -> str:
    """Return a short random suffix for unique sandbox names."""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


def _write_stdout(chunk: bytes) -> None:
    """Stream terminal output straight to this process's stdout."""
    sys.stdout.buffer.write(chunk)
    sys.stdout.buffer.flush()


def main() -> None:
    with NeevAI() as client:
        sandbox = None
        try:
            log(f"creating sandbox ({TEMPLATE})…")
            sandbox = client.sandboxes.create(
                {"name": f"pty-{_rand_suffix()}", "sandbox_template_id": TEMPLATE}
            )
            sandbox.wait_until_ready()
            log(f"ready: {sandbox.id}")

            pty = sandbox.pty.create(program="sh", cols=80, rows=24, on_data=_write_stdout)

            # Drive the shell, then exit so the session ends cleanly.
            pty.send_input("echo hello-from-pty && uname -a\n")
            pty.send_input("exit\n")

            exit_code = pty.wait()
            log(f"pty exited with code {exit_code}")
        except NeevAIError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            if sandbox is not None:
                try:
                    log(f"deleting sandbox {sandbox.id}")
                    sandbox.delete()
                except NeevAIError as e:
                    log(f"cleanup failed — sandbox {sandbox.id} may still be running: {e}")


if __name__ == "__main__":
    main()
