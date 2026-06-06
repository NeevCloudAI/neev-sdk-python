"""
Minimum asynchronous example: create a sandbox, wait, exec, delete.

Usage::

    NEEVCLOUD_API_KEY=... NEEVCLOUD_ORG_ID=... NEEVCLOUD_PROJECT_ID=... \\
        python examples/async_basic.py
"""

import asyncio
import os

from neevai import AsyncNeevAI


async def main() -> None:
    async with AsyncNeevAI(
        api_key=os.environ.get("NEEVCLOUD_API_KEY"),
        org_id=os.environ.get("NEEVCLOUD_ORG_ID"),
        project_id=os.environ.get("NEEVCLOUD_PROJECT_ID"),
    ) as client:
        sandbox = await client.sandboxes.create(
            {
                "name": "async-demo",
                "image": "ubuntu:22.04",
            }
        )
        print(f"Created {sandbox.id} (phase={sandbox.phase})")

        await sandbox.wait_until_ready()
        print(f"Ready at {sandbox.connect_url}")

        result = await sandbox.exec("echo hello")
        print(f"Exec: stdout={result['stdout']!r}")

        await client.sandboxes.delete(sandbox.id)
        print("Deleted")


if __name__ == "__main__":
    asyncio.run(main())
