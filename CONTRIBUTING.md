# Contributing to neevai

Thanks for your interest in improving the NeevAI SDK!

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) for dependency management and virtual environments

## Getting started

```sh
git clone https://github.com/NeevCloudAI/neevai-sdk-python.git
cd neevai-sdk-python
uv sync --extra dev
```

## Development workflow

| Command                    | What it does                                        |
| -------------------------- | --------------------------------------------------- |
| `uv run ruff check .`      | Lint all Python sources                             |
| `uv run ruff format --check .` | Check formatting                               |
| `uv run ruff format .`     | Apply formatting fixes                              |
| `uv run pytest -v`         | Run the unit tests                                  |
| `uv run python scripts/gen_types.py` | Regenerate OpenAPI types from `specs/`     |

Before opening a PR, make sure `uv run ruff check .`, `uv run ruff format --check .`, and `uv run pytest -v` all pass.

## Architecture: hybrid autogen + hand-written wrapper

The SDK follows a hybrid model so it can cover endpoints whether or not they have an OpenAPI spec yet:

- **Spec-backed (preferred):** the service's OpenAPI spec is vendored into `specs/<service>.yaml`, `python scripts/gen_types.py` produces `src/neevai/generated/<service>.py`, and a hand-written resource wrapper calls the generated types. Paths, params, bodies, and responses are all checked against the spec at runtime or via type hints.
- **Spec-less (escape hatch):** for endpoints without a spec, the wrapper hand-writes the request/response types and calls `client.raw.request()`. The raw client shares the exact same transport — auth, timeout, retry, and typed errors are identical to the spec-backed path.

Both paths run over a single shared transport: bearer auth, per-request timeout, and exponential-backoff retries on network errors / 429 / 5xx.

### Adding or migrating a service

1. Copy the service's OpenAPI spec to `specs/<service>.yaml`.
2. Run `uv run python scripts/gen_types.py` → generates `src/neevai/generated/<service>.py`.
3. Hand-write the resource wrapper (a `src/neevai/resources/<service>.py` + any handle classes).
4. Until a spec exists, a resource may use `client.raw.request()` with hand-written types; migrate it to the typed client when the spec lands.

## Code conventions

- **Generated code is not edited by hand.** `src/neevai/generated/` is produced by `scripts/gen_types.py` from the vendored specs. To change types, update the spec source and regenerate.
- Every exported function, method, and class carries a docstring describing what it does.
- New runtime code ships with unit tests.
- Formatting and linting are enforced by Ruff — run `uv run ruff check .` and `uv run ruff format .` before committing.

## Reporting bugs

Use the issue templates. For security issues, follow [SECURITY.md](./SECURITY.md) instead of filing a public issue.
