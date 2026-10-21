# Examples

Runnable scripts for the NeevCloud SDK for Python (`neevai`). Each one creates real
sandboxes and cleans them up when it finishes.

## Contents

- [Setup](#setup)
- [Sandboxes](#sandboxes)
- [Agents](#agents)
- [Agent tools](#agent-tools)
- [Workflows](#workflows)
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
| [`audit_trail.py`](audit_trail.py) | Calls, programs and connections, each program tied to the call that started it |
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

## Environment variables

| Variable | Used by | Default |
| --- | --- | --- |
| `NEEV_API_KEY` | All | Required |
| `NEEV_ORG_ID` | All | Required |
| `NEEV_PROJECT_ID` | All | Required |
| `NEEV_SANDBOX_TEMPLATE_ID` | Sandbox examples | `sb-ubuntu-26-04-dev` |
| `NEEV_AGENT_TEMPLATE` | `create_agent.py` | `claude-code` |
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
