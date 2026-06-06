# Release Process

## Versioning

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Pre-1.0 releases use `0.x.y`.

## Publishing a release

1. Update the version in `pyproject.toml`.
2. Update `CHANGELOG.md` with the new version and release date.
3. Commit the changes:
   ```sh
   git add -A
   git commit -m "v0.x.y"
   ```
4. Tag the commit:
   ```sh
   git tag v0.x.y
   ```
5. Push the tag:
   ```sh
   git push origin main --tags
   ```
6. The [release workflow](.github/workflows/release.yml) handles building and
   publishing to PyPI automatically.

## PyPI publishing

Publishing uses `pypa/gh-action-pypi-publish` with OpenID Connect (trusted
publishing). No API token is stored as a secret if the environment is
configured with a trusted publisher.

## Pre-release checklist

- [ ] `uv run ruff check .` passes
- [ ] `uv run ruff format --check .` passes
- [ ] `uv run pytest -v` passes
- [ ] `uv run python scripts/gen_types.py` regenerates without changes
- [ ] `uv build` succeeds
- [ ] CHANGELOG.md is up to date
