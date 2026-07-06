---
"neevai": minor
---

Add interactive PTY sessions to the sandbox handle, on both the sync and async clients. `sandbox.pty.create(...)` opens a pseudo-terminal over a WebSocket and returns a handle.

- Output streams to the `on_data` callback; drive the session with `send_input` / `resize` / `kill`, and block on its exit with `wait()` (returns the exit code). `disconnect()` closes the socket.
- Reattach to an earlier terminal with `pty.create(id=<handle.id>)` — the sandbox replays recent scrollback.

Adds a `websockets` dependency (used only for PTY).
