"""Canonical ``<handle>`` slot — resource handle objects ("handles over raw IDs")."""

from neevai.handles.agent import Agent, AsyncAgent
from neevai.handles.sandbox import AsyncSandbox, Sandbox

__all__ = ["Sandbox", "AsyncSandbox", "Agent", "AsyncAgent"]
