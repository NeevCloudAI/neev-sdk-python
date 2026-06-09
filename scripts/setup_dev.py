"""One‑time development setup.

Installs the package in editable mode.
Run this once after cloning the repo.
"""

import subprocess
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent


def main() -> None:
    subprocess.run(
        ["uv", "pip", "install", "-e", str(PROJECT)],
        check=True,
        cwd=PROJECT,
    )
    print("Done — package installed in editable mode.")


if __name__ == "__main__":
    main()
