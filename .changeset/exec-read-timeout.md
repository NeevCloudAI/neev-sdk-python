---
"neevai": patch
---

`exec`, `exec_stream` and `files.watch` no longer time out at the client's read timeout (60 s by default) when given a longer `timeout_ms`: the runtime request now waits up to `timeout_ms` plus 30 s for the server to answer. `processes.get(id, wait=True)` likewise waits up to the server's 5-minute wait ceiling plus 30 s. A shorter `timeout_ms` never lowers the client's read timeout. The async client matches. The network edge in front of the runtime still cuts off a response that stays silent for about 2 minutes, so long quiet work belongs in `sandbox.processes`.
