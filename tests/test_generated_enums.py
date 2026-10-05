"""String enums from the API spec compare equal to their wire values."""

from neevai.generated.aiagent import AuditRecord, SnapshotStatus


def test_snapshot_status_equals_its_string() -> None:
    """A `while status != "Ready"` poll must end once the snapshot is Ready."""
    assert SnapshotStatus("Ready") == "Ready"
    assert SnapshotStatus("Pending") != "Ready"


def test_audit_outcome_equals_its_string() -> None:
    """Callers filter audit records with `record.outcome == "error"`."""
    record = AuditRecord.model_validate(
        {"at": "2026-10-05T00:00:00Z", "id": "r1", "tool": "exec", "outcome": "error"}
    )
    assert record.outcome == "error"
