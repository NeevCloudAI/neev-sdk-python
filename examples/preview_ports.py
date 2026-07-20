"""
Serve something from inside a sandbox and get a preview URL for its port.

``sandbox.get_url(port)`` exposes the port and returns its public,
credential-free preview URL, waiting until the gateway has provisioned the route
before it returns. Ports are private until you expose them; ``list_ports`` shows
what's exposed and ``revoke_port`` stops serving one.

This starts a tiny web server on port 3000 and prints its preview URL — open
that URL to reach the server.

Workspace paths
---------------

File paths are **workspace-relative** (for example ``index.html``). The sandbox
runtime rejects absolute paths.

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
2. **Serve** — write ``index.html`` and start ``busybox httpd`` on port 3000
3. **Expose** — ``get_url(3000)`` returns the preview URL once it is routable
4. **List / revoke** — show exposed ports, then stop serving the port
5. **Delete** — remove the sandbox in a ``finally`` block

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    uv run python examples/preview_ports.py
"""

from __future__ import annotations

import os
import sys

from neevai import NeevAI
from neevai.errors import NeevAIError

TEMPLATE = os.environ.get("NEEV_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")
PORT = 3000


def log(message: str) -> None:
    """Print a ``[ports]`` progress line to stderr."""
    print(f"[ports] {message}", file=sys.stderr)


def main() -> None:
    with NeevAI() as client:
        sandbox = None
        try:
            log(f"creating sandbox ({TEMPLATE})…")
            sandbox = client.sandboxes.create({"sandbox_template_id": TEMPLATE})
            sandbox.wait_until_ready()
            log(f"ready: {sandbox.id}")

            # Write a page and serve the workspace on PORT (busybox ships with httpd).
            sandbox.files.write("index.html", "<h1>hello from the sandbox</h1>\n")
            sandbox.processes.start(["busybox", "httpd", "-f", "-p", str(PORT)])
            log(f"server listening on :{PORT}")

            # Expose the port and wait until its URL is routable.
            url = sandbox.get_url(PORT)
            print(f"preview URL: {url}")
            print(f"exposed ports: {[p.port for p in sandbox.list_ports()]}")

            # Stop serving the port when you're done with it.
            sandbox.revoke_port(PORT)
            print(f"revoked; exposed ports: {[p.port for p in sandbox.list_ports()]}")
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
