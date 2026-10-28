"""GET /api/health: each AD-3 alias lands in its own schema, Redis answers; 503 when not."""

import io
import json
import logging
from contextlib import contextmanager
from unittest import mock

import pytest
from django.db import OperationalError, connections
from django.test import Client

from adapters.logging.formatter import JsonFormatter
from config.health import HealthOut, HealthUnavailableOut
from shared.db import CATALOG, PERSONAL
from shared.errors import ErrorOut

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

CLOSED_PORT_REDIS = "redis://127.0.0.1:1/0"
SECRET_IN_ERROR = "password=hunter2 for alice@example.com"


@pytest.fixture
def log_lines():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        yield lambda: [json.loads(line) for line in stream.getvalue().splitlines()]
    finally:
        root.removeHandler(handler)


@contextmanager
def database_down(alias: str):
    with mock.patch.object(
        connections[alias], "cursor", side_effect=OperationalError(SECRET_IN_ERROR)
    ):
        yield


def get_health():
    return Client().get("/api/health")


def test_health_all_up_returns_200_and_every_component_ok():
    response = get_health()

    assert response.status_code == 200
    body = HealthOut.model_validate(response.json())
    assert body.status == "ok"
    assert {name: c.status for name, c in body.components} == {
        "personal": "ok",
        "catalog": "ok",
        "redis": "ok",
    }
    assert response["X-Request-ID"]


def test_health_redis_down_returns_503_in_the_shared_error_shape(settings):
    settings.CELERY_BROKER_URL = CLOSED_PORT_REDIS

    response = get_health()

    assert response.status_code == 503
    payload = response.json()
    ErrorOut.model_validate(payload)
    body = HealthUnavailableOut.model_validate(payload)
    assert body.code == "service_unavailable"
    assert body.message == "Some services aren't responding right now."
    components = body.details.components
    assert (components.redis.status, components.redis.reason) == ("down", "unreachable")
    assert (components.personal.status, components.catalog.status) == ("ok", "ok")


@pytest.mark.parametrize(("alias", "component"), [(PERSONAL, "personal"), (CATALOG, "catalog")])
def test_health_database_down_names_that_alias_only(alias, component):
    with database_down(alias):
        response = get_health()

    assert response.status_code == 503
    components = HealthUnavailableOut.model_validate(response.json()).details.components
    statuses = {name: (c.status, c.reason) for name, c in components}
    assert statuses.pop(component) == ("down", "unreachable")
    assert set(statuses.values()) == {("ok", None)}


def test_health_alias_in_the_wrong_schema_is_reported():
    # The alias answers, but its connection lands in another schema (a search_path mistake).
    cursor = mock.MagicMock()
    cursor.__enter__.return_value.fetchone.return_value = ("public",)
    with mock.patch.object(connections[CATALOG], "cursor", return_value=cursor):
        response = get_health()

    assert response.status_code == 503
    components = HealthUnavailableOut.model_validate(response.json()).details.components
    assert (components.catalog.status, components.catalog.reason) == ("down", "wrong_schema")
    assert components.personal.status == "ok"


def test_health_down_component_logs_slug_and_type_never_the_exception_text(log_lines):
    with database_down(CATALOG):
        get_health()

    [line] = [ln for ln in log_lines() if ln["message"] == "Health component down"]
    assert line["logger"] == "config.health"
    assert line["level"] == "WARNING"
    assert line["component"] == "catalog"
    assert line["error_type"] == "OperationalError"
    assert "hunter2" not in json.dumps(log_lines())
    assert "alice" not in json.dumps(log_lines())


def test_health_response_never_contains_exception_text():
    with database_down(PERSONAL):
        response = get_health()

    assert "hunter2" not in response.content.decode()
