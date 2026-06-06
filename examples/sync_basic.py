"""
Minimum synchronous example: create a sandbox, wait, exec, delete.

Usage::

    NEEVCLOUD_API_KEY=... NEEVCLOUD_ORG_ID=... NEEVCLOUD_PROJECT_ID=... \\
        python examples/sync_basic.py
"""

import os

from neevai import NeevAI


def main() -> None:
    client = NeevAI(
        api_key=os.environ.get("NEEVCLOUD_API_KEY"),
        org_id=os.environ.get("NEEVCLOUD_ORG_ID"),
        project_id=os.environ.get("NEEVCLOUD_PROJECT_ID"),
    )

    sandbox = client.sandboxes.create(
        {
            "name": "sync-demo",
            "image": "ubuntu:22.04",
        }
    )
    print(f"Created {sandbox.id} (phase={sandbox.phase})")

    sandbox.wait_until_ready()
    print(f"Ready at {sandbox.connect_url}")

    result = sandbox.exec("echo hello")
    print(f"Exec: stdout={result['stdout']!r}")

    client.sandboxes.delete(sandbox.id)
    print("Deleted")

    client.close()


if __name__ == "__main__":
    main()
