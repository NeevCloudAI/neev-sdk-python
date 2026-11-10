# Configuration

How the client authenticates, picks the organization and project to work in, and how
long it waits. These settings apply to every product.

- [Credentials](#credentials)
- [Organization and project scope](#organization-and-project-scope)
- [Client options](#client-options)
- [Timeouts and cancellation](#timeouts-and-cancellation)
- [Raw client](#raw-client)

## Credentials

The client authenticates with a NeevCloud API key. Create one in the
[NeevCloud console](https://console.ai.neevcloud.com)
([how](https://docs.ai.neevcloud.com/getting-started/create-api-key)), then set it in
the environment:

```bash
export NEEV_API_KEY="your-api-key"
```

```python
import os

from neevai import NeevAI

client = NeevAI()  # reads NEEV_API_KEY
client = NeevAI(api_key=os.environ["MY_KEY"])  # or pass it directly
```

Without a key, `NeevAI()` raises `NeevAIError` straight away. The same key covers
lifecycle calls and work inside a sandbox (`exec`, `files`, `processes`, `code`, `pty`,
`ssh`), so there is nothing else to configure. The SDK does not read `.env` files.

Keep the key out of source control and logs. Read it from the environment or a secret
store rather than writing it into code.

See [Getting started](./getting-started.md#set-your-credentials) for setting the
variables on Linux, macOS and Windows.

## Organization and project scope

Most calls act inside one organization and project. Set defaults once, in the
environment or on the client:

```bash
export NEEV_ORG_ID="your-org-id"
export NEEV_PROJECT_ID="your-project-id"
```

```python
client = NeevAI(org_id="your-org-id", project_id="your-project-id")
```

Find your IDs as described in
[Organizations and projects](https://docs.ai.neevcloud.com/getting-started/org-and-project#find-your-organization-id-and-project-id).

Every method that acts in a project also takes `org_id` and `project_id`, to override the
defaults for one call:

```python
other = client.sandboxes.list(project_id="another-project-id")
```

A handle remembers the scope it came from, so `sandbox.pause()` on a sandbox fetched from
another project acts in that project. A call with no organization or project from any of
these sources raises `NeevAIError` before any request is sent. The template catalogues
(`client.templates`, `client.agent_templates`) need no scope.

## Client options

| Option | Environment variable | Default | Meaning |
| --- | --- | --- | --- |
| `api_key` | `NEEV_API_KEY` | Required | Your API key |
| `org_id` | `NEEV_ORG_ID` | None | Default organization |
| `project_id` | `NEEV_PROJECT_ID` | None | Default project |
| `base_url` | `NEEV_BASE_URL` | `https://api.ai.neevcloud.com/agent` | API endpoint |
| `timeout_ms` | | `60000` | Timeout for each HTTP request |
| `max_retries` | | `2` | Retries for network errors, 429 and 5xx on API calls |
| `client` | | A new one | Your own `httpx.Client` (`httpx.AsyncClient` for `AsyncNeevAI`) |

An argument wins over its environment variable. Pass your own `httpx` client to set
proxies, custom certificates or connection limits for API calls; the SDK closes it when
you close the NeevCloud client. Calls inside a sandbox (`exec`, `files`, `processes`,
`code`) and preview-URL checks open their own connections and don't use it.

**Sync and async.** `NeevAI` is the sync client and `AsyncNeevAI` the async one. They take
the same options and have the same methods; with `AsyncNeevAI`, `await` each call and use
`async for` where a method streams. Use each as a context manager, or close it yourself:

```python
with NeevAI() as client:
    ...

async with AsyncNeevAI() as client:
    ...

client = NeevAI()
client.close()  # await client.aclose() for AsyncNeevAI
```

**Extras.** The core package needs nothing else. The [agent tools
adapters](./agent-tools.md#framework-adapters) need their framework, installed through an
extra: `neevai[claude]`, `neevai[openai-agents]` or `neevai[langchain]`.

See [`async_sandbox.py`](../examples/async_sandbox.py) · [reference](./api-reference.md#client)

## Timeouts and cancellation

`timeout_ms` on the client is the `httpx` timeout, 60 seconds by default: it bounds each
connect, read, write and pool wait, not the whole request. A request that runs out raises
`APITimeoutError`, after any retries. API calls are retried up to `max_retries` times
on network errors, 429 and 5xx; calls inside a sandbox are not (see
[Retrying](./errors.md#retrying)).

A call that streams, such as `exec`, waits up to `timeout_ms` for each piece of output,
so a command that stays silent for longer than that fails on the client side. Give a
long call its own limit, and the client waits at least that long:

| Call | Option | Default |
| --- | --- | --- |
| `sandbox.exec`, `exec_stream` | `timeout_ms`: how long the command may run | No limit; the client's `timeout_ms` applies to silence |
| `sandbox.files.watch` | `timeout_ms`: how long to watch | The same |
| `sandbox.processes.get(id, wait=True)`, `process.wait()` | None | Waits up to 5 minutes for the process to exit |
| `sandbox.code.run` | `timeout_ms` bounds the code only; `request_timeout_ms` bounds the whole call | No whole-call limit; the client's `timeout_ms` applies to silence, so a quiet cell longer than that needs `request_timeout_ms` |
| `sandbox.processes.follow`, `process.follow()` | None | The client's `timeout_ms` applies to silence |
| `sandbox.wait_until_ready`, `agent.wait_until_ready` | `timeout_ms`, `poll_interval_ms` | 120 s, 2 s |
| `sandbox.get_url`, `client.sandboxes.get_port_url` | `timeout_ms`, `poll_interval_ms` | 60 s, 2 s |
| `sandbox.snapshot(..., wait_until_ready=True)`, `client.sandboxes.wait_for_snapshot` | `timeout_ms`, `poll_interval_ms` | 300 s, 2 s |

```python
result = sandbox.exec(["make", "build"], timeout_ms=600_000)
sandbox.wait_until_ready(timeout_ms=300_000)
```

Whatever the timeouts, the network in front of a sandbox cuts a response that sends
nothing for about 2 minutes. The call then fails with `InternalServerError` (status 524)
or a dropped stream, and the command may still be running. Run quiet or long work with
`sandbox.processes.start(...)` and read it with `wait()` or `logs()`; see
[Commands and processes](./sandboxes.md#commands-and-processes).

A wait that runs out raises `NeevAIError`; for a sandbox, agent or snapshot the message
names the state it last saw.

**Cancelling.** Stop work inside a sandbox from your side with the call made for it:
`process.kill()` or `sandbox.processes.kill_all()` for background processes,
`term.kill()` for a terminal, and `tunnel.close()` for an SSH tunnel. With
`AsyncNeevAI`, cancel a pending call the usual asyncio way, such as with
`asyncio.wait_for` or by cancelling its task. To stop paying for a sandbox you are done
with, `pause()` or `delete()` it.

See [reference](./api-reference.md#sandbox-handle)

## Raw client

For an endpoint the SDK does not wrap yet, `client.raw.request(method, path)` sends a
request with the same authentication, retries and errors as the typed methods. It returns
the parsed JSON, or `None` for an empty response.

```python
templates = client.raw.request("GET", "/api/v1beta1/sandbox-templates", query={"limit": 3})
for item in templates["items"]:
    print(item["name"], item["id"])
```

Prefer the typed methods when they exist: they validate what you send and return typed
objects.

See [`raw_request.py`](../examples/raw_request.py) · [reference](./api-reference.md#clientraw)
