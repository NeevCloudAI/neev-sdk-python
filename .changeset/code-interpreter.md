---
"neevai": minor
---

Code interpreter, on both the sync and async clients: `sandbox.code.run(code, ...)` runs Python in a persistent kernel in sandboxes created from the interpreter template. It returns an `Execution` with `stdout`, `stderr`, `logs`, display `results` with typed properties (`text`, `html`, `markdown`, `svg`, `png`, `jpeg`, `pdf`, `latex`, `json`, `formats()`), the last expression's `text`, any raised `error`, `execution_count`, and how the run ended (`end_reason`). Options: `context` (a context or its id), `language`, `envs` for this run only, `timeout_ms`, `request_timeout_ms`, and `on_stdout` / `on_stderr` (each given an `OutputMessage`), `on_result` and `on_error`. `sandbox.code.create_context(language=, cwd=)`, `list_contexts`, `restart_context` and `delete_context` manage separate kernels, each in its own working directory. `APIError.reason` refines `code` where one code covers several cases, such as `context_busy`.
