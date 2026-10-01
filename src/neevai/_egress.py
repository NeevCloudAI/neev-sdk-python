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

    ``allow_internet`` sets the ``allow_internet`` flag and also lists ``0.0.0.0/0`` and
    ``::/0`` as allowed hosts, so all outbound traffic is allowed. ``allow_egress`` allows
    specific hosts (FQDN or CIDR).
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
    Raises before any request when the body is empty, or when a full ``egress``
    replacement (explicit or from the convenience) is combined with ``egress_add`` /
    ``egress_remove``, which edit the existing allow-list instead.
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
        fields = ", ".join(f"`{name}`" for name in param_type.model_fields)
        raise NeevAIError(
            f"{param_type.__name__} must include at least one of {fields}; "
            "empty body is not allowed."
        )
    if body.get("egress") is not None and (
        body.get("egress_add") is not None or body.get("egress_remove") is not None
    ):
        raise NeevAIError(
            "`egress` replaces the whole policy and cannot be combined with `egress_add` or "
            "`egress_remove`; `allow_internet` / `allow_egress` set `egress` too."
        )
    return body
