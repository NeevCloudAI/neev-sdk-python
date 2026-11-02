"""
Use a paused sandbox without resuming it first.

Where the platform's automatic wake-up is enabled, a request to a paused sandbox
wakes it and is delivered once the sandbox is ready: one slow response instead of
an error. This pauses a sandbox, reads a file back with ``exec`` without calling
``resume()``, and prints ``RESULT: woke automatically``, ``resumed explicitly`` or
``failed``.

If ``exec`` gets a 429 and the sandbox is still ``Paused``, it calls ``resume()``
and runs the read-only command once more. In the current backend a 429 on this
path is sent before the command runs; that is not an API guarantee, so don't
replay commands that change state. A 503 is not replayed.

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    uv run python examples/auto_resume.py
"""

from __future__ import annotations

import os
import sys
import time

from neevai import NeevAI
from neevai.errors import APIError, NeevAIError

TEMPLATE = os.environ.get("NEEV_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-dev")
MARKER_FILE = "auto-resume-marker.txt"
MARKER_TEXT = "written before the pause"
PHASE_TIMEOUT_SEC = 120


def wait_for(sandbox, done, expected: str) -> None:
    """Polls until done(sandbox) holds, or raises after PHASE_TIMEOUT_SEC."""
    deadline = time.monotonic() + PHASE_TIMEOUT_SEC
    while not done(sandbox):
        if time.monotonic() > deadline:
            raise NeevAIError(f"sandbox still {sandbox.phase}; expected {expected}")
        time.sleep(2)
        sandbox.refresh()


def read_marker(sandbox) -> str:
    """Reads the marker back; a different text means the files did not survive."""
    result = sandbox.exec(["cat", MARKER_FILE], timeout_ms=PHASE_TIMEOUT_SEC * 1000)
    text = result.stdout.strip()
    if result.exit_code != 0 or text != MARKER_TEXT:
        raise NeevAIError(f"marker not intact: {text!r} {result.stderr}")
    return text


def use_paused_sandbox(sandbox) -> str:
    """Reads the marker without resuming; returns which path made it work."""
    started = time.monotonic()
    try:
        read_marker(sandbox)
        print(f"woke in {time.monotonic() - started:.1f}s")
        return "woke automatically"
    except APIError as e:
        if e.status_code != 429:
            raise
        sandbox.refresh()
        if sandbox.phase != "Paused":
            raise
        print(f"429 and still Paused ({e}); resuming explicitly")

    sandbox.resume()
    # wait_until_ready() gives up at once on Paused, so first wait for resume to take effect.
    wait_for(sandbox, lambda s: s.phase != "Paused", "to leave Paused")
    sandbox.wait_until_ready()
    read_marker(sandbox)
    print(f"resumed in {time.monotonic() - started:.1f}s")
    return "resumed explicitly"


def main() -> None:
    with NeevAI() as client:
        sandbox = None
        try:
            sandbox = client.sandboxes.create({"sandbox_template_id": TEMPLATE})
            sandbox.wait_until_ready()
            sandbox.files.write(MARKER_FILE, MARKER_TEXT)
            print(f"ready: {sandbox.id}")

            sandbox.pause()
            wait_for(sandbox, lambda s: s.phase == "Paused", "Paused")
            print("paused")

            print(f"RESULT: {use_paused_sandbox(sandbox)}")
        except NeevAIError as e:
            print(f"Error: {e}", file=sys.stderr)
            print("RESULT: failed")
            sys.exit(1)
        finally:
            if sandbox is not None:
                try:
                    sandbox.delete()
                except NeevAIError as e:
                    print(f"cleanup failed, delete {sandbox.id} by hand: {e}", file=sys.stderr)
                    sys.exit(1)


if __name__ == "__main__":
    main()
