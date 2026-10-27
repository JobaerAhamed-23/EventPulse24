"""One HTTP mapping for every error: `{code, message, details?}` (spine Errors convention)."""

import logging

import pytest
from django.test import RequestFactory
from ninja.testing import TestClient

from config.api import api as project_api
from domain.errors import NotFoundError
from tests.api.error_api import TITLE, api

client = TestClient(api)


@pytest.mark.parametrize(
    ("kind", "status", "code", "message"),
    [
        ("domain", 400, "domain_error", "Something didn't work as expected."),
        ("not_found", 404, "not_found", "We couldn't find that."),
        ("invalid", 422, "invalid_input", "Some details need another look."),
        ("denied", 403, "permission_denied", "You don't have access to this."),
        (
            "conflict",
            409,
            "conflict",
            "This changed since you last looked. Refresh and try again.",
        ),
        ("event_not_found", 404, "not_found", "We couldn't find that."),
    ],
)
def test_domain_error_mapped_to_status_and_exact_body(kind, status, code, message):
    response = client.get(f"/domain/{kind}")

    assert response.status_code == status
    assert response.json() == {"code": code, "message": message}


def test_domain_error_details_included_when_given():
    response = client.get("/details")

    assert response.status_code == 422
    assert response.json()["details"] == {"errors": [{"loc": ["name"], "msg": "Too long."}]}


def test_request_validation_uses_the_one_errors_shape_without_echoing_input():
    response = client.post("/payload", json={"name": TITLE, "count": "many"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "invalid_request"
    assert body["message"] == "Some details in the request need another look."
    errors = body["details"]["errors"]
    assert all(set(error) == {"loc", "msg"} for error in errors)
    assert ["body", "data", "count"] in [error["loc"] for error in errors]
    assert "many" not in response.content.decode()


def test_django_field_validation_converted_to_the_one_errors_shape():
    response = client.get("/django-field-errors")

    assert response.status_code == 422
    assert response.json() == {
        "code": "invalid_input",
        "message": "Some details need another look.",
        "details": {
            "errors": [
                {"loc": ["name"], "msg": "Too long."},
                {"loc": [], "msg": "Dates overlap."},
            ]
        },
    }


def test_django_unkeyed_validation_converted_to_the_one_errors_shape():
    response = client.get("/django-list-errors")

    assert response.json()["details"] == {
        "errors": [{"loc": [], "msg": "First problem."}, {"loc": [], "msg": "Second problem."}]
    }


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (400, "bad_request"),
        (401, "not_authenticated"),
        (429, "rate_limited"),
        (418, "request_failed"),
    ],
)
def test_http_error_gets_code_and_calm_message_not_its_own_text(status, code):
    response = client.get(f"/http/{status}")

    assert response.status_code == status
    assert response.json()["code"] == code
    assert TITLE not in response.content.decode()


def test_http404_mapped_to_not_found():
    response = client.get("/not-found")

    assert response.status_code == 404
    assert response.json() == {"code": "not_found", "message": "We couldn't find that."}


def test_django_permission_denied_mapped_to_403():
    response = client.get("/forbidden")

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"


def test_suspicious_operation_400_and_security_warning_without_text(caplog):
    with caplog.at_level(logging.WARNING, logger="django.security"):
        response = client.get("/suspicious")

    assert response.status_code == 400
    assert response.json()["code"] == "bad_request"
    [record] = [r for r in caplog.records if r.name.startswith("django.security")]
    assert record.name == "django.security.SuspiciousOperation"
    assert record.levelno == logging.WARNING
    assert TITLE not in record.getMessage()


def test_unhandled_exception_500_without_text_and_logged(settings, caplog):
    settings.DEBUG = False

    with caplog.at_level(logging.ERROR, logger="config.errors"):
        response = client.get("/boom")

    assert response.status_code == 500
    assert response.json() == {
        "code": "internal_error",
        "message": "Something went wrong on our side. Try again in a moment.",
    }
    [record] = [r for r in caplog.records if r.name == "config.errors"]
    assert record.exc_info[0] is RuntimeError


def test_unhandled_exception_reraised_in_debug(settings):
    settings.DEBUG = True

    with pytest.raises(RuntimeError):
        client.get("/boom")


def test_project_api_has_the_handlers_installed():
    request = RequestFactory().get("/api/anything")

    response = project_api.on_exception(request, NotFoundError())

    assert response.status_code == 404
    assert response["Content-Type"].startswith("application/json")
