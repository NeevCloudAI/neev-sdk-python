"""Tests for the framework-neutral sandbox agent tools."""

from __future__ import annotations

import asyncio
import copy
import dataclasses
import inspect
import json
import pickle
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from neevai import agent_tools
from neevai.agent_tools import (
    _MAX_ERROR_CHARS,
    DESCRIPTIONS,
    FATAL_ERROR,
    FATAL_RESULT,
    PARAMETERS,
    TITLES,
    AsyncSandboxTools,
    FatalGuard,
    SandboxTools,
    ToolSpec,
    _truncate,
)
from neevai.errors import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    BadRequestError,
    DeadlineExceededError,
    InternalServerError,
    NeevAIError,
    NotFoundError,
    RateLimitError,
    error_from_status,
    parse_error_body,
)
from neevai.transport.runtime import RuntimeTransport

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

    def read(self, path: str, offset: int | None = None, length: int | None = None) -> bytes:
        self.sandbox.calls.append(("files.read", path, offset, length))
        if self.sandbox.fail:
            raise self.sandbox.fail
        if path in self.sandbox.raw:
            data = self.sandbox.raw[path]
        elif path in self.sandbox.workspace:
            data = self.sandbox.workspace[path].encode()
        else:
            raise api_error(NotFoundError, f"{path}: no such file")
        start = offset or 0
        return data[start : None if length is None else start + length]

    def stat(self, path: str) -> Any:
        self.sandbox.calls.append(("files.stat", path))
        if self.sandbox.fail:
            raise self.sandbox.fail
        if path in self.sandbox.dirs:
            return SimpleNamespace(
                type="directory", size=4096, modified_time="2026-10-14T09:00:00Z"
            )
        if path not in self.sandbox.workspace:
            raise NotFoundError(404, {"reason_code": "not_found", "message": "no such file"}, None)
        size = len(self.sandbox.workspace[path].encode())
        return SimpleNamespace(type="file", size=size, modified_time="2026-10-14T10:00:00Z")

    def move(self, source: str, destination: str) -> Any:
        self.sandbox.calls.append(("files.move", source, destination))
        if self.sandbox.fail:
            raise self.sandbox.fail
        if source not in self.sandbox.workspace:
            raise api_error(NotFoundError, f"{source}: no such file")
        self.sandbox.workspace[destination] = self.sandbox.workspace.pop(source)
        return SimpleNamespace(type="file")

    def remove(self, path: str, recursive: bool = False) -> None:
        self.sandbox.calls.append(("files.remove", path, recursive))
        if self.sandbox.fail:
            raise self.sandbox.fail
        if path in self.sandbox.dirs:
            if not recursive:
                raise api_error(BadRequestError, f"{path}: directory not empty")
            self.sandbox.dirs.remove(path)
            return
        if path not in self.sandbox.workspace:
            raise api_error(NotFoundError, f"{path}: no such file")
        del self.sandbox.workspace[path]


class FakeProcesses:
    def __init__(self, sandbox: FakeSandbox) -> None:
        self.sandbox = sandbox
        self.page = SimpleNamespace(entries=[], cursor=0, dropped=False, state="running")
        # States get() reports in turn; the last one repeats.
        self.states = ["exited"]
        self.gone = False
        self.listed: list[Any] = []

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

    def list(self) -> list[Any]:
        self.sandbox.calls.append(("processes.list",))
        if self.sandbox.fail:
            raise self.sandbox.fail
        return self.listed

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
        # Files read back as these bytes, for content that is not UTF-8.
        self.raw: dict[str, bytes] = {}
        self.dirs: set[str] = set()
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
    "stat_path",
    "move_path",
    "delete_path",
    "list_processes",
]

SAFE_TOOLS = ["run_command", "write_file", "read_file", "stat_path", "move_path", "delete_path"]
PROCESS_TOOLS = ["start_process", "read_process_output", "stop_process", "list_processes"]
ENABLED_ORDER = [*SAFE_TOOLS, "expose_port", "checkpoint", "rollback", *PROCESS_TOOLS]


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
            "TITLES",
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
            "FATAL_ERROR",
            "FATAL_RESULT",
            "FatalGuard",
            "ToolSpec",
            "StatPathToolResult",
            "MovePathToolResult",
            "DeletePathToolResult",
            "ListProcessesToolResult",
            "ListedProcess",
        ]
    )
    assert not hasattr(agent_tools, "truncate")
    assert not hasattr(agent_tools, "short_error")


def test_descriptions_match_the_shared_fixture():
    # The JS SDK carries a byte-identical copy of this fixture.
    fixture = json.loads((FIXTURES / "agent_tool_descriptions.json").read_text(encoding="utf-8"))
    assert dict(DESCRIPTIONS) == fixture
    assert list(DESCRIPTIONS) == ALL_TOOLS


def test_titles_match_the_shared_fixture():
    fixture = json.loads((FIXTURES / "agent_tool_titles.json").read_text(encoding="utf-8"))
    assert dict(TITLES) == fixture
    assert list(TITLES) == ALL_TOOLS


def test_fixtures_are_the_serialized_metadata():
    # Byte-for-byte, since the JS SDK compares the same files.
    for name, value in (
        ("descriptions", DESCRIPTIONS),
        ("parameters", PARAMETERS),
        ("titles", TITLES),
    ):
        text = (FIXTURES / f"agent_tool_{name}.json").read_text(encoding="utf-8")
        assert text == json.dumps(value, indent=2, ensure_ascii=False) + "\n", name


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


LIST_MUTATIONS = [
    lambda xs: xs.__setitem__(0, "x"),
    lambda xs: xs.__delitem__(0),
    lambda xs: xs.__iadd__(["x"]),
    lambda xs: xs.__imul__(2),
    lambda xs: xs.append("x"),
    lambda xs: xs.extend(["x"]),
    lambda xs: xs.insert(0, "x"),
    lambda xs: xs.pop(),
    lambda xs: xs.remove("command"),
    lambda xs: xs.clear(),
    lambda xs: xs.sort(),
    lambda xs: xs.reverse(),
]

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
    for mapping in (DESCRIPTIONS, PARAMETERS, TITLES, run_command, run_command["properties"]):
        with pytest.raises(TypeError, match="read-only"):
            mutate(mapping)
    assert len(DESCRIPTIONS) == 13 and len(PARAMETERS) == 13 and len(TITLES) == 13
    assert type(run_command["required"]) is not list and isinstance(run_command["required"], list)
    for mutate_list in LIST_MUTATIONS:
        with pytest.raises(TypeError, match="read-only"):
            mutate_list(run_command["required"])
    assert list(run_command["required"]) == ["command"]


def test_descriptions_and_parameters_serialize_as_json():
    assert json.loads(json.dumps(DESCRIPTIONS)) == dict(DESCRIPTIONS)
    assert json.loads(json.dumps(PARAMETERS["run_command"]))["required"] == ["command"]


def test_parameter_schemas_share_no_objects():
    seen: dict[int, str] = {}

    def walk(node: Any, path: str) -> None:
        if isinstance(node, (dict, list)):
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


def test_names_default_to_the_safe_tools():
    tools, _ = tools_for()
    assert tools.names() == SAFE_TOOLS


def test_names_include_opt_in_tools_only_when_enabled():
    tools, _ = tools_for(allow_preview=True, allow_rollback=True, allow_processes=True)
    assert tools.names() == ENABLED_ORDER
    assert tools_for(allow_preview=True)[0].names() == [*SAFE_TOOLS, "expose_port"]
    assert tools_for(allow_rollback=True)[0].names() == [*SAFE_TOOLS, "checkpoint", "rollback"]
    assert tools_for(allow_processes=True)[0].names() == [*SAFE_TOOLS, *PROCESS_TOOLS]


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
    assert tools.run_command("ls") == {"error": "HTTP 400: path is outside the workspace"}


def test_bad_request_error_comes_through_intact():
    tools, sandbox = tools_for()
    sandbox.fail = BadRequestError(
        400,
        {"code": "invalid_argument", "message": 'path "/etc/passwd" escapes workspace root'},
        "req-1",
    )
    assert tools.run_command("ls") == {
        "error": 'HTTP 400 invalid_argument: path "/etc/passwd" escapes workspace root'
    }


def test_api_error_text_leaves_out_request_details():
    tools, sandbox = tools_for()
    sandbox.fail = NotFoundError(
        404,
        {"code": "not_found", "message": "no such file"},
        "req-1",
        request_method="POST",
        request_url="https://api.example/orgs/org-1/projects/prj-1/sandboxes",
    )
    assert "[POST https://" in str(sandbox.fail)
    assert tools.read_file("a.txt") == {"error": "HTTP 404 not_found: no such file"}


def test_api_error_text_falls_back_to_details():
    tools, sandbox = tools_for()
    sandbox.fail = BadRequestError(400, {"details": "<html>bad</html>"}, None)
    assert tools.read_file("a.txt") == {"error": "HTTP 400: <html>bad</html>"}


def _error_fixture() -> dict[str, Any]:
    # The JS SDK carries a byte-identical copy of this fixture.
    fixture: dict[str, Any] = json.loads(
        (FIXTURES / "agent_tool_error_texts.json").read_text(encoding="utf-8")
    )
    return fixture


def _runtime_error_for(case: dict[str, Any]) -> APIError:
    headers = {"content-type": case["content_type"]}
    if "request_id" in case:
        headers["x-request-id"] = case["request_id"]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(case["status"], content=case["body_raw"].encode(), headers=headers)

    transport = RuntimeTransport(
        "https://sbx.example", "key", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(APIError) as caught:
        transport.request("POST", "/v1/files/read", body={})
    return caught.value


@pytest.mark.parametrize("case", _error_fixture()["api_errors"], ids=lambda c: c["name"])
def test_api_error_texts_match_the_shared_fixture(case: dict[str, Any]):
    runtime_error = _runtime_error_for(case)
    assert agent_tools._api_error_text(runtime_error) == case["expected"]
    # The lifecycle transport parses error bodies with the same function.
    lifecycle_error = error_from_status(
        case["status"], parse_error_body(case["body_raw"]), case.get("request_id")
    )
    assert agent_tools._api_error_text(lifecycle_error) == case["expected"]


@pytest.mark.parametrize("case", _error_fixture()["call_errors"], ids=lambda c: c["name"])
def test_call_error_texts_match_the_shared_fixture(case: dict[str, Any]):
    tools, sandbox = tools_for(allow_preview=True, allow_rollback=True, allow_processes=True)
    assert tools.call(case["tool"], case["args"]) == {"error": case["expected"]}
    assert sandbox.calls == []


def test_error_fixture_covers_the_agreed_cases():
    fixture = _error_fixture()
    assert len(fixture["api_errors"]) >= 25
    assert len(fixture["call_errors"]) >= 50
    assert all(
        set(c) >= {"name", "status", "content_type", "body_raw", "expected"}
        for c in fixture["api_errors"]
    )
    assert all(set(c) == {"name", "tool", "args", "expected"} for c in fixture["call_errors"])


def test_schema_lists_copy_deepcopy_and_pickle_to_plain_objects():
    schema = PARAMETERS["run_command"]
    for clone in (copy.deepcopy(schema), pickle.loads(pickle.dumps(schema))):
        assert type(clone) is dict
        assert type(clone["required"]) is list
        assert type(clone["properties"]["command"]) is dict
        clone["required"].append("cwd")
        clone["properties"]["command"]["type"] = "x"
        assert clone != schema
    shallow = copy.copy(schema)
    assert type(shallow) is dict and shallow == schema
    assert type(copy.copy(schema["required"])) is list
    for clone_list in (
        copy.deepcopy(schema["required"]),
        pickle.loads(pickle.dumps(schema["required"])),
    ):
        assert type(clone_list) is list and clone_list == ["command"]
    assert type(copy.deepcopy(PARAMETERS)) is dict
    assert type(pickle.loads(pickle.dumps(DESCRIPTIONS))) is dict
    assert list(PARAMETERS["run_command"]["required"]) == ["command"]


def test_schemas_are_valid_json_schema():
    jsonschema = pytest.importorskip("jsonschema")
    for schema in PARAMETERS.values():
        jsonschema.Draft202012Validator.check_schema(schema)


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
    assert result == {"error": "not UTF-8 text"}


def test_write_then_read_round_trips():
    tools, _ = tools_for()
    assert tools.write_file("a.txt", "héllo") == {"bytes_written": 6}
    assert tools.read_file("a.txt") == {"content": "héllo"}


def test_read_missing_file_is_an_error_result():
    tools, _ = tools_for()
    assert tools.read_file("nope.txt") == {"error": "HTTP 400: nope.txt: no such file"}


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
    assert tools.list_processes() == {"error": "list_processes is not enabled for this agent"}
    assert tools.call("list_processes") == {"error": "list_processes is not enabled for this agent"}
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
        ("run_command", {}, 'missing a required argument: "command"'),
        (
            "run_command",
            {"command": "ls", "shell": "bash"},
            'got an unexpected keyword argument "shell"',
        ),
        ("write_file", {"path": "a.txt"}, 'missing a required argument: "content"'),
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
    assert tools.rollback("snap-9") == {"error": "HTTP 400: snapshot not found"}


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
    assert tools.start_process("sleep 1") == {"error": f"HTTP 429 resource_exhausted: {message}"}


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
    assert tools.read_process_output("proc-9", wait_s=5) == {"error": "HTTP 400: process not found"}


def test_unknown_process_ids_are_error_results():
    tools, _ = tools_for(allow_processes=True)
    assert tools.read_process_output("proc-9") == {"error": "HTTP 400: process not found"}
    assert tools.stop_process("proc-9") == {"error": "HTTP 400: process not found"}


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
    assert tools.names() == ENABLED_ORDER


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
    assert await tools.read_file("nope.txt") == {"error": "HTTP 400: nope.txt: no such file"}


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
        "error": 'invalid arguments for stop_process: missing a required argument: "process_id"'
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
    assert await tools.list_processes() == {"error": "list_processes is not enabled for this agent"}
    assert sandbox.calls == []


async def test_async_preview_checkpoint_and_rollback(clock: FakeClock):
    sandbox = FakeSandbox(snapshot_statuses=["Pending", "Ready"])
    tools, _ = async_tools_for(sandbox, allow_preview=True, allow_rollback=True)
    assert await tools.expose_port(3000) == {"preview_url": "https://3000-x.sandboxes.example"}
    assert await tools.checkpoint("x") == {"checkpoint_id": "snap-1"}
    assert ("get_snapshot", "snap-1", "org-1", "prj-1") in sandbox.calls
    assert clock.sleeps == [2.0]
    assert await tools.rollback("snap-1") == {"ok": True}
    assert await tools.rollback("snap-9") == {"error": "HTTP 400: snapshot not found"}


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
    assert await tools.start_process("x") == {"error": "HTTP 429 resource_exhausted: full"}
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
    ("read_file", {"path": "a", "offset": "start"}, "offset must be integer"),
    ("read_file", {"path": "a", "length": 2.5}, "length must be integer"),
    ("stat_path", {"path": None}, "path must be string"),
    ("move_path", {"source": "a", "destination": 1}, "destination must be string"),
    ("delete_path", {"path": "a", "recursive": "true"}, "recursive must be boolean"),
    ("delete_path", {"path": "a", "recursive": 1}, "recursive must be boolean"),
    ("delete_path", {"path": "a", "recursive": 0}, "recursive must be boolean"),
    ("delete_path", {"path": "a", "recursive": [True]}, "recursive must be boolean"),
    ("list_processes", {"all": True}, 'got an unexpected keyword argument "all"'),
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


@pytest.mark.parametrize(
    "given,expected_ms",
    [
        ("٣٠", 60_000),  # Arabic-Indic digits are not ASCII
        (" 30", 60_000),  # a no-break space is not stripped
        ("\t30\n", 30_000),
        ("\v\f 30 \r", 30_000),
        (1.0625, 1_063),  # half up, not half to even
        (2.5005, 2_501),
    ],
)
def test_numbers_are_ascii_and_round_half_up(given: Any, expected_ms: int):
    tools, sandbox = tools_for()
    tools.run_command("ls", timeout_s=given)
    assert sandbox.calls[0][4] == expected_ms


def test_call_quotes_key_names_as_json_and_caps_the_text():
    tools, sandbox = tools_for()
    assert tools.call("read_file", {"path": "a", 'we"ird': 1}) == {
        "error": 'invalid arguments for read_file: got an unexpected keyword argument "we\\"ird"'
    }
    long_key = "k" * 1_000
    result = tools.call("read_file", {"path": "a", long_key: 1})
    assert len(result["error"]) == 501  # type: ignore[typeddict-item]
    assert result["error"].endswith("…")  # type: ignore[typeddict-item]
    result = tools.call("x" * 1_000, {})
    assert len(result["error"]) == 501  # type: ignore[typeddict-item]
    assert sandbox.calls == []


def test_call_reports_unknown_keys_before_missing_ones():
    tools, _ = tools_for()
    assert tools.call("write_file", {"bogus": 1}) == {
        "error": 'invalid arguments for write_file: got an unexpected keyword argument "bogus"'
    }
    assert tools.call("write_file", {"content": 1}) == {
        "error": 'invalid arguments for write_file: missing a required argument: "path"'
    }


def test_truncation_keeps_a_leading_bom():
    # The JS SDK keeps it too: the BOM is content, 3 bytes of the 4,000-byte head.
    text = "\ufeff" + "a" * 20_000
    cut = _truncate(text)
    assert cut.startswith("\ufeff" + "a" * 3_997 + "\n…[")
    tools, sandbox = tools_for()
    sandbox.workspace["bom.txt"] = text
    assert tools.read_file("bom.txt") == {"content": cut}


def test_titles_are_read_only_and_cover_every_tool():
    assert set(TITLES) == set(DESCRIPTIONS) == set(PARAMETERS)
    assert all(TITLES[name] for name in ALL_TOOLS)
    with pytest.raises(TypeError, match="read-only"):
        TITLES["run_command"] = "x"  # type: ignore[index]
    assert copy.deepcopy(TITLES) == dict(TITLES)


def paged(text: bytes | str, **args: Any) -> Any:
    tools, sandbox = tools_for()
    sandbox.raw["f.txt"] = text.encode() if isinstance(text, str) else text
    return tools.call("read_file", {"path": "f.txt", **args})


def test_read_file_pages_with_offset_and_length():
    tools, sandbox = tools_for()
    sandbox.workspace["f.txt"] = "abcdefghij"
    assert tools.read_file("f.txt", offset=2, length=3) == {
        "content": "cde",
        "next_offset": 5,
        "eof": False,
    }
    # Seven bytes past the window let a page finish a character and still see eof.
    assert sandbox.calls == [("files.read", "f.txt", 2, 10)]
    assert tools.read_file("f.txt", offset=5, length=5) == {
        "content": "fghij",
        "next_offset": 10,
        "eof": True,
    }


def test_read_file_offset_alone_reads_10000_bytes():
    tools, sandbox = tools_for()
    sandbox.workspace["big.log"] = "x" * 25_000
    result = tools.call("read_file", {"path": "big.log", "offset": 0})
    assert result == {"content": "x" * 10_000, "next_offset": 10_000, "eof": False}
    assert sandbox.calls[-1] == ("files.read", "big.log", 0, 10_007)
    assert tools.call("read_file", {"path": "big.log", "offset": "20000"}) == {
        "content": "x" * 5_000,
        "next_offset": 25_000,
        "eof": True,
    }


def test_read_file_length_alone_starts_at_zero():
    assert paged("hello", length=2) == {"content": "he", "next_offset": 2, "eof": False}


@pytest.mark.parametrize(
    "length,read_size",
    [(50_000, 10_007), (0, 8), (-7, 8), ("5", 12)],
)
def test_read_file_clamps_length(length: Any, read_size: int):
    tools, sandbox = tools_for()
    sandbox.workspace["f.txt"] = "abc"
    tools.call("read_file", {"path": "f.txt", "length": length})
    assert sandbox.calls[-1] == ("files.read", "f.txt", 0, read_size)


def test_read_file_negative_offset_reads_from_the_start():
    tools, sandbox = tools_for()
    sandbox.workspace["f.txt"] = "abc"
    assert tools.call("read_file", {"path": "f.txt", "offset": -4, "length": 2}) == {
        "content": "ab",
        "next_offset": 2,
        "eof": False,
    }
    assert sandbox.calls[-1] == ("files.read", "f.txt", 0, 9)


def test_read_file_skips_a_split_character_at_the_start():
    # "é" is 2 bytes and "€" 3; offset 1 lands inside "é".
    assert paged("é€x", offset=1, length=5) == {"content": "€x", "next_offset": 6, "eof": True}
    assert paged("é€x", offset=3, length=1) == {"content": "x", "next_offset": 6, "eof": True}


def test_read_file_backs_off_a_split_character_at_the_end():
    assert paged("aé€", offset=0, length=4) == {"content": "aé", "next_offset": 3, "eof": False}
    assert paged("aé€", offset=3, length=3) == {"content": "€", "next_offset": 6, "eof": True}
    assert paged("a\U0001f600b", length=3) == {"content": "a", "next_offset": 1, "eof": False}


def test_read_file_pages_cover_the_file_exactly_once():
    text = "héllo wörld, €100 \U0001f600 done" * 50
    pieces, offset, eof = [], 0, False
    for _ in range(len(text.encode())):
        if eof:
            break
        result = paged(text, offset=offset, length=7)
        pieces.append(result["content"])
        offset, eof = result["next_offset"], result["eof"]
    assert eof
    assert "".join(pieces) == text


def test_read_file_offset_past_the_end_is_eof():
    assert paged("abc", offset=3) == {"content": "", "next_offset": 3, "eof": True}
    assert paged("abc", offset=99, length=5) == {"content": "", "next_offset": 99, "eof": True}


def test_read_file_paged_bad_utf8_is_an_error_result():
    assert paged(b"ab\xffcd", offset=0, length=10) == {"error": "not UTF-8 text"}
    # A character cut by the real end of the file is not backed off.
    assert paged(b"ab\xe2\x82", offset=0, length=10) == {"error": "not UTF-8 text"}


def test_read_file_paged_missing_file_is_an_error_result():
    tools, _ = tools_for()
    assert tools.read_file("nope.txt", offset=0) == {"error": "HTTP 400: nope.txt: no such file"}


def test_read_file_null_paging_args_keep_the_whole_file_read():
    tools, sandbox = tools_for()
    sandbox.workspace["big.log"] = "x" * 50_000
    result = tools.call("read_file", {"path": "big.log", "offset": None, "length": None})
    assert set(result) == {"content"}
    assert "…[40000 bytes truncated]…" in result["content"]  # type: ignore[typeddict-item]
    assert not any(c[0] == "files.read" for c in sandbox.calls)


def test_stat_path_reports_files_directories_and_missing_paths():
    tools, sandbox = tools_for()
    sandbox.workspace["a.txt"] = "héllo"
    sandbox.dirs.add("src")
    assert tools.call("stat_path", {"path": "a.txt"}) == {
        "exists": True,
        "type": "file",
        "size": 6,
        "modified_time": "2026-10-14T10:00:00Z",
    }
    assert tools.stat_path("src")["type"] == "directory"  # type: ignore[typeddict-item]
    assert tools.stat_path("missing") == {"exists": False}


def test_stat_path_other_errors_follow_the_usual_rules():
    tools, sandbox = tools_for()
    sandbox.fail = api_error(BadRequestError, "path escapes /workspace")
    assert tools.stat_path("../etc") == {"error": "HTTP 400: path escapes /workspace"}
    sandbox.fail = api_error(AuthenticationError, "bad key")
    with pytest.raises(AuthenticationError):
        tools.stat_path("a")


def test_move_path_moves_and_reports_errors():
    tools, sandbox = tools_for()
    sandbox.workspace["a.txt"] = "x"
    assert tools.call("move_path", {"source": "a.txt", "destination": "b/c.txt"}) == {"ok": True}
    assert sandbox.workspace == {"b/c.txt": "x"}
    assert sandbox.calls == [("files.move", "a.txt", "b/c.txt")]
    assert tools.move_path("a.txt", "d.txt") == {"error": "HTTP 400: a.txt: no such file"}
    assert tools.call("move_path", {"source": "a.txt"}) == {
        "error": 'invalid arguments for move_path: missing a required argument: "destination"'
    }


def test_delete_path_needs_recursive_for_a_directory():
    tools, sandbox = tools_for()
    sandbox.workspace["a.txt"] = "x"
    sandbox.dirs.add("build")
    assert tools.call("delete_path", {"path": "a.txt"}) == {"ok": True}
    assert tools.call("delete_path", {"path": "build", "recursive": None}) == {
        "error": "HTTP 400: build: directory not empty"
    }
    assert tools.call("delete_path", {"path": "build", "recursive": True}) == {"ok": True}
    assert tools.delete_path("a.txt") == {"error": "HTTP 400: a.txt: no such file"}
    assert [c for c in sandbox.calls if c[0] == "files.remove"] == [
        ("files.remove", "a.txt", False),
        ("files.remove", "build", False),
        ("files.remove", "build", True),
        ("files.remove", "a.txt", False),
    ]


@pytest.mark.parametrize("recursive", ["true", "false", 1, [True]])
def test_delete_path_direct_call_treats_only_true_as_recursive(recursive: Any):
    tools, sandbox = tools_for()
    sandbox.dirs.add("build")
    assert "error" in tools.delete_path("build", recursive=recursive)  # type: ignore[operator]
    assert sandbox.calls[-1] == ("files.remove", "build", False)


def process(name: str, args: list[str], state: str, exit_code: int | None = None) -> Any:
    return SimpleNamespace(
        process_id=f"proc-{len(args)}", name=name, args=args, state=state, exit_code=exit_code
    )


def test_list_processes_shows_the_command_the_model_started():
    tools, sandbox = tools_for(allow_processes=True)
    sandbox.processes.listed = [
        process("sh", ["-lc", "npm run dev -- --port 3000"], "running"),
        process("python3", ["-m", "http.server"], "exited", 0),
        process("sh", ["-c", "true"], "exited", None),
    ]
    assert tools.call("list_processes", {}) == {
        "processes": [
            {"process_id": "proc-2", "command": "npm run dev -- --port 3000", "state": "running"},
            {
                "process_id": "proc-2",
                "command": "python3 -m http.server",
                "state": "exited",
                "exit_code": 0,
            },
            {"process_id": "proc-2", "command": "sh -c true", "state": "exited", "exit_code": None},
        ]
    }
    sandbox.processes.listed = []
    assert tools.list_processes() == {"processes": []}


def test_list_processes_errors_follow_the_usual_rules():
    tools, sandbox = tools_for(allow_processes=True)
    sandbox.fail = error_from_status(503, None, None)
    with pytest.raises(type(sandbox.fail)):
        tools.list_processes()


async def test_async_file_tools():
    tools, sandbox = async_tools_for()
    sandbox.workspace["a.txt"] = "aé€"
    sandbox.dirs.add("build")
    assert await tools.read_file("a.txt", offset=0, length=4) == {
        "content": "aé",
        "next_offset": 3,
        "eof": False,
    }
    # A window too short for one whole character grows to hold it.
    assert await tools.call("read_file", {"path": "a.txt", "offset": 1, "length": 1}) == {
        "content": "é",
        "next_offset": 3,
        "eof": False,
    }
    assert await tools.stat_path("a.txt") == {
        "exists": True,
        "type": "file",
        "size": 6,
        "modified_time": "2026-10-14T10:00:00Z",
    }
    assert await tools.stat_path("nope") == {"exists": False}
    assert await tools.move_path("a.txt", "b.txt") == {"ok": True}
    assert await tools.move_path("a.txt", "b.txt") == {"error": "HTTP 400: a.txt: no such file"}
    assert await tools.call("delete_path", {"path": "build"}) == {
        "error": "HTTP 400: build: directory not empty"
    }
    assert await tools.call("delete_path", {"path": "build", "recursive": True}) == {"ok": True}
    assert await tools.call("delete_path", {"path": "b", "recursive": "yes"}) == {
        "error": "invalid arguments for delete_path: recursive must be boolean"
    }


async def test_async_list_processes():
    tools, sandbox = async_tools_for(allow_processes=True)
    sandbox.processes.listed = [process("sh", ["-lc", "make"], "exited", 2)]
    assert await tools.call("list_processes") == {
        "processes": [
            {"process_id": "proc-2", "command": "make", "state": "exited", "exit_code": 2}
        ]
    }


@pytest.mark.parametrize("text", ["€uro", "\U0001f600a", "a€\U0001f600é"])
@pytest.mark.parametrize("length", [1, 2, 3])
def test_read_file_short_pages_always_advance(text: str, length: int):
    pieces, offset, eof = [], 0, False
    for _ in range(len(text.encode())):
        if eof:
            break
        result = paged(text, offset=offset, length=length)
        assert result["next_offset"] > offset
        pieces.append(result["content"])
        offset, eof = result["next_offset"], result["eof"]
    assert eof
    assert "".join(pieces) == text


def test_read_file_grows_a_page_to_one_whole_character():
    assert paged("€uro", length=1) == {"content": "€", "next_offset": 3, "eof": False}
    assert paged("\U0001f600a", offset=1, length=1) == {
        "content": "a",
        "next_offset": 5,
        "eof": True,
    }


def test_read_file_skips_at_most_three_continuation_bytes():
    assert paged(b"\x80\x80\x80a", offset=0) == {"content": "a", "next_offset": 4, "eof": True}
    assert paged(b"\x80\x80\x80\x80a", offset=0) == {"error": "not UTF-8 text"}


def test_read_file_invalid_lead_byte_is_not_utf8():
    assert paged(b"a\xf8\x80\x80\x80b", length=2) == {"error": "not UTF-8 text"}
    assert paged(b"\xf8\x80\x80\x80b", length=1) == {"error": "not UTF-8 text"}


@pytest.mark.parametrize(
    "body",
    [{"message": "route not found"}, {"code": "not_found"}, {"reason_code": "no_route"}],
)
def test_stat_path_404_without_the_runtime_envelope_is_an_error(body: dict[str, Any]):
    tools, sandbox = tools_for()
    sandbox.fail = NotFoundError(404, body, None)
    assert tools.stat_path("a.txt")["error"].startswith("HTTP 404")  # type: ignore[typeddict-item]


async def test_async_stat_path_404_without_the_runtime_envelope_is_an_error():
    tools, sandbox = async_tools_for()
    assert await tools.stat_path("nope") == {"exists": False}
    sandbox.fail = NotFoundError(404, {"message": "route not found"}, None)
    assert await tools.stat_path("nope") == {"error": "HTTP 404: route not found"}


async def test_async_read_file_short_pages_always_advance():
    tools, sandbox = async_tools_for()
    sandbox.raw["f.txt"] = "€uro".encode()
    assert await tools.read_file("f.txt", length=1) == {
        "content": "€",
        "next_offset": 3,
        "eof": False,
    }
    sandbox.raw["f.txt"] = b"\x80\x80\x80\x80a"
    assert await tools.read_file("f.txt", offset=0) == {"error": "not UTF-8 text"}
    sandbox.dirs.add("build")
    assert "error" in await tools.delete_path("build", recursive="true")  # type: ignore[arg-type,operator]
    assert sandbox.calls[-1] == ("files.remove", "build", False)


def test_stat_path_404_with_only_a_code_is_an_error():
    # Only the runtime's reason_code counts; the JS SDK applies the same rule.
    tools, sandbox = tools_for()
    sandbox.fail = NotFoundError(404, {"code": "not_found"}, None)
    assert tools.stat_path("a.txt") == {"error": "HTTP 404 not_found"}


async def test_async_stat_path_404_with_only_a_code_is_an_error():
    tools, sandbox = async_tools_for()
    sandbox.fail = NotFoundError(404, {"code": "not_found"}, None)
    assert await tools.stat_path("a.txt") == {"error": "HTTP 404 not_found"}


@pytest.mark.parametrize(
    "options,names",
    [
        ({}, SAFE_TOOLS),
        ({"allow_processes": True}, [*SAFE_TOOLS, *PROCESS_TOOLS]),
        ({"allow_preview": True, "allow_rollback": True, "allow_processes": True}, ENABLED_ORDER),
    ],
)
def test_specs_follow_names_and_carry_the_shared_metadata(
    options: dict[str, Any], names: list[str]
):
    tools, _ = tools_for(**options)
    specs = tools.specs()
    assert [s.name for s in specs] == names == tools.names()
    for spec in specs:
        assert spec.title == TITLES[spec.name]
        assert spec.description == DESCRIPTIONS[spec.name]
        assert spec.parameters is PARAMETERS[spec.name]


def test_spec_call_routes_to_its_tool():
    tools, sandbox = tools_for(allow_rollback=True)
    by_name = {s.name: s for s in tools.specs()}
    assert by_name["write_file"].call({"path": "a.txt", "content": "hi"}) == {"bytes_written": 2}
    assert sandbox.workspace == {"a.txt": "hi"}
    assert by_name["checkpoint"].call(None) == {"checkpoint_id": "snap-1"}
    assert by_name["read_file"].call({}) == {
        "error": 'invalid arguments for read_file: missing a required argument: "path"'
    }
    with pytest.raises(dataclasses.FrozenInstanceError):
        by_name["read_file"].name = "x"  # type: ignore[misc]


async def test_async_spec_call_is_a_coroutine():
    tools, sandbox = async_tools_for(allow_processes=True)
    specs = tools.specs()
    assert [s.name for s in specs] == [*SAFE_TOOLS, *PROCESS_TOOLS]
    assert specs[0].parameters is PARAMETERS["run_command"]
    assert await specs[0].call({"command": "ls"}) == {"exit_code": 0, "stdout": "ok", "stderr": ""}
    assert sandbox.calls == [("exec", "sh", ["-lc", "ls"], None, 60_000)]


def test_fatal_result_is_a_fixed_read_only_error():
    assert FATAL_ERROR == "The sandbox call failed and the run is stopping."
    assert FATAL_RESULT == {"error": FATAL_ERROR}
    with pytest.raises(TypeError, match="read-only"):
        FATAL_RESULT["error"] = "x"  # type: ignore[typeddict-readonly-mutated]
    assert (
        json.dumps(FATAL_RESULT) == '{"error": "The sandbox call failed and the run is stopping."}'
    )


def failing_spec(error: Exception, calls: list[Any]) -> ToolSpec[Any]:
    def call(args: Any) -> Any:
        calls.append(args)
        raise error

    return ToolSpec("run_command", "t", "d", PARAMETERS["run_command"], call)


def test_guard_passes_results_through_while_clean():
    guard = FatalGuard()
    tools, _ = tools_for()
    spec = tools.specs()[0]
    assert guard.call(spec, {"command": "ls"}) == {"exit_code": 0, "stdout": "ok", "stderr": ""}
    assert guard.call(spec, {}) == {
        "error": 'invalid arguments for run_command: missing a required argument: "command"'
    }
    assert not guard.failed and guard.error is None
    guard.raise_if_failed()


def test_guard_keeps_the_first_failure_and_stops_further_calls():
    guard = FatalGuard()
    calls: list[Any] = []
    first = AuthenticationError(401, {"message": "https://api.example/orgs/org-1 denied"}, None)
    assert guard.call(failing_spec(first, calls), {"command": "ls"}) is FATAL_RESULT
    assert guard.failed and guard.error is first
    assert guard.call(failing_spec(RuntimeError("second"), calls), {}) is FATAL_RESULT
    assert calls == [{"command": "ls"}]
    assert guard.error is first
    with pytest.raises(AuthenticationError) as raised:
        guard.raise_if_failed()
    assert raised.value is first


async def test_guard_acall_matches_call():
    guard = FatalGuard()
    tools, sandbox = async_tools_for()
    spec = tools.specs()[0]
    assert (await guard.acall(spec, {"command": "ls"}))["exit_code"] == 0  # type: ignore[typeddict-item]
    guard.raise_if_failed()
    sandbox.fail = error_from_status(503, None, None)
    assert await guard.acall(spec, {"command": "ls"}) is FATAL_RESULT
    assert await guard.acall(spec, {"command": "ls"}) is FATAL_RESULT
    assert sum(1 for c in sandbox.calls if c[0] == "exec") == 2
    with pytest.raises(type(sandbox.fail)):
        guard.raise_if_failed()


async def test_guard_does_not_swallow_cancellation():
    guard = FatalGuard()

    async def cancelled(args: Any) -> Any:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await guard.acall(
            ToolSpec("run_command", "t", "d", PARAMETERS["run_command"], cancelled), {}
        )
    assert not guard.failed
