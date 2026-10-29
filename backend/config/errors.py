"""The single mapping from exceptions to HTTP responses.

Every API error, domain or framework, has the shape `{code, message, details?}`, and validation
errors always use `details = {"errors": [{"loc": [...], "msg": str}]}`.
"""

import logging

from django.conf import settings
from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, SuspiciousOperation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from ninja import NinjaAPI
from ninja.errors import HttpError
from ninja.errors import ValidationError as NinjaValidationError

from domain.errors import (
    ConflictError,
    CsrfError,
    DomainError,
    NotAuthenticatedError,
    NotFoundError,
    PermissionDeniedError,
    ThrottledError,
    ValidationError,
)

logger = logging.getLogger(__name__)

# Looked up along the exception's MRO, so EventNotFoundError(NotFoundError) is a 404.
STATUS_BY_ERROR: dict[type[DomainError], int] = {
    NotFoundError: 404,
    ValidationError: 422,
    PermissionDeniedError: 403,
    # A refused request, not a permission problem. It has its own code so the frontend
    # can tell the two apart: a CSRF failure means "fetch a fresh token and retry".
    CsrfError: 403,
    ConflictError: 409,
    # A refusal, not a malformed request: the credentials did not work, or there was no
    # session. `AuthenticationFailedError` is a `ValidationError` and so a 422 — but at
    # the HTTP edge a refused sign-in is a 401, which is what the frontend branches on.
    NotAuthenticatedError: 401,
    # Too many attempts. A 429 is a distinct status from the 400 a generic domain error
    # gets: the caller can act on it — wait and retry — and the frontend branches on it.
    ThrottledError: 429,
    DomainError: 400,
}

# Framework HttpErrors get a stable code and a calm message; their own text is not shown.
HTTP_ERRORS: dict[int, tuple[str, str]] = {
    400: ("bad_request", "That request couldn't be read."),
    401: ("not_authenticated", "Please sign in to continue."),
    403: ("permission_denied", PermissionDeniedError.default_message),
    404: ("not_found", NotFoundError.default_message),
    405: ("method_not_allowed", "That action isn't available here."),
    409: ("conflict", ConflictError.default_message),
    413: ("payload_too_large", "That's more than we can take in one go."),
    422: ("invalid_input", ValidationError.default_message),
    429: ("rate_limited", "That's a lot of requests. Try again in a little while."),
}
FALLBACK_HTTP_ERROR = ("request_failed", DomainError.default_message)
INTERNAL_ERROR = ("internal_error", "Something went wrong on our side. Try again in a moment.")
INVALID_REQUEST_MESSAGE = "Some details in the request need another look."


def status_for(error: DomainError) -> int:
    for cls in type(error).__mro__:
        if cls in STATUS_BY_ERROR:
            return STATUS_BY_ERROR[cls]
    return 400


def body(code: str, message: str, details: dict | None = None) -> dict:
    payload = {"code": code, "message": message}
    if details is not None:
        payload["details"] = details
    return payload


def errors_from_pydantic(errors: list[dict]) -> list[dict]:
    # `input` would echo the submitted value; only the location and message are kept.
    return [
        {"loc": list(error.get("loc", ())), "msg": str(error.get("msg", ""))} for error in errors
    ]


def errors_from_django(exc: DjangoValidationError) -> list[dict]:
    if hasattr(exc, "error_dict"):
        return [
            {"loc": [] if field == NON_FIELD_ERRORS else [field], "msg": message}
            for field, messages in exc.message_dict.items()
            for message in messages
        ]
    return [{"loc": [], "msg": message} for message in exc.messages]


def install_error_handlers(api: NinjaAPI) -> None:
    """Register the handlers on `api`. Called once, in config/api.py."""

    def respond(request, status: int, payload: dict):
        return api.create_response(request, payload, status=status)

    def on_domain_error(request, exc: DomainError):
        return respond(request, status_for(exc), body(exc.code, exc.message, exc.details))

    def on_request_validation(request, exc: NinjaValidationError):
        details = {"errors": errors_from_pydantic(exc.errors)}
        return respond(request, 422, body("invalid_request", INVALID_REQUEST_MESSAGE, details))

    def on_django_validation(request, exc: DjangoValidationError):
        details = {"errors": errors_from_django(exc)}
        return respond(
            request, 422, body("invalid_input", ValidationError.default_message, details)
        )

    def on_http_error(request, exc: HttpError):
        code, message = HTTP_ERRORS.get(exc.status_code, FALLBACK_HTTP_ERROR)
        return respond(request, exc.status_code, body(code, message))

    def on_not_found(request, exc: Http404):
        return respond(request, 404, body(*HTTP_ERRORS[404]))

    def on_permission_denied(request, exc: PermissionDenied):
        return respond(request, 403, body(*HTTP_ERRORS[403]))

    def on_suspicious(request, exc: SuspiciousOperation):
        # Django reports these on django.security.<ClassName>; keep that signal.
        name = type(exc).__name__
        logging.getLogger(f"django.security.{name}").warning(
            "Suspicious operation rejected", extra={"error_type": name}
        )
        return respond(request, 400, body(*HTTP_ERRORS[400]))

    def on_unhandled(request, exc: Exception):
        if settings.DEBUG:
            raise exc  # keep Django's debug page locally
        logger.error("Unhandled API error", exc_info=exc)
        return respond(request, 500, body(*INTERNAL_ERROR))

    api.add_exception_handler(DomainError, on_domain_error)
    api.add_exception_handler(NinjaValidationError, on_request_validation)
    api.add_exception_handler(DjangoValidationError, on_django_validation)
    api.add_exception_handler(HttpError, on_http_error)
    api.add_exception_handler(Http404, on_not_found)
    api.add_exception_handler(PermissionDenied, on_permission_denied)
    api.add_exception_handler(SuspiciousOperation, on_suspicious)
    api.add_exception_handler(Exception, on_unhandled)
