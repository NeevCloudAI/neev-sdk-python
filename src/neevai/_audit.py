"""Query building shared by the sandbox and agent audit-trail calls."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

AuditStatus = Literal["success", "failure"]
AuditActorType = Literal["user", "api_key", "system"]


def _csv(value: str | Sequence[str]) -> str:
    # A bare str is itself a Sequence[str], so it must not be joined character by character.
    return value if isinstance(value, str) else ",".join(value)


def audit_query(
    *,
    from_: str | None,
    to: str | None,
    cursor: str | None,
    limit: int | None,
    operation: str | Sequence[str] | None,
    status: AuditStatus | None,
    actor_type: AuditActorType | Sequence[AuditActorType] | None,
    actor_uid: str | None,
    credential_uid: str | None,
) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if from_ is not None:
        query["from"] = from_
    if to is not None:
        query["to"] = to
    if cursor is not None:
        query["cursor"] = cursor
    if limit is not None:
        query["limit"] = limit
    if operation is not None:
        query["operation"] = _csv(operation)
    if status is not None:
        query["status"] = status
    if actor_type is not None:
        query["actor_type"] = _csv(actor_type)
    if actor_uid is not None:
        query["actor_uid"] = actor_uid
    if credential_uid is not None:
        query["credential_uid"] = credential_uid
    return query
