"""
Start multiple supervised processes in parallel, then kill all.

Demonstrates parallel ``sandbox.processes.start``, ``list``, per-handle
``status``, ``kill_all``, and ``wait``.

Prerequisites
-------------

Required environment variables:

- ``NEEV_API_KEY`` — API key for your organization
- ``NEEV_ORG_ID`` — organization ID
- ``NEEV_PROJECT_ID`` — project ID

Optional overrides:

- ``NEEV_SANDBOX_TEMPLATE_ID`` — template to provision (default:
  ``sb-ubuntu-26-04-minimal``)
- ``NEEVAI_WAIT_TIMEOUT_MS`` — max time to wait for connect URL, Ready phase,
  and runtime in ms (default: ``300000``)
- ``NEEVAI_POLL_INTERVAL_MS`` — poll interval while waiting in ms (default:
  ``2000``)

Flow
----

1. **Create** — call ``client.sandboxes.create`` with the template
2. **Wait** — poll until ``connect_url`` is set, block on ``wait_until_ready``,
   then probe the sandbox runtime with ``sandbox.processes.list`` before starting
   workers
3. **Start workers** — ``sandbox.processes.start`` for each worker in parallel
4. **List & status** — ``sandbox.processes.list()`` and per-handle ``status()``
5. **Kill all** — ``sandbox.processes.kill_all`` and ``wait`` each worker
6. **Delete** — remove the sandbox in a ``finally`` block

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    uv run python examples/process_pool.py
"""

from __future__ import annotations

import os
import sys
import time

from neevai import NeevAI, Signal
from neevai.errors import APIConnectionError, APIError, APITimeoutError, NeevAIError
from neevai.handles.sandbox import Sandbox

# Tunable defaults — override via environment variables listed in the docstring.
TEMPLATE = os.environ.get("NEEV_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")
WAIT_TIMEOUT_MS = int(os.environ.get("NEEVAI_WAIT_TIMEOUT_MS", "300000"))
POLL_INTERVAL_MS = int(os.environ.get("NEEVAI_POLL_INTERVAL_MS", "2000"))
WORKER_COUNT = 3


def log(message: str) -> None:
    print(f"[process-pool] {message}", file=sys.stderr)


def _remaining_ms(deadline_ms: float) -> int:
    return max(0, int(deadline_ms - time.time() * 1000.0))


def _is_transient_runtime_error(exc: Exception) -> bool:
    if isinstance(exc, (APIConnectionError, APITimeoutError)):
        return True
    return isinstance(exc, APIError) and exc.status_code in (502, 503, 504)


def _wait_for_connect_url(sandbox: Sandbox, *, deadline_ms: float) -> None:
    while not sandbox.connect_url:
        remaining = _remaining_ms(deadline_ms)
        if remaining <= 0:
            raise NeevAIError(
                f"Sandbox {sandbox.id} did not receive connect_url within {WAIT_TIMEOUT_MS}ms "
                f"(phase: {sandbox.phase}, replicas: {sandbox.replicas})."
            )
        log(f"waiting for connect_url (phase={sandbox.phase}, replicas={sandbox.replicas})…")
        time.sleep(min(POLL_INTERVAL_MS, remaining) / 1000.0)
        sandbox.refresh()

    log(f"connect_url: {sandbox.connect_url}")


def _wait_for_runtime(sandbox: Sandbox, *, deadline_ms: float) -> None:
    while True:
        remaining = _remaining_ms(deadline_ms)
        if remaining <= 0:
            raise NeevAIError(
                f"Sandbox {sandbox.id} runtime did not become reachable within "
                f"{WAIT_TIMEOUT_MS}ms (connect_url: {sandbox.connect_url})."
            )
        try:
            sandbox.processes.list()
            return
        except Exception as exc:
            if not _is_transient_runtime_error(exc):
                raise
            log("waiting for the sandbox runtime…")
            time.sleep(min(POLL_INTERVAL_MS, remaining) / 1000.0)


def _wait_before_processes(sandbox: Sandbox) -> None:
    """Wait for connect_url, Ready phase, and a reachable runtime (shared deadline)."""
    deadline_ms = time.time() * 1000.0 + WAIT_TIMEOUT_MS

    _wait_for_connect_url(sandbox, deadline_ms=deadline_ms)

    remaining = _remaining_ms(deadline_ms)
    if remaining <= 0:
        raise NeevAIError(
            f"Sandbox {sandbox.id} did not become Ready within {WAIT_TIMEOUT_MS}ms "
            f"(phase: {sandbox.phase}, replicas: {sandbox.replicas}, "
            f"connect_url: {sandbox.connect_url})."
        )
    sandbox.wait_until_ready(
        timeout_ms=remaining,
        poll_interval_ms=POLL_INTERVAL_MS,
        on_poll=lambda s: log(f"phase={s.phase} replicas={s.replicas}"),
    )

    _wait_for_runtime(sandbox, deadline_ms=deadline_ms)


def main() -> None:
    with NeevAI() as client:
        sandbox = None
        try:
            log(f"creating sandbox ({TEMPLATE})…")
            sandbox = client.sandboxes.create(
                {
                    "sandbox_template_id": TEMPLATE,
                }
            )
            _wait_before_processes(sandbox)
            log(f"ready: {sandbox.id}")

            workers = []
            for worker_id in range(WORKER_COUNT):
                proc = sandbox.processes.start(
                    ["sh", "-c", f"echo worker-{worker_id}; sleep 60"],
                )
                workers.append(proc)
                log(f"started worker {worker_id}: {proc.id}")

            listed = sandbox.processes.list()
            log(f"listed {len(listed)} process(es)")

            for proc in workers:
                status = proc.status()
                log(f"{proc.id} state={status.state}")

            signalled = sandbox.processes.kill_all(signal=Signal.TERM)
            log(f"kill_all signalled {signalled} process(es)")

            for proc in workers:
                final = proc.wait()
                log(f"{proc.id} exit_code={final.exit_code}")
        except NeevAIError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            if sandbox is not None:
                try:
                    log(f"deleting sandbox {sandbox.id}")
                    sandbox.delete()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
