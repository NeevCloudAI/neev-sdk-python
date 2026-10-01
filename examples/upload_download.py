"""
Upload a large local file into a sandbox with progress, download it back, and
check the sizes match.

``files.upload_file`` sends the file in chunks (1 MiB by default) and resumes a
chunk lost to a dropped connection from the last byte the sandbox received, so a
file of any size can be written. ``files.download_file`` streams it back to disk
and only puts the file in place once it is complete.

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
    uv run python examples/upload_download.py
"""

from __future__ import annotations

import os
import sys
import tempfile

from neevai import NeevAI
from neevai.errors import NeevAIError

TEMPLATE = os.environ.get("NEEV_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")
SIZE = 8 * 1024 * 1024  # 8 MiB, well past what one request can carry


def show_progress(sent: int, total: int) -> None:
    """Prints upload progress on one line to stderr."""
    print(f"\ruploaded {sent * 100 // total:3d}% ({sent}/{total} bytes)", end="", file=sys.stderr)


def main() -> None:
    with NeevAI() as client, tempfile.TemporaryDirectory() as tmp:
        source = os.path.join(tmp, "payload.bin")
        with open(source, "wb") as f:
            f.write(os.urandom(SIZE))

        sandbox = None
        try:
            sandbox = client.sandboxes.create({"sandbox_template_id": TEMPLATE})
            sandbox.wait_until_ready()

            result = sandbox.files.upload_file(source, "payload.bin", on_progress=show_progress)
            print(file=sys.stderr)
            print(f"uploaded {result['bytes_written']} bytes")

            copy = os.path.join(tmp, "copy.bin")
            downloaded = sandbox.files.download_file("payload.bin", copy)
            print(f"downloaded {downloaded['bytes_written']} bytes")
            print("sizes match" if os.path.getsize(copy) == SIZE else "size mismatch")
        except NeevAIError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            if sandbox is not None:
                sandbox.delete()


if __name__ == "__main__":
    main()
