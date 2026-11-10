# Agent tools

`neevai.agent_tools` gives the agent you build a ready-made set of sandbox tools, with
descriptions and JSON schemas written for a model. Use it with any model API, or through
an adapter for your agent framework. The core has no framework dependency.

This is for your own agent loop. To run a ready-made coding agent such as Claude Code,
see [Agents](./agents.md) instead.

| Capability | API | Example |
| --- | --- | --- |
| [The tool contract](#the-tool-contract) | `SandboxTools`, `AsyncSandboxTools`, `DESCRIPTIONS`, `PARAMETERS` | [`agent_tools_loop.py`](../examples/agent_patterns/agent_tools_loop.py) |
| [Framework adapters](#framework-adapters) | `to_claude`, `to_openai_agents`, `to_langchain` | [`agent_patterns/`](../examples/agent_patterns/README.md) |
| [Stopping on fatal errors](#stopping-on-fatal-errors) | `FatalGuard`, `specs()` | [`agent_tools_loop.py`](../examples/agent_patterns/agent_tools_loop.py) |
| [Lifecycle patterns](#lifecycle-patterns) | `client.sandboxes.create`, `agent.sandbox()` | [`agent_tools_loop.py`](../examples/agent_patterns/agent_tools_loop.py) |

## The tool contract

`SandboxTools` binds the tools to one sandbox. Register `tools.names()` with the model,
using `DESCRIPTIONS` and `PARAMETERS` for each tool's description and JSON Schema, and
pass each tool call the model makes to `tools.call(name, args)`.

```python
import json

from neevai.agent_tools import DESCRIPTIONS, PARAMETERS, SandboxTools

tools = SandboxTools(sandbox, allow_processes=True)
specs = [
    {"name": n, "description": DESCRIPTIONS[n], "parameters": PARAMETERS[n]}
    for n in tools.names()
]

# For each tool call from the model:
result = tools.call(tool_call.name, json.loads(tool_call.arguments))
```

| Tools | Enabled |
| --- | --- |
| `run_command`, `write_file`, `read_file`, `stat_path`, `move_path`, `delete_path` | Always |
| `expose_port` | `allow_preview=True` |
| `checkpoint`, `rollback` | `allow_rollback=True` |
| `start_process`, `read_process_output`, `stop_process`, `list_processes` | `allow_processes=True` |

Every tool returns a JSON-serializable dict for the model to read. Mistakes the model can
fix, such as a missing file, a bad argument or a disabled tool, come back as
`{"error": ...}`, and so do a few the model can work around: a 504 timeout, a command
silent for too long, or a sandbox at its process limit on `start_process`. Other
authentication, permission, rate-limit, server and network failures raise, because no
next tool call can fix them; see
[Stopping on fatal errors](#stopping-on-fatal-errors). `TITLES` holds a display title
for each tool.

`AsyncSandboxTools` works the same way with an `AsyncSandbox`: `await tools.call(name, args)`.

See [`agent_tools_loop.py`](../examples/agent_patterns/agent_tools_loop.py) · [reference](./api-reference.md#sandboxtools-and-asyncsandboxtools)

## Framework adapters

Adapters turn `SandboxTools` into one framework's own tools. Install the framework
through the matching extra.

| Framework | Extra | Adapter |
| --- | --- | --- |
| Claude Agent SDK | `neevai[claude]` | `neevai.agent_tools.claude.to_claude` |
| OpenAI Agents SDK | `neevai[openai-agents]` | `neevai.agent_tools.openai_agents.to_openai_agents` |
| LangChain and LangGraph | `neevai[langchain]` | `neevai.agent_tools.langchain.to_langchain` |

**Claude Agent SDK** (`pip install "neevai[claude]"`): an in-process MCP server with
Claude Code's own tools switched off, so Claude acts only on the sandbox.

```python
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from neevai.agent_tools import SandboxTools
from neevai.agent_tools.claude import to_claude

claude = to_claude(SandboxTools(sandbox))
async with ClaudeSDKClient(ClaudeAgentOptions(**claude.options())) as client:
    await client.query(task)
    async for message in claude.watch(client.receive_response()):
        print(message)
```

**OpenAI Agents SDK** (`pip install "neevai[openai-agents]"`):

```python
from agents import Agent, Runner

from neevai.agent_tools import SandboxTools
from neevai.agent_tools.openai_agents import to_openai_agents

agent = Agent(name="engineer", tools=to_openai_agents(SandboxTools(sandbox)))
result = await Runner.run(agent, task)
```

**LangChain and LangGraph** (`pip install "neevai[langchain]"`):

```python
from langchain.agents import create_agent

from neevai.agent_tools import SandboxTools
from neevai.agent_tools.langchain import to_langchain

agent = create_agent(model, to_langchain(SandboxTools(sandbox)))
result = agent.invoke({"messages": [{"role": "user", "content": task}]})
```

The adapters take the sync `SandboxTools` and run its calls off the event loop where the
framework is async.

See [`agent_patterns/`](../examples/agent_patterns/README.md) · [reference](./api-reference.md#framework-adapters)

## Stopping on fatal errors

A failure the model can't fix, such as an expired API key, should stop the run and reach
you, not be handed back to the model as text. How that happens depends on the framework:

| Framework | What happens |
| --- | --- |
| Your own loop | `tools.call` raises; let it propagate |
| Claude Agent SDK | `claude.watch(...)` ends the run and raises the failure |
| OpenAI Agents SDK | `Runner.run` raises `UserError`, with the original error as `__cause__` |
| LangChain and LangGraph | The exception propagates out of the run |

For another framework that turns a tool's exception into a message for the model, wrap
each tool in a `FatalGuard`. It turns the first failure into one fixed error result for
the model, returns that result for every later call without running it, and keeps the
original exception for you to raise when the run ends.

```python
from neevai.agent_tools import FatalGuard, SandboxTools

guard = FatalGuard()
specs = SandboxTools(sandbox).specs()  # name, title, description, parameters, call

def run_tool(spec, args):
    return guard.call(spec, args)  # await guard.acall(spec, args) for AsyncSandboxTools

# ... register each spec with your framework through run_tool, and run the agent ...
guard.raise_if_failed()
```

Use one guard per run.

See [reference](./api-reference.md#sandboxtools-and-asyncsandboxtools)

## Lifecycle patterns

The tools act on a sandbox you own, so your code decides when it starts and ends.

**One sandbox per run.** Create it, wait for it, and delete it in a `finally` block, so a
failed run doesn't leave it running.

```python
with NeevAI() as client:
    sandbox = client.sandboxes.create({"sandbox_template_id": "sb-ubuntu-26-04-dev"})
    try:
        sandbox.wait_until_ready()
        tools = SandboxTools(sandbox, allow_processes=True)
        ...  # run the agent
    finally:
        sandbox.delete()
```

**Keep a sandbox between runs.** Pause it instead of deleting it, and pick it up again by
name. A paused sandbox keeps its files; see [Pause and wake](./sandboxes.md#pause-and-wake).

```python
sandbox = client.sandboxes.get("research-workspace")
tools = SandboxTools(sandbox)
...  # run the agent
sandbox.pause()
```

**Let the model undo its own work.** With `allow_rollback=True`, the model can call
`checkpoint` before a risky change and `rollback` to return to it. Each checkpoint is a
snapshot of the sandbox.

**Give the tools to an agent's sandbox.** `agent.sandbox()` returns a `Sandbox`, so
`SandboxTools(agent.sandbox())` lets your own agent work alongside a NeevCloud agent in
the same workspace.

**Limit what the sandbox can reach.** The tools run whatever the model asks for, inside
the sandbox. Open only the egress the task needs (see
[Network egress](./sandboxes.md#network-egress)), and enable `allow_preview` only when
the model should be able to publish a port at a public URL.

See [`agent_tools_loop.py`](../examples/agent_patterns/agent_tools_loop.py) · [`minimal_agent.py`](../examples/agent_patterns/minimal_agent.py)
