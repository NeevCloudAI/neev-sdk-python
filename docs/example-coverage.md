# Example coverage — API usage by runnable script

Catalog of runnable `.py` examples and a lookup from SDK APIs to the scripts that
demonstrate them, with minimal inline snippets for each symbol. Use this when you
need to know whether an API is shown in runnable code, which examples cover a
given symbol, or what the typical call looks like. For fuller sync/async snippet
pairs, see [`api-reference.md`](./api-reference.md). For method signatures and
types, see [`api-inventory.md`](./api-inventory.md). For the tiered learning
path and run commands, see [`examples/README.md`](../examples/README.md).

## API → examples (inverse index)

| API / symbol | Example(s) | Example snippet |
| ------------ | ---------- | --------------- |
| `NeevAI(...)` | tier-1, `agent_patterns/*`, `workflow_examples/*`, `sandbox_lifecycle_controller.py` | `with NeevAI() as client:` |
| `AsyncNeevAI(...)` | `async_sandbox.py` | `async with AsyncNeevAI() as client:` |
| `client.sandboxes.create` | tier-1, `agent_patterns/*`, `workflow_examples/*`, `sandbox_lifecycle_controller.py` | `sandbox = client.sandboxes.create({...})` |
| `client.sandboxes.list` | `sandbox_lifecycle_controller.py` | `page = client.sandboxes.list(page=1, limit=20)` |
| `client.sandboxes.get` | `sandbox_lifecycle_controller.py` | `sandbox = client.sandboxes.get(sandbox_id)` |
| `client.sandboxes.pause` | `sandbox_lifecycle_controller.py` | `sandbox = client.sandboxes.pause(sandbox_id)` |
| `client.sandboxes.resume` | `sandbox_lifecycle_controller.py` | `sandbox = client.sandboxes.resume(sandbox_id)` |
| `client.sandboxes.delete` | `sandbox_lifecycle_controller.py` | `client.sandboxes.delete(sandbox_id)` |
| `client.sandboxes.metrics` | `sandbox_lifecycle_controller.py` | `metrics = client.sandboxes.metrics(sandbox_id)` |
| `client.templates.list` | `templates_list.py` | `page = client.templates.list(limit=10)` |
| `client.templates.get` | `templates_list.py` | `tpl = client.templates.get(template_id)` |
| `client.raw.request` | `raw_request.py` | `data = client.raw.request("GET", path, query={...})` |
| `sandbox.wait_until_ready` | tier-1 (except `raw_request.py`), `agent_patterns/*`, `workflow_examples/*` | `sandbox.wait_until_ready(timeout_ms=120_000)` |
| `sandbox.exec` | `parallel_fanout.py`, `async_sandbox.py`, `sandbox_metrics.py`, `agent_patterns/*`, `workflow_examples/*` | `result = sandbox.exec(["echo", "hi"])` / `await sandbox.exec(...)` |
| `sandbox.exec_stream` | `streaming_exec.py`, `agent_patterns/minimal_agent.py`, `agent_patterns/utils/agent_loop.py` | `for event in sandbox.exec_stream(cmd):` |
| `sandbox.files.write` | `files_api.py`, `agent_patterns/utils/sandbox_tool.py`, `workflow_examples/repo_analyzer.py` | `sandbox.files.write("path.txt", "content")` |
| `sandbox.files.read` | `agent_patterns/utils/agent_loop.py` | `data = sandbox.files.read("path.txt")` |
| `sandbox.files.read_text` | `files_api.py` | `text = sandbox.files.read_text("demo/hello.txt")` |
| `sandbox.files.list` | `files_api.py` | `entries = sandbox.files.list("demo", recursive=True)` |
| `sandbox.metrics` | `sandbox_lifecycle.py`, `sandbox_metrics.py` | `metrics = sandbox.metrics()` |
| `sandbox.pause` | `sandbox_lifecycle.py` | `sandbox.pause()` |
| `sandbox.delete` | all examples that create sandboxes | `sandbox.delete()` / `await sandbox.delete()` |
| `sandbox.to_json` | `sandbox_lifecycle_controller.py` | `sandbox.to_json()` |
| `sandbox.id` / `.phase` / `.connect_url` / `.replicas` | tier-1, `sandbox_lifecycle_controller.py`, `agent_patterns/utils/sandbox_tool.py`, `workflow_examples/*` | `print(sandbox.phase, sandbox.replicas)` |
| `client.close()` | `agent_patterns/utils/sandbox_tool.py` | `client.close()` |

---

## Example catalog

| Example | Path | Summary |
| ------- | ---- | ------- |
| Templates list & create | `examples/templates_list.py` | List templates, get by id, create sandbox, wait, delete |
| Sandbox lifecycle | `examples/sandbox_lifecycle.py` | Create → wait → metrics → pause → delete |
| Async workflow | `examples/async_sandbox.py` | `AsyncNeevAI` create → wait → exec → delete |
| Files API | `examples/files_api.py` | Write, read_text, list (recursive) |
| Streaming exec | `examples/streaming_exec.py` | `exec_stream` with progress output |
| Parallel fan-out | `examples/parallel_fanout.py` | Multiple sandboxes, parallel `exec` |
| Sandbox metrics | `examples/sandbox_metrics.py` | Poll `metrics()` under CPU load |
| Raw request | `examples/raw_request.py` | Untyped `client.raw.request` |
| Lifecycle CLI | `examples/sandbox_lifecycle_controller.py` | CLI over `client.sandboxes` CRUD |
| Minimal agent | `examples/agent_patterns/minimal_agent.py` | Hand-rolled agent with `exec_stream` |
| LangChain agent | `examples/agent_patterns/langchain_agent.py` | LangGraph ReAct via `SandboxCodeExecutor` |
| Sandbox tool helper | `examples/agent_patterns/utils/sandbox_tool.py` | `SandboxCodeExecutor` wrapper |
| Agent loop helper | `examples/agent_patterns/utils/agent_loop.py` | `StreamingAgentLoop`, `exec_stream`, `files.read` |
| Repo analyzer | `examples/workflow_examples/repo_analyzer.py` | Clone repo, agent audit, artifacts |
| Browser agent | `examples/workflow_examples/browser_agent.py` | Playwright scrape via agent loop |

---

## Maintaining this file

When you add or change an example, or introduce a new public API:

1. Update the [example catalog](#example-catalog) row.
2. Update the [inverse index](#api--examples-inverse-index) so each new or
   changed API points at the right example(s) and includes a representative
   snippet (prefer the pattern used in the linked example; fall back to
   [`api-reference.md`](./api-reference.md) one-liners when they match).
3. Cross-check [`api-reference.md`](./api-reference.md) runnable-example links.
