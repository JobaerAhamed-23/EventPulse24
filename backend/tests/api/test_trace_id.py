"""AD-13: every log line from an API request carries the request's trace id."""

import io
import json
import logging

import pytest
from django.test import Client

from adapters.logging.context import current_trace_id
from adapters.logging.formatter import JsonFormatter


@pytest.fixture
def log_lines(settings):
    settings.ROOT_URLCONF = "tests.api.trace_urls"
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        yield lambda: [json.loads(line) for line in stream.getvalue().splitlines()]
    finally:
        root.removeHandler(handler)


def test_trace_id_minted_echoed_and_on_every_log_line(log_lines):
    response = Client().get("/api/ping")

    trace_id = response["X-Request-ID"]
    assert len(trace_id) == 32
    assert int(trace_id, 16)
    lines = [line for line in log_lines() if line["logger"] == "apps.probe"]
    assert [line["message"] for line in lines] == ["Probe handled", "Probe warned"]
    assert {line["trace_id"] for line in lines} == {trace_id}


def test_django_request_error_line_logged_after_middleware_carries_trace_id(log_lines):
    response = Client().get("/api/missing")

    assert response.status_code == 404
    [line] = [line for line in log_lines() if line["logger"] == "django.request"]
    assert line["trace_id"] == response["X-Request-ID"]


def test_valid_inbound_id_reused(log_lines):
    inbound = "3f2c9a1e-7b8d-4f6a-9c0e-5b2d7a1f4c8e"

    response = Client().get("/api/ping", headers={"X-Request-ID": inbound})

    assert response["X-Request-ID"] == inbound
    assert {line["trace_id"] for line in log_lines()} == {inbound}


@pytest.mark.parametrize(
    "inbound",
    ["short", "a" * 37, "has space in it", 'x"},{"injected":1', "ünïcode-value-1234"],
)
def test_invalid_or_oversized_inbound_id_replaced(log_lines, inbound):
    response = Client().get("/api/ping", headers={"X-Request-ID": inbound})

    assert response["X-Request-ID"] != inbound
    assert len(response["X-Request-ID"]) == 32


def test_trace_context_reset_after_request(log_lines):
    Client().get("/api/ping")

    assert current_trace_id() is None
