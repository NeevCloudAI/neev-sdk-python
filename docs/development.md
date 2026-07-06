# Development Guide

The SDK is organized into resources (`resources/`), stateful handles
(`handles/`), the sandbox runtime client (`runtime/`), and HTTP transports
(`transport/`). Lifecycle agents live in `resources/agents.py` and
`resources/agent_templates.py` with handles in `handles/agent.py`.

## Setup

```sh
git clone https://github.com/NeevCloudAI/neev-sdk-python.git
cd neev-sdk-python
uv sync --extra dev
```

## Common commands

| Command                                    | What it does                        |
| ------------------------------------------ | ----------------------------------- |
| `uv run ruff check .`                      | Lint all Python sources             |
| `uv run ruff format .`                     | Auto-format sources                 |
| `uv run ruff format --check .`             | Check formatting only               |
| `uv run pytest -v`                         | Run all tests                       |
| `uv run pyright`                           | Static type check (Pyright)         |
| `uv run mypy`                              | Static type check (mypy)            |
| `uv run python scripts/gen_types.py`       | Regenerate OpenAPI types from specs |

## Code generation

The SDK uses [datamodel-code-generator](https://github.com/koxudaxi/datamodel-code-generator)
to produce Pydantic v2 `BaseModel` classes from each vendored OpenAPI spec in `specs/`.

Add a new spec file and run:

```sh
uv run python scripts/gen_types.py
```

Generated files land in `src/neevai/generated/`. **Do not edit them by hand.**

After regenerating types, manually verify type field tables in
`docs/api-inventory.md` match `src/neevai/generated/`. Type tables live in the
inventory only — not in `api-reference.md`. When adding a new API
resource, follow the agents implementation as the latest reference:
`resources/agents.py`, `resources/agent_templates.py`, `handles/agent.py`, and
`tests/test_agents.py`.

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

The CI workflow runs linting, formatting checks, Pyright and mypy type
checks, type generation verification, tests, and a build step. It is
defined in `.github/workflows/python-ci.yml`.
