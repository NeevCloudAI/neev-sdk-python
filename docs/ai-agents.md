# Use the Python SDK from an AI agent

This page lets a coding agent, such as Claude Code, Cursor or Codex, write and run
Python that uses NeevCloud through `neevai` without guessing. The first part is for
you: prompts to paste into your agent. The rest is for the agent: the checks, rules and
recipes it should follow.

- [Prompts to paste](#prompts-to-paste)
- [For agents: before the first call](#for-agents-before-the-first-call)
- [For agents: rules](#for-agents-rules)
- [Sandboxes](#sandboxes)
- [Agents](#agents)
- [Agent tools](#agent-tools)

## Prompts to paste

Each prompt points your agent at this page, so it picks up the rules below. Set
`NEEV_API_KEY`, `NEEV_ORG_ID` and `NEEV_PROJECT_ID` in the agent's environment first;
never paste a key into the chat.

**General setup**

```md
Read https://raw.githubusercontent.com/NeevCloudAI/neev-sdk-python/main/docs/ai-agents.md
and follow it to use NeevCloud from Python with the neevai package. Run its checks, tell
me which organization and project you will use, and wait for my go-ahead before creating
anything.
```

**Run code in a sandbox**

```md
Read https://raw.githubusercontent.com/NeevCloudAI/neev-sdk-python/main/docs/ai-agents.md.
Write a Python script with neevai that creates a NeevCloud sandbox, copies this
repository's source into it, installs its dependencies and runs its test suite there.
Report the results, then make sure the script deletes the sandbox.
```

**Preview a web app**

```md
Read https://raw.githubusercontent.com/NeevCloudAI/neev-sdk-python/main/docs/ai-agents.md.
Use neevai to run this app in a NeevCloud sandbox, start its server as a background
process, and give me the preview URL. Keep the sandbox running until I tell you to
delete it.
```

**Give my agent a sandbox**

```md
Read https://raw.githubusercontent.com/NeevCloudAI/neev-sdk-python/main/docs/ai-agents.md.
Add NeevCloud sandbox tools to the agent in this repository with neevai.agent_tools,
using the adapter for the framework it already uses. Create one sandbox per run and
delete it when the run ends.
```

If your agent supports MCP, the
[Sandbox MCP server](https://docs.ai.neevcloud.com/agentic-studio/Sandbox/sandbox-mcp-server)
gives it sandbox tools directly, without writing code.

---

## For agents: before the first call

Run these checks in order. Stop and ask the user only when a check fails.

1. **Python?** Run `python3 --version`. `neevai` needs Python 3.10 or later.
2. **Installed?** Run `python3 -c "import neevai"`. If it fails, install it into the
   project's environment: `uv add neevai` in a uv project, otherwise
   `pip install neevai` inside the project's virtual environment. Don't install into the
   system Python.
3. **Credentials?** Check that `NEEV_API_KEY` is set, without printing its value:
   `python3 -c "import os; print(bool(os.environ.get('NEEV_API_KEY')))"`. If it isn't,
   stop and ask the user to set it in your environment. Never ask them to paste a key
   into the chat, and never write a key into code or a file you create.
4. **Project?** Check `NEEV_ORG_ID` and `NEEV_PROJECT_ID` the same way. If either is
   missing, ask the user for the IDs, which
   [Organizations and projects](https://docs.ai.neevcloud.com/getting-started/org-and-project#find-your-organization-id-and-project-id)
   shows how to find, and tell them which ones you will use.
5. **Working?** List templates; it needs only the key:

   ```python
   from neevai import NeevAI

   with NeevAI() as client:
       print([t.id for t in client.templates.list().items])
   ```

   An `AuthenticationError` means the key is wrong or expired: ask the user for a new
   one.

## For agents: rules

1. **Use the client as a context manager.** `with NeevAI() as client:` (or
   `async with AsyncNeevAI() as client:`), so connections close.
2. **Wait before working inside.** Call `sandbox.wait_until_ready()` after `create`, and
   `agent.wait_until_ready()` after creating an agent, before `exec`, `files` or
   `processes`.
3. **Always clean up.** Delete what you create in a `finally` block, unless the user
   wants it kept. Tell the user what is still running when you finish.
4. **Name what you create.** Use a short, unique name such as `agent-tests-4821`, and
   address it by that name afterwards; `get` accepts a name or an id.
5. **Confirm before destroying.** Ask the user before `delete()` or `rollback()` on
   anything you didn't create in this task.
6. **Open only the egress you need.** Prefer `allow_egress=["pypi.org"]` over
   `allow_internet=True`, and tell the user which hosts you open.
7. **Preview URLs are public.** Anyone with one can open it. Give it only to the user,
   and close it with `revoke_port` when done.
8. **Branch on `e.code`, not the message.** Catch the typed errors from `neevai.errors`;
   see [Errors](./errors.md).
9. **Don't retry blindly.** API calls already retry. Retry a call inside a sandbox only
   when running it twice is safe; see [Retrying](./errors.md#retrying).
10. **Check the reference before guessing.** Every method is in the
    [API reference](./api-reference.md); don't invent method names or arguments.

## Sandboxes

A sandbox is an isolated Linux machine. Paths are relative to its workspace, or absolute
inside it, and outbound network access is closed unless its template or you open it.

**Create, use and remove**

```python
from neevai import NeevAI

with NeevAI() as client:
    sandbox = client.sandboxes.create(
        {"name": "task-4821", "sandbox_template_id": "sb-ubuntu-26-04-dev"},
        allow_egress=["pypi.org", "files.pythonhosted.org"],
    )
    try:
        sandbox.wait_until_ready()
        sandbox.files.write("app/main.py", "print(6 * 7)\n")
        result = sandbox.exec(["python3", "app/main.py"])
        print(result.exit_code, result.stdout, result.stderr)
    finally:
        sandbox.delete()
```

| Template | Use it for |
| --- | --- |
| `sb-ubuntu-26-04-dev` | General development: git, gh, Python 3, Node 24 |
| `sb-ubuntu-26-04-docker` | Docker; run containers with `--network=host` |
| `sb-ubuntu-26-04-interpreter` | Python kernels that keep state between runs (`sandbox.code`) |
| `sb-ubuntu-26-04-playwright` | Browser automation with Playwright and Chromium |

**Run commands.** A list runs the program directly, without a shell; use
`["sh", "-c", "..."]` for pipes, `&&` or redirects. A non-zero exit code is returned in
`result.exit_code`, not raised, so check it.

**Long-running work.** Start servers and long jobs as background processes, not with
`exec`, then read their output:

```python
proc = sandbox.processes.start(["sh", "-c", "npm run dev -- --host 0.0.0.0 --port 3000"], cwd="app")
url = sandbox.get_url(3000)  # waits until the server answers
print(proc.logs())
```

**Copy files in.** Upload only what the task needs. Never copy `.env` files,
credentials or keys the user hasn't asked you to.

```python
sandbox.files.upload_file("dist/app.tar.gz", "app.tar.gz")
sandbox.exec(["sh", "-c", "mkdir -p app && tar -xzf app.tar.gz -C app"])
```

**Checkpoints.** Snapshot before a risky change and roll back if it goes wrong.

```python
snap = sandbox.snapshot({"name": "before-migration"}, wait_until_ready=True)
sandbox.rollback(snap.id)
```

**Pause instead of delete** to keep files but stop paying for compute:
`sandbox.pause()`. A later `exec` on the paused sandbox wakes it where automatic wake-up
is enabled; if it raises `RateLimitError`, call `resume()` and retry. See
[Pause and wake](./sandboxes.md#pause-and-wake).

Full guide: [Sandboxes](./sandboxes.md).

## Agents

An agent is a ready-made coding agent, such as Claude Code, on its own sandbox.

```python
agent = client.agents.create({"name": "reviewer", "agent_template": "claude-code"})
try:
    agent.wait_until_ready()
    sandbox = agent.sandbox()
    sandbox.wait_until_ready()
    print(sandbox.exec(["git", "--version"]).stdout)
finally:
    agent.delete()
```

The template already allows the hosts the agent needs. Don't pass `allow_egress` to
`agents.create`, since it replaces that list; add a host afterwards with
`agent.update({"egress_add": {"allow": [{"host": "api.example.com"}]}})`. That needs an
allow-list to edit; if the template allows nothing, use `allow_egress` on `update` instead.

The coding agent inside a new agent isn't signed in to its model provider, so don't run
it non-interactively until the user has signed it in. A call that reaches an agent still
provisioning raises `TooEarlyError`: wait and retry.

Full guide: [Agents](./agents.md).

## Agent tools

To give your own model a sandbox, use `neevai.agent_tools` rather than writing tool
schemas by hand.

```python
import json

from neevai.agent_tools import DESCRIPTIONS, PARAMETERS, SandboxTools

tools = SandboxTools(sandbox, allow_processes=True)
specs = [{"name": n, "description": DESCRIPTIONS[n], "parameters": PARAMETERS[n]}
         for n in tools.names()]
result = tools.call(name, json.loads(arguments))  # for each tool call from the model
```

For Claude Agent SDK, OpenAI Agents SDK or LangChain, use the matching adapter
(`neevai[claude]`, `neevai[openai-agents]`, `neevai[langchain]`). Errors the model can
fix come back as `{"error": ...}`; authentication, permission and most rate-limit and
server failures raise and should end the run. Enable `allow_preview` and
`allow_rollback` only when the task needs them.

Full guide: [Agent tools](./agent-tools.md).
