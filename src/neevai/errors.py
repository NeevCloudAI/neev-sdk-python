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
    """Raised for any non-2xx HTTP response returned by the NeevAI API.

    ``code`` is the machine-readable classification of the failure (for example
    ``not_found`` or ``sandbox_quota_exceeded``); branch on it rather than on the
    message text, which may be reworded. ``scope`` names which limit was hit when a
    quota refuses the request (for example ``organization`` or ``project``).
    """

    def __init__(
        self,
        status_code: int,
        body: dict[str, Any] | None,
        request_id: str | None,
        *,
        request_method: str | None = None,
        request_url: str | None = None,
    ):
        self.status_code = status_code
        self.body = body
        self.code = _str_field(body, "code")
        self.scope = _str_field(body, "scope")
        # `message` carries the readable text; `error` is the older field with the same text.
        self._text = _str_field(body, "message") or _str_field(body, "error")
        self.details = _str_field(body, "details")
        self.request_id = request_id
        self.request_method = request_method
        self.request_url = request_url
        super().__init__(self._build_message())

    def _build_message(self) -> str:
        parts = [f"HTTP {self.status_code}"]
        if self.code:
            parts.append(self.code)
        if self._text:
            parts.append(self._text)
        if self.details:
            parts.append(f"({self.details})")
        elif self.body and not (self.code or self._text):
            parts.append(f"(body: {self.body})")
        if self.request_method and self.request_url:
            parts.append(f"[{self.request_method} {self.request_url}]")
        if self.request_id:
            parts.append(f"[request-id: {self.request_id}]")
        return " ".join(parts)


def _str_field(body: dict[str, Any] | None, key: str) -> str | None:
    """Returns ``body[key]`` when it is a non-empty string, else ``None``."""
    if not body:
        return None
    value = body.get(key)
    return value if isinstance(value, str) and value else None


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


class ServiceUnavailableError(InternalServerError):
    """503 - The service is temporarily unavailable; retry shortly."""

    pass


def error_from_status(
    status_code: int,
    body: dict[str, Any] | None,
    request_id: str | None,
    *,
    request_method: str | None = None,
    request_url: str | None = None,
) -> APIError:
    """Maps an HTTP status code and parsed JSON body to a specific APIError subclass."""
    kwargs = {
        "request_method": request_method,
        "request_url": request_url,
    }
    if status_code == 400:
        return BadRequestError(status_code, body, request_id, **kwargs)
    elif status_code == 401:
        return AuthenticationError(status_code, body, request_id, **kwargs)
    elif status_code == 403:
        return PermissionDeniedError(status_code, body, request_id, **kwargs)
    elif status_code == 404:
        return NotFoundError(status_code, body, request_id, **kwargs)
    elif status_code == 409:
        return ConflictError(status_code, body, request_id, **kwargs)
    elif status_code == 412:
        return PreconditionFailedError(status_code, body, request_id, **kwargs)
    elif status_code == 429:
        return RateLimitError(status_code, body, request_id, **kwargs)
    elif status_code == 503:
        return ServiceUnavailableError(status_code, body, request_id, **kwargs)
    elif status_code == 504:
        return DeadlineExceededError(status_code, body, request_id, **kwargs)
    elif status_code >= 500:
        return InternalServerError(status_code, body, request_id, **kwargs)
    else:
        return APIError(status_code, body, request_id, **kwargs)
