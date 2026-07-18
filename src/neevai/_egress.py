"""Egress convenience shared by sandbox and agent create."""

from __future__ import annotations

from typing import Any


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
