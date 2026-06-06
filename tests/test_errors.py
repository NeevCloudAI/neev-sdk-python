# test_errors.py
"""Tests for the error mapping utilities in `neevai.errors`."""

import pytest

from neevai.errors import (
    AuthenticationError,
    BadRequestError,
    ConflictError,
    DeadlineExceededError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    PreconditionFailedError,
    RateLimitError,
    error_from_status,
)


@pytest.mark.parametrize(
    "status, expected_type",
    [
        (400, BadRequestError),
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (404, NotFoundError),
        (409, ConflictError),
        (412, PreconditionFailedError),
        (429, RateLimitError),
        (504, DeadlineExceededError),
        (500, InternalServerError),
        (502, InternalServerError),
    ],
)
def test_error_from_status_mapping(status, expected_type):
    err = error_from_status(status, {"error": "code", "details": "msg"}, "req-123")
    assert isinstance(err, expected_type)
    # Verify that the constructed message contains status and details
    assert str(status) in str(err)
    assert "msg" in str(err)
    assert "req-123" in str(err)
