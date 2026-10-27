"""A throwaway API with the project's error handlers, for test_errors.py."""

from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError

from config.errors import install_error_handlers
from domain.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

TITLE = "Dinner with Priya"

api = NinjaAPI(urls_namespace="error_test_api")
install_error_handlers(api)


class EventNotFoundError(NotFoundError):
    pass


DOMAIN_ERRORS = {
    "domain": DomainError,
    "not_found": NotFoundError,
    "invalid": ValidationError,
    "denied": PermissionDeniedError,
    "conflict": ConflictError,
    "event_not_found": EventNotFoundError,
}


class Payload(Schema):
    name: str
    count: int


@api.get("/domain/{kind}")
def domain(request, kind: str):
    raise DOMAIN_ERRORS[kind]()


@api.get("/details")
def details(request):
    raise ValidationError(details={"errors": [{"loc": ["name"], "msg": "Too long."}]})


@api.post("/payload")
def payload(request, data: Payload):
    return {"ok": True}


@api.get("/django-field-errors")
def django_field_errors(request):
    raise DjangoValidationError({"name": ["Too long."], "__all__": ["Dates overlap."]})


@api.get("/django-list-errors")
def django_list_errors(request):
    raise DjangoValidationError(["First problem.", "Second problem."])


@api.get("/http/{status}")
def http(request, status: int):
    raise HttpError(status, f"raw text {TITLE}")


@api.get("/not-found")
def not_found(request):
    raise Http404(f"no {TITLE}")


@api.get("/forbidden")
def forbidden(request):
    raise PermissionDenied(TITLE)


@api.get("/suspicious")
def suspicious(request):
    raise SuspiciousOperation(f"weird {TITLE}")


@api.get("/boom")
def boom(request):
    raise RuntimeError(f"crashed on {TITLE}")
