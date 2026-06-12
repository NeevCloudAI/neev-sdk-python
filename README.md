# NeevAI Python SDK

Official Python client for the [NeevCloud](https://neevcloud.com) AI platform.

## Installation

```bash
pip install neevai
```

Requires **Python ≥ 3.10**.

## Repository layout

See [docs/architecture.md](docs/architecture.md) for the canonical SDK slot
layout and how this repo maps Python paths to each slot.

## Quick start

Set your API key and default scope as environment variables:

```bash
export NEEVCLOUD_API_KEY=your_api_key_here
export NEEVCLOUD_ORG_ID=your_org_id
export NEEVCLOUD_PROJECT_ID=your_project_id
export NEEVCLOUD_REGION=your_region
```

Or pass them directly when creating the client:

```python
from neevai import NeevAI

with NeevAI(api_key="...", org_id="...", project_id="...", region="...") as client:
    sandbox = client.sandboxes.create({
        "name": "my-sandbox",
        "sandbox_template_id": "<your-sandbox-template-id>",
        "image": "ubuntu:22.04",
    })
    sandbox.wait_until_ready()
    result = sandbox.exec("echo Hello World")
    print(result.stdout)
    client.sandboxes.delete(sandbox.id)
```

Runnable examples live under [`examples/`](examples/). See [`examples/README.md`](examples/README.md)
for the full catalogue. Quick start:

| Example | What it shows |
| ------- | ------------- |
| [`sandbox_lifecycle.py`](examples/sandbox_lifecycle.py) | Template listing → create → wait → metrics → pause → delete |
| [`streaming_exec.py`](examples/streaming_exec.py) | Live `sandbox.exec_stream()` output |
| [`parallel_fanout.py`](examples/parallel_fanout.py) | Concurrent sandboxes + map/reduce |
| [`sandbox_metrics.py`](examples/sandbox_metrics.py) | Metrics under CPU load |
| [`agents/ai_interpreter.py`](examples/agents/ai_interpreter.py) | Hand-rolled agent with streaming tool output |
| [`agents/langchain_agent.py`](examples/agents/langchain_agent.py) | LangGraph ReAct agent (`uv sync --extra agents`) |
| [`sandbox_lifecycle_controller.py`](examples/sandbox_lifecycle_controller.py) | CLI for individual sandbox CRUD ops |

Set `NEEVCLOUD_API_KEY`, `NEEVCLOUD_ORG_ID`, `NEEVCLOUD_PROJECT_ID`, and `NEEVCLOUD_REGION`.
Optional: `NEEVCLOUD_SANDBOX_TEMPLATE_ID` (defaults to `sb-ubuntu-26-04-minimal`).

## Typing and validation

The package ships a `[py.typed](src/neevai/py.typed)` marker (PEP 561). Control-plane
JSON is validated at the resource boundary with Pydantic v2 models generated from
`specs/aiagent.yaml`. `client.sandboxes.create({...})` still accepts plain dict
literals; pass a `CreateSandboxParams` model instance if you prefer typed input.

`sandbox.data` and `sandbox.to_json()` return JSON-compatible dicts
(`model_dump(mode="json")`). `client.raw.request()` remains an intentional untyped
escape hatch for spec-less endpoints.

## Testing

The test suite uses `pytest` and `httpx` mock transports — no network access
is required.

```bash
uv sync --extra dev
uv run pytest -v
uv run pyright
uv run mypy
```

All tests are under the `[tests/](tests/)` directory:

| File                | What it covers                        |
| ------------------- | ------------------------------------- |
| `test_client.py`    | Client init (sync & async)            |
| `test_errors.py`    | HTTP-status → error-type mapping      |
| `test_transport.py` | Retry/backoff logic, mock transport   |
| `test_sandbox.py`   | Sandbox handle properties & lifecycle |
| `test_sandboxd.py`  | Data‑plane transport, exec & exec_stream |
| `test_sandboxes.py` | Sandboxes resource CRUD operations    |
| `test_templates.py` | Templates resource list/get           |

## API overview

### Client

```python
from neevai import NeevAI, AsyncNeevAI

# Sync
with NeevAI(api_key="...") as client:
    client.sandboxes.create(...)

# Async
async with AsyncNeevAI(api_key="...") as client:
    await client.sandboxes.create(...)
```

Constructor accepts `api_key`, `org_id`, `project_id`, `region`, `base_url`,
`timeout_ms` (default 60 s), and `max_retries` (default 2). Defaults for
`org_id`, `project_id`, and `region` can also be set via `NEEVCLOUD_ORG_ID`,
`NEEVCLOUD_PROJECT_ID`, and `NEEVCLOUD_REGION`.

### Sandboxes resource

| Method              | Description                        |
| ------------------- | ---------------------------------- |
| `create(params)`    | Create a new sandbox               |
| `list(page, limit)` | List sandboxes (paginated)         |
| `get(id)`           | Get a single sandbox               |
| `pause(id)`         | Scale to 0 replicas (Paused phase) |
| `resume(id)`        | Scale back to 1 replica            |
| `delete(id)`        | Permanently delete a sandbox       |
| `metrics(id, ...)`  | Query live health metrics          |

### Templates resource

| Method              | Description                        |
| ------------------- | ---------------------------------- |
| `list(page, limit)` | List platform sandbox templates    |
| `get(template_id)`  | Get a single template by id        |

### Sandbox handle

Returned by `create()`, `get()`, etc.

| Property / Method          | Description                      |
| -------------------------- | -------------------------------- |
| `.id`                      | Sandbox UUID                     |
| `.name`                    | Human-readable name              |
| `.phase`                   | Current lifecycle phase          |
| `.replicas`                | Desired replica count            |
| `.connect_url`             | Daemon address (when Ready)      |
| `.refresh()`               | Re‑fetch state from server       |
| `.wait_until_ready(...)`   | Poll until phase is Ready        |
| `.pause()`                 | Pause this sandbox               |
| `.resume()`                | Resume this sandbox              |
| `.delete()`                | Delete this sandbox              |
| `.exec(command, ...)`      | Run a command inside the sandbox |
| `.exec_stream(command, ...)` | Stream stdout/stderr chunks as they arrive |
| `.files.write(path, data)` | Write a file                     |
| `.files.read(path)`        | Read a file (raw bytes)          |
| `.files.read_text(path)`   | Read a file (UTF‑8 string)       |
| `.files.list(path, ...)`   | List directory entries           |

### Exec

```python
result = sandbox.exec("ls -la /tmp")
# or with argv (bypasses shell):
result = sandbox.exec(["ls", "-la", "/tmp"])

print(result.stdout)       # combined stdout
print(result.stderr)       # combined stderr
print(result.exit_code)    # integer exit code
```

### Streaming exec

```python
for event in sandbox.exec_stream(["sh", "-c", "for i in 1 2 3; do echo $i; sleep 1; done"]):
    if event["type"] == "stdout":
        print(event["data"], end="")
    elif event["type"] == "exit":
        print(f"exit {event['exit_code']}")
```

### Raw client (untyped escape hatch)

```python
resp = client.raw.request("GET", "/api/v1beta1/orgs/.../projects/.../sandboxes")
```

## Errors

All errors inherit from `NeevAIError`. HTTP errors are mapped to specific
subclasses:

| Status | Exception                 |
| ------ | ------------------------- |
| 400    | `BadRequestError`         |
| 401    | `AuthenticationError`     |
| 403    | `PermissionDeniedError`   |
| 404    | `NotFoundError`           |
| 409    | `ConflictError`           |
| 412    | `PreconditionFailedError` |
| 429    | `RateLimitError`          |
| 504    | `DeadlineExceededError`   |
| 5xx    | `InternalServerError`     |

## License

[Apache 2.0](LICENSE)
