---
"neevai": minor
---

The audit trail returns events instead of records. `sandbox.audit()`, `agent.audit()` and the matching `sandboxes` / `agents` calls now return `AuditTrail.data: list[AuditEvent]`, each event saying which call ran (`api.operation`), who made it (`actor.user`, with the API key in `credential_uid`), how it ended (`status`), what it touched (`resources`) and when (`time`, in milliseconds since the Unix epoch). `AuditTrail.records`, `AuditTrail.sandbox_id` and the `AuditRecord` model are removed.

The audit calls take new filters: `operation` (one name or a list), `status` (`"success"` or `"failure"`), `actor_type` (`"user"`, `"api_key"`, `"system"`, or a list), `actor_uid` and `credential_uid`.

Snapshots carry an optional `trigger`: `manual`, or `memory_pressure` for one taken automatically as the sandbox neared its memory limit.
