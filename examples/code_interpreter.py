"""
Run Python in a sandbox's code interpreter, with state kept between runs.

Creates a sandbox from the interpreter template, defines a variable in one run and
uses it in the next, shows that an exception comes back as a result rather than being
raised, then runs in a second context to show contexts do not share state.

Run::

    NEEV_API_KEY=... NEEV_ORG_ID=... NEEV_PROJECT_ID=... \\
        uv run python examples/code_interpreter.py
"""

from __future__ import annotations

from neevai import NeevAI


def main() -> None:
    with NeevAI() as client:
        sandbox = client.sandboxes.create({"sandbox_template_id": "sb-ubuntu-26-04-interpreter"})
        try:
            sandbox.wait_until_ready()

            sandbox.code.run("x = 40")
            total = sandbox.code.run(
                "print(x + 2)\nx * 2",
                on_stdout=lambda out: print(f"stdout: {out.line}", end=""),
            )
            print(
                "last value:",
                total.text,
                "cell:",
                total.execution_count,
                "ended:",
                total.end_reason,
            )

            failed = sandbox.code.run("1 / 0")
            assert failed.error is not None
            print("ended:", failed.end_reason, "-", failed.error.name, failed.error.value)

            ctx = sandbox.code.create_context()
            other = sandbox.code.run("print('x' in globals())", context=ctx)
            print("x visible in a new context:", other.stdout.strip())

            print("contexts:", sandbox.code.list_contexts())
        finally:
            sandbox.delete()


if __name__ == "__main__":
    main()
