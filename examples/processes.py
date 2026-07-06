"""
Start a supervised process, follow logs, poll, list, kill, and wait.

Demonstrates ``sandbox.processes.start``, ``follow``, ``logs``, ``list``,
``kill``, and ``wait`` for detached long-running processes.

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
   processes
3. **Start & follow** — ``sandbox.processes.start`` and stream stdout via
   ``follow``
4. **Poll & list** — ``proc.logs()`` and ``sandbox.processes.list()``
5. **Kill & wait** — ``proc.kill`` and ``proc.wait``
6. **Delete** — remove the sandbox in a ``finally`` block

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    uv run python examples/processes.py
"""

from __future__ import annotations

import os
import random
import string
import sys
import time

from neevai import NeevAI, Signal
from neevai.errors import APIConnectionError, APIError, APITimeoutError, NeevAIError
from neevai.handles.sandbox import Sandbox

# Tunable defaults — override via environment variables listed in the docstring.
TEMPLATE = os.environ.get("NEEV_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")
WAIT_TIMEOUT_MS = int(os.environ.get("NEEVAI_WAIT_TIMEOUT_MS", "300000"))
POLL_INTERVAL_MS = int(os.environ.get("NEEVAI_POLL_INTERVAL_MS", "2000"))


def log(message: str) -> None:
    print(f"[processes] {message}", file=sys.stderr)


def _rand_suffix() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


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
                    "name": f"processes-demo-{_rand_suffix()}",
                    "sandbox_template_id": TEMPLATE,
                }
            )
            _wait_before_processes(sandbox)
            log(f"ready: {sandbox.id}")

            proc = sandbox.processes.start(
                [
                    "sh",
                    "-c",
                    "i=0; while [ $i -lt 10 ]; do echo line-$i; i=$((i+1)); sleep 1; done",
                ],
            )
            log(f"started process {proc.id}")

            line_count = 0
            for event in proc.follow():
                if event["type"] == "stdout":
                    print(event["data"], end="")
                    line_count += 1
                    if line_count >= 3:
                        break
                elif event["type"] == "exit":
                    print(f"\nexit code: {event['exit_code']}")

            page = proc.logs()
            log(f"polled {len(page.entries)} log entries (cursor={page.cursor})")

            running = sandbox.processes.list()
            log(f"listed {len(running)} process(es)")

            proc.kill(signal=Signal.TERM)
            final = proc.wait()
            log(f"process exited with code {final.exit_code}")
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
