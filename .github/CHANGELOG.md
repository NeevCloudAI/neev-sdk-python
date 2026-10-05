# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.8.1] - 2026-10-05

### Changed

- `APIError.code` is now the API's machine-readable code (`not_found`, `sandbox_quota_exceeded`, …). In 0.8.0 it held the human-readable message text, so code that compares `code` against message text must switch to the new codes. The text itself is in `error.body["message"]`. `APIError.scope` names the limit a quota refusal hit, and the message comes from the API's `message`. A `503` raises the new `ServiceUnavailableError`, a subclass of `InternalServerError`.

### Added

- `sandbox.audit()` / `client.sandboxes.audit(id)` and `agent.audit()` / `client.agents.audit(id)` read one page of what ran inside a sandbox — program names (never arguments), process and file operations, the credential each was made under, and how it ended. Page with `cursor=trail.next_cursor`.
- Preview URLs are gated by a per-port slug. `expose_port(port, slug=...)` and `get_url(port, slug=...)` choose one; exposing an exposed port with a different slug rotates it and breaks the old URL. `SandboxPort` now carries `slug`.
- `update()` accepts `egress_add` / `egress_remove` to edit the allow-list in place without restating it. Combining them with `egress` (or `allow_internet` / `allow_egress`) is rejected before the request.
- Sandboxes and agents can be addressed by name wherever an id is accepted.
- `sandbox.addressable` reports whether a new sandbox can be reached yet; `wait_until_ready()` now waits for it.
- Agents gain `keepalive()`, `rollback(snapshot_id)`, preview ports (`expose_port` / `list_ports` / `revoke_port` / `get_url`), and an idle window: `idle_timeout_seconds` on create and update, read back as `agent.idle_timeout_seconds`.
- `sandbox.files.upload(path, data)` sends bytes, str, or a seekable file in resumable chunks with progress; `files.write` uses it automatically above 1 MiB, so large writes no longer fail. `files.upload_file(local_path, remote_path)` and `files.download_file(remote_path, local_path)` move files to and from local disk without buffering them, and a failed download leaves no partial file.
- Sandbox templates carry an `icon`. `last_crash` is cleared once a restore from a snapshot taken before the crash completes.

## [0.8.0] - 2026-09-23

### Changed

- **Breaking:** the in-place snapshot revert is renamed from `restore` to `rollback`, and the create-from-snapshot field from `from_snapshot` to `restore`. Callers using `restore` to revert in place must switch to `rollback`.
- **Breaking:** `pause()` no longer takes `preserve_memory`. A pause always captures full state and a resume always restores from it.
- `0.8.0` drops the pre-release suffix, so it is the first version a plain `pip install neevai` resolves to.

### Added

- In-place resize and live egress update with `sandboxes.update` / `sandbox.update`, on the sync and async clients, and the same `allow_internet` / `allow_egress` convenience on `agents.update`.
- Lifecycle windows: `keepalive`, `update_timeout`, and `lifecycle` plus your own `image` / `command` at create time.
- `last_crash` on the sandbox and agent handles.
- `name`, `status`, and `sandbox_id` filters on `sandboxes.list()`.

## [0.7.0b0] - 2026-07-22

### Added

- Interactive PTY sessions with `sandbox.pty.create(...)`, on the sync and async clients. Output streams to the `on_data` callback; drive the session with `send_input` / `resize` / `kill`, wait for its exit code with `wait()`, and reattach with `pty.create(id=...)`. Adds a `websockets` dependency, used only for PTY.
- Preview ports on the sandbox handle: `expose_port(port)` / `list_ports()` / `revoke_port(port)`, and `get_url(port)`, which exposes the port and waits until its preview URL is reachable.
- Filesystem control and watch on `sandbox.files`: `stat`, `mkdir`, `move`, `exists`, `remove(path, recursive=False)`, and `watch(path, recursive=False, timeout_ms=None)`, which streams a `WatchEvent` per change.

## [0.6.0b0] - 2026-06-22

### Changed

- Renamed `examples/agents/` â†’ `examples/agent_patterns/`.
- Renamed `examples/use_cases/` â†’ `examples/workflow_examples/`.
- Renamed `ai_interpreter.py` â†’ `minimal_agent.py`.
- Renamed `NEEVAI_USE_CASE_MAX_STEPS` â†’ `NEEVAI_WORKFLOW_MAX_STEPS`.

### Added

- `client.agents` resource â€” `create`, `list`, `get`, `update`, `pause`, `resume`, `delete` for platform agents in a project scope.
- `client.agent_templates` resource â€” read-only `list()` and `get()` for the global agent template catalogue.
- `Agent` / `AsyncAgent` handle â€” `refresh`, `wait_until_ready`, `update`, `pause`, `resume`, `delete`, `sandbox()`, and `to_json()`.
- Runnable example [`examples/create_agent.py`](examples/create_agent.py) â€” agent template catalogue, create, sandbox exec, update, pause, delete.
- `sandbox.exec_stream()` on sync and async handles â€” yields incremental stdout/stderr/exit NDJSON events; buffered `exec()` now drains `exec_stream()` internally.
- `client.templates` resource â€” `list()` and `get()` for platform sandbox-template catalogue.
- Runnable examples: `parallel_fanout.py`, `sandbox_metrics.py`, `streaming_exec.py`, and agent demos under `examples/agent_patterns/`.
- Optional dependency group `agents` (`langchain`, `langchain-openai`, `langgraph`) for LangChain example.
- Initial SDK scaffold: `NeevAI` and `AsyncNeevAI` client with env/option config resolution.
- `neev.sandboxes` resource â€” `create`, `list`, `get`, `pause`, `resume`, `delete`, `metrics`.
- `Sandbox` handle with `refresh`, `wait_until_ready`, `pause`, `resume`, `delete`, `metrics`.
- Typed error hierarchy (`NeevAIError` and HTTP-status subclasses).
- HTTP transport with timeout and exponential-backoff retries on network errors, `429`, and `5xx`.
- Generated Python types from the AI Agent Service OpenAPI spec via `datamodel-code-generator`.
- Sandbox files: `sandbox.files.write()`, `sandbox.files.read()`, `sandbox.files.read_text()`, `sandbox.files.list()`.
- Sandbox exec: `sandbox.exec()` runs a command in a running sandbox and returns `{ stdout, stderr, exit_code }`.
- CI workflows (`python-ci.yml`, `release.yml`), Ruff lint/format config, project docs and examples.

### Fixed

- CI: `gen_types.py` now uses the `typing.TypedDict` model type expected by current
  `datamodel-code-generator`, strips the volatile generation timestamp, and runs
  `ruff format` on the output so generated code matches project style.
- Lint: replaced `raise X(..., cause=e)` with `raise X(...) from e` throughout the
  transport layer to satisfy `B904`.
- Lint: applied Ruff's safe auto-fixes (unused imports, `dict | None` syntax,
  import sorting, deprecated `typing` aliases) and formatters across the codebase.
