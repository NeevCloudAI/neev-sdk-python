#!/usr/bin/env python3
"""Generate Python types from vendored OpenAPI specs.

Each ``specs/<service>.yaml`` produces
``src/neevai/generated/<service>.py`` via datamodel-code-generator.
Specs are migrated into ``specs/`` from the backend services one at a time;
dropping a new file here and re-running this script is all that is needed
to make a service's types available for a hand-written wrapper.

Usage::

    uv run python scripts/gen_types.py
"""

import pathlib
import subprocess
import sys

SPECS_DIR = pathlib.Path(__file__).resolve().parent.parent / "specs"
OUT_DIR = pathlib.Path(__file__).resolve().parent.parent / "src" / "neevai" / "generated"


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
            "TypedDict",
        ],
        check=True,
    )


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
