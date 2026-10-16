"""
Run Docker inside a sandbox: start the daemon, then run a container.

The ``sb-ubuntu-26-04-docker`` template ships Docker and Docker Compose. Start the
daemon with ``start-docker`` (safe to rerun), then use ``docker`` as usual, with
two differences:

- run and build with ``--network=host`` (Compose: ``network_mode: host`` and
  ``build.network: host``);
- start containers that never exit, such as ``docker compose up``, with
  ``sandbox.processes.start``; ``exec`` waits for the command to finish.

A sandbox from this template can pull from Docker Hub and GHCR by default; pass
your own ``egress`` at create to allow other registries.

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    uv run python examples/docker.py
"""

from __future__ import annotations

import sys

from neevai import NeevAI
from neevai.errors import NeevAIError


def main() -> None:
    with NeevAI() as client:
        sandbox = None
        try:
            sandbox = client.sandboxes.create({"sandbox_template_id": "sb-ubuntu-26-04-docker"})
            sandbox.wait_until_ready()
            print(f"ready: {sandbox.id}", file=sys.stderr)

            started = sandbox.exec("start-docker")
            print(started.stdout.strip())
            if started.exit_code != 0:
                print(started.stderr, file=sys.stderr)
                sys.exit(1)

            run = sandbox.exec(["docker", "run", "--rm", "--network=host", "hello-world"])
            print(run.stdout.strip())
            if run.exit_code != 0:
                print(run.stderr, file=sys.stderr)
                sys.exit(1)
        except NeevAIError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            if sandbox is not None:
                sandbox.delete()


if __name__ == "__main__":
    main()
