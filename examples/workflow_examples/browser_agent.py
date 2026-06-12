"""
Browser Automation — scrape web content with Playwright in a Neev sandbox.

Demonstrates:
- Browser automation in an isolated environment
- Installing and running Playwright + Chromium in a sandbox
- Scraping untrusted web content without host exposure
- Real isolation and environment management

Run::

    uv run python examples/workflow_examples/browser_agent.py \\
        --query "AI"
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent_patterns"))

from utils.agent_loop import (
    RUN_SHELL_TOOL,
    StreamingAgentLoop,
    make_run_shell_handler,
    pull_artifact_if_exists,
)

from neevai import NeevAI
from neevai.handles import Sandbox

SYSTEM_PROMPT = (
    "You are a browser-automation assistant. You have a run_shell tool that executes "
    "POSIX sh in a secure Neev sandbox. Playwright and Chromium are already installed.\n"
    "Write a Python script (saved as /workspace/scrape.py) using 'asyncio' and "
    "'playwright.async_api' that:\n"
    "1. Launches Chromium headless\n"
    "2. Navigates to the target URL\n"
    "3. Extracts the required data\n"
    "4. Saves the results to /workspace/results.md\n"
    "5. Prints the results to stdout\n"
    "Run it with: python3 /workspace/scrape.py\n"
    "Use <<'PY' heredoc syntax to write the script."
)

MAX_STEPS = int(os.environ.get("NEEVAI_WORKFLOW_MAX_STEPS", "70"))

HERE = Path(__file__).resolve().parent
OUTPUT_DIR = HERE / "output"


def create_browser_sandbox(
    client: NeevAI, region: str | None = None
) -> Sandbox:
    template_id = os.environ.get("NEEVCLOUD_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")
    resolved_region = region or os.environ.get("NEEVCLOUD_REGION", "as-south-1")
    suffix = hex(int(time.time() * 1e6))[-6:]
    print(
        f"[sandbox] creating browser sandbox (template={template_id}, region={resolved_region})…",
        file=sys.stderr,
    )
    sandbox = client.sandboxes.create(
        {
            "name": f"browser-agent-{suffix}",
            "sandbox_template_id": template_id,
            "region": resolved_region,
        }
    )
    print(f"[sandbox] created {sandbox.id}; waiting until ready…", file=sys.stderr)
    sandbox.wait_until_ready()
    print(f"[sandbox] ready: {sandbox.connect_url}", file=sys.stderr)
    return sandbox


def bootstrap(sandbox: Sandbox) -> None:
    print("[bootstrap] installing playwright + chromium…", file=sys.stderr)
    result = sandbox.exec(
        ["sh", "-c", "pip install playwright --quiet 2>&1 && playwright install chromium 2>&1"],
        timeout_ms=180_000,
    )
    if result.exit_code != 0:
        print(f"[bootstrap] install warning (non-fatal): {result.stderr[:300]}", file=sys.stderr)
    else:
        print("[bootstrap] done", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape web content with Playwright in a sandbox.")
    parser.add_argument(
        "--query",
        default="AI",
        help="Search query for Hacker News (default: AI)",
    )
    args = parser.parse_args()

    task = (
        f"Navigate to https://news.ycombinator.com and extract the titles "
        f"of the first 5 stories on the homepage that contain the term "
        f"'{args.query}' (case-insensitive). If fewer than 5 stories match, "
        f"return all matching stories found. Save the results to "
        f"/workspace/results.md as a markdown list and print them to stdout."
    )

    artifact_path: Path | None = None
    with NeevAI() as client:
        sandbox = create_browser_sandbox(client)
        try:
            bootstrap(sandbox)

            loop = StreamingAgentLoop(
                sandbox,
                system_prompt=SYSTEM_PROMPT,
                tools=[RUN_SHELL_TOOL],
                handlers={"run_shell": make_run_shell_handler(sandbox)},
                max_steps=MAX_STEPS,
            )
            final = loop.run(task)
            print(final)
        finally:
            artifact_path = pull_artifact_if_exists(sandbox, "results.md", OUTPUT_DIR)
            if artifact_path is None:
                print(
                    "warning: results.md was not created. The agent may have failed to scrape.",
                    file=sys.stderr,
                )
            print(f"[sandbox] deleting {sandbox.id}", file=sys.stderr)
            sandbox.delete()

    if artifact_path is None:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
