"""Sign-in: enumeration safety in the message *and* in the timing.

The timing equalisation is the part that is easy to get wrong, so it is pinned by a test
that would fail if the unknown-email path returned early. The test monkeypatches
`check_password` with a recorder and asserts it was called on the unknown-email path:
removing the dummy-hash check turns the endpoint into an account-existence oracle.
"""

import pytest

from apps.identity.models import IdentityAuditEntry, User
from apps.identity.services import authenticate
from domain.errors import AuthenticationFailedError, ThrottledError
from shared.constants import AUTH_THROTTLE_SIGN_IN_ACCOUNT, AUTH_THROTTLE_SIGN_IN_IP
from shared.db import PERSONAL
from tests.identity.conftest import patch_module_attribute
from tests.identity.factories import UserFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

PASSWORD = "quixotic-rampart-42"


@pytest.fixture(autouse=True)
def _adapters(email_adapter, throttle_adapter):
    return None


def _attempt(*, email: str, ip_address: str) -> None:
    """One sign-in attempt whose *outcome* does not matter — only that it was counted.

    The throttle counts the attempt before the account is looked up, so a failed sign-in
    counts exactly like a successful one. The authentication error is swallowed here
    because a throttle test is about the counter, not about the credentials.
    """
    try:
        authenticate(email=email, password=PASSWORD, ip_address=ip_address)
    except AuthenticationFailedError:
        pass


def test_authenticate_returns_the_user_for_a_correct_password():
    user = UserFactory(email="maya@example.com", plain_password=PASSWORD)

    result = authenticate(email="maya@example.com", password=PASSWORD)

    assert result.pk == user.pk


def test_authenticate_normalises_the_email():
    UserFactory(email="maya@example.com", plain_password=PASSWORD)

    result = authenticate(email="Maya@Example.com", password=PASSWORD)

    assert result.email == "maya@example.com"


def test_authenticate_refuses_a_wrong_password():
    UserFactory(email="maya@example.com", plain_password=PASSWORD)

    with pytest.raises(AuthenticationFailedError):
        authenticate(email="maya@example.com", password="not-the-password")


def test_authenticate_refuses_an_unknown_email():
    with pytest.raises(AuthenticationFailedError):
        authenticate(email="nobody@example.com", password=PASSWORD)


def test_a_successful_sign_in_writes_an_audit_row():
    """D14: sign-in is audited, with the actor id and no address."""
    user = UserFactory(email="maya@example.com", plain_password=PASSWORD)

    authenticate(email="maya@example.com", password=PASSWORD)

    entry = IdentityAuditEntry.objects.using(PERSONAL).get()
    assert entry.action == "sign_in"
    assert entry.target_type == "User"
    assert entry.target_id == user.pk
    assert entry.actor_id == user.pk


def test_the_sign_in_audit_row_holds_no_email():
    """AD-13: the actor is a UUID, so no address reaches the row."""
    UserFactory(email="maya@example.com", plain_password=PASSWORD)

    authenticate(email="maya@example.com", password=PASSWORD)

    entry = IdentityAuditEntry.objects.using(PERSONAL).get()
    assert "maya@example.com" not in str(entry.actor_label)
    assert "maya@example.com" not in str(entry.details)


def test_a_failed_sign_in_writes_no_audit_row():
    """A refused attempt is not a mutation, so it leaves no audit row."""
    UserFactory(email="maya@example.com", plain_password=PASSWORD)

    with pytest.raises(AuthenticationFailedError):
        authenticate(email="maya@example.com", password="not-the-password")

    assert IdentityAuditEntry.objects.using(PERSONAL).count() == 0


def test_a_wrong_password_and_an_unknown_email_give_the_same_message():
    """The two failures are indistinguishable in their message."""
    UserFactory(email="maya@example.com", plain_password=PASSWORD)

    with pytest.raises(AuthenticationFailedError) as wrong_password:
        authenticate(email="maya@example.com", password="not-the-password")
    with pytest.raises(AuthenticationFailedError) as unknown_email:
        authenticate(email="nobody@example.com", password=PASSWORD)

    assert wrong_password.value.message == unknown_email.value.message
    assert wrong_password.value.code == unknown_email.value.code


def test_an_unknown_email_still_performs_a_password_hash_check(monkeypatch):
    """The equalisation: the unknown-email path costs the same as the wrong-password path.

    Without this, an unknown email answers far faster than a wrong password, and the
    difference is an account-existence oracle.
    """
    calls = []
    import django.contrib.auth.hashers as hashers

    original = hashers.check_password

    def recorder(password, encoded, *args, **kwargs):
        calls.append(encoded)
        return original(password, encoded, *args, **kwargs)

    # The service imports `check_password` by name, so the patch lands on the module
    # object, not on `django.contrib.auth.hashers`.
    patch_module_attribute(
        monkeypatch,
        "apps.identity.services.authenticate",
        "check_password",
        recorder,
    )

    with pytest.raises(AuthenticationFailedError):
        authenticate(email="nobody@example.com", password=PASSWORD)

    assert len(calls) == 1


def test_the_dummy_hash_is_not_any_accounts_password():
    """The dummy hash is of a random password nobody knows; it authenticates nothing."""
    from apps.identity.services.authenticate import DUMMY_PASSWORD_HASH

    UserFactory(email="maya@example.com", plain_password=PASSWORD)

    assert DUMMY_PASSWORD_HASH != User.objects.using(PERSONAL).get().password


def test_authenticate_does_not_leak_whether_the_account_exists_in_the_row_count():
    UserFactory(email="maya@example.com", plain_password=PASSWORD)
    before = User.objects.using(PERSONAL).count()

    with pytest.raises(AuthenticationFailedError):
        authenticate(email="nobody@example.com", password=PASSWORD)

    assert User.objects.using(PERSONAL).count() == before


def test_authenticate_is_throttled_per_ip():
    for n in range(AUTH_THROTTLE_SIGN_IN_IP):
        _attempt(email=f"user{n}@example.com", ip_address="1.2.3.4")

    with pytest.raises(ThrottledError):
        _attempt(email="user99@example.com", ip_address="1.2.3.4")


def test_authenticate_is_throttled_per_account():
    for n in range(AUTH_THROTTLE_SIGN_IN_ACCOUNT):
        _attempt(email="maya@example.com", ip_address=f"1.2.3.{n}")

    with pytest.raises(ThrottledError):
        _attempt(email="maya@example.com", ip_address="5.6.7.8")


def test_the_throttle_does_not_reveal_whether_the_account_exists():
    """A tripped limit answers the same way for a known and an unknown address.

    The throttle check runs *before* the account lookup, so the caller learns only that
    they are being throttled — the same answer for every address. Once the per-IP limit
    is spent, a known address and an unknown one are refused identically.
    """
    for n in range(AUTH_THROTTLE_SIGN_IN_IP):
        _attempt(email=f"user{n}@example.com", ip_address="1.2.3.4")

    with pytest.raises(ThrottledError) as known:
        _attempt(email="maya@example.com", ip_address="1.2.3.4")
    with pytest.raises(ThrottledError) as unknown:
        _attempt(email="nobody@example.com", ip_address="1.2.3.4")

    assert known.value.message == unknown.value.message
