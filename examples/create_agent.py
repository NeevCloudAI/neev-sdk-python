"""
Provision an agent from a catalogue template, wait for it to become Ready,
drive its backing sandbox, then clean up.

Set NEEV_AGENT_TEMPLATE to pick a template (default "claude-code"),
NEEV_REGION to pin a region (e.g. on dev), and NEEV_BASE_URL to target
another environment.

Run::

    NEEVCLOUD_API_KEY=... NEEVCLOUD_ORG_ID=... NEEVCLOUD_PROJECT_ID=... \\
    uv run python examples/create_agent.py
"""

from __future__ import annotations

import os
import sys
from typing import Any

from neevai import NeevAI
from neevai.errors import NeevAIError

AGENT_TEMPLATE = os.environ.get("NEEV_AGENT_TEMPLATE", "claude-code")
REGION = os.environ.get("NEEVCLOUD_REGION")


def main() -> None:
    with NeevAI(
        api_key=os.environ.get("NEEVCLOUD_API_KEY"),
        org_id=os.environ.get("NEEVCLOUD_ORG_ID"),
        project_id=os.environ.get("NEEVCLOUD_PROJECT_ID"),
        region=REGION,
    ) as client:
        try:
            templates = client.agent_templates.list()
            names = ", ".join(t.name for t in templates.items) or "(none)"
            print(f"templates: {names}")

            create_params: dict[str, Any] = {
                "name": "example-coder",
                "agent_template": AGENT_TEMPLATE,
            }
            if REGION:
                create_params["region"] = REGION

            agent = client.agents.create(create_params)
            print(
                f"created {agent.id} (status: {agent.status}, sandbox: {agent.sandbox_id})"
            )

            agent.wait_until_ready()
            print("ready")

            sandbox = agent.sandbox()
            sandbox.files.write("notes.md", "# scratch\n")
            result = sandbox.exec(["ls", "-la"])
            print(result.stdout.rstrip())

            agent.update({"resources": {"cpu": 2, "memory_gb": 4}})
            print("resized")

            agent.pause()
            print(f"paused (status: {agent.status})")

            agent.delete()
            print("deleted")
        except NeevAIError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
