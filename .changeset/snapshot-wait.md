---
"neevai": minor
---

Wait for a snapshot to finish. `client.sandboxes.wait_for_snapshot(snapshot_id, timeout_ms=300000, poll_interval_ms=2000)` polls until the snapshot is Ready and returns it, and raises `NeevAIError` if it fails (with its reason) or is not Ready in time. `sandbox.snapshot(params, wait_until_ready=True)` takes a snapshot and waits the same way. Both work on the sync and async clients, as the JS SDK's `waitForSnapshot` and `snapshot({ waitUntilReady: true })` do.
