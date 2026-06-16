# Process API Review Analysis

Here is what the Python implementation actually does, and how it compares to the review comments and the documented contract.

## Comment 1: `ProcessLogEntry` missing `stream` in poll mode

### What Python does today

Poll and follow are modeled differently on purpose:

**Poll (`logs`)** — JSON page, entries with only `data`:

```python
# src/neevai/runtime/schemas.py
class RawProcessLogEntry(BaseModel):
    data: str
```

```python
# src/neevai/types.py
class ProcessLogEntry(BaseModel):
    """Single log line from poll-mode log retrieval."""

    data: str
```

**Follow (`follow`)** — NDJSON frames, stream identity via `type`:

```python
# src/neevai/runtime/_stream.py
def _yield_log_frame_events(
    frame: ProcessLogFrame,
    state: _StreamState,
) -> Iterator[ProcessLogEvent]:
    if isinstance(frame, StdoutFrame):
        ...
                yield {"type": "stdout", "data": text}
    elif isinstance(frame, StderrFrame):
        ...
                yield {"type": "stderr", "data": text}
```

Tests reinforce that split: poll mock returns `{"data": "line one\n"}` with no `stream`; follow mock uses `type: stdout|stderr|exit` with base64 on the wire.

### Was this intentional?

Yes — this looks deliberate, not an accidental omission.

1. **Shared product docs** describe poll as plain text, follow as typed streams:
   - Python `api-inventory.md`: "Poll-mode UTF-8 log lines"
   - JS changeset / README in `neev-sdk/`: "`logs` returns plain-text entries … `follow` streams decoded stdout/stderr chunks"

2. **Two-mode design** is consistent across SDKs:
   - `logs()` = buffered ring snapshot, cursor pagination
   - `follow()` = live NDJSON, same frame shape as `exec_stream`

3. **Your own tests and examples** never use `entry.stream` in poll mode; `examples/processes.py` only counts entries from `proc.logs()`.

### Where the reviewer has a point

There is tension in the docs, not necessarily in runtime behavior:

- External [Sandbox Agent SDK process docs](https://sandboxagent.dev/docs/processes) and the JS `api-inventory` type line show `ProcessLogEntry = { stream, data }`.
- But the JS behavioral text also says poll `entries[].data` is **plain UTF-8** (not base64), which matches Python more than the sandboxagent.dev `atob(entry.data)` examples.

So the reviewer may be looking at:
- wire format / public daemon docs, or
- a stale/contradictory type table in JS inventory (line 875 says `stream`; line 859 says plain UTF-8 `data` only).

If the daemon **does** return `{ "stream": "stderr", "data": "..." }` in poll responses, Pydantic will accept the payload but **drop `stream`** because it is not on the model. That is silent information loss — but only matters if poll entries are meant to preserve stdout/stderr identity.

### Recommendation

| Verdict | Action |
|--------|--------|
| **Not clearly a bug** if poll contract is "plain chronological text" | Current design is reasonable and documented |
| **Worth fixing** if daemon poll entries include `stream` and callers need stderr vs stdout in poll mode | Add `stream: Literal["stdout", "stderr"]` to `RawProcessLogEntry` / `ProcessLogEntry` |

Before changing code, confirm with one real `POST /v1/processes/logs` response (non-follow). If entries have `stream`, I'd accept the review. If they are `{ data: "..." }` only, Python is aligned with the intended SDK surface and the reviewer is comparing against follow-mode or outdated docs.

---

## Comment 2: `kill(signal=Signal.TERM)` omits signal on the wire

### What Python does today

```python
# src/neevai/runtime/processes.py
def _signal_body_value(signal: int | None) -> int | None:
    if signal is None or signal == Signal.TERM:
        return None
    return signal
```

So:

| Call | Wire body |
|------|-----------|
| `kill()` | `{"process_id": "..."}` |
| `kill(signal=Signal.TERM)` | `{"process_id": "..."}` (same) |
| `kill(signal=Signal.KILL)` | `{"process_id": "...", "signal": 9}` |

This is **explicitly documented** in your inventory:

> Default on the wire is SIGTERM (`Signal.TERM`); **omitted when `signal` is `None` or `Signal.TERM`**.

Tests cover default omission (`test_kill_default_signal_omitted`) but **not** `kill(signal=Signal.TERM)` explicitly.

### Was this intentional?

Yes. This is a documented wire optimization: daemon default = SIGTERM, so omitting the field is equivalent at runtime. It is not an accidental bug.

### Is the reviewer still right?

From a **SDK ergonomics** standpoint, yes:

- `kill()` and `kill(signal=Signal.TERM)` look different to the caller but produce identical payloads.
- If JS always sends `{"signal": 15}` for explicit TERM, Python is inconsistent at the client layer even if daemon behavior is the same.

### Recommendation

| Verdict | Action |
|--------|--------|
| **Not a functional bug** | Runtime behavior is the same |
| **Reasonable polish** | Change to only omit when `signal is None`; send `15` when `Signal.TERM` is passed explicitly |
| **Low risk** | Daemon should treat `{}` and `{"signal": 15}` identically |

I would accept this review as a small consistency fix, not a hotfix. Update docs/tests if you change it (`test_kill_explicit_term_sends_15`).

---

## Bottom line

| Comment | Deliberate deviation? | Worth implementing? |
|---------|----------------------|---------------------|
| **#1 `stream` on poll entries** | Likely **yes** — poll/follow split is intentional; poll = plain `data`, follow = typed events | **Verify daemon response first.** Add `stream` only if wire includes it and poll consumers need it. Otherwise document the asymmetry vs sandboxagent.dev. |
| **#2 TERM → omit signal** | **Yes** — coded and documented on purpose | **Nice to have** for API predictability and JS alignment; not urgent |

Neither looks like a careless mistake. Comment #1 is the one that needs a live API check before you change types. Comment #2 is a clean, low-risk consistency improvement if you want Python to mirror JS call semantics exactly.

