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


def test_error_from_status_includes_request_context():
    err = error_from_status(
        500,
        None,
        "req-456",
        request_method="POST",
        request_url="https://agent.example.com/api/v1beta1/sandboxes",
    )
    assert err.request_method == "POST"
    assert err.request_url == "https://agent.example.com/api/v1beta1/sandboxes"
    assert "POST https://agent.example.com/api/v1beta1/sandboxes" in str(err)
    assert "req-456" in str(err)


def test_error_reads_code_scope_and_message():
    err = error_from_status(
        429,
        {
            "error": "sandbox quota exceeded",
            "message": "sandbox quota exceeded",
            "code": "sandbox_quota_exceeded",
            "scope": "project",
        },
        None,
    )
    assert err.code == "sandbox_quota_exceeded"
    assert err.scope == "project"
    assert str(err) == "HTTP 429 sandbox_quota_exceeded sandbox quota exceeded"


def test_error_prefers_message_over_deprecated_error():
    err = error_from_status(400, {"error": "old text", "message": "new text"}, None)
    assert "new text" in str(err)
    assert "old text" not in str(err)


def test_legacy_error_body_still_parses():
    err = error_from_status(404, {"error": "sandbox not found"}, "req-1")
    assert isinstance(err, NotFoundError)
    assert err.code is None
    assert err.scope is None
    assert str(err) == "HTTP 404 sandbox not found [request-id: req-1]"


def test_unknown_code_is_kept_as_a_plain_string():
    err = error_from_status(400, {"code": "something_new", "message": "x"}, None)
    assert err.code == "something_new"


def test_503_is_service_unavailable_and_internal():
    from neevai.errors import ServiceUnavailableError

    err = error_from_status(503, {"code": "service_unavailable", "message": "retry"}, None)
    assert isinstance(err, ServiceUnavailableError)
    assert isinstance(err, InternalServerError)
    assert err.code == "service_unavailable"
