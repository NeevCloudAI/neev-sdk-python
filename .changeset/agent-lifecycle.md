---
"neevai": minor
---

Add an agent lifecycle surface: `client.agents` and `client.agent_templates`.

Provision a packaged agent from a catalogue template onto its own backing sandbox (1:1), then manage it through a handle.

- `client.agents` — `create`, `list`, `get`, `update`, `pause`, `resume`, `delete`. Every method returns an `Agent` handle (or a page of handles).
- `Agent` handle — `id`, `name`, `status`, `agent_template_id`, `sandbox_id`, `config`, `data`/`to_json()`, plus `refresh()`, `update()`, `pause()`, `resume()`, `delete()`, and `wait_until_ready()`. `agent.sandbox()` resolves the backing sandbox handle.
- `client.agent_templates` — read-only catalogue: `list()` and `get(id)`. The template `name` (e.g. `claude-code`) is passed as `agent_template` at create.
- Exports `Agent`, `AsyncAgent`, pagination/list param types, and `AgentData` / `AgentStatus` / `CreateAgentParams` / `UpdateAgentParams` / `AgentListResponse` / `AgentTemplate` / `AgentTemplateListResponse`.
