# NeevCloud SDK for Python

The official Python client for NeevCloud, published as `neevai`.

[![PyPI](https://img.shields.io/pypi/v/neevai)](https://pypi.org/project/neevai/)
[![Python](https://img.shields.io/pypi/pyversions/neevai)](https://pypi.org/project/neevai/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![CI](https://github.com/NeevCloudAI/neev-sdk-python/actions/workflows/python-ci.yml/badge.svg)](https://github.com/NeevCloudAI/neev-sdk-python/actions/workflows/python-ci.yml)

One package for the NeevCloud products you build with: Sandboxes, Agents and Agent tools
today, with more to come. It works sync or async, with one client, one API key, and
typed requests, responses and errors.

> **AI agents:** before writing code with `neevai`, read [`docs/ai-agents.md`](docs/ai-agents.md)
> ([raw](https://raw.githubusercontent.com/NeevCloudAI/neev-sdk-python/main/docs/ai-agents.md)).
> It has the checks to run first, the rules to follow, and a recipe per product.

## Contents

- [Install](#install)
- [Quick start](#quick-start)
- [Products](#products)
- [Documentation](#documentation)
- [Examples](#examples)
- [Security](#security)
- [License](#license)

## Install

```bash
pip install neevai
# or
uv add neevai
```

Requires Python 3.10 or later, on Linux, macOS or Windows. The agent tools adapters
install through extras, such as `pip install "neevai[langchain]"`; see
[Agent tools](docs/agent-tools.md#framework-adapters).

## Quick start

Set your credentials:

```bash
export NEEV_API_KEY="your-api-key"
export NEEV_ORG_ID="your-org-id"
export NEEV_PROJECT_ID="your-project-id"
```

Find your organization and project IDs as described in [Organizations and projects](https://docs.ai.neevcloud.com/getting-started/org-and-project#find-your-organization-id-and-project-id).

Create a sandbox, run a command, read a file, and clean up:

```python
from neevai import NeevAI

with NeevAI() as client:  # reads the NEEV_* variables
    sandbox = client.sandboxes.create({"sandbox_template_id": "sb-ubuntu-26-04-dev"})
    try:
        sandbox.wait_until_ready()
        result = sandbox.exec(["python3", "-c", "print(6 * 7)"])
        print(result.stdout)  # 42

        sandbox.files.write("hello.txt", "hello from NeevCloud\n")
        print(sandbox.files.read_text("hello.txt"))
    finally:
        sandbox.delete()
```

`AsyncNeevAI` offers the same API with `async`/`await`. See
[`async_sandbox.py`](examples/async_sandbox.py).

New to NeevCloud? [Getting started](docs/getting-started.md) walks through each step.

## Products

| Product | What it is | Entry point | Guide |
| --- | --- | --- | --- |
| Sandboxes | Isolated machines that run your code, commands and servers | `client.sandboxes`, `client.templates` | [Sandboxes](docs/sandboxes.md) |
| Agents | Ready-made coding agents, such as Claude Code, each on its own sandbox | `client.agents`, `client.agent_templates` | [Agents](docs/agents.md) |
| Agent tools | A sandbox tool set, with model-ready schemas, for the agent you build | `neevai.agent_tools` | [Agent tools](docs/agent-tools.md) |

**What you can do with a sandbox:** run commands and background processes, read and
write files, run Python in a code interpreter that keeps its state, open a terminal or
SSH in, serve an app at a public preview URL, control which hosts it can reach,
snapshot, fork and roll back, label it, read its audit trail, and pause it to wake later.
The [Sandboxes guide](docs/sandboxes.md) covers each one.

## Documentation

| Guide | What you'll find |
| --- | --- |
| [Getting started](docs/getting-started.md) | Install, set your credentials, and run code in your first sandbox |
| [Sandboxes](docs/sandboxes.md) · [Agents](docs/agents.md) · [Agent tools](docs/agent-tools.md) | One guide per product |
| [Configuration](docs/configuration.md) | Credentials, organization and project, client options, timeouts and the raw client |
| [Errors](docs/errors.md) | Error classes, error codes and what to retry |
| [API reference](docs/api-reference.md) | Every public method, grouped by product, with sync and async snippets |
| [Use from an AI agent](docs/ai-agents.md) | Prompts to paste into Claude Code, Cursor or Codex, and the rules they follow |
| [Changelog](.github/CHANGELOG.md) | What changed in each release |

The [documentation index](docs/README.md) lists every page. The full NeevCloud
documentation is at <https://docs.ai.neevcloud.com>.

## Examples

[`examples/`](examples/README.md) has runnable scripts for each product, from creating a
sandbox to complete agent workflows. Run them from a clone:

```bash
git clone https://github.com/NeevCloudAI/neev-sdk-python.git
cd neev-sdk-python
uv sync
uv run python examples/templates_list.py
```

## Security

Report vulnerabilities as described in [SECURITY.md](SECURITY.md); please don't open a
public issue for one. Keep your API key out of source control and logs. Contributions are
welcome; see [docs/development.md](docs/development.md).

## License

[Apache-2.0](LICENSE) © NeevCloud
