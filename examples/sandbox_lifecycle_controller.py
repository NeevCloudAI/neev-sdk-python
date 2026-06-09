"""
Command-line controller for sandbox resource operations.

Requires ``NEEVCLOUD_SANDBOX_TEMPLATE_ID`` for ``create``. Set ``NEEVCLOUD_REGION``
for the deployment region (or pass ``region`` on the client / in create params).

Usage::

    NEEVCLOUD_API_KEY=... NEEVCLOUD_ORG_ID=... NEEVCLOUD_PROJECT_ID=... \\
    NEEVCLOUD_REGION=... NEEVCLOUD_SANDBOX_TEMPLATE_ID=... \\
    python examples/sandbox_lifecycle_controller.py create --name my-sandbox

    python examples/sandbox_lifecycle_controller.py list --page 1 --limit 20
    python examples/sandbox_lifecycle_controller.py get <sandbox-id>
    python examples/sandbox_lifecycle_controller.py pause <sandbox-id>
    python examples/sandbox_lifecycle_controller.py resume <sandbox-id>
    python examples/sandbox_lifecycle_controller.py delete <sandbox-id>
    python examples/sandbox_lifecycle_controller.py metrics <sandbox-id> \\
        --from 2025-01-01T00:00:00Z --to 2025-01-02T00:00:00Z --step 1m
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from neevai import NeevAI
from neevai.errors import NeevAIError
from neevai.handles.sandbox import Sandbox

DEFAULT_IMAGE = "ghcr.io/neevcloud/sandbox-python:3.12"
WAIT_TIMEOUT_MS = int(os.environ.get("NEEVAI_WAIT_TIMEOUT_MS", "300000"))


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2))


def _print_sandbox(sandbox: Sandbox, *, as_json: bool) -> None:
    if as_json:
        _print_json(sandbox.to_json())
        return
    line = f"{sandbox.id}  name={sandbox.name}  phase={sandbox.phase}  replicas={sandbox.replicas}"
    if sandbox.connect_url:
        line += f"  connect_url={sandbox.connect_url}"
    print(line)


def _cmd_create(client: NeevAI, args: argparse.Namespace) -> None:
    template_id = args.template_id or os.environ.get("NEEVCLOUD_SANDBOX_TEMPLATE_ID")
    if not template_id:
        print(
            "Error: --template-id or NEEVCLOUD_SANDBOX_TEMPLATE_ID is required for create",
            file=sys.stderr,
        )
        sys.exit(1)

    sandbox = client.sandboxes.create(
        {
            "name": args.name,
            "sandbox_template_id": template_id,
            "image": args.image,
        }
    )
    if args.wait:
        sandbox.wait_until_ready(
            timeout_ms=WAIT_TIMEOUT_MS,
            on_poll=lambda s: print(f"  phase={s.phase} replicas={s.replicas}", file=sys.stderr),
        )
    _print_sandbox(sandbox, as_json=args.json)


def _cmd_list(client: NeevAI, args: argparse.Namespace) -> None:
    page = client.sandboxes.list(page=args.page, limit=args.limit)
    if args.json:
        _print_json(
            {
                "total": page.total,
                "page": page.page,
                "limit": page.limit,
                "items": [item.to_json() for item in page.items],
            }
        )
        return
    print(f"total={page.total}  page={page.page}  limit={page.limit}")
    for item in page.items:
        print(f"  {item.id}  name={item.name}  phase={item.phase}")


def _cmd_get(client: NeevAI, args: argparse.Namespace) -> None:
    sandbox = client.sandboxes.get(args.sandbox_id)
    _print_sandbox(sandbox, as_json=args.json)


def _cmd_pause(client: NeevAI, args: argparse.Namespace) -> None:
    sandbox = client.sandboxes.pause(args.sandbox_id)
    _print_sandbox(sandbox, as_json=args.json)


def _cmd_resume(client: NeevAI, args: argparse.Namespace) -> None:
    sandbox = client.sandboxes.resume(args.sandbox_id)
    _print_sandbox(sandbox, as_json=args.json)


def _cmd_delete(client: NeevAI, args: argparse.Namespace) -> None:
    client.sandboxes.delete(args.sandbox_id)
    if args.json:
        _print_json({"deleted": args.sandbox_id})
    else:
        print(f"deleted {args.sandbox_id}")


def _cmd_metrics(client: NeevAI, args: argparse.Namespace) -> None:
    metrics = client.sandboxes.metrics(
        args.sandbox_id,
        from_=args.from_,
        to=args.to,
        step=args.step,
    )
    if args.json:
        _print_json(metrics.model_dump(mode="json"))
        return
    print(f"sandbox_id={metrics.sandbox_id}  step={metrics.step}")
    for series in metrics.series:
        print(f"  {series.metric}: {len(series.points)} points")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Control sandbox lifecycle via client.sandboxes resource methods.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON instead of human-readable output.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create a new sandbox.")
    create.add_argument("--name", required=True, help="Sandbox name.")
    create.add_argument(
        "--template-id",
        help="Sandbox template ID (default: NEEVCLOUD_SANDBOX_TEMPLATE_ID).",
    )
    create.add_argument(
        "--image",
        default=DEFAULT_IMAGE,
        help=f"Container image (default: {DEFAULT_IMAGE}).",
    )
    create.add_argument(
        "--wait",
        action="store_true",
        help="Block until the sandbox is ready after create.",
    )

    list_cmd = subparsers.add_parser("list", help="List sandboxes with pagination.")
    list_cmd.add_argument("--page", type=int, default=1, help="Page number (default: 1).")
    list_cmd.add_argument("--limit", type=int, default=20, help="Page size (default: 20).")

    get = subparsers.add_parser("get", help="Get sandbox details.")
    get.add_argument("sandbox_id", help="Sandbox UUID.")

    pause = subparsers.add_parser("pause", help="Pause a sandbox (scale to 0 replicas).")
    pause.add_argument("sandbox_id", help="Sandbox UUID.")

    resume = subparsers.add_parser("resume", help="Resume a paused sandbox.")
    resume.add_argument("sandbox_id", help="Sandbox UUID.")

    delete = subparsers.add_parser("delete", help="Permanently delete a sandbox.")
    delete.add_argument("sandbox_id", help="Sandbox UUID.")

    metrics = subparsers.add_parser("metrics", help="Query sandbox health metrics.")
    metrics.add_argument("sandbox_id", help="Sandbox UUID.")
    metrics.add_argument("--from", dest="from_", help="Start of the query window (ISO 8601).")
    metrics.add_argument("--to", help="End of the query window (ISO 8601).")
    metrics.add_argument("--step", help="Resolution step (e.g. 1m, 5m).")

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    handlers = {
        "create": _cmd_create,
        "list": _cmd_list,
        "get": _cmd_get,
        "pause": _cmd_pause,
        "resume": _cmd_resume,
        "delete": _cmd_delete,
        "metrics": _cmd_metrics,
    }

    with NeevAI(
        api_key=os.environ.get("NEEVCLOUD_API_KEY"),
        org_id=os.environ.get("NEEVCLOUD_ORG_ID"),
        project_id=os.environ.get("NEEVCLOUD_PROJECT_ID"),
    ) as client:
        try:
            handlers[args.command](client, args)
        except NeevAIError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
