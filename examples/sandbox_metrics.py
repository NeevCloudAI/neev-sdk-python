"""
Read live metrics from a sandbox under load.

Provisions one sandbox, drives CPU in short bursts, and polls
``sandbox.metrics()`` after each burst, then tears it down.

Run::

    NEEVCLOUD_API_KEY=... NEEVCLOUD_ORG_ID=... NEEVCLOUD_PROJECT_ID=... \\
    uv run python examples/sandbox_metrics.py
"""

from __future__ import annotations

import os
import random
import string
import sys

from neevai import NeevAI
from neevai.types import SandboxMetricsResponse

REGION = os.environ.get("NEEVCLOUD_REGION", "as-south-1")
TEMPLATE = os.environ.get("NEEVCLOUD_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")
BURSTS = 8
BURST_SECONDS = 15


def log(message: str) -> None:
    print(f"[metrics] {message}", file=sys.stderr)


def _rand_suffix() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


def burn(sandbox, seconds: int) -> None:
    script = f"end=$(( $(date +%s) + {seconds} )); while [ $(date +%s) -lt $end ]; do :; done"
    sandbox.exec(["sh", "-c", script], timeout_ms=(seconds + 10) * 1000)


def summarize(metrics: SandboxMetricsResponse) -> str:
    parts = []
    for series in metrics.series:
        last = series.points[-1] if series.points else None
        value = f"{float(last[1]):.3g}" if last else "—"
        unit = f" {series.unit}" if series.unit else ""
        parts.append(f"{series.metric}={value}{unit}({len(series.points)}pts)")
    return "  ".join(parts)


def main() -> None:
    with NeevAI() as client:
        log(f"creating sandbox ({TEMPLATE}, {REGION})…")
        sandbox = client.sandboxes.create(
            {
                "name": f"metrics-{_rand_suffix()}",
                "sandbox_template_id": TEMPLATE,
                "region": REGION,
            }
        )

        try:
            sandbox.wait_until_ready()
            log(f"ready: {sandbox.id}")

            for i in range(1, BURSTS + 1):
                burn(sandbox, BURST_SECONDS)
                metrics = sandbox.metrics()
                log(f"burst {i}/{BURSTS}: {summarize(metrics)}")
                if any(s.points for s in metrics.series) and i >= 3:
                    break

            metrics = sandbox.metrics()
            print(f"metrics for sandbox {sandbox.id} ({metrics.from_} -> {metrics.to}):")
            for series in metrics.series:
                last = series.points[-1] if series.points else None
                tail = (
                    f", last={float(last[1])}{(' ' + series.unit) if series.unit else ''}"
                    if last
                    else ""
                )
                print(f"  {series.metric}: {len(series.points)} points{tail}")
        finally:
            log(f"deleting sandbox {sandbox.id}")
            sandbox.delete()


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        print(err, file=sys.stderr)
        sys.exit(1)
