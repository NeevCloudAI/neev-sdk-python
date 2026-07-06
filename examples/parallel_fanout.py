"""
Distribute work across multiple sandboxes and combine the results.

Provisions one isolated sandbox per job, downloads a different public
GitHub repository in each, counts source files by language in parallel, prints
aggregated totals on stdout, and tears everything down.

Why parallel sandboxes
----------------------

Use a separate sandbox per independent task when you need **isolation** (untrusted
code or data cannot affect other jobs), **security** (a compromise stays
contained), or **speed** (CPU-bound or I/O-bound work with no shared state).
Each sandbox gets its own filesystem and process space; you combine results only
after all workers finish.

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

1. **Provision** — create one sandbox per job with distinct names
2. **Wait until ready** — call ``wait_until_ready`` on each sandbox
3. **Parallel analysis** — ``ThreadPoolExecutor`` runs ``analyze_repo`` per job
4. **Aggregate** — sum file counts and print the summary on stdout
5. **Cleanup** — delete all sandboxes in a ``finally`` block

Example Output
--------------

::

    [fanout] provisioning 3 sandboxes…

    [fanout] analyzing repo 1…
    [fanout] analyzing repo 2…
    [fanout] analyzing repo 3…

    [fanout] repo 1 -> 42 Python files
    [fanout] repo 2 -> 18 TypeScript files
    [fanout] repo 3 -> 35 Go files

    Analysis complete:
      Total repositories: 3
      Total source files: 95

    [fanout] deleting sandboxes…

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    NEEV_SANDBOX_TEMPLATE_ID=sb-ubuntu-26-04-minimal \\
    uv run python examples/parallel_fanout.py
"""

from __future__ import annotations

import os
import random
import string
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TypedDict

from neevai import NeevAI
from neevai.handles import Sandbox

# Tunable defaults — override via environment variables listed in the docstring.
TEMPLATE = os.environ.get("NEEV_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")
EXEC_TIMEOUT_MS = 300_000


class RepoJob(TypedDict):
    id: int
    display_name: str
    owner: str
    repo: str
    language: str
    extensions: list[str]


JOBS: list[RepoJob] = [
    {
        "id": 1,
        "display_name": "click",
        "owner": "pallets",
        "repo": "click",
        "language": "Python",
        "extensions": ["py"],
    },
    {
        "id": 2,
        "display_name": "zod",
        "owner": "colinhacks",
        "repo": "zod",
        "language": "TypeScript",
        "extensions": ["ts", "tsx"],
    },
    {
        "id": 3,
        "display_name": "hello",
        "owner": "golang",
        "repo": "example",
        "language": "Go",
        "extensions": ["go"],
    },
]

SHARDS = len(JOBS)


def log(message: str) -> None:
    """Print a ``[fanout]`` progress line to stderr."""
    print(f"[fanout] {message}", file=sys.stderr)


def _rand_suffix() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


def _find_expr(extensions: list[str]) -> str:
    clauses = " -o ".join(f'-name "*.{ext}"' for ext in extensions)
    return f"\\( {clauses} \\)" if len(extensions) > 1 else f"-name '*.{extensions[0]}'"


def analyze_repo(sandbox: Sandbox, job: RepoJob) -> int:
    """Download a GitHub archive, extract it, and count matching source files."""
    owner = job["owner"]
    repo = job["repo"]
    find_expr = _find_expr(job["extensions"])
    script = f"""
set -e
mkdir -p /workspace
downloader=""
for tool in wget curl; do
  if command -v "$tool" >/dev/null 2>&1; then downloader="$tool"; break; fi
done
if [ -z "$downloader" ]; then
  echo "wget or curl required" >&2
  exit 1
fi

downloaded=0
for branch in main master; do
  url="https://codeload.github.com/{owner}/{repo}/tar.gz/refs/heads/$branch"
  rm -f /workspace/repo.tar.gz
  if [ "$downloader" = "curl" ]; then
    curl -fsSL "$url" -o /workspace/repo.tar.gz && downloaded=1 && break
  else
    wget -qO /workspace/repo.tar.gz "$url" && downloaded=1 && break
  fi
done

if [ "$downloaded" -ne 1 ] || [ ! -s /workspace/repo.tar.gz ]; then
  echo "archive download failed for {owner}/{repo}" >&2
  exit 1
fi

mkdir -p /workspace/repo
tar -xzf /workspace/repo.tar.gz -C /workspace/repo --strip-components=1
cd /workspace/repo
find . {find_expr} -type f | wc -l
"""
    result = sandbox.exec(["sh", "-c", script], timeout_ms=EXEC_TIMEOUT_MS)
    if result.exit_code != 0:
        raise RuntimeError(
            f"repo {job['id']} ({owner}/{repo}) failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    return int(result.stdout.strip())


def main() -> None:
    with NeevAI() as client:
        log(f"provisioning {SHARDS} sandboxes…")
        sandboxes = [
            client.sandboxes.create(
                {
                    "name": f"fanout-{job['id']}-{_rand_suffix()}",
                    "sandbox_template_id": TEMPLATE,
                }
            )
            for job in JOBS
        ]

        try:
            for sandbox in sandboxes:
                sandbox.wait_until_ready()

            counts: list[int] = [0] * SHARDS

            def run_job(index: int) -> tuple[int, int]:
                job = JOBS[index]
                log(f"analyzing repo {job['id']}…")
                return index, analyze_repo(sandboxes[index], job)

            with ThreadPoolExecutor(max_workers=SHARDS) as pool:
                futures = [pool.submit(run_job, i) for i in range(SHARDS)]
                for future in as_completed(futures):
                    index, count = future.result()
                    counts[index] = count

            for job, count in zip(JOBS, counts, strict=True):
                log(f"repo {job['id']} -> {count} {job['language']} files")

            total_files = sum(counts)
            print("Analysis complete:")
            print(f"  Total repositories: {len(JOBS)}")
            print(f"  Total source files: {total_files}")
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
