"""Tests for the agent-framework adapters over the sandbox agent tools."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import AsyncIterator
from typing import Any

import pytest

from neevai.agent_tools import FATAL_RESULT, PARAMETERS, TITLES
from neevai.errors import AuthenticationError
from tests.test_agent_tools import ENABLED_ORDER, SAFE_TOOLS, api_error, tools_for

ALL_OPTIONS = {"allow_preview": True, "allow_rollback": True, "allow_processes": True}


def plain(value: Any) -> Any:
    return json.loads(json.dumps(value))


class TestClaudeAgentSdk:
    sdk = pytest.importorskip("claude_agent_sdk")

    @pytest.fixture
    def served(self, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
        from neevai.agent_tools import claude as adapter

        captured: dict[str, Any] = {}

        def fake_server(**kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {"type": "sdk", "name": kwargs["name"]}

        monkeypatch.setattr(adapter, "create_sdk_mcp_server", fake_server)
        return captured

    def test_options_give_claude_only_the_sandbox_tools(self, served: dict[str, Any]):
        from neevai.agent_tools.claude import to_claude

        tools, _ = tools_for(**ALL_OPTIONS)
        options = to_claude(tools).options()
        assert options == {
            "tools": [],
            "mcp_servers": {"neev": {"type": "sdk", "name": "neev"}},
            "strict_mcp_config": True,
            "allowed_tools": [f"mcp__neev__{n}" for n in ENABLED_ORDER],
            "setting_sources": [],
            "permission_mode": "dontAsk",
        }
        assert [t.name for t in served["tools"]] == ENABLED_ORDER
        for sdk_tool in served["tools"]:
            assert sdk_tool.input_schema == plain(PARAMETERS[sdk_tool.name])
            assert sdk_tool.input_schema is not PARAMETERS[sdk_tool.name]
            assert sdk_tool.annotations is not None
            assert sdk_tool.annotations.title == TITLES[sdk_tool.name]

    def test_each_options_call_builds_a_fresh_server_sharing_one_guard(self):
        from neevai.agent_tools.claude import to_claude

        claude = to_claude(tools_for()[0])
        first, second = claude.options(), claude.options()
        assert first["mcp_servers"]["neev"] is not second["mcp_servers"]["neev"]
        assert first["mcp_servers"]["neev"]["instance"] is not None

    def test_options_build_real_claude_agent_options(self):
        from neevai.agent_tools.claude import to_claude

        tools, _ = tools_for()
        options = self.sdk.ClaudeAgentOptions(**to_claude(tools).options(), max_turns=3)
        assert options.mcp_servers["neev"]["type"] == "sdk"
        assert options.allowed_tools == [f"mcp__neev__{n}" for n in SAFE_TOOLS]

    async def test_handlers_return_json_text_and_flag_only_the_fatal_result(
        self, served: dict[str, Any]
    ):
        from neevai.agent_tools.claude import to_claude

        tools, sandbox = tools_for()
        claude = to_claude(tools)
        claude.options()
        handlers = {t.name: t.handler for t in served["tools"]}
        assert await handlers["run_command"]({"command": "ls"}) == {
            "content": [
                {"type": "text", "text": json.dumps({"exit_code": 0, "stdout": "ok", "stderr": ""})}
            ],
            "is_error": False,
        }
        missing = await handlers["read_file"]({"path": "nope.txt"})
        assert missing["is_error"] is False
        assert json.loads(missing["content"][0]["text"]) == {
            "error": "HTTP 400: nope.txt: no such file"
        }
        sandbox.fail = api_error(AuthenticationError, "https://api.example/orgs/org-1")
        fatal = await handlers["run_command"]({"command": "ls"})
        assert fatal == {
            "content": [{"type": "text", "text": json.dumps(FATAL_RESULT)}],
            "is_error": True,
        }
        assert claude.guard.failed and isinstance(claude.guard.error, AuthenticationError)

    def messages(self, *items: Any) -> AsyncIterator[Any]:
        async def stream() -> AsyncIterator[Any]:
            for item in items:
                yield item

        return stream()

    def assistant(self, *tool_names: str) -> Any:
        blocks = [
            self.sdk.ToolUseBlock(id=f"t{i}", name=n, input={}) for i, n in enumerate(tool_names)
        ]
        return self.sdk.AssistantMessage(content=blocks, model="m")

    async def test_watch_yields_every_message_of_a_clean_run(self, served: dict[str, Any]):
        from neevai.agent_tools.claude import to_claude

        claude = to_claude(tools_for()[0])
        first = self.assistant("mcp__neev__run_command")
        seen = [m async for m in claude.watch(self.messages(first, "result"))]
        assert seen == [first, "result"]

    async def test_watch_stops_after_a_fatal_call_and_raises_it(self, served: dict[str, Any]):
        from neevai.agent_tools.claude import to_claude

        tools, sandbox = tools_for()
        claude = to_claude(tools)
        claude.options()
        handler = served["tools"][0].handler
        seen: list[Any] = []
        with pytest.raises(AuthenticationError):
            async for message in claude.watch(self.messages("one", "two", "three")):
                seen.append(message)
                if message == "one":
                    sandbox.fail = api_error(AuthenticationError, "bad key")
                    await handler({"command": "ls"})
        assert seen == ["one"]

    async def test_watch_rejects_host_tools(self, served: dict[str, Any]):
        from neevai.agent_tools.claude import to_claude

        claude = to_claude(tools_for()[0])
        stream = self.messages(self.assistant("mcp__neev__read_file", "Bash", "mcp__other__x"))
        with pytest.raises(RuntimeError, match=r"^host tools were used: Bash, mcp__other__x$"):
            async for _ in claude.watch(stream):
                pass


class TestOpenAIAgents:
    agents = pytest.importorskip("agents")

    def test_function_tools_mirror_the_specs(self):
        from neevai.agent_tools.openai_agents import to_openai_agents

        built = to_openai_agents(tools_for(**ALL_OPTIONS)[0])
        assert [t.name for t in built] == ENABLED_ORDER
        for t in built:
            assert isinstance(t, self.agents.FunctionTool)
            assert t.strict_json_schema is False
            assert t.params_json_schema == plain(PARAMETERS[t.name])

    async def test_invoke_returns_json_text(self):
        from neevai.agent_tools.openai_agents import to_openai_agents

        run_command = to_openai_agents(tools_for()[0])[0]
        out = await run_command.on_invoke_tool(None, '{"command": "ls"}')  # type: ignore[arg-type]
        assert json.loads(out) == {"exit_code": 0, "stdout": "ok", "stderr": ""}
        out = await run_command.on_invoke_tool(None, "")  # type: ignore[arg-type]
        assert json.loads(out) == {
            "error": 'invalid arguments for run_command: missing a required argument: "command"'
        }

    async def test_invoke_reports_non_json_arguments(self):
        from neevai.agent_tools.openai_agents import to_openai_agents

        read_file = to_openai_agents(tools_for()[0])[2]
        out = await read_file.on_invoke_tool(None, "{path: a.txt")  # type: ignore[arg-type]
        assert json.loads(out) == {"error": "invalid arguments for read_file: not JSON"}

    async def test_invoke_lets_fatal_errors_propagate(self):
        from neevai.agent_tools.openai_agents import to_openai_agents

        tools, sandbox = tools_for()
        sandbox.fail = api_error(AuthenticationError, "bad key")
        with pytest.raises(AuthenticationError):
            await to_openai_agents(tools)[0].on_invoke_tool(None, '{"command": "ls"}')  # type: ignore[arg-type]

    async def test_runner_stops_on_a_fatal_call_instead_of_retrying(self):
        from agents import Agent, ModelResponse, RunConfig, Runner, Usage
        from agents.models.interface import Model
        from openai.types.responses import ResponseFunctionToolCall

        from neevai.agent_tools.openai_agents import to_openai_agents

        class ToolCallingModel(Model):
            calls = 0

            async def get_response(self, *args: Any, **kwargs: Any) -> ModelResponse:
                type(self).calls += 1
                call = ResponseFunctionToolCall(
                    type="function_call",
                    call_id=f"c{self.calls}",
                    name="run_command",
                    arguments='{"command": "ls"}',
                )
                return ModelResponse(output=[call], usage=Usage(), response_id=None)

            def stream_response(self, *args: Any, **kwargs: Any) -> Any:
                raise NotImplementedError

        tools, sandbox = tools_for()
        sandbox.fail = api_error(AuthenticationError, "bad key")
        agent = Agent(name="t", tools=to_openai_agents(tools), model=ToolCallingModel())
        with pytest.raises(self.agents.exceptions.UserError) as raised:
            await Runner.run(agent, "go", max_turns=5, run_config=RunConfig(tracing_disabled=True))
        # The run ends at the first fatal call rather than handing it back to the model.
        assert isinstance(raised.value.__cause__, AuthenticationError)
        assert ToolCallingModel.calls == 1


class TestLangChain:
    tools_module = pytest.importorskip("langchain_core.tools")

    def test_structured_tools_mirror_the_specs(self):
        from neevai.agent_tools.langchain import to_langchain

        built = to_langchain(tools_for(**ALL_OPTIONS)[0])
        assert [t.name for t in built] == ENABLED_ORDER
        for t in built:
            assert isinstance(t, self.tools_module.StructuredTool)
            assert t.args_schema == plain(PARAMETERS[t.name])
            assert t.handle_tool_error is False

    def test_invoke_returns_json_text(self):
        from neevai.agent_tools.langchain import to_langchain

        tools, sandbox = tools_for()
        write_file, read_file = to_langchain(tools)[1:3]
        assert json.loads(write_file.invoke({"path": "a.txt", "content": "hé"})) == {
            "bytes_written": 3
        }
        assert json.loads(read_file.invoke({"path": "a.txt"})) == {"content": "hé"}
        assert json.loads(read_file.invoke({"path": "nope"})) == {
            "error": "HTTP 400: nope: no such file"
        }
        assert sandbox.workspace == {"a.txt": "hé"}

    def test_invoke_lets_fatal_errors_propagate(self):
        from neevai.agent_tools.langchain import to_langchain

        tools, sandbox = tools_for()
        sandbox.fail = api_error(AuthenticationError, "bad key")
        with pytest.raises(AuthenticationError):
            to_langchain(tools)[0].invoke({"command": "ls"})

    def test_create_agent_stops_on_a_fatal_call_instead_of_retrying(self):
        from langchain.agents import create_agent
        from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
        from langchain_core.messages import AIMessage

        from neevai.agent_tools.langchain import to_langchain

        class ScriptedModel(GenericFakeChatModel):
            def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
                return self

        call = AIMessage(
            content="", tool_calls=[{"name": "run_command", "args": {"command": "ls"}, "id": "c1"}]
        )
        model = ScriptedModel(messages=iter([call, call, AIMessage(content="done")]))
        tools, sandbox = tools_for()
        sandbox.fail = api_error(AuthenticationError, "bad key")
        agent = create_agent(model, to_langchain(tools))
        with pytest.raises(AuthenticationError):
            agent.invoke({"messages": [{"role": "user", "content": "go"}]})


@pytest.mark.parametrize(
    "module,framework,extra",
    [
        ("claude", "claude_agent_sdk", "claude"),
        ("openai_agents", "agents", "openai-agents"),
        ("langchain", "langchain_core", "langchain"),
    ],
)
def test_adapters_name_their_extra_when_the_framework_is_missing(
    module: str, framework: str, extra: str
):
    code = (
        "import sys\n"
        f"sys.modules[{framework!r}] = None\n"
        "import neevai, neevai.agent_tools\n"
        "try:\n"
        f"    import neevai.agent_tools.{module}\n"
        "except ImportError as e:\n"
        "    print(e)\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert f'pip install "neevai[{extra}]"' in out.stdout
