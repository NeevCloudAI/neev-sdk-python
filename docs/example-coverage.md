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
| `client.sandboxes.create` | tier-1, `agent_patterns/*`, `workflow_examples/*`, `sandbox_lifecycle_controller.py`, `snapshot_fork_restore.py` | `sandbox = client.sandboxes.create({...})` |
| `client.sandboxes.create` (`from_snapshot`) | `snapshot_fork_restore.py` | `restored = client.sandboxes.create({..., "from_snapshot": snapshot_id})` |
| `client.sandboxes.list` | `sandbox_lifecycle_controller.py` | `page = client.sandboxes.list(page=1, limit=20)` |
| `client.sandboxes.get` | `sandbox_lifecycle_controller.py` | `sandbox = client.sandboxes.get(sandbox_id)` |
| `client.sandboxes.pause` | `sandbox_lifecycle_controller.py` | `sandbox = client.sandboxes.pause(sandbox_id)` |
| `client.sandboxes.resume` | `sandbox_lifecycle_controller.py` | `sandbox = client.sandboxes.resume(sandbox_id)` |
| `client.sandboxes.delete` | `sandbox_lifecycle_controller.py` | `client.sandboxes.delete(sandbox_id)` |
| `client.sandboxes.metrics` | `sandbox_lifecycle_controller.py` | `metrics = client.sandboxes.metrics(sandbox_id)` |
| `client.sandboxes.create_snapshot` | `snapshot_fork_restore.py` (via `sandbox.snapshot`) | `pending = sandbox.snapshot({"name": "demo-snap"})` |
| `client.sandboxes.get_snapshot` | `snapshot_fork_restore.py` | `snap = client.sandboxes.get_snapshot(snapshot_id)` |
| `client.sandboxes.delete_snapshot` | `snapshot_fork_restore.py` | `client.sandboxes.delete_snapshot(snapshot_id)` |
| `sandbox.snapshot` | `snapshot_fork_restore.py` | `pending = sandbox.snapshot({"name": "demo-snap"})` |
| `sandbox.fork` | `snapshot_fork_restore.py` | `fork = restored.fork("snapshot-fork")` |
| `client.templates.list` | `templates_list.py` | `page = client.templates.list(limit=10)` |
| `client.templates.get` | `templates_list.py` | `tpl = client.templates.get(template_id)` |
| `client.agents.create` | `create_agent.py` | `agent = client.agents.create({"name": "...", "agent_template": "claude-code"})` |
| `client.agents.list` | — | `page = client.agents.list(page=1, limit=20)` |
| `client.agents.get` | — | `agent = client.agents.get(agent_id)` |
| `client.agents.update` | `create_agent.py` | `agent = client.agents.update(agent.id, {"resources": {...}})` |
| `client.agents.pause` / `.resume` | — | `agent = client.agents.pause(agent_id)` / `client.agents.resume(agent_id)` |
| `client.agents.delete` | `create_agent.py` | `client.agents.delete(agent_id)` |
| `client.agent_templates.list` | `create_agent.py` | `page = client.agent_templates.list()` |
| `client.agent_templates.get` | — | `tpl = client.agent_templates.get(template_id)` |
| `agent.wait_until_ready` | `create_agent.py` | `agent.wait_until_ready(timeout_ms=120_000)` |
| `agent.refresh` | — | `agent.refresh()` |
| `agent.sandbox` | `create_agent.py` | `sandbox = agent.sandbox()` |
| `agent.update` | `create_agent.py` | `agent.update({"resources": {"cpu": 2, "memory_gb": 4}})` |
| `agent.pause` / `agent.delete` | `create_agent.py` | `agent.pause(); agent.delete()` |
| `agent.resume` | — | `agent.resume()` — not shown in `create_agent.py`; see [getting-started.md](./getting-started.md#create-an-agent) |
| `agent.to_json` | — | `agent.to_json()` |
| `client.raw.request` | `raw_request.py` | `data = client.raw.request("GET", path, query={...})` |
| `sandbox.wait_until_ready` | tier-1 (except `raw_request.py`), `processes.py`, `process_pool.py`, `agent_patterns/*`, `workflow_examples/*` | `sandbox.wait_until_ready(timeout_ms=120_000)` — after `connect_url` is set in process examples |
| `sandbox.refresh` | `processes.py`, `process_pool.py` | `sandbox.refresh()` — poll until `connect_url` is set |
| `sandbox.exec` | `parallel_fanout.py`, `async_sandbox.py`, `sandbox_metrics.py`, `agent_patterns/*`, `workflow_examples/*` | `result = sandbox.exec(["echo", "hi"])` / `await sandbox.exec(...)` |
| `sandbox.exec_stream` | `streaming_exec.py`, `agent_patterns/minimal_agent.py`, `agent_patterns/utils/agent_loop.py` | `for event in sandbox.exec_stream(cmd):` |
| `sandbox.processes.start` | `processes.py`, `process_pool.py` | `proc = sandbox.processes.start(["sleep", "30"])` — after connect_url → Ready → runtime probe |
| `sandbox.processes.follow` | `processes.py` | `for event in proc.follow():` |
| `sandbox.processes.logs` | `processes.py` | `page = proc.logs()` |
| `sandbox.processes.list` | `processes.py`, `process_pool.py` | `sandbox.processes.list()` — runtime probe before start; list running processes after |
| `sandbox.processes.kill` | `processes.py` | `proc.kill(signal=Signal.TERM)` |
| `sandbox.processes.get` | — | `sandbox.processes.get(proc.id)` — no dedicated example; `proc.wait()` uses `get(wait=True)` |
| `Process.status` | — | `proc.status()` — no dedicated example |
| `sandbox.processes.kill_all` | `process_pool.py` | `count = sandbox.processes.kill_all(signal=Signal.TERM)` |
| `Signal` | `processes.py`, `process_pool.py` | `proc.kill(signal=Signal.TERM)` |
| `Process.wait` | `processes.py`, `process_pool.py` | `final = proc.wait()` |
| `sandbox.files.write` | `files_api.py`, `snapshot_fork_restore.py`, `agent_patterns/utils/sandbox_tool.py`, `workflow_examples/repo_analyzer.py` | `sandbox.files.write("demo/message.txt", "original state")` |
| `sandbox.files.read` | `agent_patterns/utils/agent_loop.py` | `data = sandbox.files.read("path.txt")` |
| `sandbox.files.read_text` | `files_api.py`, `snapshot_fork_restore.py` | `text = sandbox.files.read_text("demo/message.txt")` |
| `sandbox.files.list` | `files_api.py` | `entries = sandbox.files.list("demo", recursive=True)` |
| `sandbox.metrics` | `sandbox_lifecycle.py`, `sandbox_metrics.py` | `metrics = sandbox.metrics()` |
| `sandbox.pause` | `sandbox_lifecycle.py` | `sandbox.pause()` |
| `sandbox.delete` | all examples that create sandboxes | `sandbox.delete()` / `await sandbox.delete()` |
| `sandbox.to_json` | `sandbox_lifecycle_controller.py` | `sandbox.to_json()` |
| `sandbox.id` / `.phase` / `.connect_url` / `.replicas` | tier-1, `processes.py`, `process_pool.py`, `sandbox_lifecycle_controller.py`, `agent_patterns/utils/sandbox_tool.py`, `workflow_examples/*` | `print(sandbox.phase, sandbox.connect_url, sandbox.replicas)` — polled until `connect_url` in process examples |
| `client.close()` | `agent_patterns/utils/sandbox_tool.py` | `client.close()` |

---

## Example catalog

| Example | Path | Summary |
| ------- | ---- | ------- |
| Templates list & create | `examples/templates_list.py` | List templates, get by id, create sandbox, wait, delete |
| Agent lifecycle | `examples/create_agent.py` | List agent templates, create agent, wait, sandbox exec, update, pause, delete |
| Sandbox lifecycle | `examples/sandbox_lifecycle.py` | Create → wait → metrics → pause → delete |
| Snapshot fork & restore | `examples/snapshot_fork_restore.py` | Write state → snapshot → modify → `from_snapshot` create → fork → cleanup |
| Async workflow | `examples/async_sandbox.py` | `AsyncNeevAI` create → wait → exec → delete |
| Files API | `examples/files_api.py` | Write, read_text, list (recursive) |
| Streaming exec | `examples/streaming_exec.py` | `exec_stream` with progress output |
| Processes lifecycle | `examples/processes.py` | Create → connect_url wait → Ready → runtime probe → start → follow → logs → list → kill → wait |
| Process pool | `examples/process_pool.py` | Create → connect_url wait → Ready → runtime probe → parallel start → list → kill_all → wait |
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
