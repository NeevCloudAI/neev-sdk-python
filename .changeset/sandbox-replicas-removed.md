---
"neevai": minor
---

`Sandbox.replicas` and `AsyncSandbox.replicas` are removed; read `phase` instead, which is `"Paused"` while a sandbox is paused. The field is deprecated in the API and is now optional on the generated `Sandbox` model, so a sandbox response without it parses.

`snapshot_type` adds `"filesystem"` for a files-only snapshot that cannot be restored; a snapshot of that type no longer fails response validation.
