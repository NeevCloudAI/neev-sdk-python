# NeevAI Python SDK

Official Python client for the [NeevCloud](https://neevcloud.com) AI platform.

## Installation

```bash
pip install neevai
```

Requires **Python ≥ 3.10**.

## Quick start

Set your API key and default scope as environment variables:

```bash
export NEEVCLOUD_API_KEY=your_api_key_here
export NEEVCLOUD_ORG_ID=your_org_id
export NEEVCLOUD_PROJECT_ID=your_project_id
```

Or pass them directly when creating the client:

```python
from neevai import NeevAI

with NeevAI(api_key="...", org_id="...", project_id="...") as client:
    sandbox = client.sandboxes.create({"name": "my-sandbox", "image": "ubuntu:22.04"})
    sandbox.wait_until_ready()
    result = sandbox.exec("echo Hello World")
    print(result["stdout"])
    client.sandboxes.delete(sandbox.id)
```

See [`examples/demo.py`](examples/demo.py) for a complete walk‑through covering
create, list, get, pause, resume, exec, file operations, metrics, the raw
client, and error handling.

## Testing

The test suite uses `pytest` and `httpx` mock transports — no network access
is required.

```bash
# Install dev dependencies
pip install pytest pytest-asyncio

# Run all tests
pytest tests/ -v
```

All tests are under the [`tests/`](tests/) directory:

| File                   | What it covers                           |
|------------------------|------------------------------------------|
| `test_client.py`       | Client init (sync & async)               |
| `test_errors.py`       | HTTP-status → error-type mapping         |
| `test_transport.py`    | Retry/backoff logic, mock transport      |
| `test_sandbox.py`      | Sandbox handle properties & lifecycle    |
| `test_sandboxd.py`     | Data‑plane transport & connection        |
| `test_sandboxes.py`    | Sandboxes resource CRUD operations       |

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

Constructor accepts `api_key`, `org_id`, `project_id`, `base_url`,
`timeout_ms` (default 60 s), and `max_retries` (default 2).

### Sandboxes resource

| Method              | Description                              |
|---------------------|------------------------------------------|
| `create(params)`    | Create a new sandbox                     |
| `list(page, limit)` | List sandboxes (paginated)               |
| `get(id)`           | Get a single sandbox                     |
| `pause(id)`         | Scale to 0 replicas (Paused phase)       |
| `resume(id)`        | Scale back to 1 replica                  |
| `delete(id)`        | Permanently delete a sandbox             |
| `metrics(id, ...)`  | Query live health metrics                |

### Sandbox handle

Returned by `create()`, `get()`, etc.

| Property / Method          | Description                            |
|----------------------------|----------------------------------------|
| `.id`                      | Sandbox UUID                           |
| `.name`                    | Human-readable name                    |
| `.phase`                   | Current lifecycle phase                |
| `.replicas`                | Desired replica count                  |
| `.connect_url`             | Daemon address (when Ready)            |
| `.refresh()`               | Re‑fetch state from server             |
| `.wait_until_ready(...)`   | Poll until phase is Ready              |
| `.pause()`                 | Pause this sandbox                     |
| `.resume()`                | Resume this sandbox                    |
| `.delete()`                | Delete this sandbox                    |
| `.exec(command, ...)`      | Run a command inside the sandbox       |
| `.files.write(path, data)` | Write a file                           |
| `.files.read(path)`        | Read a file (raw bytes)                |
| `.files.read_text(path)`   | Read a file (UTF‑8 string)             |
| `.files.list(path, ...)`   | List directory entries                 |

### Exec

```python
result = sandbox.exec("ls -la /tmp")
# or with argv (bypasses shell):
result = sandbox.exec(["ls", "-la", "/tmp"])

print(result["stdout"])    # combined stdout
print(result["stderr"])    # combined stderr
print(result["exit_code"]) # integer exit code
```

### Raw client (untyped escape hatch)

```python
resp = client.raw.request("GET", "/api/v1beta1/orgs/.../projects/.../sandboxes")
```

## Errors

All errors inherit from `NeevAIError`. HTTP errors are mapped to specific
subclasses:

| Status | Exception              |
|--------|------------------------|
| 400    | `BadRequestError`      |
| 401    | `AuthenticationError`  |
| 403    | `PermissionDeniedError`|
| 404    | `NotFoundError`        |
| 409    | `ConflictError`        |
| 412    | `PreconditionFailedError` |
| 429    | `RateLimitError`       |
| 504    | `DeadlineExceededError`|
| 5xx    | `InternalServerError`  |

## License

[Apache 2.0](LICENSE)
