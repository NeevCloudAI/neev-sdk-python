---
"neevai": minor
---

`SandboxTools.specs()` and `AsyncSandboxTools.specs()` return a frozen `ToolSpec` per enabled tool, in `names()` order. Each carries `name`, `title`, `description`, the read-only `parameters` schema and a bound `call(args)`. `FatalGuard` stops one agent run at the first exception a tool raises. `call` (sync) and `acall` (async) return the read-only `FATAL_RESULT` (`{"error": "The sandbox call failed and the run is stopping."}`) instead, so the exception's text never reaches the model, and keep the first exception for `raise_if_failed()`.

New optional adapters build framework tools from these. `neevai.agent_tools.claude.to_claude(tools)` gives `ClaudeAgentOptions` keyword arguments for an in-process MCP server with Claude Code's own tools off, plus a `watch()` that ends the run and raises on a sandbox failure. `neevai.agent_tools.openai_agents.to_openai_agents(tools)` returns OpenAI Agents SDK `FunctionTool`s, and `neevai.agent_tools.langchain.to_langchain(tools)` returns LangChain `StructuredTool`s. Install a framework with the `claude`, `openai-agents` or `langchain` extra.
