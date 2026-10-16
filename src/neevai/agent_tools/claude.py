"""The sandbox agent tools for the Claude Agent SDK, as an in-process MCP server.

Needs ``claude-agent-sdk`` (``pip install "neevai[claude]"``)::

    claude = to_claude(SandboxTools(sandbox))
    async with ClaudeSDKClient(ClaudeAgentOptions(**claude.options())) as client:
        await client.query(task)
        async for message in claude.watch(client.receive_response()):
            ...
"""

from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import AsyncIterable, AsyncIterator
from typing import Any

from neevai.agent_tools import FATAL_RESULT, FatalGuard, SandboxTools, ToolResult, ToolSpec

try:
    from claude_agent_sdk import (
        AssistantMessage,
        SdkMcpTool,
        ToolUseBlock,
        create_sdk_mcp_server,
        tool,
    )
    from mcp.types import ToolAnnotations
except ImportError as e:  # pragma: no cover
    raise ImportError(
        'neevai.agent_tools.claude needs claude-agent-sdk: pip install "neevai[claude]"'
    ) from e

__all__ = ["ClaudeTools", "to_claude"]

_SERVER = "neev"
_PREFIX = f"mcp__{_SERVER}__"


class ClaudeTools:
    """The enabled sandbox tools as Claude Agent SDK options, guarded for one run."""

    def __init__(self, tools: SandboxTools) -> None:
        """Binds ``tools.specs()`` to a new guard."""
        self.guard = FatalGuard()
        self._specs = tools.specs()

    def options(self) -> dict[str, Any]:
        """Returns keyword arguments for ``ClaudeAgentOptions`` that give Claude these tools and nothing else."""
        return {
            # Claude Code's own tools act on the machine running the agent, not the sandbox.
            "tools": [],
            "mcp_servers": {
                _SERVER: create_sdk_mcp_server(
                    name=_SERVER, version="1.0.0", tools=[self._sdk_tool(s) for s in self._specs]
                )
            },
            "strict_mcp_config": True,
            "allowed_tools": [_PREFIX + s.name for s in self._specs],
            # Keeps the user's Claude Code settings and hooks out of the run; login auth is not a setting.
            "setting_sources": [],
            # Anything not in allowed_tools is denied rather than left to a permission prompt.
            "permission_mode": "dontAsk",
        }

    async def watch(self, messages: AsyncIterable[Any]) -> AsyncIterator[Any]:
        """Yields the run's messages, stopping once a tool call failed, then raises that failure.

        Raises:
            RuntimeError: Claude used a tool other than these.
        """
        async for message in messages:
            if self.guard.failed:
                break
            if isinstance(message, AssistantMessage):
                stray = [
                    b.name
                    for b in message.content
                    if isinstance(b, ToolUseBlock) and not b.name.startswith(_PREFIX)
                ]
                if stray:
                    raise RuntimeError(f"host tools were used: {', '.join(stray)}")
            yield message
        self.guard.raise_if_failed()

    def _sdk_tool(self, spec: ToolSpec[ToolResult]) -> SdkMcpTool[Any]:
        async def handler(args: dict[str, Any]) -> dict[str, Any]:
            # The sandbox client is synchronous; keep it off the event loop.
            result = await asyncio.to_thread(self.guard.call, spec, args)
            text = json.dumps(result)
            return {"content": [{"type": "text", "text": text}], "is_error": result is FATAL_RESULT}

        # A plain copy, since the framework may rewrite the schema and PARAMETERS is read-only.
        return tool(
            spec.name,
            spec.description,
            copy.deepcopy(dict(spec.parameters)),
            annotations=ToolAnnotations(title=spec.title),
        )(handler)


def to_claude(tools: SandboxTools) -> ClaudeTools:
    """Returns the enabled sandbox tools for one Claude Agent SDK run."""
    return ClaudeTools(tools)
