# Errors

Every API and network failure the SDK raises is a `NeevAIError`; invalid arguments can also raise `ValueError` or `TypeError`. API failures are `APIError` subclasses
that carry the HTTP status, a machine-readable code and a request id for support. They
are the same for every product.

- [Error classes](#error-classes)
- [Error codes](#error-codes)
- [Retrying](#retrying)

## Error classes

Import them from `neevai` or `neevai.errors`.

```python
from neevai.errors import APIError, NotFoundError

try:
    client.sandboxes.get("missing")
except NotFoundError:
    ...  # handle a missing sandbox
except APIError as e:
    print(e.status_code, e.code, e.request_id)
```

| Error | When |
| --- | --- |
| `BadRequestError` | 400: invalid request |
| `AuthenticationError` | 401: missing or invalid API key |
| `PermissionDeniedError` | 403: not allowed |
| `NotFoundError` | 404: no such resource |
| `ConflictError` | 409: conflicting state, such as a name already in use |
| `PreconditionFailedError` | 412: a precondition of the call failed |
| `TooEarlyError` | 425: not ready yet, such as forking an agent that is still provisioning; retry later |
| `RateLimitError` | 429: too many requests |
| `DeadlineExceededError` | 504: the call ran past its deadline |
| `InternalServerError` | Other 5xx (`ServiceUnavailableError` for 503); 524 means the network cut a silent response, and the command may still be running |
| `APIConnectionError` | The request did not reach the API: DNS, connection reset, unreachable host |
| `APITimeoutError` | The request ran past the client's `timeout_ms` (a subclass of `APIConnectionError`) |
| `NeevAIError` | Everything else, such as a missing API key or project, or a wait that timed out |

Calls inside a sandbox, such as `exec` and `files.write`, raise the same classes.

See [reference](./api-reference.md#errors)

## Error codes

Branch on `e.code` rather than on the message text, which may be reworded. An `APIError`
has:

| Attribute | What it holds |
| --- | --- |
| `status_code` | The HTTP status |
| `code` | The machine-readable code, such as `not_found`; `None` when the response has none |
| `reason` | A finer reason where one code covers several cases |
| `scope` | The limit a quota refusal hit, such as `organization` or `project` |
| `details` | Extra detail, or the raw body when it wasn't JSON |
| `body` | The full parsed response body |
| `request_id` | The request's id; include it when you contact support |
| `request_method`, `request_url` | The request that failed |

`str(e)` reads well in a log: it holds the status, code, message and request id.

Codes you are likely to handle:

| Code | Meaning | What to do |
| --- | --- | --- |
| `not_found` | No such sandbox, agent, snapshot or path | Check the id or name |
| `validation_error` | A field failed validation | Fix the request; the message names the field |
| `sandbox_quota_exceeded` | A quota is used up; `scope` says which | Delete sandboxes you no longer need, or ask for a higher quota |
| `resource_exhausted` | A sandbox has too many processes or requests in flight (429) | Stop a process, or retry shortly |

The code interpreter sets `reason` when it refuses a run: `context_busy` when the context
is already running code, and `interpreter_not_enabled` when the sandbox wasn't created
from the interpreter template.

```python
from neevai.errors import APIError

try:
    client.sandboxes.create({"sandbox_template_id": "sb-ubuntu-26-04-dev"})
except APIError as e:
    if e.code == "sandbox_quota_exceeded":
        print(f"quota reached for this {e.scope}")
    else:
        raise
```

New codes can appear, so keep a fallback for codes you don't know.

## Retrying

API calls, such as `client.sandboxes.create` or `sandbox.pause()`, are retried
automatically on network errors, 429 and 5xx, up to `max_retries` times (2 by default),
with exponential backoff that honours `Retry-After`. You see the error only once those
retries are used up.

Calls inside a sandbox, such as `exec`, `files.write` and `processes.start`, are not
retried, because running them twice could repeat their effect. Retry one yourself only
when it is safe to run twice:

| Error | Retry? |
| --- | --- |
| `TooEarlyError` (425) | Yes, after a short wait: the resource is still getting ready |
| `RateLimitError` (429) on a `Paused` sandbox | Call `resume()` and retry; see [Pause and wake](./sandboxes.md#pause-and-wake) |
| 502, 503 or 504 right after a sandbox becomes ready | Yes, briefly; [`processes.py`](../examples/processes.py) shows a helper |
| `ConflictError`, `BadRequestError`, `NotFoundError` | No: change the request first |
| `AuthenticationError`, `PermissionDeniedError` | No: check the API key and its access |

```python
import time

from neevai.errors import TooEarlyError


def retry_too_early(call, attempts=5):
    for attempt in range(attempts):
        try:
            return call()
        except TooEarlyError:
            if attempt == attempts - 1:
                raise
            time.sleep(2 * (attempt + 1))


copy = retry_too_early(lambda: client.agents.fork("my-coder", "my-coder-copy"))
```

Set `max_retries=0` on the client to turn automatic retries off, for example when your
own code already retries.
