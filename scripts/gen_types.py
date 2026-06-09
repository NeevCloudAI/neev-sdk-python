#!/usr/bin/env python3
"""Generate Python types from vendored OpenAPI specs.

Each ``specs/<service>.yaml`` (or ``$NEEV_PUBLIC_SPECS/<service>.yaml``)
produces ``src/neevai/generated/<service>.py`` via datamodel-code-generator.
Specs are migrated into ``specs/`` from the backend services one at a time;
dropping a new file here and re-running this script is all that is needed
to make a service's types available for a hand-written wrapper.

Set ``NEEV_PUBLIC_SPECS`` to override the local vendored ``specs/`` directory
(for example, when developing against a monorepo ``public-specs/`` checkout).

Usage::

    uv run python scripts/gen_types.py
"""

import os
import pathlib
import re
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SPECS_DIR = pathlib.Path(os.environ.get("NEEV_PUBLIC_SPECS", REPO_ROOT / "specs"))
OUT_DIR = REPO_ROOT / "src" / "neevai" / "generated"


def spec_files() -> list[pathlib.Path]:
    """Collect every YAML spec file in the specs directory."""
    return sorted(SPECS_DIR.glob("*.yaml")) + sorted(SPECS_DIR.glob("*.yml"))


def generate(spec: pathlib.Path) -> None:
    """Run datamodel-code-generator for one spec."""
    service = spec.stem
    output = OUT_DIR / f"{service}.py"
    print(f"datamodel-code-generator {spec.name} -> {output.name}")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "datamodel_code_generator",
            "--input",
            str(spec),
            "--output",
            str(output),
            "--output-model-type",
            "pydantic_v2.BaseModel",
        ],
        check=True,
    )
    _strip_timestamp(output)
    _ruff_format(output)


def _ruff_format(path: pathlib.Path) -> None:
    """Run ruff format on a single file so generated code matches project style."""
    subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            str(path),
        ],
        check=True,
    )


_TIMESTAMP_RE = re.compile(r"^#   timestamp:.*\n", re.MULTILINE)


def _strip_timestamp(path: pathlib.Path) -> None:
    """Remove the volatile timestamp line so CI diffs stay stable."""
    text = path.read_text(encoding="utf-8")
    new_text = _TIMESTAMP_RE.sub("", text)
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    specs = spec_files()
    if not specs:
        print(f"No specs found in {SPECS_DIR}/", file=sys.stderr)
        sys.exit(1)
    for spec in specs:
        generate(spec)


if __name__ == "__main__":
    main()
