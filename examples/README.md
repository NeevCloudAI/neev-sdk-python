# Examples

Runnable scripts for the NeevCloud SDK for Python (`neevai`). Each one creates real
sandboxes and cleans them up when it finishes.

## Contents

- [Setup](#setup)
- [Sandboxes](#sandboxes)
- [Agents](#agents)
- [Agent tools](#agent-tools)
- [Workflows](#workflows)
- [Step-by-step: run every example](#step-by-step-run-every-example)
- [Environment variables](#environment-variables)
- [Notes](#notes)

## Setup

From the repository root:

```bash
uv sync
export NEEV_API_KEY="your-api-key"
export NEEV_ORG_ID="your-org-id"
export NEEV_PROJECT_ID="your-project-id"
```

On Windows PowerShell, use `$env:NEEV_API_KEY = "..."` and so on.

Run any example from the repository root:

```bash
uv run python examples/<script>.py
```

Examples create from `sb-ubuntu-26-04-dev` unless you set `NEEV_SANDBOX_TEMPLATE_ID`.

## Sandboxes

These need only your credentials. Start with `templates_list.py`.

| Example | Shows |
| --- | --- |
| [`templates_list.py`](templates_list.py) | List templates, get one, create a sandbox from it |
| [`sandbox_lifecycle.py`](sandbox_lifecycle.py) | Create, wait, metrics, pause, delete |
| [`auto_resume.py`](auto_resume.py) | Use a paused sandbox without calling `resume()`; reports whether it woke by itself |
| [`sandbox_lifecycle_windows.py`](sandbox_lifecycle_windows.py) | Idle timeout and maximum lifetime, `keepalive`, `update_timeout` |
| [`sandbox_update.py`](sandbox_update.py) | Resize a running sandbox, then change its egress |
| [`update_resize_egress.py`](update_resize_egress.py) | Resize and change egress in one call; `egress_add` and `egress_remove` |
| [`e2e_live_update.py`](e2e_live_update.py) | A pass/fail check of a combined resize and egress update |
| [`last_crash.py`](last_crash.py) | Force an out-of-memory crash and read `last_crash` |
| [`sandbox_labels.py`](sandbox_labels.py) | Label sandboxes and find them by label |
| [`byoi_create.py`](byoi_create.py) | Create a sandbox from your own image |
| [`snapshot_fork_restore.py`](snapshot_fork_restore.py) | Snapshot, restore into a new sandbox, fork |
| [`async_sandbox.py`](async_sandbox.py) | The same workflow with `AsyncNeevAI` |
| [`files_api.py`](files_api.py) | Write, read and list files |
| [`upload_download.py`](upload_download.py) | Upload and download a large file with progress |
| [`preview_ports.py`](preview_ports.py) | Serve a port, get its preview URL, rotate it, revoke it |
| [`audit_trail.py`](audit_trail.py) | Run commands, then page through the audit trail |
| [`pty.py`](pty.py) | An interactive terminal |
| [`ssh_tunnel.py`](ssh_tunnel.py) | SSH, `rsync` and port forwarding through one tunnel |
| [`streaming_exec.py`](streaming_exec.py) | Stream command output line by line |
| [`processes.py`](processes.py) | Start, follow, read logs of and stop a process |
| [`process_pool.py`](process_pool.py) | Run processes in parallel, stop them all |
| [`code_interpreter.py`](code_interpreter.py) | Python runs that keep state, errors as results, a second context |
| [`docker.py`](docker.py) | Start Docker in a sandbox and run a container |
| [`parallel_fanout.py`](parallel_fanout.py) | Three sandboxes working in parallel |
| [`sandbox_metrics.py`](sandbox_metrics.py) | Metrics while the sandbox is under load |
| [`raw_request.py`](raw_request.py) | Call an API route directly with `client.raw.request` |
| [`sandbox_lifecycle_controller.py`](sandbox_lifecycle_controller.py) | A small command-line tool for sandbox operations |

The lifecycle controller is handy for trying things by hand:

```bash
uv run python examples/sandbox_lifecycle_controller.py create --name my-sandbox --wait
uv run python examples/sandbox_lifecycle_controller.py list --limit 20
uv run python examples/sandbox_lifecycle_controller.py metrics <sandbox-id>
```

## Agents

These need only your credentials.

| Example | Shows |
| --- | --- |
| [`create_agent.py`](create_agent.py) | Create an agent, use its sandbox, update, pause, delete |
| [`agent_ports_audit.py`](agent_ports_audit.py) | An agent's preview URL, keepalive and audit trail |
| [`agent_auto_resume.py`](agent_auto_resume.py) | Use a paused agent without calling `resume()`; reports whether it woke by itself |

## Agent tools

These connect a model to a sandbox as a tool. They use NeevCloud inference and your
API key unless you set `NEEV_INFERENCE_API_KEY`.

| Example | Shows | Extra install |
| --- | --- | --- |
| [`agent_patterns/minimal_agent.py`](agent_patterns/minimal_agent.py) | A small agent loop with streamed tool output | None |
| [`agent_patterns/agent_tools_loop.py`](agent_patterns/agent_tools_loop.py) | The ready-made `neevai.agent_tools` | None |
| [`agent_patterns/langchain_agent.py`](agent_patterns/langchain_agent.py) | A LangGraph agent | `uv sync --extra agents` |

Run the LangChain example with `uv run --extra agents python examples/agent_patterns/langchain_agent.py`.
See [`agent_patterns/README.md`](agent_patterns/README.md) for details.

## Workflows

Complete agent workflows that save their results locally.

| Example | Shows | Saves |
| --- | --- | --- |
| [`workflow_examples/repo_analyzer.py`](workflow_examples/repo_analyzer.py) | Clone and review a repository | `workflow_examples/output/repo-analysis.md` |
| [`workflow_examples/browser_agent.py`](workflow_examples/browser_agent.py) | Browse a site and summarise it | `workflow_examples/output/results.md` |

```bash
uv run python examples/workflow_examples/repo_analyzer.py
uv run python examples/workflow_examples/browser_agent.py --query "AI"
```

See [`workflow_examples/README.md`](workflow_examples/README.md) for options.

## Step-by-step: run every example

Do the [Setup](#setup) once, then run each example from the repository root. Almost
every example creates real sandboxes or agents, so your project needs available credits.

### Sandboxes

**1. List templates**
```bash
uv run python examples/templates_list.py
```
→ `templates: … of … (page …)` → `  … — … […]` (one line per template) → `selected: … — …` → `[templates] creating sandbox (…)…` → `created … (phase: …)` → `[templates] waiting until ready…` → `ready at …` → `[templates] deleting sandbox …`.

**2. Lifecycle**
```bash
uv run python examples/sandbox_lifecycle.py
```
→ `created … from … (phase: …)` → `waiting 3.0s before wait_until_ready…` → `  phase=…` (one line per poll) → `ready at …` → `waiting 3.0s before metrics…` → `metric series: […]` → `waiting 3.0s before pause…` → `paused (phase: …)` → `waiting 3.0s before delete…` → `deleted`.

**3. Auto-resume**
```bash
uv run python examples/auto_resume.py
```
→ `ready: …` → `paused` → `woke in N.Ns` → `RESULT: woke automatically` (or `429 and still Paused (…); resuming explicitly` → `resumed in N.Ns` → `RESULT: resumed explicitly` where automatic wake-up is off).

**4. Idle timeout, lifetime and keepalive**
```bash
uv run python examples/sandbox_lifecycle_windows.py
```
→ `ready … — windows: {…}` → `keepalive 1/5 — phase=…` … `keepalive 5/5 — phase=…` (20s apart) → `retuned — windows: {…}` → `deleted`.

**5. Resize and change egress**
```bash
uv run python examples/sandbox_update.py
```
→ `ready … at …` → `resized: {…}` → `egress now allows: ['api.github.com']` → `verified via get: resources={…}` → `deleted`.

**6. Resize and egress in one call, then edit egress**
```bash
uv run python examples/update_resize_egress.py
```
→ `ready … — resources: …, egress: …` → `updated … in one PATCH — resources: …, egress: github.com -> google.com` → `confirmed resources: …, egress: …` → `edited egress in place: …` → `cleaned up`.

**7. Live update check**
```bash
uv run python examples/e2e_live_update.py
```
→ `ready … (name=…)` → `[PASS] …` (one line per check, 12 in all) → `cleaned up …` → `E2E PASSED — combined resize+egress verified against the live API` (the last two checks are replaced by one `[SKIP] in-sandbox allow/deny proof — …` line if the sandbox can't run `curl`; any `[FAIL]` ends with `E2E FAILED — …` and exit code 1).

**8. Crash detection**
```bash
uv run python examples/last_crash.py
```
→ `ready … — last_crash=None` → `wrote /workspace/marker.txt` → `allocating past the memory limit...` → `  exec died as expected: …` → `  poll N/30 — phase=…, no crash yet` (one line per poll until the crash shows) → `crash: reason=… at=…` → `  storage_reset=…` → `  marker file present: …` → `storage_reset agrees with the filesystem: …` (`/workspace was wiped, re-provision before reusing this sandbox` or `files survived the restart`) → `deleted`.

**9. Labels**
```bash
uv run python examples/sandbox_labels.py
```
→ `created … labels={…}` (twice) → `team=labels-demo-…: [… , …]` → `team=labels-demo-…, run=2: […]` → `deleted …` (twice).

**10. Your own image**
```bash
uv run python examples/byoi_create.py
```
→ `ready … from image docker.io/library/python:3.12-slim` → `exec exit=0 out=Python 3.12.…` → `deleted`.

**11. Snapshot, restore and fork**
```bash
uv run python examples/snapshot_fork_restore.py
```
→ `[snapshot] created sandbox …` → `[snapshot] ready: …` → `[snapshot] wrote original state` → `[snapshot] snapshot pending: … (status=…)` → `[snapshot] snapshot ready` → `before restore:` → `modified state` → `[snapshot] restored sandbox … from snapshot` → `after restore:` → `original state` → `[snapshot] forked sandbox … (snapshot-fork)` → `[snapshot] fork inherited: original state` → `[snapshot] deleting fork …` → `[snapshot] deleting restored sandbox …` → `[snapshot] deleting sandbox …` → `[snapshot] deleting snapshot …`.

**12. Async client**
```bash
uv run python examples/async_sandbox.py
```
→ `[async] creating sandbox (…)…` → `created … (phase: …)` → `[async] waiting until ready…` → `ready at …` → `exec stdout: hello from async (exit 0)` → `[async] deleting sandbox …`.

**13. Files**
```bash
uv run python examples/files_api.py
```
→ `[files] creating sandbox (…)…` → `[files] ready: …` → `read_text: Hello from files API` → `  …: demo/… (N bytes)` (one line per entry under `demo/`) → `stat: … is a … of N bytes` → `exists demo/hello.txt: True` → `exists demo/missing: False` → `moved: exists archive copy = True` → `removed demo/nested: exists = False` → `watch: … …` (only if a change arrives in the 2s watch) → `[files] deleting sandbox …`.

**14. Upload and download a large file**
```bash
uv run python examples/upload_download.py
```
→ `uploaded N% (…/… bytes)` (one line, updated in place) → `uploaded 8388608 bytes` → `downloaded 8388608 bytes` → `sizes match`.

**15. Preview URLs**
```bash
uv run python examples/preview_ports.py
```
→ `[ports] creating sandbox (…)…` → `[ports] ready: …` → `[ports] server listening on :3000` → `preview URL: …` → `exposed ports: [3000]` → `rotated preview URL: … (old URL no longer works)` → `revoked; exposed ports: []` → `[ports] deleting sandbox …`.

**16. Audit trail**
```bash
uv run python examples/audit_trail.py
```
→ `ready: …` → `retention: … days, truncated: …` → `HH:MM:SS <operation> <who> <status>` (one line per event, newest first) → `exec calls:` → the same kind of line for each `exec` event.

**17. Terminal (PTY)**
```bash
uv run python examples/pty.py
```
Runs a short shell session for you; nothing to type. → `[pty] creating sandbox (…)…` → `[pty] ready: …` → the raw terminal output: the shell echoes `echo hello-from-pty && uname -a`, then prints `hello-from-pty` and the `uname -a` line → `[pty] pty exited with code …` → `[pty] deleting sandbox …`.

**18. SSH tunnel**
```bash
uv run python examples/ssh_tunnel.py
```
Needs `ssh`, `rsync` and `curl` on your machine. It always uses the `mcr.microsoft.com/devcontainers/python:3.12` image, whatever `NEEV_SANDBOX_TEMPLATE_ID` says. → `[ssh] creating sandbox from mcr.microsoft.com/devcontainers/python:3.12…` → `[ssh] ready: …` → `[ssh] tunnel on …:… — e.g. ssh -p … neev@localhost` → `[ssh] exec: uname + workspace listing` → the `uname -a` line and a listing of `/workspace` → `[ssh] rsync: local dir → sandbox:/workspace/uploaded` → `shipped over rsync` → `[ssh] port-forward: python http.server in sandbox → http://localhost:18080` → `shipped over rsync` (fetched with `curl` through the forward) → `[ssh] tunnel closed` → `[ssh] deleting sandbox …`.

**19. Streaming exec**
```bash
uv run python examples/streaming_exec.py
```
→ `[+    Nms] creating sandbox…` → `[+…ms] stdout: Starting download...` → `stdout: Download progress: 20%` … `100%` (one line about every second) → `stdout: Download completed` → `exit 0` → `deleting sandbox…`.

**20. Processes**
```bash
uv run python examples/processes.py
```
→ `[processes] creating sandbox (…)…` → `[processes] connect_url: …` → `[processes] phase=…` (one line per poll) → `[processes] ready: …` → `[processes] started process …` → `line-0` → `line-1` → `line-2` (it stops following after three lines) → `[processes] polled N log entries (cursor=…)` → `[processes] listed N process(es)` → `[processes] process exited with code …` → `[processes] deleting sandbox …`.

**21. Process pool**
```bash
uv run python examples/process_pool.py
```
→ `[process-pool] creating sandbox (…)…` → `[process-pool] connect_url: …` → `[process-pool] ready: …` → `[process-pool] started worker 0: …` (and workers 1, 2) → `[process-pool] listed N process(es)` → `[process-pool] … state=…` (one per worker) → `[process-pool] kill_all signalled … process(es)` → `[process-pool] … exit_code=…` (one per worker) → `[process-pool] deleting sandbox …`.

**22. Code interpreter**
```bash
uv run python examples/code_interpreter.py
```
Always uses the `sb-ubuntu-26-04-interpreter` template. → `stdout: 42` → `last value: 80 cell: … ended: …` → `ended: … - ZeroDivisionError division by zero` → `x visible in a new context: False` → `contexts: […]`.

**23. Docker**
```bash
uv run python examples/docker.py
```
Always uses the `sb-ubuntu-26-04-docker` template. → `ready: …` → the `hello-world` container's output, starting `Hello from Docker!`.

**24. Parallel fan-out**
```bash
uv run python examples/parallel_fanout.py
```
→ `[fanout] provisioning 3 sandboxes…` → `[fanout] analyzing repo 1…` (and 2, 3, in any order) → `[fanout] repo 1 -> … Python files` → `[fanout] repo 2 -> … TypeScript files` → `[fanout] repo 3 -> … Go files` → `Analysis complete:` → `  Total repositories: 3` → `  Total source files: …` → `[fanout] deleting sandboxes…`.

**25. Metrics under load**
```bash
uv run python examples/sandbox_metrics.py
```
→ `[metrics] creating sandbox (…)…` → `[metrics] ready: …` → `[metrics] starting report generation job` → `[metrics] batch N/8 complete — checking sandbox health…` and `[metrics] batch N/8: <metric>=…(Npts) …` (one pair per 15-second batch; stops after batch 3 once any metric has data) → `metrics for sandbox … (… -> …):` → `  <metric>: N points, last=…` (one line per metric) → `[metrics] deleting sandbox …`.

**26. Raw API request**
```bash
uv run python examples/raw_request.py
```
Creates no sandbox. → `raw templates: N item(s)` → `  … — …` (one line per template, up to 3) → `raw sandboxes: … total in project`.

**27. Lifecycle controller**
```bash
uv run python examples/sandbox_lifecycle_controller.py list --limit 20
```
→ `total=…  page=1  limit=20` → `  …  name=…  phase=…` (one line per sandbox). The other subcommands (`create`, `get`, `pause`, `resume`, `delete`, `metrics`) print one result line each; add `--json` before the subcommand for JSON. `create` needs `--template-id` or `NEEV_SANDBOX_TEMPLATE_ID`, and it does not delete the sandbox, so run `delete <sandbox-id>` afterwards.

### Agents

**28. Create an agent**
```bash
uv run python examples/create_agent.py
```
→ `templates: …` → `created … (status: …, sandbox: …)` → `ready` → an `ls -la` listing of the agent's workspace (includes `notes.md`) → `resized` → `paused (status: …)` → `deleted`.

**29. Agent ports, keepalive and audit trail**
```bash
uv run python examples/agent_ports_audit.py
```
→ `ready: … (idle window: …)` → `preview URL: …` → `rotated to: … (the old URL no longer works)` → `exposed ports: [3000]` → `HH:MM:SS <operation> <who> <status>` (one line per audit event).

**30. Agent auto-resume**
```bash
uv run python examples/agent_auto_resume.py
```
→ `created agent …, waiting for it to be Ready...` → `agent is Ready; wrote auto-resume-marker.txt into its sandbox …` → `agent paused (status: Paused)` → `reading auto-resume-marker.txt from the paused agent, without calling resume()...` → `file read back intact after N.Ns` → `agent status now: Ready` → `RESULT: woke automatically` (or `the read was refused with 429 and the agent is still Paused (…)` → `calling resume() and reading the file again...` → `file read back intact after N.Ns` → … → `RESULT: resumed explicitly` where automatic wake-up is off) → `deleted agent …`.

### Agent tools

These call a model. They use `NEEV_API_KEY` for inference unless you set `NEEV_INFERENCE_API_KEY`, and the model is `gpt-oss-120b` unless you set `NEEV_MODEL`.

**31. Minimal agent loop**
```bash
uv run python examples/agent_patterns/minimal_agent.py
```
→ `AI code-interpreter (gpt-oss-120b -> Neev sandbox)` → `task: Print every prime number below 50, …` → `[sandbox] creating (template=…)…` → for each step: `━━━━━ step N ━━━━━` → `[model] calling … with N messages…` → `[model] tokens: prompt=… completion=… total=…` → `[model] requested N tool call(s)` → `[tool] run_shell` and `  $ <command>` → `  ┌─ live output ───…` → the command's output as it runs → `  └─ exit 0 ───…` → `[tool] returned N bytes to the model` … → `✅ final answer:` → the model's answer → `[sandbox] deleting …`.

**32. Ready-made agent tools**
```bash
uv run python examples/agent_patterns/agent_tools_loop.py
```
→ `[sandbox] …` → `[tool] <name>({…}) -> {…}` (one line per tool call, as the model writes and runs `fib.py`) → `[answer] …` (the model's reply with the last Fibonacci number) → `[sandbox] deleted …`.

**33. LangGraph agent**
```bash
uv sync --extra agents
uv run --extra agents python examples/agent_patterns/langchain_agent.py
```
→ `[agent] LangChain · … — running (first sandbox call waits for warmup)…` → `[neev] creating sandbox (template=…)…` → `[neev] created … (…); waiting until ready…` → `[neev] ready: …` → `[neev] exec: <command>` and `[neev]   -> exit N` (one pair per command the model runs) → the model's answer, the number of `.py` and `.js` files (expected `5`) → `[neev] deleting sandbox …`.

### Workflows

These also call a model, and save their result under `examples/workflow_examples/output/`.

**34. Repository analyzer**
```bash
uv run python examples/workflow_examples/repo_analyzer.py
```
→ `[sandbox] creating (template=…)…` → `[sandbox] created …; waiting until ready…` → `[sandbox] ready: …` → `[bootstrap] git available` and `[bootstrap] ripgrep available` (or `installing … via …` lines if the template lacks them) → `[clone] fetching https://github.com/NeevCloudAI/neevai-sdk-python…` → `[clone] done (…)` → for each step: `[model] calling … (step N)…` → `  tokens: …` → `  $ <command>` with its live output between `┌─ live output` and `└─ exit N` … → the four-section report → `[artifact] saved N bytes → …/output/repo-analysis.md` → `[sandbox] deleting …`. Pass `--repo <url>` to analyze another repository.

**35. Browser agent**
```bash
uv run python examples/workflow_examples/browser_agent.py --query "AI"
```
→ `[sandbox] creating browser sandbox (template=…)…` → `[sandbox] created …; waiting until ready…` → `[sandbox] ready: …` → `[bootstrap] installing playwright + chromium…` → `[bootstrap] done` → model steps as in the analyzer (`[model] calling …`, `  $ <command>`, live output) → the matching Hacker News titles → `[artifact] saved N bytes -> …/output/results.md` → `[sandbox] deleting …` (if the agent never writes `results.md`, you get `warning: results.md was not created. …` and exit code 1).

## Environment variables

| Variable | Used by | Default |
| --- | --- | --- |
| `NEEV_API_KEY` | All | Required |
| `NEEV_ORG_ID` | All | Required |
| `NEEV_PROJECT_ID` | All | Required |
| `NEEV_SANDBOX_TEMPLATE_ID` | Sandbox examples | `sb-ubuntu-26-04-dev` |
| `NEEV_AGENT_TEMPLATE` | `create_agent.py`, `agent_ports_audit.py`, `agent_auto_resume.py` | `claude-code` |
| `NEEV_INFERENCE_API_KEY` | Agent and workflow examples | `NEEV_API_KEY` |
| `NEEV_INFERENCE_BASE_URL` | Agent and workflow examples | `https://inference.ai.neevcloud.com/v1` |
| `NEEV_MODEL` | Agent and workflow examples | `gpt-oss-120b` |
| `NEEVAI_WORKFLOW_MAX_STEPS` | Workflow examples | 35 (`repo_analyzer`), 70 (`browser_agent`) |
| `NEEVAI_WAIT_TIMEOUT_MS` | Lifecycle, snapshot and process examples | `300000` |
| `NEEVAI_POLL_INTERVAL_MS` | `processes.py`, `process_pool.py` | `2000` |
| `NEEVAI_SNAPSHOT_POLL_MS` | `snapshot_fork_restore.py` | `3000` |
| `NEEVAI_STEP_DELAY_SEC` | `sandbox_lifecycle.py` | `3` |
| `NEEV_GIT_STATIC_URL` | `repo_analyzer.py` | Optional |

## Notes

- File paths are relative to the workspace, or absolute inside it.
- Examples call `wait_until_ready()` before running commands.
- Progress goes to stderr; each example's result goes to stdout.
- For which example covers which API, see [example coverage](../docs/example-coverage.md).
