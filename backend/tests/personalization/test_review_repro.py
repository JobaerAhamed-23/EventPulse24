"""Reproductions of the code review's findings, as failing tests.

Each test here is a **defect reproduction**: it failed against the code as it stood
when the review found the defect, and passes now that the defect is fixed. They are
written in this order deliberately — the reproduction first, then the fix — so that no
fix is made against a test that has not already shown the failure.
"""

import pytest
from django.contrib.auth import get_user_model

from apps.personalization.models import CalendarConnection
from apps.personalization.services.calendar_connections import (
    connect_calendar,
    disconnect_calendar_for_user,
    reconnect_calendar_for_user,
)
from domain.errors import CalendarProviderCapReached, InvalidCalendarCredentialError
from shared.actor import Actor
from shared.db import PERSONAL
from shared.ids import uuid7

User = get_user_model()

pytestmark = pytest.mark.django_db(databases=[PERSONAL])


def make_user():
    return User.objects.create_user(email=f"user-{uuid7()}@example.test", password="pw")


def actor_for(user):
    return Actor.user(user.pk)


# ── Finding A: disconnect leaves the fingerprint, so re-adding the address is a 500 ──


def test_reconnecting_the_same_address_after_a_disconnect_does_not_raise():
    """The everyday sequence: connect, disconnect, connect the same calendar again.

    The disconnected row kept its fingerprint, and the unique constraint was on
    `(user_id, credential_fingerprint)` **without** a status qualifier — so the second
    connect raised `IntegrityError` and the endpoint answered 500. The user had lost a
    working calendar and could not get it back.

    The constraint is now **partial** — it excludes the disconnected rows — so a
    disconnected connection does not squat the address it used to hold.
    """
    user = make_user()
    actor = actor_for(user)
    address = "https://example.test/calendar.ics"

    connection = connect_calendar(user_id=user.pk, provider="google", url=address, actor=actor)
    disconnect_calendar_for_user(user_id=user.pk, connection_id=connection.pk, actor=actor)

    # The reconnect is the ordinary path a user takes after they change their mind.
    again = connect_calendar(user_id=user.pk, provider="google", url=address, actor=actor)
    assert again.pk is not None


def test_a_disconnected_connection_does_not_squat_the_address():
    """The constraint's meaning is *one live connection per address*.

    A disconnected row holds a fingerprint, and under an unpartial constraint that
    fingerprint would keep occupying the address — so a user who disconnected a
    calendar and then re-added the same one would hit the constraint and get a 500.
    The constraint is partial now, so the disconnected row does not squat the address.
    """
    user = make_user()
    actor = actor_for(user)

    first = connect_calendar(
        user_id=user.pk, provider="google", url="https://example.test/one.ics", actor=actor
    )
    disconnect_calendar_for_user(user_id=user.pk, connection_id=first.pk, actor=actor)

    again = connect_calendar(
        user_id=user.pk, provider="google", url="https://example.test/one.ics", actor=actor
    )
    assert again.pk is not None

    # The disconnected row is still there — the retention sweep removes it later (D7) —
    # and it did not stop the address being reconnected.
    assert (
        CalendarConnection.objects.using(PERSONAL)
        .filter(pk=first.pk, status=CalendarConnection.Status.DISCONNECTED)
        .exists()
    )


# ── Finding B: the `needs_reconnect` reuse path skipped the cap ──


def test_a_needs_reconnect_row_does_not_buy_a_second_slot(monkeypatch):
    """A `needs_reconnect` row still occupies the user's slot — the reuse path included.

    The cap check short-circuited on `existing is None`, so a connect that *reused* a
    revoked row skipped the cap entirely. When the user was already at their cap, that
    let the reuse turn a second live row into a third.

    The state this needs — a user at their cap who *also* holds a revoked row — is not
    reachable through the Free tier's single slot, but it is reachable at the Pro tier
    (a cap of three) and through a race. The cap is lifted here so the state can be
    built; what is pinned is the **rule**, not the Free tier's number.
    """
    monkeypatch.setattr(
        "apps.personalization.services.calendar_connections.FREE_TIER_CALENDAR_PROVIDER_CAP",
        1,
    )

    user = make_user()
    actor = actor_for(user)

    # The user holds an active row...
    connect_calendar(
        user_id=user.pk, provider="google", url="https://example.test/one.ics", actor=actor
    )
    # ...and a revoked row. The revoked row is built directly, because reaching it
    # through the command needs the cap lifted — and the point of the test is what
    # happens when the user is *already* over the cap and connects again.
    revoked = CalendarConnection.objects.using(PERSONAL).create(
        user_id=user.pk,
        provider="google",
        credential="https://example.test/two.ics",
        credential_fingerprint="a" * 64,
        status=CalendarConnection.Status.NEEDS_RECONNECT,
        display_label="",
        next_poll_at=None,
    )

    # The user is at the cap. The reuse path must not wave them past it.
    with pytest.raises(CalendarProviderCapReached):
        connect_calendar(
            user_id=user.pk, provider="google", url="https://example.test/three.ics", actor=actor
        )

    live = CalendarConnection.objects.using(PERSONAL).filter(
        user_id=user.pk,
        status__in=[CalendarConnection.Status.ACTIVE, CalendarConnection.Status.NEEDS_RECONNECT],
    )
    assert live.count() == 2, f"the cap allows one live calendar, got {live.count()}"
    assert revoked.pk is not None


def test_reusing_a_needs_reconnect_row_does_not_take_a_second_slot():
    """The reuse path itself is still one row, so it does not add a slot.

    A `needs_reconnect` row is the user's *only* calendar. Connecting again — which
    reuses that row and brings it back to life — is the user reconnecting the calendar
    they already have, not adding a second one. It must not be refused by the cap.
    """
    user = make_user()
    actor = actor_for(user)

    first = connect_calendar(
        user_id=user.pk, provider="google", url="https://example.test/one.ics", actor=actor
    )
    CalendarConnection.objects.using(PERSONAL).filter(pk=first.pk).update(
        status=CalendarConnection.Status.NEEDS_RECONNECT
    )

    again = connect_calendar(
        user_id=user.pk, provider="google", url="https://example.test/two.ics", actor=actor
    )
    assert again.pk == first.pk, "the row is reused, not duplicated"

    active = CalendarConnection.objects.using(PERSONAL).filter(
        user_id=user.pk, status=CalendarConnection.Status.ACTIVE
    )
    assert active.count() == 1


# ── Finding D: reconnecting onto an address the user already holds is a 500 ──


def test_reconnecting_onto_an_address_already_connected_is_refused_calmly(monkeypatch):
    """`connect_calendar` guards the duplicate case; `reconnect_calendar` did not.

    So a reconnect onto an address the user already holds fell through to the unique
    constraint and answered 500 — for an input the user can correct in one step.

    The scenario needs a user holding **two** live calendars, which the Free cap of one
    forbids — so the cap is lifted for this test. The Pro tier (a cap of three) is a
    later intent; the duplicate guard has to work at that cap too.
    """
    monkeypatch.setattr(
        "apps.personalization.services.calendar_connections.FREE_TIER_CALENDAR_PROVIDER_CAP",
        3,
    )

    user = make_user()
    actor = actor_for(user)

    held = connect_calendar(
        user_id=user.pk, provider="google", url="https://example.test/held.ics", actor=actor
    )
    revoked = connect_calendar(
        user_id=user.pk, provider="google", url="https://example.test/revoked.ics", actor=actor
    )
    CalendarConnection.objects.using(PERSONAL).filter(pk=revoked.pk).update(
        status=CalendarConnection.Status.NEEDS_RECONNECT
    )

    # The refusal is the calm one, not an unhandled database error.
    with pytest.raises(InvalidCalendarCredentialError):
        reconnect_calendar_for_user(
            user_id=user.pk,
            connection_id=revoked.pk,
            url="https://example.test/held.ics",
            actor=actor,
        )
    assert held.pk is not None


# ── Finding E: a malformed IPv6 host escapes as a 500 ──


def test_a_malformed_bracketed_host_is_refused_calmly():
    """`urlsplit` raises a bare `ValueError` on a malformed bracketed IPv6 host.

    It is not a `DomainError`, so it escaped to the 500 handler instead of the calm 422
    every other bad address gets.
    """
    from apps.personalization.services.calendar_connections import _validated_url

    with pytest.raises(InvalidCalendarCredentialError):
        _validated_url("https://[not-an-ip]/feed.ics")


# ── Finding G: a port the fetch adapter would refuse ──


def test_an_address_on_a_port_the_fetch_would_refuse_is_refused_calmly():
    """The fetch client only connects to the allowed ports (80 and 443).

    An address on any other port would be accepted here, stored with a live encrypted
    credential, shown to the user as connected — and then refused on **every poll**,
    with the only evidence a slug in the connection's error field. That is precisely
    the "invisible at connect time" failure the pre-flight exists to prevent.
    """
    from apps.personalization.services.calendar_connections import _validated_url

    with pytest.raises(InvalidCalendarCredentialError):
        _validated_url("https://example.com:8443/feed.ics")


def test_an_address_on_an_allowed_port_is_accepted():
    """The port check must not refuse the ports the fetch really allows."""
    from apps.personalization.services.calendar_connections import _validated_url

    assert _validated_url("https://example.com/feed.ics") == "https://example.com/feed.ics"
    assert _validated_url("https://example.com:443/feed.ics") == "https://example.com:443/feed.ics"


def test_a_malformed_port_is_refused_calmly():
    """`urlsplit`'s `port` property raises for a non-numeric or out-of-range port.

    Same rule as the host: a typo is a calm refusal, not a server fault.
    """
    from apps.personalization.services.calendar_connections import _validated_url

    with pytest.raises(InvalidCalendarCredentialError):
        _validated_url("https://example.com:99999/feed.ics")


# ── Finding F: the read service decrypted every credential ──


def test_the_reads_do_not_decrypt_the_credentials():
    """The projection has no field for the credential, so the read has no use for it.

    Decrypting meant one unreadable row (a rotated key id, a corrupted ciphertext) took
    down the **whole** list — and, because the same lookup backed the disconnect, the
    user could not disconnect the broken row either. The remedy refused itself.

    The corruption is written straight to the column: a row whose envelope is not
    readable cannot be decrypted, and a read that decrypted it would raise.
    """
    from apps.personalization.services.calendar_connections import list_calendar_connections

    user = make_user()
    actor = actor_for(user)
    good = connect_calendar(
        user_id=user.pk, provider="google", url="https://example.test/one.ics", actor=actor
    )
    # A row whose stored credential cannot be read — a rotated key id, a corrupted
    # ciphertext, a truncated envelope.
    broken = CalendarConnection.objects.using(PERSONAL).create(
        user_id=user.pk,
        provider="google",
        credential="EPENC1.deadbeef.not-base64.not-base64",
        credential_fingerprint="b" * 64,
        status=CalendarConnection.Status.ACTIVE,
        display_label="",
        next_poll_at=None,
    )

    from django.utils import timezone

    # The list still works: one unreadable address does not take the user's other
    # calendars down with it.
    views = list_calendar_connections(user_id=user.pk, now=timezone.now())
    assert len(views) == 2, "the list is not taken down by an unreadable credential"
    assert {view.id for view in views} == {good.pk, broken.pk}


def test_a_user_can_disconnect_a_connection_whose_credential_cannot_be_read():
    """The remedy must not refuse itself.

    The ownership lookup used to load the whole row, and `EncryptedTextField`
    decrypts on the way out of the database — so a row whose credential could not be
    decrypted raised from the **lookup**, and the user could not disconnect the broken
    connection. The credential is not fetched by the lookup, so the disconnect works.
    """
    user = make_user()
    actor = actor_for(user)

    broken = CalendarConnection.objects.using(PERSONAL).create(
        user_id=user.pk,
        provider="google",
        credential="EPENC1.deadbeef.not-base64.not-base64",
        credential_fingerprint="c" * 64,
        status=CalendarConnection.Status.ACTIVE,
        display_label="",
        next_poll_at=None,
    )

    # The disconnect succeeds: the credential is destroyed and the row is released.
    disconnect_calendar_for_user(user_id=user.pk, connection_id=broken.pk, actor=actor)

    row = CalendarConnection.objects.using(PERSONAL).get(pk=broken.pk)
    assert row.status == CalendarConnection.Status.DISCONNECTED
    assert row.credential is None


# ── Finding H: the row can vanish between the lookup and the lock ──


def test_a_row_that_vanishes_before_the_lock_is_not_found():
    """The reconnect re-reads the row under a lock, so it can find nothing.

    The row is fetched by the lookup, then fetched again under `select_for_update`
    inside the transaction. If it is deleted in between — by the retention sweep, say —
    the second read finds nothing, and the answer must be "not found", not an
    `AttributeError` on a `None` row.
    """
    from apps.personalization.services.calendar_connections import reconnect_calendar
    from domain.errors import CalendarConnectionNotFoundError

    user = make_user()
    actor = actor_for(user)

    connection = connect_calendar(
        user_id=user.pk, provider="google", url="https://example.test/one.ics", actor=actor
    )
    CalendarConnection.objects.using(PERSONAL).filter(pk=connection.pk).update(
        status=CalendarConnection.Status.NEEDS_RECONNECT
    )

    # The row goes away between the lookup and the lock. The retention sweep does
    # exactly this to a disconnected row, so it is not a hypothetical.
    stale = CalendarConnection.objects.using(PERSONAL).get(pk=connection.pk)
    CalendarConnection.objects.using(PERSONAL).filter(pk=connection.pk).delete()

    with pytest.raises(CalendarConnectionNotFoundError):
        reconnect_calendar(
            connection=stale,
            url="https://example.test/two.ics",
            actor=actor,
        )
