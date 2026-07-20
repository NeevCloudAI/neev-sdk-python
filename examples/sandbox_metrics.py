"""
Simulate a realistic workload while polling live sandbox health.

Provisions a sandbox, runs a simulated quarterly report job in timed
processing batches, and calls ``sandbox.metrics()`` after each batch to show
how CPU, memory, and disk usage change under load. Prints a final metrics
summary and deletes the sandbox. Polling stops early after batch 3 once at
least one metric series has data points.

Why metrics matter
------------------

``sandbox.metrics()`` returns CPU, memory, and disk time series from the
the API. Use it to see whether a sandbox is under load, hitting limits,
or ready for more work — for example when monitoring long-running jobs,
debugging slow tasks, or planning capacity. This example focuses on what
developers can learn from those numbers, not on how Neev collects metrics
internally.

What ``sandbox.metrics()`` is
-----------------------------

Queries live health metrics for the sandbox. The response contains one or
more series — each with a metric name, data points, and units (for example
cores or bytes). As the SDK puts it: queries live health metrics for this
sandbox.

Prerequisites
-------------

Required environment variables:

- ``NEEV_API_KEY`` — API key for your organization
- ``NEEV_ORG_ID`` — organization ID
- ``NEEV_PROJECT_ID`` — project ID

Optional overrides:

- ``NEEV_SANDBOX_TEMPLATE_ID`` — template to provision (default:
  ``sb-ubuntu-26-04-minimal``)

Module constants (not env-overridable):

- ``BATCHES`` — number of processing batches to run (default: ``8``)
- ``BATCH_SECONDS`` — duration of each batch in seconds (default: ``15``)

Flow
----

1. **Create** — call ``client.sandboxes.create`` with the template
2. **Wait** — block on ``sandbox.wait_until_ready``
3. **Processing loop** — for each batch, run a simulated record-processing job,
   then call ``sandbox.metrics()`` and log health; exit early after batch 3 if
   any series has points
4. **Final summary** — fetch metrics again and print per-series point counts
   and last values on stdout
5. **Delete** — remove the sandbox in a ``finally`` block

Example Output
--------------

::

    [metrics] creating sandbox (sb-ubuntu-26-04-minimal)…
    [metrics] ready: sb-abc123
    [metrics] starting report generation job
    [metrics] batch 1/8 complete — checking sandbox health…
    [metrics] batch 1/8: cpu_usage_cores=0.12 cores(2pts)  memory_usage_bytes=…
    [metrics] batch 2/8 complete — checking sandbox health…
    [metrics] batch 2/8: cpu_usage_cores=0.35 cores(3pts)  memory_usage_bytes=…
    [metrics] batch 3/8 complete — checking sandbox health…
    [metrics] batch 3/8: cpu_usage_cores=0.41 cores(4pts)  memory_usage_bytes=…
    metrics for sandbox sb-abc123 (2026-06-12T10:00:00Z -> 2026-06-12T10:01:00Z):
      cpu_usage_cores: 4 points, last=0.41 cores
      memory_usage_bytes: 4 points, last=524288000 bytes
    [metrics] deleting sandbox sb-abc123

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    NEEV_SANDBOX_TEMPLATE_ID=sb-ubuntu-26-04-minimal \\
    uv run python examples/sandbox_metrics.py
"""

from __future__ import annotations

import os
import sys

from neevai import NeevAI
from neevai.handles import Sandbox
from neevai.types import SandboxMetricsResponse

# Tunable defaults — override via environment variables listed in the docstring.
# BATCHES and BATCH_SECONDS are module constants (see docstring).
TEMPLATE = os.environ.get("NEEV_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")
BATCHES = 8
BATCH_SECONDS = 15


def log(message: str) -> None:
    """Print a ``[metrics]`` progress line to stderr."""
    print(f"[metrics] {message}", file=sys.stderr)


def run_processing_batch(sandbox: Sandbox, batch: int, total: int, seconds: int) -> None:
    """Simulate CPU-heavy batch work (e.g. processing customer records)."""
    script = f"""
echo "Processing batch {batch} of {total} customer record batches..."
end=$(( $(date +%s) + {seconds} )); while [ $(date +%s) -lt $end ]; do :; done
"""
    sandbox.exec(["sh", "-c", script.strip()], timeout_ms=(seconds + 10) * 1000)


def summarize(metrics: SandboxMetricsResponse) -> str:
    """Format a one-line per-series snapshot for batch-loop logging."""
    parts = []
    for series in metrics.series:
        last = series.points[-1] if series.points else None
        value = f"{float(last[1]):.3g}" if last else "—"
        unit = f" {series.unit}" if series.unit else ""
        parts.append(f"{series.metric}={value}{unit}({len(series.points)}pts)")
    return "  ".join(parts)  # pyright: ignore[reportUnknownArgumentType]


def main() -> None:
    with NeevAI() as client:
        # --- Create ---
        log(f"creating sandbox ({TEMPLATE})…")
        sandbox = client.sandboxes.create(
            {
                "sandbox_template_id": TEMPLATE,
            }
        )

        try:
            # --- Wait until ready ---
            sandbox.wait_until_ready()
            log(f"ready: {sandbox.id}")

            # --- Processing loop ---
            log("starting report generation job")
            for i in range(1, BATCHES + 1):
                run_processing_batch(sandbox, i, BATCHES, BATCH_SECONDS)
                log(f"batch {i}/{BATCHES} complete — checking sandbox health…")
                metrics = sandbox.metrics()
                log(f"batch {i}/{BATCHES}: {summarize(metrics)}")
                if any(s.points for s in metrics.series) and i >= 3:
                    break

            # --- Final summary ---
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
            # --- Cleanup ---
            log(f"deleting sandbox {sandbox.id}")
            sandbox.delete()


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        print(err, file=sys.stderr)
        sys.exit(1)
