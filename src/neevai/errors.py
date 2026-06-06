from typing import Any


class NeevAIError(Exception):
    """Base exception for all errors raised by the NeevAI SDK."""

    pass


class APIConnectionError(NeevAIError):
    """Raised when a request fails to connect to the NeevAI API.

    This covers DNS failures, connection resets, network timeouts, or when the request is aborted.
    """

    def __init__(self, message: str, cause: Exception | None = None):
        super().__init__(message)
        self.__cause__ = cause


class APITimeoutError(APIConnectionError):
    """Raised when a request is aborted because it exceeded the configured timeout."""

    pass


class APIError(NeevAIError):
    """Raised for any non-2xx HTTP response returned by the NeevAI API."""

    def __init__(
        self,
        status_code: int,
        body: dict[str, Any] | None,
        request_id: str | None,
    ):
        self.status_code = status_code
        self.code = body.get("error") if body else None
        self.details = body.get("details") if body else None
        self.request_id = request_id
        super().__init__(self._build_message())

    def _build_message(self) -> str:
        parts = [f"HTTP {self.status_code}"]
        if self.code:
            parts.append(self.code)
        if self.details:
            parts.append(f"({self.details})")
        if self.request_id:
            parts.append(f"[request-id: {self.request_id}]")
        return " ".join(parts)


class BadRequestError(APIError):
    """400 - Request was malformed or failed validation."""

    pass


class AuthenticationError(APIError):
    """401 - Missing, invalid, or expired API key."""

    pass


class PermissionDeniedError(APIError):
    """403 - Authenticated but not allowed to touch this org/project/resource."""

    pass


class NotFoundError(APIError):
    """404 - The requested resource does not exist."""

    pass


class ConflictError(APIError):
    """409 - The resource already exists or conflicts with current state."""

    pass


class PreconditionFailedError(APIError):
    """412 - Precondition failed (e.g., unsupported protocol version)."""

    pass


class RateLimitError(APIError):
    """429 - Rate limit exceeded."""

    pass


class DeadlineExceededError(APIError):
    """504 - The operation exceeded the server's deadline."""

    pass


class InternalServerError(APIError):
    """5xx - The server failed to handle a valid request."""

    pass


def error_from_status(
    status_code: int,
    body: dict[str, Any] | None,
    request_id: str | None,
) -> APIError:
    """Maps an HTTP status code and parsed JSON body to a specific APIError subclass."""
    if status_code == 400:
        return BadRequestError(status_code, body, request_id)
    elif status_code == 401:
        return AuthenticationError(status_code, body, request_id)
    elif status_code == 403:
        return PermissionDeniedError(status_code, body, request_id)
    elif status_code == 404:
        return NotFoundError(status_code, body, request_id)
    elif status_code == 409:
        return ConflictError(status_code, body, request_id)
    elif status_code == 412:
        return PreconditionFailedError(status_code, body, request_id)
    elif status_code == 429:
        return RateLimitError(status_code, body, request_id)
    elif status_code == 504:
        return DeadlineExceededError(status_code, body, request_id)
    elif status_code >= 500:
        return InternalServerError(status_code, body, request_id)
    else:
        return APIError(status_code, body, request_id)
