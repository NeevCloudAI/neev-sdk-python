# Development Guide

For the canonical SDK layout and Python slot mapping, see
[architecture.md](./architecture.md).

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

### Interim: vendored `specs/`

Today, OpenAPI specs are vendored locally under `specs/`. This is an
intentional interim deviation from the canonical layout (which expects
monorepo `public-specs/`). The workflow is unchanged:

1. Update or add `specs/<service>.yaml`.
2. Run `uv run python scripts/gen_types.py`.
3. Commit both the spec change and regenerated `src/neevai/generated/`.

### Future: monorepo specs

The target end state:

1. CI checks out the monorepo `public-specs/` directory.
2. CI sets `NEEV_PUBLIC_SPECS` to that checkout path.
3. CI runs `uv run python scripts/gen_types.py`.
4. CI verifies `git diff --exit-code src/neevai/generated`.
5. The local `specs/` directory is removed once monorepo wiring is confirmed.

For local monorepo development today, point at the shared specs checkout:

```sh
export NEEV_PUBLIC_SPECS=/path/to/monorepo/public-specs
uv run python scripts/gen_types.py
```

When `NEEV_PUBLIC_SPECS` is set, `scripts/gen_types.py` reads specs from
that directory instead of the vendored `specs/` copy.

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
