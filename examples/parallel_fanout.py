"""
Fan out work across several isolated sandboxes, then read their metrics.

Provisions N gVisor-isolated sandboxes concurrently, runs an independent piece
of a map/reduce (each sums a slice of 1..3000) in each, reduces the partials,
reads each sandbox's live metric series, and tears them all down.

Run::

    NEEVCLOUD_API_KEY=... NEEVCLOUD_ORG_ID=... NEEVCLOUD_PROJECT_ID=... \\
    uv run python examples/parallel_fanout.py
"""

from __future__ import annotations

import os
import random
import string
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from neevai import NeevAI

REGION = os.environ.get("NEEVCLOUD_REGION", "as-south-1")
TEMPLATE = os.environ.get("NEEVCLOUD_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")
TOTAL = 3000
SHARDS = 3


def log(message: str) -> None:
    print(f"[fanout] {message}", file=sys.stderr)


def _rand_suffix() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


def sum_range(sandbox, start: int, end: int) -> int:
    script = (
        f"s=0; i={start}; while [ $i -le {end} ]; do s=$((s+i)); i=$((i+1)); done; echo $s"
    )
    result = sandbox.exec(["sh", "-c", script])
    if result.exit_code != 0:
        raise RuntimeError(f"shard [{start},{end}] failed: {result.stderr}")
    return int(result.stdout.strip())


def main() -> None:
    size = (TOTAL + SHARDS - 1) // SHARDS
    slices = [
        {"from": i * size + 1, "to": min((i + 1) * size, TOTAL)} for i in range(SHARDS)
    ]

    with NeevAI() as client:
        log(f"provisioning {SHARDS} sandboxes ({TEMPLATE}, {REGION})…")
        sandboxes = [
            client.sandboxes.create(
                {
                    "name": f"fanout-{i}-{_rand_suffix()}",
                    "sandbox_template_id": TEMPLATE,
                    "region": REGION,
                }
            )
            for i in range(SHARDS)
        ]

        try:
            for sandbox in sandboxes:
                sandbox.wait_until_ready()

            log("running shards…")

            def run_shard(index: int) -> tuple[int, int]:
                s = slices[index]
                return index, sum_range(sandboxes[index], s["from"], s["to"])

            partials: list[int] = [0] * SHARDS
            with ThreadPoolExecutor(max_workers=SHARDS) as pool:
                futures = [pool.submit(run_shard, i) for i in range(SHARDS)]
                for future in as_completed(futures):
                    index, value = future.result()
                    partials[index] = value

            for i, s in enumerate(slices):
                log(f"shard [{s['from']}, {s['to']}] -> {partials[i]}")

            total = sum(partials)

            log("reading metrics…")
            for i, sandbox in enumerate(sandboxes):
                metrics = sandbox.metrics()
                series = ", ".join(
                    f"{entry.metric}({len(entry.points)}pts)" for entry in metrics.series
                )
                log(f"sandbox {i} metrics: {series or '(none yet)'}")

            print(f"sum(1..{TOTAL}) across {SHARDS} sandboxes = {total}")
        finally:
            log("deleting sandboxes…")
            for sandbox in sandboxes:
                try:
                    sandbox.delete()
                except Exception:
                    pass


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        print(err, file=sys.stderr)
        sys.exit(1)
