---
"neevai": minor
---

Sandboxes and agents: audit trail, rotatable preview URLs, in-place egress edits, and large-file transfer, on both the sync and async clients.

- `sandbox.audit()` / `client.sandboxes.audit(id)` and `agent.audit()` / `client.agents.audit(id)` read one page of what ran inside a sandbox — program names (never arguments), process and file operations, the credential each was made under, and how it ended. Page with `cursor=trail.next_cursor`.
- Preview URLs are gated by a per-port slug. `expose_port(port, slug=...)` and `get_url(port, slug=...)` choose one; exposing an exposed port with a different slug rotates it and breaks the old URL. `SandboxPort` now carries `slug`.
- `update()` accepts `egress_add` / `egress_remove` to edit the allow-list in place without restating it. Combining them with `egress` (or `allow_internet` / `allow_egress`) is rejected before the request.
- Sandboxes and agents can be addressed by name wherever an id is accepted.
- `sandbox.addressable` reports whether a new sandbox can be reached yet; `wait_until_ready()` now waits for it.
- Agents gain `keepalive()`, `rollback(snapshot_id)`, preview ports (`expose_port` / `list_ports` / `revoke_port` / `get_url`), and an idle window: `idle_timeout_seconds` on create and update, read back as `agent.idle_timeout_seconds`.
- `sandbox.files.upload(path, data)` sends bytes, str, or a seekable file in resumable chunks with progress; `files.write` uses it automatically above 1 MiB, so large writes no longer fail. `files.upload_file(local_path, remote_path)` and `files.download_file(remote_path, local_path)` move files to and from local disk without buffering them, and a failed download leaves no partial file.
- Errors: `APIError.code` is now the API's machine-readable code (`not_found`, `sandbox_quota_exceeded`, …), `APIError.scope` names the limit a quota refusal hit, and the message comes from the API's `message`. A `503` raises the new `ServiceUnavailableError`, a subclass of `InternalServerError`.
- Sandbox templates carry an `icon`. `last_crash` is cleared once a restore from a snapshot taken before the crash completes.
