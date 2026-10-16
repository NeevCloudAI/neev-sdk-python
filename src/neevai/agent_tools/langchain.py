"""The sandbox agent tools for LangChain and LangGraph.

Needs ``langchain`` (``pip install "neevai[langchain]"``)::

    agent = create_agent(model, to_langchain(SandboxTools(sandbox)))

An exception from a tool built here propagates out of the run instead of reaching
the model, since ``handle_tool_error`` stays off.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import Any

from neevai.agent_tools import SandboxTools, ToolResult, ToolSpec

try:
    from langchain_core.tools import StructuredTool
except ImportError as e:  # pragma: no cover
    raise ImportError(
        'neevai.agent_tools.langchain needs langchain: pip install "neevai[langchain]"'
    ) from e

__all__ = ["to_langchain"]


def to_langchain(tools: SandboxTools) -> list[StructuredTool]:
    """Returns a ``StructuredTool`` per enabled sandbox tool, in ``names()`` order."""
    return [
        StructuredTool(
            name=spec.name,
            description=spec.description,
            # A plain copy, since the framework may rewrite the schema and PARAMETERS is read-only.
            args_schema=copy.deepcopy(dict(spec.parameters)),
            func=_runner(spec),
        )
        for spec in tools.specs()
    ]


def _runner(spec: ToolSpec[ToolResult]) -> Callable[..., str]:
    def run(**args: Any) -> str:
        return json.dumps(spec.call(args))

    return run
