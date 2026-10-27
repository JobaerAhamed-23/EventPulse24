"""Domain error types: stable codes, calm default messages, optional details (no Django)."""

import pytest

from domain.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

ERRORS = [DomainError, NotFoundError, ValidationError, PermissionDeniedError, ConflictError]


@pytest.mark.parametrize(
    ("error_class", "code"),
    [
        (DomainError, "domain_error"),
        (NotFoundError, "not_found"),
        (ValidationError, "invalid_input"),
        (PermissionDeniedError, "permission_denied"),
        (ConflictError, "conflict"),
    ],
)
def test_error_code_is_stable_slug(error_class, code):
    assert error_class.code == code
    assert error_class().code == code


@pytest.mark.parametrize("error_class", ERRORS)
def test_error_without_message_uses_calm_default(error_class):
    error = error_class()

    assert error.message == error_class.default_message
    assert str(error) == error_class.default_message
    assert "!" not in error.message
    assert error.details is None


def test_error_custom_message_and_details_kept():
    error = NotFoundError("That event isn't available.", details={"event_id": "abc"})

    assert error.message == "That event isn't available."
    assert error.details == {"event_id": "abc"}


@pytest.mark.parametrize("error_class", ERRORS[1:])
def test_generic_errors_are_domain_errors(error_class):
    assert issubclass(error_class, DomainError)


def test_specific_error_inherits_code_from_generic_parent():
    class EventNotFoundError(NotFoundError):
        pass

    assert EventNotFoundError().code == "not_found"
