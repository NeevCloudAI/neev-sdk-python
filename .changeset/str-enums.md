---
"neevai": patch
---

String enums from the API now subclass `str`, so they compare equal to their values. `client.sandboxes.get_snapshot(id).status == "Ready"` is `True` once a snapshot is ready. Before, it was always `False`, so a `while ... != "Ready"` poll never ended. The same applies to `outcome` on audit records, a sandbox's phase, agent status, and the other enums.
