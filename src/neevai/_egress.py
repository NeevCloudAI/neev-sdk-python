"""Egress convenience shared by sandbox and agent create/update."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from pydantic import BaseModel

from neevai._parse import coerce_params
from neevai.errors import NeevAIError

T = TypeVar("T", bound=BaseModel)


def build_egress(
    allow_internet: bool | None,
    allow_egress: list[str] | None,
) -> dict[str, Any] | None:
    """Map the ``allow_internet`` / ``allow_egress`` convenience to an egress policy.

    ``allow_internet`` emits BOTH the ``allow_internet`` gate AND explicit ``0.0.0.0/0``
    and ``::/0`` routes, because the gate alone is a server-side no-op — the routes are
    what actually open egress. ``allow_egress`` allows specific hosts (FQDN or CIDR).
    Returns ``None`` when neither is set, so the platform/template default applies.
    """
    if not allow_internet and not allow_egress:
        return None
    rules: list[dict[str, str]] = []
    if allow_internet:
        rules.append({"host": "0.0.0.0/0"})
        rules.append({"host": "::/0"})
    for host in allow_egress or []:
        rules.append({"host": host})
    return {"mode": "allow_list", "allow_internet": bool(allow_internet), "allow": rules}


def prepare_update_body(
    param_type: type[T],
    params: T | Mapping[str, Any],
    allow_internet: bool | None = None,
    allow_egress: list[str] | None = None,
) -> dict[str, Any]:
    """Build the PATCH body for a sandbox/agent in-place update.

    Applies the ``allow_internet`` / ``allow_egress`` convenience (unless an explicit
    ``egress`` is already set), validates against ``param_type``, and serialises with
    ``mode="json"`` so the egress policy is byte-identical to what ``create`` sends.
    Raises before any request when neither ``resources`` nor ``egress`` is present.
    """
    if isinstance(params, Mapping):
        raw: dict[str, Any] = dict(params)
    else:
        raw = params.model_dump(exclude_unset=True)
    if raw.get("egress") is None:
        egress = build_egress(allow_internet, allow_egress)
        if egress is not None:
            raw["egress"] = egress
    body = coerce_params(param_type, raw).model_dump(mode="json", exclude_unset=True)
    if not body:
        raise NeevAIError(
            f"{param_type.__name__} must include at least one of `resources` or `egress`; "
            "empty body is not allowed."
        )
    return body
