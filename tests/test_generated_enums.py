"""String enums from the API spec compare equal to their wire values."""

from neevai.generated.aiagent import AuditActorUser, SnapshotStatus


def test_snapshot_status_equals_its_string() -> None:
    """A `while status != "Ready"` poll must end once the snapshot is Ready."""
    assert SnapshotStatus("Ready") == "Ready"
    assert SnapshotStatus("Pending") != "Ready"


def test_audit_actor_type_equals_its_string() -> None:
    """Callers filter audit events with `event.actor.user.type == "api_key"`."""
    user = AuditActorUser.model_validate({"type": "api_key", "type_id": 99, "uid": "key-1"})
    assert user.type == "api_key"
