"""AD-13: the JSON formatter redacts by allowlist and pattern; free text never reaches the sink."""

import json
import logging
import sys
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from adapters.logging.context import bind_trace_id, reset_trace_id
from adapters.logging.formatter import JsonFormatter
from shared.constants import SEND_KEY_SEPARATOR

TITLE = "Dinner with Priya at Rosa's"
EMAIL = "alice@example.com"


def emit(name="apps.probe", msg="Probe ran", args=(), exc_info=None, **extra) -> dict:
    record = logging.LogRecord(name, logging.INFO, __file__, 1, msg, args or None, exc_info)
    record.__dict__.update(extra)
    line = JsonFormatter().format(record)
    assert "\n" not in line
    return json.loads(line)


def raised(exc: BaseException):
    try:
        raise exc
    except BaseException:
        return sys.exc_info()


def test_line_has_core_fields_and_utc_timestamp():
    line = emit()

    assert line["level"] == "INFO"
    assert line["logger"] == "apps.probe"
    assert line["message"] == "Probe ran"
    assert line["trace_id"] is None
    assert datetime.fromisoformat(line["ts"]).utcoffset().total_seconds() == 0


def test_trace_id_comes_from_context():
    token = bind_trace_id("0123456789abcdef0123456789abcdef")
    try:
        line = emit()
    finally:
        reset_trace_id(token)

    assert line["trace_id"] == "0123456789abcdef0123456789abcdef"


def test_allowlisted_field_kept_and_other_field_redacted():
    line = emit(count=3, job="network_check", title=TITLE, email=EMAIL)

    assert line["count"] == 3
    assert line["job"] == "network_check"
    assert line["title"] == "[redacted]"
    assert line["email"] == "[redacted]"


def test_email_inside_allowlisted_field_redacted():
    line = emit(error_code=f"bounce for {EMAIL}", job="x%40y.example.com")

    assert line["error_code"] == "bounce for [email]"
    assert line["job"] == "[email]"


@pytest.mark.parametrize(
    "secret",
    [
        "sk-ant-api03-" + "a1B2" * 8,
        "sk_live_" + "Z" * 24,
        "whsec_" + "q" * 20,
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlLXZhbHVl",
        "Bearer abc.def.ghi.jkl",
        "xoxb-" + "1" * 20,
        "R" * 48,
    ],
)
def test_token_shaped_values_redacted(secret):
    line = emit(error_code=f"failed with {secret} today")

    assert secret not in json.dumps(line)
    assert "[token]" in line["error_code"]


def test_url_credentials_query_secrets_and_secret_ics_redacted():
    line = emit(
        error_code="postgresql://ep_owner:hunter2@db.local/x",
        job="https://x.test/cb?token=abc123&page=2",
        model="https://calendar.google.com/calendar/ical/x/private-0123456789abcdef/basic.ics",
        stream="webcal://example.test/feed.ics",
    )

    assert line["error_code"] == "postgresql://[token]@db.local/x"
    assert line["job"] == "https://x.test/cb?token=[token]&page=2"
    assert "private-0123" not in line["model"]
    assert line["stream"] == "[token]"


@pytest.mark.parametrize(
    "value",
    [
        "network_check",
        "work_item",
        "task-runner-abcdefghijklmnopq",
        "the bearer of good news",
        str(uuid.uuid4()),
        uuid.uuid4().hex,
        SEND_KEY_SEPARATOR.join(
            [str(uuid.uuid4()), "event_reminder", str(uuid.uuid4()), "1d", "3"]
        ),
    ],
)
def test_ids_slugs_and_send_keys_not_mistaken_for_tokens(value):
    assert emit(idempotency_key=value)["idempotency_key"] == value


def test_project_logger_never_interpolates_args():
    line = emit(name="apps.personalization.services", msg="Saved %s", args=(TITLE,))

    assert line["message"] == "Saved %s"
    assert line["args"] == "[redacted]"
    assert TITLE not in json.dumps(line)


def test_project_logger_template_still_scrubbed():
    assert emit(msg=f"oops {EMAIL}")["message"] == "oops [email]"


def test_framework_logger_interpolated_and_scrubbed():
    line = emit(name="django.request", msg="Not Found: %s", args=(f"/api/x?email={EMAIL}",))

    assert line["message"] == "Not Found: /api/x?email=[email]"
    assert "args" not in line


def test_exception_logs_type_chain_and_stack_but_never_its_message():
    def raise_from_a_function_with_a_rather_long_identifier_name():
        try:
            raise KeyError(EMAIL)
        except KeyError as error:
            raise ValueError(f"input_value='{TITLE}'") from error

    try:
        raise_from_a_function_with_a_rather_long_identifier_name()
    except ValueError:
        exc_info = sys.exc_info()

    line = emit(msg="Failed", exc_info=exc_info)

    assert line["exc_type"] == ["ValueError", "KeyError"]
    assert "raise_from_a_function_with_a_rather_long_identifier_name" in line["exc_stack"]
    text = json.dumps(line)
    assert TITLE not in text
    assert EMAIL not in text


def test_non_json_values_serialised_as_strings():
    user_id = uuid.uuid4()

    line = emit(
        user_id=user_id,
        cost_micros=Decimal("12.50"),
        attempt=datetime(2026, 1, 1, tzinfo=UTC),
        job=object(),
    )

    assert line["user_id"] == str(user_id)
    assert line["cost_micros"] == "12.50"
    assert line["attempt"] == "2026-01-01 00:00:00+00:00"
    assert line["job"].startswith("<object object")


def test_nested_values_scrubbed():
    line = emit(error_code={"to": [EMAIL], "count": 2})

    assert line["error_code"] == {"to": ["[email]"], "count": 2}
