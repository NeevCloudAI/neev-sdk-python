# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Renamed `examples/agents/` → `examples/agent_patterns/`.
- Renamed `examples/use_cases/` → `examples/workflow_examples/`.
- Renamed `ai_interpreter.py` → `minimal_agent.py`.
- Renamed `NEEVAI_USE_CASE_MAX_STEPS` → `NEEVAI_WORKFLOW_MAX_STEPS`.

### Added

- `client.agents` resource — `create`, `list`, `get`, `update`, `pause`, `resume`, `delete` for platform agents in a project scope.
- `client.agent_templates` resource — read-only `list()` and `get()` for the global agent template catalogue.
- `Agent` / `AsyncAgent` handle — `refresh`, `wait_until_ready`, `update`, `pause`, `resume`, `delete`, `sandbox()`, and `to_json()`.
- Runnable example [`examples/create_agent.py`](examples/create_agent.py) — agent template catalogue, create, sandbox exec, update, pause, delete.
- `sandbox.exec_stream()` on sync and async handles — yields incremental stdout/stderr/exit NDJSON events; buffered `exec()` now drains `exec_stream()` internally.
- `client.templates` resource — `list()` and `get()` for platform sandbox-template catalogue.
- Runnable examples: `parallel_fanout.py`, `sandbox_metrics.py`, `streaming_exec.py`, and agent demos under `examples/agent_patterns/`.
- Optional dependency group `agents` (`langchain`, `langchain-openai`, `langgraph`) for LangChain example.
- Initial SDK scaffold: `NeevAI` and `AsyncNeevAI` client with env/option config resolution.
- `neev.sandboxes` resource — `create`, `list`, `get`, `pause`, `resume`, `delete`, `metrics`.
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
