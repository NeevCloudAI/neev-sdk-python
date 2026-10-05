---
"neevai": patch
---

Request bodies are encoded the way the API expects, so IDs straight from SDK models work. `sandbox.rollback(snap.id)` and `client.sandboxes.rollback(id, snap.id)` raised `TypeError: Object of type UUID is not JSON serializable`, because a snapshot's `id` is a `UUID`. UUIDs, enums and datetimes inside any request body now serialise to their API form. `snapshot_id` parameters accept `str | UUID`, so passing `snap.id` also type-checks.
