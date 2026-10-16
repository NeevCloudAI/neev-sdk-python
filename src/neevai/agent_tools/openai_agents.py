"""The sandbox agent tools for the OpenAI Agents SDK.

Needs ``openai-agents`` (``pip install "neevai[openai-agents]"``)::

    agent = Agent(name="engineer", tools=to_openai_agents(SandboxTools(sandbox)), model=...)
    result = await Runner.run(agent, task)

No ``FatalGuard`` is needed: an exception from a tool built here ends ``Runner.run``
as ``agents.exceptions.UserError`` with the original error as ``__cause__``, instead of
reaching the model.
"""

from __future__ import annotations

import asyncio
import copy
import json
from typing import Any

from neevai.agent_tools import SandboxTools, ToolResult, ToolSpec

try:
    from agents import FunctionTool
    from agents.tool_context import ToolContext
except ImportError as e:  # pragma: no cover
    raise ImportError(
        'neevai.agent_tools.openai_agents needs openai-agents: pip install "neevai[openai-agents]"'
    ) from e

__all__ = ["to_openai_agents"]


def to_openai_agents(tools: SandboxTools) -> list[FunctionTool]:
    """Returns a ``FunctionTool`` per enabled sandbox tool, in ``names()`` order."""
    return [_function_tool(spec) for spec in tools.specs()]


def _function_tool(spec: ToolSpec[ToolResult]) -> FunctionTool:
    async def invoke(_ctx: ToolContext[Any], raw: str) -> str:
        try:
            args = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return json.dumps({"error": f"invalid arguments for {spec.name}: not JSON"})
        # The sandbox client is synchronous; keep it off the event loop.
        return json.dumps(await asyncio.to_thread(spec.call, args))

    return FunctionTool(
        name=spec.name,
        description=spec.description,
        # A plain copy, since the framework may rewrite the schema and PARAMETERS is read-only.
        params_json_schema=copy.deepcopy(dict(spec.parameters)),
        on_invoke_tool=invoke,
        # Strict schemas cannot express optional fields; call() checks the arguments instead.
        strict_json_schema=False,
    )
