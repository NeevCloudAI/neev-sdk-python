# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial SDK scaffold: `NeevAI` and `AsyncNeevAI` client with env/option config resolution.
- `neev.sandboxes` resource — `create`, `list`, `get`, `pause`, `resume`, `delete`, `metrics`.
- `Sandbox` handle with `refresh`, `wait_until_ready`, `pause`, `resume`, `delete`, `metrics`.
- Typed error hierarchy (`NeevAIError` and HTTP-status subclasses).
- HTTP transport with timeout and exponential-backoff retries on network errors, `429`, and `5xx`.
- Generated Python types from the AI Agent Service OpenAPI spec via `datamodel-code-generator`.
- Sandbox files: `sandbox.files.write()`, `sandbox.files.read()`, `sandbox.files.read_text()`, `sandbox.files.list()`.
- Sandbox exec: `sandbox.exec()` runs a command in a running sandbox and returns `{ stdout, stderr, exit_code }`.
