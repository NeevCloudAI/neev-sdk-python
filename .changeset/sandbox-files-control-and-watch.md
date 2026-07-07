---
"neevai": minor
---

Add filesystem control and watch methods to `sandbox.files`, on both the sync and async clients:

- `stat(path)` / `mkdir(path)` / `move(source, destination)` return a `FileEntry`.
- `exists(path)` returns a `bool`; `remove(path, recursive=False)` deletes a file or directory.
- `watch(path, recursive=False, timeout_ms=None)` streams a `WatchEvent` per change (create/write/remove/rename/chmod) until the watch ends.
