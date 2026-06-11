"""
Data Analysis — analyze a CSV with pandas/matplotlib in a Neev sandbox.

Demonstrates:
- Reading and analyzing untrusted CSV data
- Running data-science code (pandas, matplotlib) in isolation
- Producing visual artifacts safely
- Disposable sandbox for Code Interpreter-style workflows

Run::

    python examples/use_cases/data_analysis.py \\
        --csv examples/use_cases/fixtures/sales.csv
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agents"))

from utils.agent_loop import (
    RUN_SHELL_TOOL,
    StreamingAgentLoop,
    make_run_shell_handler,
    pull_artifact,
)

from neevai import NeevAI

SYSTEM_PROMPT = (
    "You are a data-analysis assistant. You have a run_shell tool that executes "
    "POSIX sh in a secure Neev sandbox. The file /workspace/sales.csv contains "
    "columns: date, product, region, units, revenue.\n"
    "Write a Python script using pandas and matplotlib (saved as /workspace/analyze.py) "
    "that:\n"
    "1. Loads and summarizes the CSV\n"
    "2. Creates a compelling chart (save as /workspace/chart.png)\n"
    "3. Prints key insights to stdout\n"
    "Run it with: python3 /workspace/analyze.py\n"
    "Use <<'PY' heredoc syntax to write the script. Print insights to stdout."
)

MAX_STEPS = int(os.environ.get("NEEVAI_USE_CASE_MAX_STEPS", "12"))

HERE = Path(__file__).resolve().parent
OUTPUT_DIR = HERE / "output"
DEFAULT_CSV = HERE / "fixtures" / "sales.csv"


def create_python_sandbox(
    client: NeevAI, region: str | None = None
) -> NeevAI.handles.sandbox.Sandbox:
    template_id = os.environ.get(
        "NEEVCLOUD_PYTHON_SANDBOX_IMAGE",
        os.environ.get("NEEVCLOUD_SANDBOX_TEMPLATE_ID", "ghcr.io/neevcloud/sandbox-python:3.12"),
    )
    resolved_region = region or os.environ.get("NEEVCLOUD_REGION", "as-south-1")
    suffix = hex(int(time.time() * 1e6))[-6:]
    print(
        f"[sandbox] creating (template={template_id}, region={resolved_region})…", file=sys.stderr
    )
    sandbox = client.sandboxes.create(
        {
            "name": f"data-analysis-{suffix}",
            "sandbox_template_id": template_id,
            "region": resolved_region,
        }
    )
    print(f"[sandbox] created {sandbox.id}; waiting until ready…", file=sys.stderr)
    sandbox.wait_until_ready()
    print(f"[sandbox] ready: {sandbox.connect_url}", file=sys.stderr)
    return sandbox


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze a CSV with pandas/matplotlib in a sandbox."
    )
    parser.add_argument(
        "--csv",
        default=str(DEFAULT_CSV),
        help=f"Path to CSV file (default: {DEFAULT_CSV})",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"error: CSV not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    with NeevAI() as client:
        sandbox = create_python_sandbox(client)
        try:
            csv_data = csv_path.read_bytes()
            sandbox.files.write("sales.csv", csv_data)
            print(f"[seed] uploaded {len(csv_data)} bytes as /workspace/sales.csv", file=sys.stderr)

            loop = StreamingAgentLoop(
                sandbox,
                system_prompt=SYSTEM_PROMPT,
                tools=[RUN_SHELL_TOOL],
                handlers={"run_shell": make_run_shell_handler(sandbox)},
                max_steps=MAX_STEPS,
            )
            final = loop.run("Analyze /workspace/sales.csv and create /workspace/chart.png.")
            print(final)

            pull_artifact(sandbox, "/workspace/chart.png", OUTPUT_DIR)
        except FileNotFoundError as exc:
            print(f"error: {exc}", file=sys.stderr)
            print(
                "The chart was not created. The agent may have failed to produce it.",
                file=sys.stderr,
            )
            sys.exit(1)
        finally:
            print(f"[sandbox] deleting {sandbox.id}", file=sys.stderr)
            sandbox.delete()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
