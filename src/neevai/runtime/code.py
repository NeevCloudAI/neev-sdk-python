"""Code interpreter on the sandbox runtime: persistent kernels, in sandboxes created
from the interpreter template."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable, Iterable
from typing import TYPE_CHECKING, Any

from neevai.errors import APIError, APITimeoutError, NeevAIError
from neevai.types import (
    CodeContext,
    CodeError,
    CodeResult,
    CreatedCodeContext,
    Execution,
    OutputMessage,
)

if TYPE_CHECKING:
    from neevai.runtime.connection import AsyncSandboxConnection, SandboxConnection

# Prefer: wait=0 asks not to be held while a paused sandbox wakes; the SDK retries instead.
_RUN_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/x-ndjson",
    "Prefer": "wait=0",
}
_JSON_HEADERS = {"Content-Type": "application/json", "Prefer": "wait=0"}

# How long a call keeps retrying a sandbox that is waking, and how often.
_WAKE_BUDGET_S = 120.0
_WAKE_RETRY_S = 2.0

# A context, or its id.
ContextRef = str | CodeContext | CreatedCodeContext


def _context_id(context: ContextRef) -> str:
    return context if isinstance(context, str) else context.context_id


def _run_body(
    code: str,
    context: ContextRef | None,
    language: str | None,
    envs: dict[str, str] | None,
    timeout_ms: int | None,
) -> dict[str, object]:
    if context is not None and language is not None:
        raise NeevAIError("code.run: pass a context or a language, not both.")
    if language is not None and language != "python":
        raise NeevAIError(f'code.run: language "{language}" is not supported; use "python".')
    body: dict[str, object] = {"code": code}
    if context is not None:
        body["context_id"] = _context_id(context)
    if timeout_ms is not None:
        body["timeout_ms"] = timeout_ms
    if envs:
        body["envs"] = envs
    return body


def _create_body(language: str | None, cwd: str | None) -> dict[str, object]:
    body: dict[str, object] = {}
    if language:
        body["language"] = language
    if cwd:
        body["cwd"] = cwd
    return body


class _Deadline:
    """A bound on a whole request, checked as each line arrives."""

    def __init__(self, timeout_ms: int | None):
        self._at = time.monotonic() + timeout_ms / 1000.0 if timeout_ms is not None else None

    def check(self) -> None:
        if self._at is not None and time.monotonic() > self._at:
            raise APITimeoutError("code run exceeded its request timeout")

    def remaining(self) -> float | None:
        """Seconds left, or None when unbounded; raises once none are left."""
        if self._at is None:
            return None
        left = self._at - time.monotonic()
        if left <= 0:
            raise APITimeoutError("code run exceeded its request timeout")
        return left


class _Waking:
    """Paces retries while the sandbox is waking; that answer precedes the cell."""

    def __init__(self, deadline: _Deadline):
        self._deadline = deadline
        self._until = time.monotonic() + _WAKE_BUDGET_S

    def pause(self, err: APIError) -> float | None:
        """Returns the pause before the next try, or None when err is final."""
        left = self._until - time.monotonic()
        if err.reason != "sandbox_waking" or left <= 0:
            return None
        remaining = self._deadline.remaining()
        return min(_WAKE_RETRY_S, left, remaining if remaining is not None else left)


class _Collector:
    """Builds an Execution from run events, calling back as each arrives."""

    def __init__(
        self,
        on_stdout: Callable[[OutputMessage], None] | None,
        on_stderr: Callable[[OutputMessage], None] | None,
        on_result: Callable[[CodeResult], None] | None,
        on_error: Callable[[CodeError], None] | None,
    ):
        self.out = Execution()
        self._on_stdout = on_stdout
        self._on_stderr = on_stderr
        self._on_result = on_result
        self._on_error = on_error
        self.ended = False

    def add(self, line: str) -> None:
        """Adds one NDJSON line; ignored once the run has ended."""
        line = line.strip()
        if not line or self.ended:
            return
        frame: dict[str, Any] = json.loads(line)
        kind = frame.get("type")
        if kind == "stream":
            is_err = frame.get("name") == "stderr"
            message = OutputMessage(
                line=str(frame.get("text", "")), timestamp=int(time.time() * 1000), error=is_err
            )
            if is_err:
                self.out.stderr += message.line
                self.out.logs.stderr.append(message.line)
                if self._on_stderr:
                    self._on_stderr(message)
            else:
                self.out.stdout += message.line
                self.out.logs.stdout.append(message.line)
                if self._on_stdout:
                    self._on_stdout(message)
        elif kind == "result":
            result = CodeResult(data=frame.get("data") or {}, is_main=bool(frame.get("is_main")))
            self.out.results.append(result)
            if result.is_main:
                self.out.text = result.text
            if self._on_result:
                self._on_result(result)
        elif kind == "error":
            error = CodeError(
                name=str(frame.get("name", "")),
                value=str(frame.get("value", "")),
                traceback=list(frame.get("traceback") or []),
            )
            self.out.error = error
            if self._on_error:
                self._on_error(error)
        elif kind == "end":
            self.out.end_reason = str(frame.get("reason", ""))
            self.out.generation = str(frame.get("generation", ""))
            count = frame.get("execution_count")
            self.out.execution_count = count if isinstance(count, int) else None
            self.out.truncated = bool(frame.get("truncated"))
            self.ended = True

    def result(self) -> Execution:
        """Returns the Execution, or raises when the stream was cut before its end."""
        if not self.ended:
            raise NeevAIError("code run ended without an end event: its output is incomplete.")
        return self.out


def _contexts(data: Any) -> list[CodeContext]:
    return [CodeContext.model_validate(c) for c in data["contexts"]]


def _created(data: Any) -> CreatedCodeContext:
    return CreatedCodeContext.model_validate(data)


class SandboxCode:
    """Runs code in persistent kernels. Reached via ``sandbox.code``."""

    def __init__(self, connection: SandboxConnection):
        self._conn = connection

    def run(
        self,
        code: str,
        *,
        context: ContextRef | None = None,
        language: str | None = None,
        envs: dict[str, str] | None = None,
        timeout_ms: int | None = None,
        request_timeout_ms: int | None = None,
        on_stdout: Callable[[OutputMessage], None] | None = None,
        on_stderr: Callable[[OutputMessage], None] | None = None,
        on_result: Callable[[CodeResult], None] | None = None,
        on_error: Callable[[CodeError], None] | None = None,
    ) -> Execution:
        """Runs code and returns everything it produced; callbacks see output as it arrives.

        ``context`` is a context or its id (default: the ``default`` context), ``language``
        picks the default context of that language (``python`` today), ``envs`` apply to this
        run only, ``timeout_ms`` bounds the cell and ``request_timeout_ms`` the whole request.
        Code that raises is returned, not raised: ``end_reason`` is ``"error"`` and ``error``
        is set. A run refused before it started (busy context, no interpreter) raises an
        ``APIError`` whose ``reason`` says why. A paused sandbox is woken; the call waits
        for it up to two minutes.
        """
        body = _run_body(code, context, language, envs, timeout_ms)
        deadline = _Deadline(request_timeout_ms)
        waking = _Waking(deadline)
        while True:
            collector = _Collector(on_stdout, on_stderr, on_result, on_error)
            lines: Iterable[str] = self._conn._transport.stream_request(
                "POST",
                "/v1/interpreter/run",
                headers=_RUN_HEADERS,
                body=body,
                timeout_s=deadline.remaining(),
            )
            try:
                for line in lines:
                    deadline.check()
                    collector.add(line)
                return collector.result()
            except APIError as err:
                pause = waking.pause(err)
                if pause is None:
                    raise
                time.sleep(pause)

    def create_context(
        self,
        *,
        language: str | None = None,
        cwd: str | None = None,
        request_timeout_ms: int | None = None,
    ) -> CreatedCodeContext:
        """Creates a named context with its own state, its kernel started in ``cwd``.

        ``cwd`` is absolute or relative to the workspace and must exist. The kernel starts
        in the background; a run sent before it is ready waits for it.
        """
        return _created(self._call("create", _create_body(language, cwd), request_timeout_ms))

    def list_contexts(self, *, request_timeout_ms: int | None = None) -> list[CodeContext]:
        """Lists the sandbox's contexts."""
        return _contexts(self._call("list", {}, request_timeout_ms))

    def restart_context(self, context: ContextRef, *, request_timeout_ms: int | None = None) -> str:
        """Restarts a context, dropping its state, and returns its new generation."""
        reply = self._call("restart", {"context_id": _context_id(context)}, request_timeout_ms)
        return str(reply["generation"])

    def delete_context(self, context: ContextRef, *, request_timeout_ms: int | None = None) -> None:
        """Deletes a named context; deleting ``default`` restarts it instead."""
        self._call("delete", {"context_id": _context_id(context)}, request_timeout_ms)

    def _call(self, op: str, body: dict[str, object], request_timeout_ms: int | None) -> Any:
        deadline = _Deadline(request_timeout_ms)
        waking = _Waking(deadline)
        while True:
            try:
                response = self._conn._transport.request(
                    method="POST",
                    path=f"/v1/interpreter/contexts/{op}",
                    headers=_JSON_HEADERS,
                    body=body,
                    timeout_s=deadline.remaining(),
                )
                return response.json()
            except APIError as err:
                pause = waking.pause(err)
                if pause is None:
                    raise
                time.sleep(pause)


class AsyncSandboxCode:
    """Async variant of :class:`SandboxCode`. Reached via ``sandbox.code``."""

    def __init__(self, connection: AsyncSandboxConnection):
        self._conn = connection

    async def run(
        self,
        code: str,
        *,
        context: ContextRef | None = None,
        language: str | None = None,
        envs: dict[str, str] | None = None,
        timeout_ms: int | None = None,
        request_timeout_ms: int | None = None,
        on_stdout: Callable[[OutputMessage], None] | None = None,
        on_stderr: Callable[[OutputMessage], None] | None = None,
        on_result: Callable[[CodeResult], None] | None = None,
        on_error: Callable[[CodeError], None] | None = None,
    ) -> Execution:
        """Runs code and returns everything it produced (see ``SandboxCode.run``)."""
        body = _run_body(code, context, language, envs, timeout_ms)
        deadline = _Deadline(request_timeout_ms)
        waking = _Waking(deadline)
        while True:
            collector = _Collector(on_stdout, on_stderr, on_result, on_error)
            lines: AsyncIterator[str] = self._conn._transport.stream_request(
                "POST",
                "/v1/interpreter/run",
                headers=_RUN_HEADERS,
                body=body,
                timeout_s=deadline.remaining(),
            )
            try:
                async for line in lines:
                    deadline.check()
                    collector.add(line)
                return collector.result()
            except APIError as err:
                pause = waking.pause(err)
                if pause is None:
                    raise
                await asyncio.sleep(pause)

    async def create_context(
        self,
        *,
        language: str | None = None,
        cwd: str | None = None,
        request_timeout_ms: int | None = None,
    ) -> CreatedCodeContext:
        """Creates a named context with its own state (see ``SandboxCode.create_context``)."""
        return _created(await self._call("create", _create_body(language, cwd), request_timeout_ms))

    async def list_contexts(self, *, request_timeout_ms: int | None = None) -> list[CodeContext]:
        """Lists the sandbox's contexts."""
        return _contexts(await self._call("list", {}, request_timeout_ms))

    async def restart_context(
        self, context: ContextRef, *, request_timeout_ms: int | None = None
    ) -> str:
        """Restarts a context, dropping its state, and returns its new generation."""
        reply = await self._call(
            "restart", {"context_id": _context_id(context)}, request_timeout_ms
        )
        return str(reply["generation"])

    async def delete_context(
        self, context: ContextRef, *, request_timeout_ms: int | None = None
    ) -> None:
        """Deletes a named context; deleting ``default`` restarts it instead."""
        await self._call("delete", {"context_id": _context_id(context)}, request_timeout_ms)

    async def _call(self, op: str, body: dict[str, object], request_timeout_ms: int | None) -> Any:
        deadline = _Deadline(request_timeout_ms)
        waking = _Waking(deadline)
        while True:
            try:
                response = await self._conn._transport.request(
                    method="POST",
                    path=f"/v1/interpreter/contexts/{op}",
                    headers=_JSON_HEADERS,
                    body=body,
                    timeout_s=deadline.remaining(),
                )
                return response.json()
            except APIError as err:
                pause = waking.pause(err)
                if pause is None:
                    raise
                await asyncio.sleep(pause)
