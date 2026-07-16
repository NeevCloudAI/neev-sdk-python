"""
Open an SSH tunnel to a sandbox and run a command over it with the system ``ssh``.

``sandbox.ssh()`` binds a local loopback listener and forwards each connection to
the sandbox over an authenticated WebSocket, so any ssh client, ``scp``/``rsync``,
or IDE remote-dev points at ``127.0.0.1:<port>`` with no keys to manage and no
public port. The tunnel is a context manager; closing it stops the listener.

Prerequisites
-------------

Required environment variables:

- ``NEEV_API_KEY`` — API key for your organization
- ``NEEV_ORG_ID`` — organization ID
- ``NEEV_PROJECT_ID`` — project ID

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    uv run python examples/ssh_tunnel.py
"""

from __future__ import annotations

import subprocess
import sys

from neevai import NeevAI
from neevai.errors import NeevAIError


def log(message: str) -> None:
    """Print a ``[ssh]`` progress line to stderr."""
    print(f"[ssh] {message}", file=sys.stderr)


def run_ssh(port: int, command: str) -> int:
    """Run one command over the tunnel with the system ssh client.

    Host-key checking is disabled here only to keep the demo non-interactive.
    """
    result = subprocess.run(
        [
            "ssh",
            "-p",
            str(port),
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "LogLevel=ERROR",
            "neev@localhost",
            command,
        ],
        check=False,
    )
    return result.returncode


def main() -> None:
    with NeevAI() as client:
        sandbox = None
        try:
            log("creating sandbox…")
            sandbox = client.sandboxes.create({})
            sandbox.wait_until_ready()
            log(f"ready: {sandbox.id}")

            with sandbox.ssh() as tunnel:
                log(f"tunnel listening on {tunnel.host}:{tunnel.port}")
                log(f"try it yourself: ssh -p {tunnel.port} neev@localhost")
                code = run_ssh(tunnel.port, 'echo "hello from $(hostname)"; pwd')
                log(f"ssh exited with code {code}")
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
