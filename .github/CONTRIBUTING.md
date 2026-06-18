# Contributing to neevai

Thanks for your interest in improving the NeevAI SDK!

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) for dependency management and virtual environments

## Getting started

```sh
git clone https://github.com/NeevCloudAI/neev-sdk-python.git
cd neev-sdk-python
uv sync --extra dev
```

## Development workflow

| Command                    | What it does                                        |
| -------------------------- | --------------------------------------------------- |
| `uv run ruff check .`      | Lint all Python sources                             |
| `uv run ruff format --check .` | Check formatting                               |
| `uv run ruff format .`     | Apply formatting fixes                              |
| `uv run pytest -v`         | Run the unit tests                                  |
| `uv run pyright`           | Static type check (Pyright)                         |
| `uv run mypy`              | Static type check (mypy)                            |
| `uv run python scripts/gen_types.py` | Regenerate OpenAPI types from `specs/`     |

Before opening a PR, make sure `uv run ruff check .`, `uv run ruff format --check .`, `uv run pyright`, `uv run mypy`, and `uv run pytest -v` all pass.

### API documentation

Any PR that modifies public SDK exports must also update:

- [`docs/getting-started.md`](../docs/getting-started.md) — if install, env vars, or quick-start flows change
- [`docs/api-reference.md`](../docs/api-reference.md) — control-plane/data-plane lists and inline snippet rows
- [`docs/api-inventory.md`](../docs/api-inventory.md) — per-method detail, type field tables, symbol index
- [`docs/example-coverage.md`](../docs/example-coverage.md) — example catalog and API → examples lookup
- [`examples/`](../examples/) — if the change introduces a new major capability without an example
- [`README.md`](../README.md) / [`examples/README.md`](../examples/README.md) — links and tables if examples change

After `gen_types.py`, manually verify type field tables in `api-inventory.md` only.

## Architecture: hybrid autogen + hand-written wrapper

The SDK follows a hybrid model so it can cover endpoints whether or not they have an OpenAPI spec yet:

- **Spec-backed (preferred):** the service's OpenAPI spec is vendored into `specs/<service>.yaml`, `python scripts/gen_types.py` produces `src/neevai/generated/<service>.py`, and a hand-written resource wrapper calls the generated types. Paths, params, bodies, and responses are all checked against the spec at runtime or via type hints.
- **Spec-less (escape hatch):** for endpoints without a spec, the wrapper hand-writes the request/response types and calls `client.raw.request()`. The raw client shares the exact same transport — auth, timeout, retry, and typed errors are identical to the spec-backed path.

Both paths run over a single shared transport: bearer auth, per-request timeout, and exponential-backoff retries on network errors / 429 / 5xx.

### Adding or migrating a service

Follow the slot-based layout (see [docs/architecture.md](../docs/architecture.md)):

1. **Spec** — copy the service OpenAPI spec to `specs/<service>.yaml`.
2. **Generated types** — run `uv run python scripts/gen_types.py` → `src/neevai/generated/<service>.py`.
3. **Type aliases** — add public aliases in `src/neevai/types.py` if needed.
4. **Resource class** — hand-write `src/neevai/resources/<plural>.py` (control-plane CRUD).
5. **Handle** (if lifecycle object) — hand-write `src/neevai/handles/<singular>.py`.
6. **Data-plane surface** (if applicable) — hand-write `src/neevai/runtime/<name>.py`.
7. **Tests** — add `tests/test_<plural>.py`, `tests/test_<handle>.py`, etc.
8. **Public exports** — re-export new types from `src/neevai/__init__.py`.

Until a spec exists, a resource may use `client.raw.request()` with hand-written types; migrate it to the typed client when the spec lands.

## Code conventions

- **Generated code is not edited by hand.** `src/neevai/generated/` is produced by `scripts/gen_types.py` from the vendored specs using `--output-model-type pydantic_v2.BaseModel`. To change types, update the spec source and regenerate.
- Every exported function, method, and class carries a docstring describing what it does.
- New runtime code ships with unit tests.
- Formatting and linting are enforced by Ruff — run `uv run ruff check .` and `uv run ruff format .` before committing.

## Reporting bugs

Use the issue templates. For security issues, follow [SECURITY.md](./SECURITY.md) instead of filing a public issue.
