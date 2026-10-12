"""Tests for the framework-neutral sandbox agent tools."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from neevai import agent_tools
from neevai.agent_tools import (
    _MAX_ERROR_CHARS,
    DESCRIPTIONS,
    PARAMETERS,
    AsyncSandboxTools,
    SandboxTools,
    _truncate,
)
from neevai.errors import (
    APIConnectionError,
    AuthenticationError,
    BadRequestError,
    DeadlineExceededError,
    InternalServerError,
    NeevAIError,
    NotFoundError,
    RateLimitError,
    error_from_status,
)

FIXTURES = Path(__file__).parent / "fixtures"


def api_error(cls: type[Exception], message: str) -> Exception:
    return cls(400, {"message": message}, None)


def entry(stream: str, data: str) -> SimpleNamespace:
    return SimpleNamespace(stream=stream, data=data)


class FakeClock:
    """Stands in for the module's clock and sleep so waits take no real time."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    async def async_sleep(self, seconds: float) -> None:
        self.sleep(seconds)


# The current test's clock, so fakes can make a call take time.
CLOCK = FakeClock()


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(agent_tools, "_sleep", fake.sleep)
    monkeypatch.setattr(agent_tools, "_async_sleep", fake.async_sleep)
    monkeypatch.setattr(agent_tools, "_now", lambda: fake.now)
    monkeypatch.setitem(globals(), "CLOCK", fake)
    return fake


class FakeFiles:
    def __init__(self, sandbox: FakeSandbox) -> None:
        self.sandbox = sandbox

    def write(self, path: str, content: str) -> dict[str, int]:
        if self.sandbox.fail:
            raise self.sandbox.fail
        self.sandbox.workspace[path] = content
        return {"bytes_written": len(content.encode())}

    def read_text(self, path: str) -> str:
        if self.sandbox.fail:
            raise self.sandbox.fail
        if path not in self.sandbox.workspace:
            raise api_error(NotFoundError, f"{path}: no such file")
        return self.sandbox.workspace[path]


class FakeProcesses:
    def __init__(self, sandbox: FakeSandbox) -> None:
        self.sandbox = sandbox
        self.page = SimpleNamespace(entries=[], cursor=0, dropped=False, state="running")
        # States get() reports in turn; the last one repeats.
        self.states = ["exited"]
        self.gone = False

    def start(self, program: str, args: list[str] | None = None, cwd: str | None = None) -> Any:
        self.sandbox.calls.append(("processes.start", program, args, cwd))
        if self.sandbox.fail:
            raise self.sandbox.fail
        return SimpleNamespace(id="proc-1")

    def logs(self, process_id: str, cursor: int | None = None) -> Any:
        self.sandbox.calls.append(("processes.logs", process_id, cursor))
        if process_id != "proc-1":
            raise api_error(NotFoundError, "process not found")
        return self.page

    def get(self, process_id: str) -> Any:
        self.sandbox.calls.append(("processes.get", process_id))
        if process_id != "proc-1" or self.gone:
            raise api_error(NotFoundError, "process not found")
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        return SimpleNamespace(
            process_id=process_id, state=state, exit_code=3 if state == "exited" else None
        )

    def kill(self, process_id: str) -> bool:
        self.sandbox.calls.append(("processes.kill", process_id))
        if process_id != "proc-1":
            raise api_error(NotFoundError, "process not found")
        return True


class FakeSandboxes:
    def __init__(self, sandbox: FakeSandbox) -> None:
        self.sandbox = sandbox

    def get_snapshot(
        self, snapshot_id: str, org_id: str | None = None, project_id: str | None = None
    ) -> Any:
        self.sandbox.calls.append(("get_snapshot", snapshot_id, org_id, project_id))
        CLOCK.now += self.sandbox.fetch_s
        return self.sandbox.next_snapshot()


class FakeSandbox:
    def __init__(
        self,
        exec_result: Any = None,
        snapshot_statuses: tuple[str, ...] | list[str] = ("Ready",),
    ) -> None:
        self.workspace: dict[str, str] = {}
        self.calls: list[tuple[Any, ...]] = []
        self.fail: BaseException | None = None
        self.exec_result = exec_result or SimpleNamespace(exit_code=0, stdout="ok", stderr="")
        self.snapshot_statuses = list(snapshot_statuses)
        self.snapshot_error: str | None = None
        # Seconds each get_snapshot takes on the fake clock.
        self.fetch_s = 0.0
        self.files = FakeFiles(self)
        self.processes = FakeProcesses(self)
        self.sandboxes: FakeSandboxes | None = FakeSandboxes(self)
        self.scope = SimpleNamespace(org_id="org-1", project_id="prj-1")

    def next_snapshot(self) -> Any:
        return SimpleNamespace(
            id="snap-1",
            status=self.snapshot_statuses.pop(0),
            error_message=self.snapshot_error,
        )

    def _connection(self) -> FakeSandbox:
        return self

    def _exec(
        self,
        command: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        timeout_ms: int | None = None,
        errors: str = "strict",
    ) -> Any:
        self.calls.append(("exec", command, args, cwd, timeout_ms))
        self.exec_errors = errors
        if self.fail:
            raise self.fail
        return self.exec_result

    def get_url(self, port: int) -> str:
        self.calls.append(("get_url", port))
        if self.fail:
            raise self.fail
        return f"https://{port}-x.sandboxes.example"

    def snapshot(self, params: dict[str, Any] | None = None) -> Any:
        self.calls.append(("snapshot", params))
        return self.next_snapshot()

    def rollback(self, snapshot_id: str) -> FakeSandbox:
        self.calls.append(("rollback", snapshot_id))
        if snapshot_id != "snap-1":
            raise api_error(NotFoundError, "snapshot not found")
        return self


def tools_for(sandbox: FakeSandbox | None = None, **kw: Any) -> tuple[SandboxTools, FakeSandbox]:
    sandbox = sandbox or FakeSandbox()
    return SandboxTools(sandbox, **kw), sandbox  # type: ignore[arg-type]


ALL_TOOLS = [
    "run_command",
    "write_file",
    "read_file",
    "expose_port",
    "checkpoint",
    "rollback",
    "start_process",
    "read_process_output",
    "stop_process",
]


def test_truncate_leaves_short_text_alone():
    assert _truncate("hello") == "hello"
    assert _truncate("x" * 10_000) == "x" * 10_000


def test_truncate_keeps_head_and_tail_and_counts_dropped_bytes():
    text = "h" * 4_000 + "m" * 5_000 + "t" * 6_000
    assert _truncate(text) == "h" * 4_000 + "\n…[5000 bytes truncated]…\n" + "t" * 6_000


def test_truncate_replaces_a_split_character():
    assert "…[2000 bytes truncated]…" in _truncate("é" * 6_000)
    assert "\N{REPLACEMENT CHARACTER}" in _truncate("a" + "é" * 6_000)


def test_public_names():
    assert sorted(agent_tools.__all__) == sorted(
        [
            "DESCRIPTIONS",
            "PARAMETERS",
            "AsyncSandboxTools",
            "SandboxTools",
            "ToolName",
            "ToolResult",
            "ToolErrorResult",
            "RunCommandToolResult",
            "WriteFileToolResult",
            "ReadFileToolResult",
            "ExposePortToolResult",
            "CheckpointToolResult",
            "RollbackToolResult",
            "StartProcessToolResult",
            "ReadProcessOutputToolResult",
            "StopProcessToolResult",
        ]
    )
    assert not hasattr(agent_tools, "truncate")
    assert not hasattr(agent_tools, "short_error")


def test_descriptions_match_the_shared_fixture():
    # The JS SDK carries a byte-identical copy of this fixture.
    fixture = json.loads((FIXTURES / "agent_tool_descriptions.json").read_text(encoding="utf-8"))
    assert dict(DESCRIPTIONS) == fixture
    assert list(DESCRIPTIONS) == ALL_TOOLS


def test_parameters_match_the_shared_fixture():
    fixture = json.loads((FIXTURES / "agent_tool_parameters.json").read_text(encoding="utf-8"))
    assert json.loads(json.dumps(PARAMETERS)) == fixture
    assert list(PARAMETERS) == ALL_TOOLS


def test_every_parameter_schema_is_closed_and_described():
    for name, schema in PARAMETERS.items():
        assert schema["type"] == "object", name
        assert schema["additionalProperties"] is False, name
        assert set(schema["required"]) <= set(schema["properties"]), name
        for prop in schema["properties"].values():
            assert prop["description"], name


def test_schemas_match_the_method_signatures():
    tools, _ = tools_for()

    for name, schema in PARAMETERS.items():
        params = inspect.signature(getattr(tools, name)).parameters
        assert list(params) == list(schema["properties"]), name
        required = [p for p, v in params.items() if v.default is inspect.Parameter.empty]
        assert required == list(schema["required"]), name


MUTATIONS = [
    lambda m: m.__setitem__("run_command", "x"),
    lambda m: m.__delitem__("run_command"),
    lambda m: m.update({"x": "y"}),
    lambda m: m.pop("run_command"),
    lambda m: m.popitem(),
    lambda m: m.clear(),
    lambda m: m.setdefault("x", "y"),
    lambda m: m.__ior__({"x": "y"}),
]


@pytest.mark.parametrize("mutate", MUTATIONS)
def test_descriptions_and_parameters_are_read_only(mutate: Any):
    run_command = PARAMETERS["run_command"]
    for mapping in (DESCRIPTIONS, PARAMETERS, run_command, run_command["properties"]):
        with pytest.raises(TypeError, match="read-only"):
            mutate(mapping)
    assert len(DESCRIPTIONS) == 9 and len(PARAMETERS) == 9
    assert isinstance(run_command["required"], tuple)


def test_descriptions_and_parameters_serialize_as_json():
    assert json.loads(json.dumps(DESCRIPTIONS)) == dict(DESCRIPTIONS)
    assert json.loads(json.dumps(PARAMETERS["run_command"]))["required"] == ["command"]


def test_parameter_schemas_share_no_objects():
    seen: dict[int, str] = {}

    def walk(node: Any, path: str) -> None:
        if isinstance(node, (dict, tuple)):
            assert id(node) not in seen, f"{path} shares an object with {seen.get(id(node))}"
            seen[id(node)] = path
            items = node.items() if isinstance(node, dict) else enumerate(node)
            for key, child in items:
                walk(child, f"{path}.{key}")

    walk(PARAMETERS, "PARAMETERS")
    assert (
        PARAMETERS["run_command"]["properties"]["command"]
        is not PARAMETERS["start_process"]["properties"]["command"]
    )


def test_process_descriptions_state_retention_cursor_and_wait():
    read = DESCRIPTIONS["read_process_output"]
    assert "about 10 minutes, after which exit_code is no longer returned" in read
    assert "cursor still moves past the cut part" in read
    assert "wait_s (0 to 60, default 0)" in read
    assert "saves turns" in read
    assert "about 10 minutes" in DESCRIPTIONS["stop_process"]
    assert "processes or in-flight requests" in DESCRIPTIONS["start_process"]


def test_names_default_to_the_three_safe_tools():
    tools, _ = tools_for()
    assert tools.names() == ["run_command", "write_file", "read_file"]


def test_names_include_opt_in_tools_only_when_enabled():
    tools, _ = tools_for(allow_preview=True, allow_rollback=True, allow_processes=True)
    assert tools.names() == ALL_TOOLS


@pytest.mark.parametrize("option", ["allow_preview", "allow_rollback"])
def test_preview_and_rollback_need_a_handle_with_a_client(option: str):
    sandbox = FakeSandbox()
    sandbox.sandboxes = None
    with pytest.raises(ValueError, match="client context"):
        SandboxTools(sandbox, **{option: True})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="client context"):
        AsyncSandboxTools(sandbox, **{option: True})  # type: ignore[arg-type]


def test_a_handle_without_a_client_still_runs_the_core_tools():
    sandbox = FakeSandbox()
    sandbox.sandboxes = None
    tools, _ = tools_for(sandbox, allow_processes=True)
    assert tools.run_command("ls")["exit_code"] == 0  # type: ignore[typeddict-item]


def test_run_command_uses_a_login_shell_and_default_timeout():
    tools, sandbox = tools_for()
    assert tools.run_command("ls") == {"exit_code": 0, "stdout": "ok", "stderr": ""}
    assert sandbox.calls == [("exec", "sh", ["-lc", "ls"], None, 60_000)]


@pytest.mark.parametrize(
    "given,expected_ms",
    [
        (5, 5_000),
        (0, 1_000),
        (-3, 1_000),
        (9_999, 600_000),
        (2.5, 2_500),
        (30.0, 30_000),
        ("30", 30_000),
        (" 2.5 ", 2_500),
        ("abc", 60_000),
        ("", 60_000),
        (True, 60_000),
        (False, 60_000),
        (float("nan"), 60_000),
        (float("inf"), 60_000),
        (float("-inf"), 60_000),
        ("inf", 60_000),
        ("1e400", 60_000),
        (10**400, 60_000),
        ("1_000", 60_000),
        ("0x10", 60_000),
        ("   ", 60_000),
        ("+45", 45_000),
        ("1e2", 100_000),
        (".5", 1_000),
        (None, 60_000),
        ([5], 60_000),
    ],
)
def test_run_command_coerces_and_clamps_timeout(given: Any, expected_ms: int):
    tools, sandbox = tools_for()
    tools.run_command("ls", timeout_s=given)
    sent = sandbox.calls[0][4]
    assert sent == expected_ms
    assert type(sent) is int


def test_run_command_null_optionals_use_defaults():
    tools, sandbox = tools_for()
    tools.run_command("ls", cwd=None, timeout_s=None)
    assert sandbox.calls[0][3:] == (None, 60_000)


def test_run_command_returns_a_non_zero_exit_as_data():
    failed = SimpleNamespace(exit_code=2, stdout="", stderr="no such file")
    tools, _ = tools_for(FakeSandbox(exec_result=failed))
    assert tools.run_command("cat nope") == {"exit_code": 2, "stdout": "", "stderr": "no such file"}


def test_run_command_truncates_each_stream():
    big = SimpleNamespace(exit_code=0, stdout="o" * 20_000, stderr="e" * 20_000)
    tools, _ = tools_for(FakeSandbox(exec_result=big))
    result = tools.run_command("yes")
    assert "…[10000 bytes truncated]…" in result["stdout"]  # type: ignore[typeddict-item]
    assert "…[10000 bytes truncated]…" in result["stderr"]  # type: ignore[typeddict-item]


@pytest.mark.parametrize("cls", [BadRequestError, NotFoundError])
def test_recoverable_errors_become_results(cls: type[Exception]):
    tools, sandbox = tools_for()
    sandbox.fail = api_error(cls, "path is outside the workspace")
    assert tools.run_command("ls") == {"error": "HTTP 400 path is outside the workspace"}


def test_bad_request_error_comes_through_intact():
    tools, sandbox = tools_for()
    sandbox.fail = BadRequestError(
        400,
        {"code": "invalid_argument", "message": 'path "/etc/passwd" escapes workspace root'},
        "req-1",
    )
    assert tools.run_command("ls") == {"error": str(sandbox.fail)}
    assert "[request-id: req-1]" in str(sandbox.fail)


@pytest.mark.parametrize(
    "timeout_s,text",
    [(1, "1 s"), (9999, "600 s"), (2.5, "2.5 s"), (30.0, "30 s"), ("45", "45 s")],
)
def test_run_command_deadline_says_the_command_did_not_finish(timeout_s: Any, text: str):
    tools, sandbox = tools_for()
    sandbox.fail = DeadlineExceededError(504, None, None)
    assert tools.run_command("sleep 5", timeout_s=timeout_s) == {
        "error": f"command did not finish within {text}"
    }


def test_other_deadlines_are_a_short_timeout_error():
    tools, sandbox = tools_for()
    sandbox.fail = DeadlineExceededError(504, None, None)
    assert tools.write_file("a.txt", "x") == {"error": "timed out"}


def test_long_multi_line_errors_keep_a_capped_first_line():
    tools, sandbox = tools_for()
    sandbox.fail = NeevAIError("x" * 2_000 + "\n<html>\n" + "y" * 5_000)
    assert tools.run_command("ls") == {"error": "x" * _MAX_ERROR_CHARS + "…"}


def test_auth_errors_raise():
    tools, sandbox = tools_for()
    sandbox.fail = api_error(AuthenticationError, "bad key")
    with pytest.raises(AuthenticationError):
        tools.run_command("ls")


def test_connection_errors_raise():
    tools, sandbox = tools_for()
    sandbox.fail = APIConnectionError("connection reset")
    with pytest.raises(APIConnectionError):
        tools.write_file("a.txt", "x")


def test_non_sdk_errors_raise():
    tools, sandbox = tools_for()
    sandbox.fail = RuntimeError("bug")
    with pytest.raises(RuntimeError):
        tools.run_command("ls")


def test_client_side_sdk_errors_become_results():
    tools, sandbox = tools_for()
    sandbox.fail = NeevAIError(
        "exec stream ended without an exit status (the command may have timed out)."
    )
    assert tools.run_command("sleep 1") == {
        "error": "exec stream ended without an exit status (the command may have timed out)."
    }


def test_run_command_decodes_output_with_replacement():
    tools, sandbox = tools_for()
    tools.run_command("cat blob.bin")
    assert sandbox.exec_errors == "replace"


async def test_async_run_command_decodes_output_with_replacement():
    tools, sandbox = async_tools_for()
    await tools.run_command("cat blob.bin")
    assert sandbox.exec_errors == "replace"


def test_non_utf8_content_is_an_error_result():
    tools, sandbox = tools_for()
    sandbox.fail = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
    result = tools.read_file("blob.bin")
    assert result["error"].startswith("not UTF-8 text: ")  # type: ignore[typeddict-item]


def test_write_then_read_round_trips():
    tools, _ = tools_for()
    assert tools.write_file("a.txt", "héllo") == {"bytes_written": 6}
    assert tools.read_file("a.txt") == {"content": "héllo"}


def test_read_missing_file_is_an_error_result():
    tools, _ = tools_for()
    assert tools.read_file("nope.txt") == {"error": "HTTP 400 nope.txt: no such file"}


def test_read_truncates_large_files():
    tools, sandbox = tools_for()
    sandbox.workspace["big.log"] = "x" * 50_000
    assert "…[40000 bytes truncated]…" in tools.read_file("big.log")["content"]  # type: ignore[typeddict-item]


def test_disabled_tools_refuse():
    tools, sandbox = tools_for()
    assert tools.expose_port(3000) == {"error": "expose_port is not enabled for this agent"}
    assert tools.checkpoint() == {"error": "checkpoint is not enabled for this agent"}
    assert tools.rollback("snap-1") == {"error": "rollback is not enabled for this agent"}
    assert tools.start_process("sleep 1") == {
        "error": "start_process is not enabled for this agent"
    }
    assert tools.read_process_output("proc-1") == {
        "error": "read_process_output is not enabled for this agent"
    }
    assert tools.stop_process("proc-1") == {"error": "stop_process is not enabled for this agent"}
    assert sandbox.calls == []


def test_call_dispatches_by_name_with_model_args():
    tools, sandbox = tools_for(allow_processes=True)
    assert tools.call("run_command", {"command": "ls", "timeout_s": "30"}) == {
        "exit_code": 0,
        "stdout": "ok",
        "stderr": "",
    }
    assert sandbox.calls == [("exec", "sh", ["-lc", "ls"], None, 30_000)]
    assert tools.call("write_file", {"path": "a.txt", "content": "hi"}) == {"bytes_written": 2}
    assert tools.call("stop_process", {"process_id": "proc-1"}) == {"ok": True}


def test_call_with_no_args_uses_defaults():
    tools, sandbox = tools_for(allow_rollback=True)
    assert tools.call("checkpoint") == {"checkpoint_id": "snap-1"}
    assert sandbox.calls[0] == ("snapshot", None)


def test_call_unknown_tool():
    tools, _ = tools_for()
    assert tools.call("rm_rf", {}) == {"error": "unknown tool: rm_rf"}


def test_call_disabled_tool_refuses_before_checking_args():
    tools, sandbox = tools_for()
    assert tools.call("expose_port", {"bogus": 1}) == {
        "error": "expose_port is not enabled for this agent"
    }
    assert sandbox.calls == []


@pytest.mark.parametrize(
    "name,args,reason",
    [
        ("run_command", {}, "missing a required argument: 'command'"),
        (
            "run_command",
            {"command": "ls", "shell": "bash"},
            "got an unexpected keyword argument 'shell'",
        ),
        ("write_file", {"path": "a.txt"}, "missing a required argument: 'content'"),
        ("read_file", ["a.txt"], "expected an object"),
        ("read_file", "a.txt", "expected an object"),
    ],
)
def test_call_with_bad_args_is_an_error_result(name: str, args: Any, reason: str):
    tools, sandbox = tools_for()
    assert tools.call(name, args) == {"error": f"invalid arguments for {name}: {reason}"}
    assert sandbox.calls == []


def test_expose_port_returns_the_preview_url():
    tools, _ = tools_for(allow_preview=True)
    assert tools.expose_port(3000) == {"preview_url": "https://3000-x.sandboxes.example"}


def test_expose_port_not_routable_is_an_error_result():
    tools, sandbox = tools_for(allow_preview=True)
    sandbox.fail = NeevAIError(
        "Preview URL https://3000-x.sandboxes.example was not routable within 30000ms."
    )
    assert tools.expose_port(3000) == {
        "error": "Preview URL https://3000-x.sandboxes.example was not routable within 30000ms."
    }


def test_checkpoint_polls_through_the_handle_until_ready_and_passes_the_label(clock: FakeClock):
    sandbox = FakeSandbox(snapshot_statuses=["Pending", "Running", "Ready"])
    tools, _ = tools_for(sandbox, allow_rollback=True)
    assert tools.checkpoint("before-migration") == {"checkpoint_id": "snap-1"}
    assert sandbox.calls == [
        ("snapshot", {"name": "before-migration"}),
        ("get_snapshot", "snap-1", "org-1", "prj-1"),
        ("get_snapshot", "snap-1", "org-1", "prj-1"),
    ]
    assert clock.sleeps == [2.0, 2.0]


def test_checkpoint_without_a_label_sends_no_params():
    tools, sandbox = tools_for(allow_rollback=True)
    assert tools.checkpoint() == {"checkpoint_id": "snap-1"}
    assert sandbox.calls == [("snapshot", None)]


def test_checkpoint_failed_is_an_error_result():
    tools, _ = tools_for(FakeSandbox(snapshot_statuses=["Pending", "Failed"]), allow_rollback=True)
    assert tools.checkpoint() == {"error": "checkpoint snap-1 failed"}


def test_checkpoint_failed_carries_the_snapshot_reason():
    sandbox = FakeSandbox(snapshot_statuses=["Failed"])
    sandbox.snapshot_error = "disk full\nmore detail"
    tools, _ = tools_for(sandbox, allow_rollback=True)
    assert tools.checkpoint() == {"error": "checkpoint snap-1 failed: disk full"}


def test_checkpoint_that_never_becomes_ready_times_out_after_300_s(clock: FakeClock):
    tools, sandbox = tools_for(
        FakeSandbox(snapshot_statuses=["Pending"] * 200), allow_rollback=True
    )
    assert tools.checkpoint() == {"error": "checkpoint snap-1 not ready after 300 s"}
    assert clock.now == 300.0
    assert sum(1 for c in sandbox.calls if c[0] == "get_snapshot") == 150


def test_checkpoint_ready_on_the_final_fetch_succeeds(clock: FakeClock):
    sandbox = FakeSandbox(snapshot_statuses=["Pending"] * 150 + ["Ready"])
    tools, _ = tools_for(sandbox, allow_rollback=True)
    assert tools.checkpoint() == {"checkpoint_id": "snap-1"}
    assert clock.now == 300.0


def test_checkpoint_deadline_counts_elapsed_time_not_polls(clock: FakeClock):
    sandbox = FakeSandbox(snapshot_statuses=["Pending"] * 200)
    sandbox.fetch_s = 10.0
    tools, _ = tools_for(sandbox, allow_rollback=True)
    assert tools.checkpoint() == {"error": "checkpoint snap-1 not ready after 300 s"}
    # Each round is a 2 s sleep plus a 10 s fetch, so the deadline hits after 25 rounds.
    assert sum(1 for c in sandbox.calls if c[0] == "get_snapshot") == 25
    assert clock.now == 300.0


def test_rollback_to_a_known_checkpoint():
    tools, _ = tools_for(allow_rollback=True)
    assert tools.rollback("snap-1") == {"ok": True}


def test_rollback_to_an_unknown_checkpoint_is_an_error_result():
    tools, _ = tools_for(allow_rollback=True)
    assert tools.rollback("snap-9") == {"error": "HTTP 400 snapshot not found"}


def test_start_process_runs_a_login_shell_in_cwd():
    tools, sandbox = tools_for(allow_processes=True)
    assert tools.start_process("npm run dev", cwd="app") == {"process_id": "proc-1"}
    assert sandbox.calls == [("processes.start", "sh", ["-lc", "npm run dev"], "app")]


@pytest.mark.parametrize(
    "message", ["too many concurrent processes", "too many in-flight requests"]
)
def test_start_process_resource_exhausted_is_an_error_result(message: str):
    tools, sandbox = tools_for(allow_processes=True)
    sandbox.fail = RateLimitError(429, {"code": "resource_exhausted", "message": message}, None)
    assert tools.start_process("sleep 1") == {"error": f"HTTP 429 resource_exhausted {message}"}


def test_start_process_other_rate_limits_raise():
    tools, sandbox = tools_for(allow_processes=True)
    sandbox.fail = RateLimitError(429, {"message": "slow down"}, None)
    with pytest.raises(RateLimitError):
        tools.start_process("sleep 1")


def test_read_process_output_splits_streams_and_passes_the_cursor():
    tools, sandbox = tools_for(allow_processes=True)
    sandbox.processes.page = SimpleNamespace(
        entries=[
            entry("stdout", "line 1\n"),
            entry("stderr", "warn\n"),
            entry("stdout", "line 2\n"),
        ],
        cursor=42,
        dropped=False,
        state="running",
    )
    assert tools.read_process_output("proc-1", cursor=7) == {
        "stdout": "line 1\nline 2\n",
        "stderr": "warn\n",
        "cursor": 42,
        "state": "running",
        "dropped": False,
    }
    assert sandbox.calls == [("processes.logs", "proc-1", 7)]


def test_read_process_output_adds_the_exit_code_once_exited():
    tools, sandbox = tools_for(allow_processes=True)
    sandbox.processes.page = SimpleNamespace(
        entries=[entry("stderr", "bye\n")], cursor=9, dropped=True, state="exited"
    )
    assert tools.read_process_output("proc-1") == {
        "stdout": "",
        "stderr": "bye\n",
        "cursor": 9,
        "state": "exited",
        "dropped": True,
        "exit_code": 3,
    }
    assert sandbox.calls == [("processes.logs", "proc-1", None), ("processes.get", "proc-1")]


def test_read_process_output_keeps_the_page_when_status_is_already_gone():
    tools, sandbox = tools_for(allow_processes=True)
    sandbox.processes.page = SimpleNamespace(
        entries=[entry("stdout", "done\n")], cursor=5, dropped=False, state="exited"
    )
    sandbox.processes.gone = True
    assert tools.read_process_output("proc-1") == {
        "stdout": "done\n",
        "stderr": "",
        "cursor": 5,
        "state": "exited",
        "dropped": False,
    }


def test_read_process_output_truncates_each_stream():
    tools, sandbox = tools_for(allow_processes=True)
    sandbox.processes.page = SimpleNamespace(
        entries=[entry("stdout", "o" * 20_000), entry("stderr", "e" * 20_000)],
        cursor=40_000,
        dropped=False,
        state="running",
    )
    result = tools.read_process_output("proc-1")
    assert "…[10000 bytes truncated]…" in result["stdout"]  # type: ignore[typeddict-item]
    assert "…[10000 bytes truncated]…" in result["stderr"]  # type: ignore[typeddict-item]
    assert result["cursor"] == 40_000  # type: ignore[typeddict-item]


def test_read_process_output_waits_until_the_process_exits(clock: FakeClock):
    tools, sandbox = tools_for(allow_processes=True)
    sandbox.processes.states = ["running", "running", "exited"]
    sandbox.processes.page = SimpleNamespace(
        entries=[entry("stdout", "built\n")], cursor=6, dropped=False, state="exited"
    )
    assert tools.read_process_output("proc-1", wait_s=30) == {
        "stdout": "built\n",
        "stderr": "",
        "cursor": 6,
        "state": "exited",
        "dropped": False,
        "exit_code": 3,
    }
    # The exited status from the wait supplies the exit code; no second get.
    assert sandbox.calls == [("processes.get", "proc-1")] * 3 + [("processes.logs", "proc-1", None)]
    assert clock.sleeps == [1.0, 1.0]


def test_read_process_output_returns_running_when_the_wait_runs_out(clock: FakeClock):
    tools, sandbox = tools_for(allow_processes=True)
    sandbox.processes.states = ["running"]
    result = tools.read_process_output("proc-1", wait_s=2.5)
    assert result["state"] == "running"  # type: ignore[typeddict-item]
    assert "exit_code" not in result
    assert clock.sleeps == [1.0, 1.0, 0.5]
    assert clock.now == 2.5
    assert sandbox.calls[-1] == ("processes.logs", "proc-1", None)


def test_read_process_output_exits_between_the_wait_and_the_logs(clock: FakeClock):
    tools, sandbox = tools_for(allow_processes=True)
    # The wait runs out on running; by the logs call the process has exited.
    sandbox.processes.states = ["running", "running", "exited"]
    sandbox.processes.page = SimpleNamespace(
        entries=[entry("stdout", "late\n")], cursor=5, dropped=False, state="exited"
    )
    result = tools.read_process_output("proc-1", wait_s=1)
    assert result["exit_code"] == 3  # type: ignore[typeddict-item]
    assert sandbox.calls == [
        ("processes.get", "proc-1"),
        ("processes.get", "proc-1"),
        ("processes.logs", "proc-1", None),
        ("processes.get", "proc-1"),
    ]


def test_read_process_output_wait_on_an_expired_status_falls_through_to_logs():
    tools, sandbox = tools_for(allow_processes=True)
    sandbox.processes.gone = True
    sandbox.processes.page = SimpleNamespace(
        entries=[entry("stdout", "end\n")], cursor=4, dropped=False, state="exited"
    )
    assert tools.read_process_output("proc-1", wait_s=10) == {
        "stdout": "end\n",
        "stderr": "",
        "cursor": 4,
        "state": "exited",
        "dropped": False,
    }


@pytest.mark.parametrize(
    "given,expected",
    [(0, 0.0), (-5, 0.0), (None, 0.0), (999, 60.0), ("2", 2.0), (True, 0.0), ("x", 0.0)],
)
def test_read_process_output_coerces_and_clamps_wait(clock: FakeClock, given: Any, expected: float):
    tools, sandbox = tools_for(allow_processes=True)
    sandbox.processes.states = ["running"]
    tools.read_process_output("proc-1", wait_s=given)
    assert clock.now == expected
    if expected == 0:
        assert sandbox.calls == [("processes.logs", "proc-1", None)]


def test_read_process_output_wait_on_an_unknown_process_is_an_error_result():
    tools, _ = tools_for(allow_processes=True)
    assert tools.read_process_output("proc-9", wait_s=5) == {"error": "HTTP 400 process not found"}


def test_unknown_process_ids_are_error_results():
    tools, _ = tools_for(allow_processes=True)
    assert tools.read_process_output("proc-9") == {"error": "HTTP 400 process not found"}
    assert tools.stop_process("proc-9") == {"error": "HTTP 400 process not found"}


def test_stop_process_reports_whether_it_was_signalled():
    tools, sandbox = tools_for(allow_processes=True)
    assert tools.stop_process("proc-1") == {"ok": True}
    assert sandbox.calls == [("processes.kill", "proc-1")]


class AsyncWrapper:
    """Exposes a sync fake's methods as coroutines, keeping its attributes."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._inner, name)
        if not callable(value):
            return value

        async def call(*args: Any, **kwargs: Any) -> Any:
            return value(*args, **kwargs)

        return call


class AsyncFakeSandbox(AsyncWrapper):
    def __init__(self, inner: FakeSandbox) -> None:
        super().__init__(inner)
        self.files = AsyncWrapper(inner.files)
        self.processes = AsyncWrapper(inner.processes)
        self.sandboxes = AsyncWrapper(inner.sandboxes) if inner.sandboxes else None
        self.scope = inner.scope

    def _connection(self) -> AsyncWrapper:
        return AsyncWrapper(self._inner)


def async_tools_for(
    sandbox: FakeSandbox | None = None, **kw: Any
) -> tuple[AsyncSandboxTools, FakeSandbox]:
    sandbox = sandbox or FakeSandbox()
    return AsyncSandboxTools(AsyncFakeSandbox(sandbox), **kw), sandbox  # type: ignore[arg-type]


async def test_async_names_match_the_sync_tools():
    tools, _ = async_tools_for(allow_preview=True, allow_rollback=True, allow_processes=True)
    assert tools.names() == ALL_TOOLS


async def test_async_core_tools():
    tools, sandbox = async_tools_for()
    assert await tools.run_command("ls", timeout_s=0) == {
        "exit_code": 0,
        "stdout": "ok",
        "stderr": "",
    }
    assert sandbox.calls == [("exec", "sh", ["-lc", "ls"], None, 1_000)]
    assert await tools.write_file("a.txt", "hi") == {"bytes_written": 2}
    assert await tools.read_file("a.txt") == {"content": "hi"}
    assert await tools.read_file("nope.txt") == {"error": "HTTP 400 nope.txt: no such file"}


async def test_async_call():
    tools, sandbox = async_tools_for(allow_processes=True)
    assert await tools.call("run_command", {"command": "ls", "timeout_s": 2.5}) == {
        "exit_code": 0,
        "stdout": "ok",
        "stderr": "",
    }
    assert sandbox.calls[-1] == ("exec", "sh", ["-lc", "ls"], None, 2_500)
    assert await tools.call("nope", {}) == {"error": "unknown tool: nope"}
    assert await tools.call("expose_port", {"port": 1}) == {
        "error": "expose_port is not enabled for this agent"
    }
    assert await tools.call("stop_process", {}) == {
        "error": "invalid arguments for stop_process: missing a required argument: 'process_id'"
    }


async def test_async_errors_classify_like_sync():
    tools, sandbox = async_tools_for()
    sandbox.fail = DeadlineExceededError(504, None, None)
    assert await tools.run_command("sleep 5", timeout_s=1) == {
        "error": "command did not finish within 1 s"
    }
    sandbox.fail = api_error(AuthenticationError, "bad key")
    with pytest.raises(AuthenticationError):
        await tools.run_command("ls")


async def test_async_disabled_tools_refuse():
    tools, sandbox = async_tools_for()
    assert await tools.expose_port(3000) == {"error": "expose_port is not enabled for this agent"}
    assert await tools.checkpoint() == {"error": "checkpoint is not enabled for this agent"}
    assert await tools.rollback("snap-1") == {"error": "rollback is not enabled for this agent"}
    assert await tools.start_process("x") == {
        "error": "start_process is not enabled for this agent"
    }
    assert await tools.read_process_output("proc-1") == {
        "error": "read_process_output is not enabled for this agent"
    }
    assert await tools.stop_process("proc-1") == {
        "error": "stop_process is not enabled for this agent"
    }
    assert sandbox.calls == []


async def test_async_preview_checkpoint_and_rollback(clock: FakeClock):
    sandbox = FakeSandbox(snapshot_statuses=["Pending", "Ready"])
    tools, _ = async_tools_for(sandbox, allow_preview=True, allow_rollback=True)
    assert await tools.expose_port(3000) == {"preview_url": "https://3000-x.sandboxes.example"}
    assert await tools.checkpoint("x") == {"checkpoint_id": "snap-1"}
    assert ("get_snapshot", "snap-1", "org-1", "prj-1") in sandbox.calls
    assert clock.sleeps == [2.0]
    assert await tools.rollback("snap-1") == {"ok": True}
    assert await tools.rollback("snap-9") == {"error": "HTTP 400 snapshot not found"}


async def test_async_checkpoint_failed_final_fetch_and_deadline(clock: FakeClock):
    sandbox = FakeSandbox(snapshot_statuses=["Failed"])
    sandbox.snapshot_error = "quota"
    tools, _ = async_tools_for(sandbox, allow_rollback=True)
    assert await tools.checkpoint() == {"error": "checkpoint snap-1 failed: quota"}
    tools, _ = async_tools_for(
        FakeSandbox(snapshot_statuses=["Pending"] * 150 + ["Ready"]), allow_rollback=True
    )
    assert await tools.checkpoint() == {"checkpoint_id": "snap-1"}
    slow = FakeSandbox(snapshot_statuses=["Pending"] * 200)
    slow.fetch_s = 10.0
    tools, _ = async_tools_for(slow, allow_rollback=True)
    assert await tools.checkpoint() == {"error": "checkpoint snap-1 not ready after 300 s"}
    assert sum(1 for c in slow.calls if c[0] == "get_snapshot") == 25


async def test_async_process_tools(clock: FakeClock):
    tools, sandbox = async_tools_for(allow_processes=True)
    assert await tools.start_process("make", cwd="app") == {"process_id": "proc-1"}
    sandbox.processes.states = ["running", "exited"]
    sandbox.processes.page = SimpleNamespace(
        entries=[entry("stdout", "ok\n")], cursor=3, dropped=False, state="exited"
    )
    assert (await tools.read_process_output("proc-1", wait_s=10))["exit_code"] == 3  # type: ignore[typeddict-item]
    assert clock.sleeps == [1.0]
    assert await tools.stop_process("proc-1") == {"ok": True}
    sandbox.fail = RateLimitError(429, {"code": "resource_exhausted", "message": "full"}, None)
    assert await tools.start_process("x") == {"error": "HTTP 429 resource_exhausted full"}
    sandbox.fail = RateLimitError(429, {"message": "slow down"}, None)
    with pytest.raises(RateLimitError):
        await tools.start_process("x")


async def test_async_read_process_output_wait_runs_out_and_status_gone(clock: FakeClock):
    tools, sandbox = async_tools_for(allow_processes=True)
    sandbox.processes.states = ["running"]
    result = await tools.read_process_output("proc-1", cursor=4, wait_s=2)
    assert result["state"] == "running" and "exit_code" not in result  # type: ignore[typeddict-item]
    assert clock.now == 2.0
    sandbox.processes.page = SimpleNamespace(entries=[], cursor=0, dropped=False, state="exited")
    sandbox.processes.gone = True
    assert "exit_code" not in await tools.read_process_output("proc-1")
    assert "exit_code" not in await tools.read_process_output("proc-1", wait_s=5)
    sandbox.processes.gone = False
    sandbox.processes.states = ["exited"]
    assert (await tools.read_process_output("proc-1"))["exit_code"] == 3  # type: ignore[typeddict-item]


TYPE_CASES = [
    ("run_command", {"command": 1}, "command must be string"),
    ("run_command", {"command": None}, "command must be string"),
    ("run_command", {"command": "ls", "cwd": 5}, "cwd must be string"),
    ("run_command", {"command": "ls", "timeout_s": "abc"}, "timeout_s must be number"),
    ("run_command", {"command": "ls", "timeout_s": True}, "timeout_s must be number"),
    ("run_command", {"command": "ls", "timeout_s": [5]}, "timeout_s must be number"),
    ("write_file", {"path": "a", "content": 123}, "content must be string"),
    ("write_file", {"path": "a", "content": None}, "content must be string"),
    ("write_file", {"path": ["a"], "content": "x"}, "path must be string"),
    ("read_file", {"path": 7}, "path must be string"),
    ("expose_port", {"port": "http"}, "port must be integer"),
    ("expose_port", {"port": 80.5}, "port must be integer"),
    ("expose_port", {"port": None}, "port must be integer"),
    ("checkpoint", {"label": 3}, "label must be string"),
    ("rollback", {"checkpoint_id": 1}, "checkpoint_id must be string"),
    ("start_process", {"command": {"x": 1}}, "command must be string"),
    ("read_process_output", {"process_id": 1}, "process_id must be string"),
    ("read_process_output", {"process_id": "p", "cursor": "next"}, "cursor must be integer"),
    ("read_process_output", {"process_id": "p", "cursor": 1.5}, "cursor must be integer"),
    ("read_process_output", {"process_id": "p", "wait_s": float("nan")}, "wait_s must be number"),
    ("stop_process", {"process_id": None}, "process_id must be string"),
]


@pytest.mark.parametrize("name,args,reason", TYPE_CASES)
def test_call_rejects_wrongly_typed_args(name: str, args: dict[str, Any], reason: str):
    tools, sandbox = tools_for(allow_preview=True, allow_rollback=True, allow_processes=True)
    assert tools.call(name, args) == {"error": f"invalid arguments for {name}: {reason}"}
    assert sandbox.calls == []


@pytest.mark.parametrize("name,args,reason", TYPE_CASES[:3])
async def test_async_call_rejects_wrongly_typed_args(name: str, args: dict[str, Any], reason: str):
    tools, sandbox = async_tools_for()
    assert await tools.call(name, args) == {"error": f"invalid arguments for {name}: {reason}"}
    assert sandbox.calls == []


def test_call_accepts_null_optionals_and_parses_integer_strings():
    tools, sandbox = tools_for(allow_preview=True, allow_rollback=True, allow_processes=True)
    assert tools.call("run_command", {"command": "ls", "cwd": None, "timeout_s": None}) == {
        "exit_code": 0,
        "stdout": "ok",
        "stderr": "",
    }
    assert tools.call("checkpoint", {"label": None}) == {"checkpoint_id": "snap-1"}
    assert tools.call("expose_port", {"port": "8080"}) == {
        "preview_url": "https://8080-x.sandboxes.example"
    }
    assert ("get_url", 8080) in sandbox.calls
    tools.call("read_process_output", {"process_id": "proc-1", "cursor": "42", "wait_s": "0"})
    assert sandbox.calls[-1] == ("processes.logs", "proc-1", 42)
    tools.call("read_process_output", {"process_id": "proc-1", "cursor": 7.0})
    assert sandbox.calls[-1] == ("processes.logs", "proc-1", 7)


EDGE_CUT = (
    "the command printed nothing for about 2 minutes and the connection was cut; "
    "it may still be running. Use start_process for long or quiet commands"
)


def edge_timeout() -> Exception:
    # The edge answers 524 with an HTML page, not JSON.
    return error_from_status(524, {"details": "<!DOCTYPE html>\n<html>524</html>"}, None)


def test_run_command_edge_timeout_is_an_error_result():
    tools, sandbox = tools_for()
    sandbox.fail = edge_timeout()
    assert isinstance(sandbox.fail, InternalServerError)
    assert tools.run_command("sleep 150; echo ok", timeout_s=300) == {"error": EDGE_CUT}


async def test_async_run_command_edge_timeout_is_an_error_result():
    tools, sandbox = async_tools_for()
    sandbox.fail = edge_timeout()
    assert await tools.run_command("sleep 150", timeout_s=300) == {"error": EDGE_CUT}


@pytest.mark.parametrize("status", [500, 502, 503, 520, 522])
def test_run_command_other_5xx_still_raise(status: int):
    tools, sandbox = tools_for()
    sandbox.fail = error_from_status(status, None, None)
    with pytest.raises(type(sandbox.fail)):
        tools.run_command("ls")


def test_edge_timeout_outside_run_command_still_raises():
    tools, sandbox = tools_for(allow_processes=True)
    sandbox.fail = edge_timeout()
    with pytest.raises(InternalServerError):
        tools.read_file("missing.txt")
    with pytest.raises(InternalServerError):
        tools.start_process("sleep 1")


def test_dropped_exec_stream_still_raises():
    tools, sandbox = tools_for()
    sandbox.fail = APIConnectionError("Failed to reach the sandbox runtime during stream")
    with pytest.raises(APIConnectionError):
        tools.run_command("echo start; sleep 130")
