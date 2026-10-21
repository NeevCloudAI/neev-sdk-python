---
"neevai": minor
---

The audit trail now records every program a sandbox runs and every connection those programs open, not only the calls made to it. `audit()` returns three OCSF event classes in `data`: API Activity (`class_uid` 6003) for a call, Process Activity (1007) for a program starting or ending, and Network Activity (4001) for a connection. A program event carries `process` (`pid`, `name`, `file.path`, `working_directory`, `parent_process.pid`) and, when it ends, `exit_code` or a `status_detail` such as `signal 9`; a connection carries `actor.process` and `dst_endpoint`. New models: `AuditProcess`, `AuditFile`, `AuditDstEndpoint`, `AuditDevice`.

`api` and `resources` are present on API Activity only and are `None` otherwise. `actor.user.type` is now the OCSF caption (`"User"`, `"API Key"`, `"System"`, `"Unknown"`), and an API key is in `actor.user.programmatic_credentials[0].uid` instead of `credential_uid`. The `actor_type` filter still takes `"user"`, `"api_key"` and `"system"`.

`client.sandboxes.update(id, {"execution_trace": False})` and `sandbox.update({"execution_trace": False})` stop recording programs and connections without a restart; `True` turns it back on. `sandbox.execution_trace` reports the current setting.
