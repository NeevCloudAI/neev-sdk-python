"""
Use a sandbox as a remote host over SSH.

``sandbox.ssh()`` opens a local loopback tunnel; point any ssh client, ``rsync``,
``scp``, or an IDE's Remote-SSH at ``{host, port}`` — no keys to manage and no
public port. Over a single tunnel this example:

  1. runs a command on the sandbox,
  2. rsyncs a local directory up into the workspace,
  3. port-forwards a server running in the sandbox back to your machine.

It creates the sandbox from a bring-your-own image that ships openssh, rsync, and
python3 (the default minimal template has none of those). Any image with an
SSH-capable userland works.

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
import tempfile
import time
from pathlib import Path

from neevai import NeevAI
from neevai.errors import NeevAIError

# A public image with openssh-client, rsync, and python3 already installed.
IMAGE = "mcr.microsoft.com/devcontainers/python:3.12"

# Common ssh options that keep the demo non-interactive. The tunnel is loopback
# and per-session, so skipping host-key prompts here is safe for the example.
SSH_OPTS = [
    "-o",
    "StrictHostKeyChecking=no",
    "-o",
    "UserKnownHostsFile=/dev/null",
    "-o",
    "LogLevel=ERROR",
]


def log(message: str) -> None:
    """Print a ``[ssh]`` progress line to stderr."""
    print(f"[ssh] {message}", file=sys.stderr)


def run(cmd: list[str]) -> int:
    """Run a command inheriting stdio and return its exit code."""
    return subprocess.run(cmd, check=False).returncode


def main() -> None:
    with NeevAI() as client:
        sandbox = None
        try:
            log(f"creating sandbox from {IMAGE}…")
            sandbox = client.sandboxes.create({"image": IMAGE})
            sandbox.wait_until_ready(timeout_ms=180_000)
            log(f"ready: {sandbox.id}")

            with sandbox.ssh() as tunnel:
                log(
                    f"tunnel on {tunnel.host}:{tunnel.port} — e.g. ssh -p {tunnel.port} neev@localhost"
                )
                target = "neev@localhost"
                p = ["-p", str(tunnel.port), *SSH_OPTS]

                # 1. Run a command on the sandbox.
                log("exec: uname + workspace listing")
                run(["ssh", *p, target, "uname -a; echo; ls -la /workspace"])

                # 2. rsync a local directory up into the workspace.
                local = tempfile.mkdtemp(prefix="ssh-demo-")
                Path(local, "hello.txt").write_text("shipped over rsync\n")
                log("rsync: local dir → sandbox:/workspace/uploaded")
                run(
                    [
                        "rsync",
                        "-az",
                        "-e",
                        "ssh " + " ".join(p),
                        f"{local}/",
                        f"{target}:/workspace/uploaded/",
                    ]
                )
                run(["ssh", *p, target, "cat /workspace/uploaded/hello.txt"])

                # 3. Serve a file from the sandbox and port-forward it back to localhost.
                log("port-forward: python http.server in sandbox → http://localhost:18080")
                run(
                    [
                        "ssh",
                        *p,
                        target,
                        "cd /workspace && (setsid python3 -m http.server 8080 >/tmp/httpd.log 2>&1 &); sleep 1",
                    ]
                )
                forward = subprocess.Popen(
                    ["ssh", *p, "-N", "-L", "18080:localhost:8080", target],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                try:
                    time.sleep(2)
                    run(["curl", "-s", "http://localhost:18080/uploaded/hello.txt"])
                finally:
                    forward.terminate()
            log("tunnel closed")
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
