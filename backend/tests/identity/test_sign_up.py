"""Sign-up: enumeration safety, the unique-constraint race, and the password rules."""

import pytest

from apps.identity.models import IdentityAuditEntry, User
from apps.identity.services import sign_up
from domain.errors import ThrottledError, ValidationError
from ports.email import Stream
from shared.constants import AUTH_THROTTLE_SIGN_UP_ACCOUNT, AUTH_THROTTLE_SIGN_UP_IP
from shared.db import PERSONAL
from tests.identity.factories import UserFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

STRONG_PASSWORD = "quixotic-rampart-42"


@pytest.fixture(autouse=True)
def _throttle(email_adapter, throttle_adapter):
    """Every sign-up test runs against a fresh throttle and a fresh email adapter."""
    return None


def test_sign_up_creates_an_account():
    outcome = sign_up(email="Maya@Example.com", password=STRONG_PASSWORD)

    assert outcome.accepted is True
    user = User.objects.using(PERSONAL).get()
    assert user.email == "maya@example.com"


def test_sign_up_does_not_store_the_password_in_the_clear():
    sign_up(email="maya@example.com", password=STRONG_PASSWORD)

    user = User.objects.using(PERSONAL).get()
    assert user.password != STRONG_PASSWORD
    assert user.check_password(STRONG_PASSWORD) is True


def test_sign_up_for_a_known_address_returns_the_same_outcome():
    """The outcome shape never says whether the account was created or already existed."""
    UserFactory(email="maya@example.com")

    outcome = sign_up(email="maya@example.com", password=STRONG_PASSWORD)

    assert outcome.accepted is True
    assert outcome == sign_up(email="maya@example.com", password=STRONG_PASSWORD)


def test_sign_up_for_a_known_address_creates_no_second_account():
    UserFactory(email="maya@example.com")

    sign_up(email="maya@example.com", password=STRONG_PASSWORD)

    assert User.objects.using(PERSONAL).filter(email="maya@example.com").count() == 1


def test_sign_up_for_a_known_address_notifies_the_holder(email_adapter):
    """The existing holder is told, by email — not the caller."""
    UserFactory(email="maya@example.com")

    sign_up(email="maya@example.com", password=STRONG_PASSWORD)

    assert len(email_adapter.sent) == 1
    sent = email_adapter.sent[0]
    assert sent.message.to == "maya@example.com"
    assert sent.stream is Stream.TRANSACTIONAL


def test_sign_up_for_a_new_address_sends_nothing(email_adapter):
    sign_up(email="new@example.com", password=STRONG_PASSWORD)

    assert email_adapter.sent == []


def test_sign_up_outcome_carries_no_created_flag():
    """No field can distinguish "created" from "already existed"."""
    assert not hasattr(sign_up(email="a@example.com", password=STRONG_PASSWORD), "created")
    assert not hasattr(sign_up(email="b@example.com", password=STRONG_PASSWORD), "existed")


def test_a_failed_audit_write_is_not_reported_as_a_duplicate(monkeypatch, email_adapter):
    """A real failure must not look like "that address is taken".

    The `IntegrityError` catch covers **only** the insert. If it also covered the audit
    write, an infrastructure failure would roll the account back, tell the caller their
    sign-up was accepted, and send the holder a "someone tried to sign up with your email"
    notice for an account that does not exist.
    """
    from django.db import IntegrityError

    from tests.identity.conftest import patch_module_attribute

    def explode(**_kwargs):
        raise IntegrityError("the audit table is unhappy")

    patch_module_attribute(monkeypatch, "apps.identity.services.audit", "write_audit", explode)

    with pytest.raises(IntegrityError):
        sign_up(email="maya@example.com", password=STRONG_PASSWORD)

    # The account was rolled back with the audit row, and no "duplicate" notice was sent.
    assert User.objects.using(PERSONAL).count() == 0
    assert email_adapter.sent == []


def test_a_failed_audit_write_leaves_no_orphan_account(monkeypatch):
    """The account and its audit row commit together, or neither does."""
    from django.db import IntegrityError

    from tests.identity.conftest import patch_module_attribute

    def explode(**_kwargs):
        raise IntegrityError("the audit table is unhappy")

    patch_module_attribute(monkeypatch, "apps.identity.services.audit", "write_audit", explode)

    with pytest.raises(IntegrityError):
        sign_up(email="maya@example.com", password=STRONG_PASSWORD)

    assert User.objects.using(PERSONAL).count() == 0
    assert IdentityAuditEntry.objects.using(PERSONAL).count() == 0


def test_sign_up_writes_an_audit_row():
    sign_up(email="maya@example.com", password=STRONG_PASSWORD)

    entry = IdentityAuditEntry.objects.using(PERSONAL).get()
    assert entry.action == "sign_up"
    assert entry.target_type == "User"


def test_sign_up_audit_row_holds_no_email():
    sign_up(email="maya@example.com", password=STRONG_PASSWORD)

    entry = IdentityAuditEntry.objects.using(PERSONAL).get()
    assert "maya@example.com" not in str(entry.actor_label)
    assert "maya@example.com" not in str(entry.details)


@pytest.mark.parametrize(
    "password",
    ["short", "password", "12345678", "maya@example.com"],
)
def test_sign_up_refuses_a_weak_password(password):
    with pytest.raises(ValidationError):
        sign_up(email="maya@example.com", password=password)

    assert User.objects.using(PERSONAL).count() == 0


def test_sign_up_refuses_an_empty_email():
    with pytest.raises(ValidationError):
        sign_up(email="   ", password=STRONG_PASSWORD)


def test_sign_up_is_throttled_per_ip():
    """The throttle trips before the account is even looked up."""
    for n in range(AUTH_THROTTLE_SIGN_UP_IP):
        sign_up(email=f"user{n}@example.com", password=STRONG_PASSWORD, ip_address="1.2.3.4")

    with pytest.raises(ThrottledError):
        sign_up(email="user99@example.com", password=STRONG_PASSWORD, ip_address="1.2.3.4")


def test_sign_up_is_throttled_per_account():
    """The same address from a different IP still hits the wall."""
    for n in range(AUTH_THROTTLE_SIGN_UP_ACCOUNT):
        sign_up(email="maya@example.com", password=STRONG_PASSWORD, ip_address=f"1.2.3.{n}")

    with pytest.raises(ThrottledError):
        sign_up(email="maya@example.com", password=STRONG_PASSWORD, ip_address="5.6.7.8")
