# NeevAI SDK — Architecture Summary

`neevai` is a Python client for the NeevAI platform. It ships one
control-plane resource (`sandboxes`) backed by a hybrid
**OpenAPI-generated types + hand-written wrappers** model, plus a
**data-plane client** (`sandboxd`) for file and exec operations on running
sandboxes.

---

## High-level architecture

```mermaid
flowchart TB
  subgraph consumer [Consumer code]
    App["App / script / CI"]
  end

  subgraph sdk [Hand-written SDK layer]
    NeevAI["NeevAI / AsyncNeevAI client<br/>src/neevai/client.py"]
    Sandboxes["Sandboxes resource<br/>src/neevai/resources/sandboxes.py"]
    SandboxHandle["Sandbox handle<br/>src/neevai/sandbox.py"]
    Sandboxd["SandboxConnection + SandboxFiles<br/>src/neevai/sandboxd.py"]
    Types["Public type aliases<br/>src/neevai/types.py"]
    Errors["Error hierarchy<br/>src/neevai/errors.py"]
  end

  subgraph transport [HTTP transport]
    ControlTransport["ControlTransport (retries)<br/>src/neevai/transport/control.py"]
    DataplaneTransport["DataPlaneTransport (no retry)<br/>src/neevai/transport/dataplane.py"]
    RawClient["RawClient / AsyncRawClient"]
  end

  subgraph generated [Generated layer]
    Spec["specs/aiagent.yaml"]
    GenScript["scripts/gen_types.py"]
    GenTypes["src/neevai/generated/aiagent.py"]
  end

  subgraph apis [NeevAI APIs]
    ControlPlane["agent.ai.neevcloud.com<br/>Bearer auth"]
    DataPlane["sandbox connect_url<br/>sandboxd daemon"]
  end

  App --> NeevAI
  NeevAI --> Sandboxes
  Sandboxes --> SandboxHandle
  SandboxHandle --> Sandboxd
  Sandboxes --> ControlTransport
  NeevAI --> RawClient
  NeevAI --> Sandboxd
  ControlTransport --> ControlPlane
  DataplaneTransport --> DataPlane

  Spec --> GenScript
  GenScript -->|"datamodel-code-generator"| GenTypes
  GenTypes --> Types
```

---

## Repository layout

```
neev-sdk-python/
+-- specs/                    # Vendored OpenAPI (source of truth for control-plane types)
|   +-- aiagent.yaml
+-- scripts/
|   +-- gen_types.py          # datamodel-code-generator runner
+-- src/neevai/
|   +-- generated/            # AUTO-GENERATED types (never hand-edit)
|   |   +-- aiagent.py
|   +-- resources/            # Hand-written API resource classes
|   |   +-- sandboxes.py
|   +-- transport/            # HTTP transport + retry
|   |   +-- control.py
|   |   +-- dataplane.py
|   |   +-- retry.py
|   +-- client.py             # NeevAI / AsyncNeevAI root client
|   +-- sandbox.py            # Sandbox handle (lifecycle + files/exec ergonomics)
|   +-- sandboxd.py           # Data-plane: SandboxConnection, SandboxFiles, exec
|   +-- types.py              # Public type aliases
|   +-- errors.py
|   +-- __init__.py           # Package exports
+-- tests/                    # pytest, mock transport
+-- examples/
```

## Key design principles

1. **Spec first (control plane)** — update `specs/aiagent.yaml`, then run
   `python scripts/gen_types.py`, then write wrappers.
2. **Thin generated layer** — types only; all UX lives in `resources/`,
   handles, and `sandboxd.py`.
3. **Shared transport pattern** — retrying `ControlTransport` for control
   plane, non-retrying `DataPlaneTransport` for the data plane.
4. **Handles over raw IDs** — lifecycle returns `Sandbox` objects so callers
   can chain `create -> wait_until_ready -> files.write -> exec -> delete`.
5. **Scope model** — `org_id`/`project_id` on client or per-call.
6. **No retries on sandboxd** — exec and writes are not idempotent.
7. **CI enforcement** — generated types must match spec
   (`git diff --exit-code src/neevai/generated`).
