---
"neevai": minor
---

Agents can be snapshotted and forked. `client.agents.create_snapshot(id, params=None)` and `list_snapshots(id, page=None, limit=None)` snapshot the sandbox backing an agent and list those snapshots, with the same params and `Snapshot` shape as the sandbox calls. `client.agents.fork(id, name)` forks an agent into a new agent with the source's template and configuration; it returns the new `Agent`, which is `Provisioning` until `wait_until_ready()`, and the source keeps running. The `Agent` and `AsyncAgent` handles gain `snapshot(params=None, *, wait_until_ready=False, ...)`, `snapshots()` and `fork(name)`.

`CreateSnapshotParams` takes `snapshot_type`: `"filesystem"` captures /workspace only, without process memory, so it can be restored onto any sandbox image; `"full"` captures both.

A new `TooEarlyError` is raised for HTTP 425, such as calling an agent that is still provisioning. It was a plain `APIError` before.

The audit trail now also records every program that runs in a sandbox, unless its `execution_trace` is turned off: a Process Activity event (`class_uid` 1007) for a program starting or ending, with `process` and `exit_code`, and a Network Activity event (4001) for a connection it opened. These events have no `api`, so check `e.api` before reading `e.api.operation`. Every event carries `device` (the sandbox) and `cloud.org`. `actor.user.type` is now `User`, `API Key`, `System` or `Unknown`; the `actor_type` filter still takes `"user"`, `"api_key"` and `"system"`.
