---
"neevai": minor
---

Add preview-port methods to the sandbox handle, on both the sync and async clients. Ports are private by default; expose one to reach it through a public, credential-free preview URL.

- `sandbox.expose_port(port)` / `sandbox.list_ports()` / `sandbox.revoke_port(port)` manage exposed ports, each returning a `SandboxPort` (`port` + `preview_url`).
- `sandbox.get_url(port)` exposes the port and returns its preview URL, polling until the gateway routes it by default (`wait_until_ready=False` to skip the wait; `timeout_ms` / `poll_interval_ms` to tune it).
