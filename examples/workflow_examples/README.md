# Real-world workflow examples

Two complete agent workflows that use a NeevCloud sandbox as a safe place to run code. Every example uses a shared
[`StreamingAgentLoop`](../agent_patterns/utils/agent_loop.py) with a single
`run_shell` tool.

Do the setup in [`../README.md`](../README.md). The model key defaults to
`NEEV_API_KEY`; set `NEEV_INFERENCE_API_KEY` to use a different one.

## Contents

- [Examples](#examples)
- [Repository analyzer](#repository-analyzer)
- [Browser automation](#browser-automation)
- [Environment variables](#environment-variables)
- [Common patterns](#common-patterns)

These workflows use sandboxes directly — not platform agents (`client.agents`).
For catalogue-managed agents, see [`create_agent.py`](../create_agent.py).

## Examples

| Example | What it demonstrates | SDK features | Artifact |
| ------- | -------------------- | ------------ | -------- |
| [`repo_analyzer.py`](./repo_analyzer.py) | Cloning and auditing untrusted repos in isolation | `sandboxes.create`, `exec`, `delete` | `output/repo-analysis.md` |
| [`browser_agent.py`](./browser_agent.py) | Playwright browser automation in a sandbox | `sandboxes.create`, `exec`, `files.read`, `delete` | `output/results.md` |


## Repository analyzer

Analyzes a git repository for architecture, dependencies, security patterns,
and interesting observations — all inside a disposable sandbox. The agent's
final answer is written to `output/repo-analysis.md` on the host (from the
loop's return value, not a sandbox file pull).

```sh
# defaults to https://github.com/NeevCloudAI/neev-sdk-python
uv run python examples/workflow_examples/repo_analyzer.py

# analyze a different repo
uv run python examples/workflow_examples/repo_analyzer.py \
  --repo https://github.com/user/repo.git
```

**Recommended template** — one that ships `git` and `ripgrep` (`rg`) preinstalled.
Set `NEEV_SANDBOX_TEMPLATE_ID` accordingly. If `git` is missing, the script
tries GitHub archive fallback (HTTPS GitHub URLs only) or a static binary from
`NEEV_GIT_STATIC_URL`.

**Output:** `output/repo-analysis.md` — saved on success.


## Browser automation

Uses `NEEV_SANDBOX_TEMPLATE_ID` (default `sb-ubuntu-26-04-dev`). Bootstrap
runs `pip install playwright` and `playwright install chromium` before the agent
loop. The agent scrapes [Hacker News](https://news.ycombinator.com) for story
titles matching `--query` (case-insensitive) and saves matches to
`/workspace/results.md` inside the sandbox. On exit, the script pulls that file
to `output/results.md` via `pull_artifact_if_exists`.

```sh
uv run python examples/workflow_examples/browser_agent.py

# optional title filter (default: AI)
uv run python examples/workflow_examples/browser_agent.py --query "AI"
```

**Output:** `output/results.md` — saved when the sandbox produced the file (including
partial results after max steps). Exits with code 1 if the artifact is missing.


## Environment variables

| Variable | Required | Default | Used by |
| -------- | -------- | ------- | ------- |
| `NEEV_API_KEY` | yes | — | All |
| `NEEV_ORG_ID` | yes | — | All |
| `NEEV_PROJECT_ID` | yes | — | All |
| `NEEV_INFERENCE_API_KEY` | no | `NEEV_API_KEY` | All |
| `NEEV_INFERENCE_BASE_URL` | no | `https://inference.ai.neevcloud.com/v1` | All |
| `NEEV_MODEL` | no | `gpt-oss-120b` | All |
| `NEEV_SANDBOX_TEMPLATE_ID` | no | `sb-ubuntu-26-04-dev` | All |
| `NEEVAI_WORKFLOW_MAX_STEPS` | no | `35` (`repo_analyzer`), `70` (`browser_agent`) | All |
| `NEEV_GIT_STATIC_URL` | no | — | `repo_analyzer.py` (optional static git binary) |


## Common patterns

- **Progress → stderr**, final answer → **stdout**
- Sandbox is always cleaned up via `try / finally`
- `browser_agent.py` bootstraps Playwright + Chromium *before* the agent loop;
  `repo_analyzer.py` bootstraps `git` / `ripgrep` (or archive fallbacks) before cloning
- `repo_analyzer.py` saves the agent's final text to `output/repo-analysis.md` on the host
- `browser_agent.py` pulls `results.md` from the sandbox into `output/` on exit when present
