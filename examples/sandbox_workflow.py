"""
End-to-end sandbox workflow: create, wait, write files, exec, read, clean up.

Usage::

    NEEVCLOUD_API_KEY=... NEEVCLOUD_ORG_ID=... NEEVCLOUD_PROJECT_ID=... \\
        python examples/sandbox_workflow.py
"""

import os

from neevai import NeevAI


def main() -> None:
    with NeevAI(
        api_key=os.environ.get("NEEVCLOUD_API_KEY"),
        org_id=os.environ.get("NEEVCLOUD_ORG_ID"),
        project_id=os.environ.get("NEEVCLOUD_PROJECT_ID"),
    ) as client:

        sandbox = client.sandboxes.create({
            "name": "workflow-demo",
            "image": "ghcr.io/neevcloud/sandbox-python:3.12",
        })
        print(f"Created {sandbox.id}")

        sandbox.wait_until_ready()
        print("Sandbox is ready")

        sandbox.files.write("/tmp/script.py", "print('Hello from NeevAI!')\n")
        result = sandbox.exec("python /tmp/script.py")
        print(f"Output: {result['stdout']!r}")

        metrics = sandbox.metrics()
        print(f"Metric series: {[s['metric'] for s in metrics.get('series', [])]}")

        sandbox.pause()
        print(f"Paused (replicas={sandbox.replicas})")

        sandbox.resume()
        print(f"Resumed (phase={sandbox.phase})")

        client.sandboxes.delete(sandbox.id)
        print("Deleted")


if __name__ == "__main__":
    main()
