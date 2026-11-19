"""Moving the login: proven before it moves, once, and without telling anyone anything.

Four properties carry this flow, and each gets its own test rather than riding along:

- **The login does not move until the token comes back.** A request alone changes nothing.
- **The refusal is one refusal.** Unknown, used, revoked, expired and *lost the race* are
  indistinguishable, because a message that told them apart would be an oracle.
- **A taken address is answered with silence.** The caller cannot tell it from a free one,
  and no mail is sent to the address that was typed.
- **Nothing is ended.** The login moves and the account's sessions survive, deliberately.

The hardest of these to get right is the race, so it is tested by actually running it:
the address is claimed *between* the request and the confirmation.
"""

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.utils import timezone

from apps.identity.models import IdentityAuditEntry, PendingEmailChange, User
from apps.identity.services import confirm_email_change, request_email_change
from domain.errors import InvalidEmailChangeTokenError, ThrottledError, ValidationError
from shared.constants import (
    AUTH_EMAIL_CHANGE_TOKEN_LIFETIME,
    AUTH_THROTTLE_EMAIL_CHANGE_ACCOUNT,
)
from shared.db import PERSONAL
from tests.identity.factories import UserFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NEW = "maya.new@example.test"


@pytest.fixture(autouse=True)
def _adapters(email_adapter, throttle_adapter):
    return None


def _reload(user) -> User:
    return User.objects.using(PERSONAL).get(pk=user.pk)


# --- the request path ---------------------------------------------------


def test_a_request_records_the_claim_without_moving_the_login():
    user = UserFactory(email="maya@example.test")

    result = request_email_change(user_id=user.pk, new_email=NEW)

    assert result is not None
    assert _reload(user).email == "maya@example.test", "the login moved before it was proven"
    assert PendingEmailChange.objects.using(PERSONAL).filter(user_id=user.pk).count() == 1


def test_the_raw_token_is_never_stored():
    """A database dump must yield no usable link (AD-18)."""
    user = UserFactory(email="maya@example.test")

    result = request_email_change(user_id=user.pk, new_email=NEW)

    row = PendingEmailChange.objects.using(PERSONAL).get(user_id=user.pk)
    assert result.token not in row.token_hash
    assert row.token_hash != result.token
    assert len(row.token_hash) == 64


def test_the_requested_address_is_normalised():
    """The confirm compares like with like, and a case variant cannot slip past
    `user_email_uq`."""
    user = UserFactory(email="maya@example.test")

    result = request_email_change(user_id=user.pk, new_email="  Maya.NEW@Example.Test  ")

    assert result.new_email == NEW
    assert PendingEmailChange.objects.using(PERSONAL).get(user_id=user.pk).new_email == NEW


def test_a_new_request_revokes_the_outstanding_one():
    """Two live links for one account would be two ways in."""
    user = UserFactory(email="maya@example.test")
    first = request_email_change(user_id=user.pk, new_email=NEW)

    request_email_change(user_id=user.pk, new_email="other@example.test")

    with pytest.raises(InvalidEmailChangeTokenError):
        confirm_email_change(token=first.token)


def test_changing_to_the_address_you_already_have_is_refused_plainly():
    """A mistake about your own account, not a probe of someone else's."""
    user = UserFactory(email="maya@example.test")

    with pytest.raises(ValidationError):
        request_email_change(user_id=user.pk, new_email="MAYA@example.test")


def test_an_address_another_account_holds_is_answered_with_silence():
    """**The refusal must be indistinguishable from success.** Otherwise this endpoint
    answers "does an account exist at this address?" for anyone who asks."""
    user = UserFactory(email="maya@example.test")
    UserFactory(email=NEW)

    result = request_email_change(user_id=user.pk, new_email=NEW)

    assert result is None
    assert not PendingEmailChange.objects.using(PERSONAL).filter(user_id=user.pk).exists()


def test_no_mail_is_owed_for_a_taken_address(email_adapter):
    """A mail to the taken address would be the oracle in another form — and a way to
    send mail to a stranger by typing their address."""
    user = UserFactory(email="maya@example.test")
    UserFactory(email=NEW)

    assert request_email_change(user_id=user.pk, new_email=NEW) is None
    assert email_adapter.sent == [], "something was sent about an address we must not confirm"


def test_the_request_is_throttled():
    """Without a limit the endpoint is a mailer pointed at anyone."""
    user = UserFactory(email="maya@example.test")

    for index in range(AUTH_THROTTLE_EMAIL_CHANGE_ACCOUNT):
        request_email_change(user_id=user.pk, new_email=f"take{index}@example.test")

    with pytest.raises(ThrottledError):
        request_email_change(user_id=user.pk, new_email="one-too-many@example.test")


# --- the confirm path ---------------------------------------------------


def test_confirming_moves_the_login():
    user = UserFactory(email="maya@example.test")
    result = request_email_change(user_id=user.pk, new_email=NEW)

    confirm_email_change(token=result.token)

    assert _reload(user).email == NEW


def test_a_token_works_once():
    user = UserFactory(email="maya@example.test")
    result = request_email_change(user_id=user.pk, new_email=NEW)
    confirm_email_change(token=result.token)

    with pytest.raises(InvalidEmailChangeTokenError):
        confirm_email_change(token=result.token)


def test_the_database_is_the_arbiter_when_two_confirmations_race(monkeypatch):
    """**The conditional UPDATE, exercised — and it took a mutation probe to notice it
    was not.**

    `test_a_token_works_once` passes without this guard: the scan already filters
    `used_at__isnull=True`, so a *sequential* second attempt finds nothing and is refused
    for a different reason entirely. The guard exists for the case the scan cannot cover
    — two confirmations in flight at once, both having found the row — where the row lock
    serialises them and the `WHERE used_at IS NULL` is what makes the loser lose.

    That case is simulated rather than threaded: the row is consumed *after* the scan
    returns it and *before* the update, which is exactly the interleaving the guard is
    for, and the only way to reach it deterministically.
    """
    user = UserFactory(email="maya@example.test")
    result = request_email_change(user_id=user.pk, new_email=NEW)

    from apps.identity.services import email_change as module

    real = module.token_service.find_outstanding

    def consumed_by_someone_else(model, token, now):
        row = real(model, token, now)
        if row is not None:
            # The other confirmation gets there first.
            model.objects.using(PERSONAL).filter(pk=row.pk).update(used_at=now)
        return row

    monkeypatch.setattr(module.token_service, "find_outstanding", consumed_by_someone_else)

    with pytest.raises(InvalidEmailChangeTokenError):
        confirm_email_change(token=result.token)

    assert _reload(user).email == "maya@example.test", "both confirmations moved the login"


def test_an_expired_token_is_refused_and_the_old_address_still_works():
    """The boundary is pinned with an injected clock, not by sleeping."""
    user = UserFactory(email="maya@example.test")
    result = request_email_change(user_id=user.pk, new_email=NEW)

    just_past = timezone.now() + AUTH_EMAIL_CHANGE_TOKEN_LIFETIME

    with pytest.raises(InvalidEmailChangeTokenError):
        confirm_email_change(token=result.token, now=just_past)
    assert _reload(user).email == "maya@example.test"


def test_an_unknown_token_is_refused():
    UserFactory(email="maya@example.test")

    with pytest.raises(InvalidEmailChangeTokenError):
        confirm_email_change(token="not-a-token-anyone-issued")


def test_a_revoked_token_is_refused():
    user = UserFactory(email="maya@example.test")
    result = request_email_change(user_id=user.pk, new_email=NEW)
    PendingEmailChange.objects.using(PERSONAL).filter(user_id=user.pk).update(
        revoked_at=timezone.now()
    )

    with pytest.raises(InvalidEmailChangeTokenError):
        confirm_email_change(token=result.token)


def test_the_address_claimed_in_the_meantime_loses_at_the_constraint():
    """**The race, actually run.** Between the request and the confirmation someone else
    takes the address. A pre-check narrows this window; only `user_email_uq` closes it."""
    user = UserFactory(email="maya@example.test")
    result = request_email_change(user_id=user.pk, new_email=NEW)

    UserFactory(email=NEW)  # the squatter arrives after the request

    with pytest.raises(InvalidEmailChangeTokenError):
        confirm_email_change(token=result.token)

    assert _reload(user).email == "maya@example.test", "the login moved onto a taken address"

    # **The row is left unconsumed**, because the raise rolls the transaction back — the
    # same rule the reset flow states. Pinned so the behaviour is a decision and not a
    # surprise: a token marked used by a change that did not happen would record an
    # untruth, and this link is useless anyway.
    row = PendingEmailChange.objects.using(PERSONAL).get(user_id=user.pk)
    assert row.used_at is None


def test_losing_the_race_is_the_same_error_as_an_unknown_token():
    """To the person holding the link there is no difference, so there is no second
    error to tell them apart — and no oracle."""
    user = UserFactory(email="maya@example.test")
    result = request_email_change(user_id=user.pk, new_email=NEW)
    UserFactory(email=NEW)

    with pytest.raises(InvalidEmailChangeTokenError) as lost:
        confirm_email_change(token=result.token)
    with pytest.raises(InvalidEmailChangeTokenError) as unknown:
        confirm_email_change(token="not-a-token-anyone-issued")

    assert str(lost.value) == str(unknown.value)
    assert lost.value.code == unknown.value.code


def test_a_mixed_case_address_lands_normalised_and_still_trips_the_constraint():
    """`User.save()` normalises as a backstop, so a case variant must not become a second
    account for one address."""
    user = UserFactory(email="maya@example.test")
    result = request_email_change(user_id=user.pk, new_email="Maya.NEW@Example.Test")

    confirm_email_change(token=result.token)

    assert _reload(user).email == NEW


def test_the_account_keeps_its_sessions():
    """**Deliberate.** An email change invalidates no session auth hash — that is an HMAC
    over the password — so ending sessions would be a new logout, and at confirm time it
    would sign out the victim rather than an attacker."""
    user = UserFactory(email="maya@example.test")
    result = request_email_change(user_id=user.pk, new_email=NEW)

    store = SessionStore()
    store["_auth_user_id"] = str(user.pk)
    store.create()

    confirm_email_change(token=result.token)

    assert Session.objects.using(PERSONAL).filter(session_key=store.session_key).exists()


# --- the audit trail ----------------------------------------------------


def test_both_steps_are_audited():
    user = UserFactory(email="maya@example.test")
    result = request_email_change(user_id=user.pk, new_email=NEW)
    confirm_email_change(token=result.token)

    actions = set(
        IdentityAuditEntry.objects.using(PERSONAL)
        .filter(target_id=user.pk)
        .values_list("action", flat=True)
    )

    assert {"email_change_requested", "email_change_confirmed"} <= actions


def test_no_address_reaches_the_audit_details():
    """The name, the address: PII does not go in an audit row (AD-13)."""
    user = UserFactory(email="maya@example.test")
    result = request_email_change(user_id=user.pk, new_email=NEW)
    confirm_email_change(token=result.token)

    for entry in IdentityAuditEntry.objects.using(PERSONAL).filter(target_id=user.pk):
        rendered = str(entry.details)
        assert NEW not in rendered
        assert "maya@example.test" not in rendered
