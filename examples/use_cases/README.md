# Use-Case Agent Examples

Three hand-rolled agent demos that show what you can do with a **Neev sandbox**
as a secure code-execution environment. Every example uses a shared
`[StreamingAgentLoop](../agents/utils/agent_loop.py)` with a single
`run_shell` tool.

## Examples


| Example                                  | What it demonstrates                                   | Artifact              |
| ---------------------------------------- | ------------------------------------------------------ | --------------------- |
| `[repo_analyzer.py](./repo_analyzer.py)` | Cloning & auditing untrusted repos in isolation        | `output/repo-analysis.md` |
| `[data_analysis.py](./data_analysis.py)` | Running data-science code (pandas / matplotlib) safely | `output/chart.png`    |
| `[browser_agent.py](./browser_agent.py)` | Playwright browser automation in a sandbox             | `output/results.md` |


---

### Hero: Repository Analyzer (`repo_analyzer.py`)

Analyzes a git repository for architecture, dependencies, security patterns,
and interesting observations — all inside a disposable sandbox.

```sh
# defaults to analyzing NeevCloudAI/neevai-sdk-python
python examples/use_cases/repo_analyzer.py

# analyze a different repo
python examples/use_cases/repo_analyzer.py --repo https://github.com/user/repo.git
```

**Recommended template** — one that ships `git` + `ripgrep` (`rg`) preinstalled.
Set `NEEVCLOUD_SANDBOX_TEMPLATE_ID` accordingly.

**Output:** `output/repo-analysis.md` — always saved on success.

---

### Data Analysis (`data_analysis.py`)

Uploads a CSV to the sandbox, asks the model to analyze it with pandas /
matplotlib, and automatically downloads the resulting chart.

```sh
# uses the default fixtures/sales.csv
python examples/use_cases/data_analysis.py

# use a custom CSV
python examples/use_cases/data_analysis.py --csv /path/to/data.csv
```

**Output:** `output/chart.png` — always saved on success.

---

### Browser Automation (`browser_agent.py`)

Defaults to `ghcr.io/neevcloud/sandbox-python:3.12` via `NEEVCLOUD_PYTHON_SANDBOX_IMAGE`
(does **not** use `NEEVCLOUD_SANDBOX_TEMPLATE_ID` — browser automation needs Python and
Playwright; minimal templates break). Bootstrap runs `pip install playwright` and
`playwright install --with-deps chromium`, then writes `/workspace/.env.sh` with `PYTHON`
and `PATH` so the agent can run scripts without installing packages. Scrapes the
[python.org](https://www.python.org/) homepage (page 1 only) for news headlines and
upcoming events.

```sh
python examples/use_cases/browser_agent.py

# optional title filter (case-insensitive)
python examples/use_cases/browser_agent.py --query "PyCon"
```

**Output:** `output/results.md` — saved on exit whenever the sandbox produced it (including partial results after max steps).

---

## Environment Variables


| Variable                        | Required                   | Default                                 | Used by                          |
| ------------------------------- | -------------------------- | --------------------------------------- | -------------------------------- |
| `NEEVCLOUD_API_KEY`             | ✅                          | —                                       | All                              |
| `NEEVCLOUD_ORG_ID`              | ✅                          | —                                       | All                              |
| `NEEVCLOUD_PROJECT_ID`          | ✅                          | —                                       | All                              |
| `NEEV_INFERENCE_API_KEY`        | ✅ (or `NEEVCLOUD_API_KEY`) | —                                       | All                              |
| `NEEV_INFERENCE_BASE_URL`       | ❌                          | `https://inference.ai.neevcloud.com/v1` | All                              |
| `NEEV_MODEL`                    | ❌                          | `gpt-oss-120b`                          | All                              |
| `NEEVCLOUD_REGION`              | ❌                          | `as-south-1`                            | All                              |
| `NEEVCLOUD_SANDBOX_TEMPLATE_ID` | ❌                          | `sb-ubuntu-26-04-minimal`               | All                              |
| `NEEVCLOUD_PYTHON_SANDBOX_IMAGE` | ❌                         | `ghcr.io/neevcloud/sandbox-python:3.12` (`browser_agent.py` only; `data_analysis.py` falls back to `NEEVCLOUD_SANDBOX_TEMPLATE_ID`) | `browser_agent.py`, `data_analysis.py` |
| `NEEVAI_USE_CASE_MAX_STEPS`     | ❌                          | `12`                                    | All                              |


---

## Common patterns

- **Progress → stderr**, final answer → **stdout**
- Sandbox is always cleaned up via `try / finally`
- Bootstrap (Python + Playwright install with fail-fast verification) runs *before* the agent loop
- Artifact download is automatic and mandatory — no extra flags

