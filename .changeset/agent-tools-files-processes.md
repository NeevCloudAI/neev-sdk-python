---
"neevai": minor
---

`neevai.agent_tools` gains `stat_path`, `move_path` and `delete_path`, on by default, and `list_processes`, enabled with `allow_processes`. `stat_path` returns `{"exists": False}` for a missing path, otherwise its `type`, `size` and `modified_time`. `delete_path` deletes a non-empty directory only with `recursive: true`. `list_processes` returns each process's `process_id`, `command`, `state` and, once exited, `exit_code`. A process started with `start_process` is listed by the command the model gave, without its `sh -lc` wrapper. `names()` lists the file tools after `read_file`, and `list_processes` after `stop_process`.

`read_file` takes optional `offset` and `length` (1 to 10000, default 10000) to page through a large file. A paged read returns whole UTF-8 characters plus `next_offset` and `eof`, and `next_offset` always advances until `eof`, even when `length` is shorter than one character. Without them it reads the whole file and cuts it in the middle as before. Its description now says so. A new read-only `TITLES` mapping gives every tool a short display title. `call()` now checks boolean parameters: anything other than `true`, `false` or `null` is `recursive must be boolean`.

`sandbox.files.read` and `read_text` (sync and async) take optional `offset` and `length` to read a byte range. The response is streamed and closed once the range has arrived. A negative `offset`, a `length` below 1, or either one not an `int` raises `ValueError`.
