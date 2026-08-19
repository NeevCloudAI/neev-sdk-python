---
"neevai": minor
---

Add in-place sandbox resize, on both the sync and async clients: `client.sandboxes.update(id, {"resources": {"cpu": 2, "memory_gb": 4}})` and `sandbox.update({...})` resize cpu/memory on the running sandbox with no restart. Sizes you leave out keep their current value; `disk_gb` is not resizable in place. A patch that would resize nothing — an empty `resources`, or only sizes the API does not define — raises `NeevAIError` instead of being sent, since the server accepts an empty resize as a no-op.

**Breaking:** `pause()` no longer accepts `preserve_memory`, on the resource methods and the sandbox handles alike. The field is not part of the pause request contract: a pause always captures the sandbox's full state (root filesystem, process memory, and workspace), so `preserve_memory=False` never disabled memory capture. Drop the argument; pause behaviour is unchanged. The `neevai.types.PauseSandboxParams` alias goes with it — the pause body has no fields, so the type carried no information and silently accepted the removed one.
