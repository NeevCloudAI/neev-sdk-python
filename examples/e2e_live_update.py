"""
LIVE end-to-end check for in-place resize + live egress update (sandbox).

This is the criterion the mock suite cannot cover: it runs against the real
backend and specifically exercises the **combined** ``resources + egress``
PATCH that AIPLATFORM-1896 is about (a bundled update briefly reverting the new
egress policy). It is a standalone script (not part of the mock pytest suite) so
it only ever touches the backend when you run it deliberately.

Run it from a network that can actually reach the API (VPN / allow-listed host)::

    NEEV_API_KEY=...            # key scoped for the AGENT/SANDBOX API
    NEEV_ORG_ID=org-...
    NEEV_PROJECT_ID=prj-...     # a real project id, distinct from the org id
    NEEV_BASE_URL=https://api.dev.ai.neevcloud.com/agent
    NEEV_SANDBOX_TEMPLATE_ID=sb-ubuntu-26-04-minimal   # optional
    uv run python examples/e2e_live_update.py

Exit code is 0 only if every check passes. Each check prints PASS/FAIL.

What it verifies
----------------
1. One combined ``update(resources=…, allow_egress=…)`` emits exactly ONE PATCH
   to ``/sandboxes/{id}`` whose body carries both ``resources`` and ``egress``.
2. ID, name, and preview-URL template are unchanged after the update.
3. The resize is reflected by a fresh ``get``.
4. The new egress policy PERSISTS across repeated reads (the AIPLATFORM-1896
   guard — a brief revert would be caught here).
5. The sandbox does not restart: it stays ``Ready`` with ``replicas == 1`` and
   grows no new ``last_crash``.
6. Real allow/deny behaviour from inside the sandbox: a connection to the
   allowed host succeeds and one to a non-allowed host fails (best-effort — only
   runs if the sandbox runtime is reachable and has a usable HTTP client).
"""

from __future__ import annotations

import os
import sys
import time

from neevai import NeevAI
from neevai.errors import NeevAIError

TEMPLATE = os.environ.get("NEEV_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")
REGION = os.environ.get("NEEV_REGION")  # optional; some backends require it at create
WAIT_TIMEOUT_MS = int(os.environ.get("NEEVAI_WAIT_TIMEOUT_MS", "300000"))
ALLOWED_HOST = "api.github.com"
BLOCKED_HOST = "example.com"

_failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        _failures.append(label)


def main() -> int:
    client = NeevAI()  # reads NEEV_* from the environment

    # Capture every request so we can prove exactly one PATCH is sent.
    calls: list[tuple[str, str, dict | None]] = []
    original = client._transport.request

    def capturing(method, path, query=None, body=None):
        calls.append((method, path, body))
        return original(method, path, query=query, body=body)

    client._transport.request = capturing  # type: ignore[method-assign]

    sandbox = None
    try:
        create_params: dict = {"sandbox_template_id": TEMPLATE}
        if REGION:
            create_params["region"] = REGION
        sandbox = client.sandboxes.create(create_params)
        sandbox.wait_until_ready(timeout_ms=WAIT_TIMEOUT_MS)
        before_id, before_name = sandbox.id, sandbox.name
        before_preview = sandbox.data.get("preview_url_template")
        print(f"ready {before_id} (name={before_name})")

        # --- The combined single PATCH: resize AND re-scope egress at once ---
        n_before = len(calls)
        sandbox.update(
            {"resources": {"cpu": 2, "memory_gb": 4}},
            allow_egress=[ALLOWED_HOST],
        )
        patches = [(p, b) for (m, p, b) in calls[n_before:] if m == "PATCH"]
        check(
            "exactly one PATCH for the combined update",
            len(patches) == 1,
            f"{len(patches)} PATCH(es)",
        )
        if patches:
            path, body = patches[0]
            check("PATCH targets /sandboxes/{id}", path.endswith(f"/sandboxes/{before_id}"), path)
            check(
                "body carries both resources and egress",
                isinstance(body, dict) and "resources" in body and "egress" in body,
                str(body),
            )

        # --- Identity is preserved ---
        check("id unchanged", sandbox.id == before_id)
        check("name unchanged", sandbox.name == before_name)
        check(
            "preview URL template unchanged",
            sandbox.data.get("preview_url_template") == before_preview,
        )

        # --- Resize reflected by a fresh get ---
        got = client.sandboxes.get(before_id)
        res = got.data.get("resources") or {}
        check(
            "resize reflected by get", res.get("cpu") == 2 and res.get("memory_gb") == 4, str(res)
        )

        # --- No restart: still Ready, replicas 1, no new crash ---
        check("still Ready after update", got.phase == "Ready", got.phase)
        check(
            "replicas still 1 (not paused/restarted)",
            got.data.get("replicas") == 1,
            str(got.data.get("replicas")),
        )
        check(
            "no crash recorded by the update",
            got.data.get("last_crash") is None,
            str(got.data.get("last_crash")),
        )

        # --- AIPLATFORM-1896 guard: egress must PERSIST, not briefly revert ---
        def egress_hosts(sb_data: dict) -> list[str]:
            eg = sb_data.get("egress") or {}
            return [r.get("host") for r in (eg.get("allow") or [])]

        persisted = True
        seen = None
        for _ in range(6):  # ~12s of polling
            seen = egress_hosts(client.sandboxes.get(before_id).data)
            if seen != [ALLOWED_HOST]:
                persisted = False
                break
            time.sleep(2)
        check(
            "egress policy persists across reads (no 1896 revert)", persisted, f"last seen={seen}"
        )

        # --- Real allow/deny proof from inside the sandbox (best-effort) ---
        try:
            allowed = sandbox.exec(
                [
                    "sh",
                    "-lc",
                    f"curl -sS -m 8 -o /dev/null -w '%{{http_code}}' https://{ALLOWED_HOST}/ || echo FAIL",
                ],
                timeout_ms=20000,
            )
            blocked = sandbox.exec(
                [
                    "sh",
                    "-lc",
                    f"curl -sS -m 8 -o /dev/null -w '%{{http_code}}' https://{BLOCKED_HOST}/ || echo FAIL",
                ],
                timeout_ms=20000,
            )
            check(
                "allowed host reachable from sandbox",
                allowed.stdout.strip().startswith("2"),
                f"{ALLOWED_HOST} -> {allowed.stdout.strip()!r}",
            )
            check(
                "non-allowed host blocked from sandbox",
                not blocked.stdout.strip().startswith("2"),
                f"{BLOCKED_HOST} -> {blocked.stdout.strip()!r}",
            )
        except Exception as e:  # runtime not reachable / no curl — don't fail the run
            print(f"[SKIP] in-sandbox allow/deny proof — {type(e).__name__}: {str(e)[:160]}")

    except NeevAIError as e:
        check("no unexpected API error", False, f"{type(e).__name__}: {e}")
    finally:
        if sandbox is not None:
            try:
                sandbox.delete()
                print(f"cleaned up {sandbox.id}")
            except NeevAIError as e:
                print(f"[WARN] cleanup failed: {e}", file=sys.stderr)
        client.close()

    print()
    if _failures:
        print(f"E2E FAILED — {len(_failures)} check(s): {_failures}")
        return 1
    print("E2E PASSED — combined resize+egress verified against the live backend")
    return 0


if __name__ == "__main__":
    sys.exit(main())
