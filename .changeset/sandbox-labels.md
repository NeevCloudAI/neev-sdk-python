---
"neevai": minor
---

Sandboxes take key-value labels. `client.sandboxes.create(params, labels={"team": "payments"})` tags a sandbox, `client.sandboxes.list(labels={"team": "payments"})` returns only the sandboxes carrying every given label (sent as one repeated `label=key=value` query parameter per label), and `sandbox.labels` reads them back as a `dict`, `{}` when there are none. The async client takes the same arguments. More than 16 labels or a value over 63 characters raises `ResponseValidationError` before the request; a key or value in the wrong format is rejected by the server with `BadRequestError`.
