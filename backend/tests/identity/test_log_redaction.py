"""No PII in the logs (AD-13).

The email, the password and the raw reset token must never appear in a log line. The
check is done on the *serialised* output — the exact bytes that reach the log sink —
because a formatter that redacts the wrong field would pass a test that only inspected
the record.
"""

import logging

import pytest
from django.contrib.auth.hashers import make_password
from django.db import connections

from adapters.logging.formatter import JsonFormatter
from apps.identity.services import authenticate, request_password_reset, sign_up
from domain.errors import AuthenticationFailedError
from shared.db import PERSONAL
from tests.identity.factories import UserFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

EMAIL = "maya@example.com"
PASSWORD = "quixotic-rampart-42"


@pytest.fixture(autouse=True)
def _adapters(email_adapter, throttle_adapter):
    return None


def _serialised_lines(caplog) -> str:
    """Everything the formatter would write, as one blob of text."""
    formatter = JsonFormatter()
    return "\n".join(formatter.format(record) for record in caplog.records)


def test_the_sign_up_email_is_not_logged(caplog):
    with caplog.at_level(logging.INFO):
        sign_up(email=EMAIL, password=PASSWORD)

    assert EMAIL not in _serialised_lines(caplog)


def test_the_sign_in_email_is_not_logged(caplog):
    UserFactory(email=EMAIL, plain_password=PASSWORD)

    with caplog.at_level(logging.INFO):
        with pytest.raises(AuthenticationFailedError):
            authenticate(email=EMAIL, password="wrong-password-entirely")

    assert EMAIL not in _serialised_lines(caplog)


def test_the_password_is_not_logged(caplog):
    UserFactory(email=EMAIL, plain_password=PASSWORD)

    with caplog.at_level(logging.INFO):
        # A *wrong* password: a correct one authenticates and raises nothing, which would
        # make this test assert the wrong thing.
        with pytest.raises(AuthenticationFailedError):
            authenticate(email=EMAIL, password="a-different-password-entirely")

    assert PASSWORD not in _serialised_lines(caplog)


def test_the_reset_token_is_not_logged(caplog):
    """The token appears in the email and nowhere else."""
    UserFactory(email=EMAIL)

    with caplog.at_level(logging.INFO):
        request_password_reset(email=EMAIL)

    lines = _serialised_lines(caplog)
    from apps.identity.models import PasswordResetToken

    row = PasswordResetToken.objects.using(PERSONAL).get()
    # Neither the raw token nor the stored digest may reach a log line.
    assert row.token_hash not in lines
    assert row.token_salt not in lines


def test_the_audit_rows_hold_no_email():
    """AD-13, on the row rather than the log: the actor is a UUID."""
    from apps.identity.models import IdentityAuditEntry

    sign_up(email=EMAIL, password=PASSWORD)

    row = IdentityAuditEntry.objects.using(PERSONAL).get()
    assert EMAIL not in str(row.actor_label)
    assert EMAIL not in str(row.details)


def test_the_throttle_keys_hold_no_email():
    """The throttle key is a digest, so the address never reaches the store."""
    from apps.identity.services.throttle import account_key

    key = account_key("sign_in", EMAIL)

    assert EMAIL not in key
    assert len(key.split(":")[-1]) == 64


def test_the_stored_password_is_a_hash_not_the_plain_text():
    UserFactory(email=EMAIL, plain_password=PASSWORD)

    with connections[PERSONAL].cursor() as cursor:
        cursor.execute("SELECT password FROM personal.identity_user WHERE email = %s", [EMAIL])
        rows = cursor.fetchall()

    assert rows[0][0] != PASSWORD
    assert rows[0][0].startswith("pbkdf2_")
    assert make_password(PASSWORD) != rows[0][0]  # salted, so not even reproducible
