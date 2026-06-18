# Real-world workflow examples

Two hand-rolled agent demos that show what you can do with a **Neev sandbox**
as a secure code-execution environment. Every example uses a shared
[`StreamingAgentLoop`](../agent_patterns/utils/agent_loop.py) with a single
`run_shell` tool.

Do the one-time credential setup in [`../README.md`](../README.md), then set an
inference key (`NEEV_INFERENCE_API_KEY` or `NEEVCLOUD_INFERENCE_API_KEY`; falls
back to `NEEVCLOUD_API_KEY`).

## Examples

| Example | What it demonstrates | SDK features | Artifact |
| ------- | -------------------- | ------------ | -------- |
| [`repo_analyzer.py`](./repo_analyzer.py) | Cloning and auditing untrusted repos in isolation | `sandboxes.create`, `exec`, `delete` | `output/repo-analysis.md` |
| [`browser_agent.py`](./browser_agent.py) | Playwright browser automation in a sandbox | `sandboxes.create`, `exec`, `files.read`, `delete` | `output/results.md` |

---

### Hero: Repository Analyzer (`repo_analyzer.py`)

Analyzes a git repository for architecture, dependencies, security patterns,
and interesting observations — all inside a disposable sandbox. The agent's
final answer is written to `output/repo-analysis.md` on the host (from the
loop's return value, not a sandbox file pull).

```sh
# defaults to https://github.com/NeevCloudAI/neevai-sdk-python
uv run python examples/workflow_examples/repo_analyzer.py

# analyze a different repo
uv run python examples/workflow_examples/repo_analyzer.py \
  --repo https://github.com/user/repo.git
```

**Recommended template** — one that ships `git` and `ripgrep` (`rg`) preinstalled.
Set `NEEVCLOUD_SANDBOX_TEMPLATE_ID` accordingly. If `git` is missing, the script
tries GitHub archive fallback (HTTPS GitHub URLs only) or a static binary from
`NEEV_GIT_STATIC_URL`.

**Output:** `output/repo-analysis.md` — saved on success.

---

### Browser Automation (`browser_agent.py`)

Uses `NEEVCLOUD_SANDBOX_TEMPLATE_ID` (default `sb-ubuntu-26-04-minimal`). Bootstrap
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

---

## Environment variables

| Variable | Required | Default | Used by |
| -------- | -------- | ------- | ------- |
| `NEEVCLOUD_API_KEY` | yes | — | All |
| `NEEVCLOUD_ORG_ID` | yes | — | All |
| `NEEVCLOUD_PROJECT_ID` | yes | — | All |
| `NEEV_INFERENCE_API_KEY` | yes (or alias below) | — | All |
| `NEEVCLOUD_INFERENCE_API_KEY` | alias | — | All |
| `NEEV_INFERENCE_BASE_URL` | no | `https://inference.ai.neevcloud.com/v1` | All |
| `NEEVCLOUD_INFERENCE_BASE_URL` | alias | same as above | All |
| `NEEV_MODEL` | no | `gpt-oss-120b` | All |
| `NEEVCLOUD_REGION` | no | `as-south-1` | All |
| `NEEVCLOUD_SANDBOX_TEMPLATE_ID` | no | `sb-ubuntu-26-04-minimal` | All |
| `NEEVAI_WORKFLOW_MAX_STEPS` | no | `35` (`repo_analyzer`), `70` (`browser_agent`) | All |
| `NEEV_GIT_STATIC_URL` | no | — | `repo_analyzer.py` (optional static git binary) |

---

## Common patterns

- **Progress → stderr**, final answer → **stdout**
- Sandbox is always cleaned up via `try / finally`
- `browser_agent.py` bootstraps Playwright + Chromium *before* the agent loop;
  `repo_analyzer.py` bootstraps `git` / `ripgrep` (or archive fallbacks) before cloning
- `repo_analyzer.py` saves the agent's final text to `output/repo-analysis.md` on the host
- `browser_agent.py` pulls `results.md` from the sandbox into `output/` on exit when present
