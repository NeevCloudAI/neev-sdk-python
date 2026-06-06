# Development Guide

## Setup

```sh
git clone https://github.com/NeevCloudAI/neevai-sdk-python.git
cd neevai-sdk-python
uv sync --extra dev
```

## Common commands

| Command                                    | What it does                        |
| ------------------------------------------ | ----------------------------------- |
| `uv run ruff check .`                      | Lint all Python sources             |
| `uv run ruff format .`                     | Auto-format sources                 |
| `uv run ruff format --check .`             | Check formatting only               |
| `uv run pytest -v`                         | Run all tests                       |
| `uv run python scripts/gen_types.py`       | Regenerate OpenAPI types from specs |

## Code generation

The SDK uses [datamodel-code-generator](https://github.com/koxudaxi/datamodel-code-generator)
to produce `TypedDict` classes from each vendored OpenAPI spec in `specs/`.

Add a new spec file and run:

```sh
uv run python scripts/gen_types.py
```

Generated files land in `src/neevai/generated/`. **Do not edit them by hand.**

## Testing

Tests use `pytest` with mock HTTP transports — no network access is required.

```sh
uv run pytest -v
```

All tests are under `tests/`.

## Linting and formatting

Ruff enforces a consistent code style:

```sh
uv run ruff check .       # Find issues
uv run ruff format .      # Fix formatting
```

## CI

The CI workflow runs linting, formatting checks, type generation
verification, tests, and a build step. It is defined in
`.github/workflows/python-ci.yml`.
