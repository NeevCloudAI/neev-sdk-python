"""
Serve a port from an agent, rotate its preview URL, keep the agent awake, and
read what it ran.

- ``agent.expose_port(port, slug=...)`` returns a credential-free preview URL; the
  slug in it is the only thing gating it, so treat it as a secret. Exposing the
  port again with a new slug rotates the URL.
- ``agent.keepalive()`` resets the idle timer, for a busy agent with no open
  connection.
- ``agent.audit()`` reads the agent's command audit trail, one page at a time.

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    uv run python examples/agent_ports_audit.py
"""

from __future__ import annotations

import os
import secrets
import string
import sys

from neevai import NeevAI
from neevai.errors import NeevAIError

AGENT_TEMPLATE = os.environ.get("NEEV_AGENT_TEMPLATE", "claude-code")
PORT = 3000


def random_slug() -> str:
    """Eight random lowercase letters and digits, the shape a preview slug takes."""
    return "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))


def main() -> None:
    with NeevAI() as client:
        agent = None
        try:
            agent = client.agents.create(
                {"name": "ports-audit-demo", "agent_template": AGENT_TEMPLATE}
            )
            agent.wait_until_ready()
            print(f"ready: {agent.id} (idle window: {agent.idle_timeout_seconds})", file=sys.stderr)

            # Start something listening on PORT inside the agent's sandbox.
            sandbox = agent.sandbox()
            sandbox.wait_until_ready()
            sandbox.files.write("index.html", "<h1>hello from the agent</h1>\n")
            sandbox.processes.start(["busybox", "httpd", "-f", "-p", str(PORT)])

            port = agent.expose_port(PORT, slug=random_slug())
            print(f"preview URL: {port.preview_url}")
            rotated = agent.expose_port(PORT, slug=random_slug())
            print(f"rotated to: {rotated.preview_url} (the old URL no longer works)")
            print(f"exposed ports: {[p.port for p in agent.list_ports()]}")

            agent.keepalive()

            trail = agent.audit(limit=20)
            for r in trail.records:
                print(
                    f"{r.at:%H:%M:%S} {r.tool:<14} {r.command or r.target or ''} {r.outcome.value}"
                )

            agent.revoke_port(PORT)
        except NeevAIError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            if agent is not None:
                agent.delete()


if __name__ == "__main__":
    main()
