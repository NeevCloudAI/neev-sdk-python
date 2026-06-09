# Public entry point for @neevai/sdk. Re-exports the client, resource types,
# the Sandbox handle, and the typed error hierarchy.

from neevai.client import AsyncNeevAI, NeevAI
from neevai.dataplane import (
    AsyncSandboxConnection,
    AsyncSandboxFiles,
    SandboxConnection,
    SandboxFiles,
)
from neevai.errors import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    DeadlineExceededError,
    InternalServerError,
    NeevAIError,
    NotFoundError,
    PermissionDeniedError,
    PreconditionFailedError,
    RateLimitError,
)
from neevai.handles import AsyncSandbox, Sandbox
from neevai.transport.control import AsyncRawClient, RawClient
from neevai.types import Scope

__all__ = [
    "NeevAI",
    "AsyncNeevAI",
    "RawClient",
    "AsyncRawClient",
    "Sandbox",
    "AsyncSandbox",
    "SandboxConnection",
    "AsyncSandboxConnection",
    "SandboxFiles",
    "AsyncSandboxFiles",
    "Scope",
    "NeevAIError",
    "APIConnectionError",
    "APITimeoutError",
    "APIError",
    "BadRequestError",
    "AuthenticationError",
    "PermissionDeniedError",
    "NotFoundError",
    "ConflictError",
    "PreconditionFailedError",
    "RateLimitError",
    "DeadlineExceededError",
    "InternalServerError",
]
