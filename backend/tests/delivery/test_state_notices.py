"""FR-54's state-change notice: raised once, capped at one a day, silenced by a mute.

**Three rules that FR-54 states as if they were one**, and these tests keep them apart:

- **never repeats** — one notice per `(user, state change)`, held by the unique constraint,
  so a retried propagation adds nothing;
- **at most one per event per day** — a different rule, about *different* changes, resolved
  by `domain.lifecycle.PRECEDENCE`;
- **a muted event is silent** — unless the change is terminal, which is the one place this
  design departs from FR-55's literal wording and is tested as such.

**The cap is not an edge case.** `ingestion.event_writes` appends one `EVENT_STATE_CHANGE`
per kind within a single poll, so a source update that moves an event's time *and* marks it
sold out produces two changes seconds apart. The tests below use that shape deliberately.
"""

from datetime import UTC, datetime, time, timedelta

import pytest

from apps.delivery.models import EventNoticeMute, ScheduledSend, StateChangeNotice
from apps.delivery.send_keys import state_notice_key
from apps.delivery.services.mutes import mute_event_notices
from apps.delivery.services.notice_state import read_event_notice_state
from apps.delivery.services.notification_preferences import set_quiet_hours
from apps.delivery.services.state_notices import (
    dismiss_notice,
    list_undismissed_notices,
    mark_seen,
    raise_state_notice,
)
from domain.lifecycle import ChangeKind
from domain.quiet_hours import QuietHours
from ports.email import Stream
from shared.actor import Actor
from shared.db import PERSONAL
from shared.ids import uuid7
from tests.personalization.factories import DigestPreferenceFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

#: Midday UTC, which is 04:00 in the test zone — outside the default quiet window either way.
NOW = datetime(2026, 11, 1, 20, 0, tzinfo=UTC)  # 12:00 in Los Angeles
#: Far enough out that the `1hr` lead margin never fires unless a test asks for it.
START = datetime(2026, 11, 20, 3, 0, tzinfo=UTC)
TZ = "America/Los_Angeles"

USER = uuid7()
EVENT = uuid7()
SYSTEM = Actor.system("propagation")


@pytest.fixture(autouse=True)
def _zone():
    """Every test needs a zone, because the cap is keyed on the user's *local* date."""
    DigestPreferenceFactory(user_id=USER, timezone=TZ, delivery_time=time(9, 0))


def raise_notice(
    *,
    kind=ChangeKind.SOLD_OUT,
    version=2,
    user_id=USER,
    event_id=EVENT,
    start=START,
    now=NOW,
    state_change_id=None,
    before=None,
    after=None,
):
    """Raise one notice, the way `worker.propagation` raises it.

    **`before`/`after` are the change's own facts.** A `detail_changed` is only
    notified when it moved the venue — that is the PRD's "moved to [new location]"
    subject, and the PRD names no subject for a title edit — so a test that wants a
    `detail_changed` notice has to say it moved the venue. `detail_changed` is
    otherwise the least important kind in `PRECEDENCE`, which is what several tests
    below rely on it for.
    """
    return raise_state_notice(
        user_id=user_id,
        event_id=event_id,
        state_change_id=state_change_id or uuid7(),
        change_kind=kind.value if isinstance(kind, ChangeKind) else kind,
        event_version=version,
        event_start_utc=start,
        actor=SYSTEM,
        now=now,
        before=before,
        after=after,
    )


#: A `detail_changed` that moved the venue — the one `detail_changed` that is notified.
#:
#: **The fingerprints differ, so the venue moved.** `venue_fingerprint` is a hash of the
#: venue's identity, so two different fingerprints are two different venues; a change
#: that moved the venue records both.
VENUE_MOVED = {
    "before": {"venue_fingerprint": "sha256:old"},
    "after": {"venue_fingerprint": "sha256:new"},
}


def notices(user_id=USER):
    return StateChangeNotice.objects.using(PERSONAL).filter(user_id=user_id)


def pending_sends(user_id=USER):
    return ScheduledSend.objects.using(PERSONAL).filter(
        user_id=user_id,
        kind=ScheduledSend.Kind.STATE_NOTICE,
        status=ScheduledSend.Status.PENDING,
    )


# --- Raising, and "never repeats" --------------------------------------------------------------


def test_a_change_raises_one_notice_and_one_email():
    assert raise_notice() is True

    assert notices().count() == 1
    assert pending_sends().count() == 1


def test_the_notice_records_what_happened():
    change_id = uuid7()

    raise_notice(kind=ChangeKind.CANCELLED, version=7, state_change_id=change_id)

    notice = notices().get()
    assert notice.event_id == EVENT
    assert notice.state_change_id == change_id
    assert notice.change_kind == ChangeKind.CANCELLED.value
    assert notice.event_version == 7
    # 20:00 UTC is 12:00 in Los Angeles — the user's day, not the server's.
    assert notice.local_date == date_in_la(NOW)


def date_in_la(instant):
    from zoneinfo import ZoneInfo

    return instant.astimezone(ZoneInfo(TZ)).date()


def test_the_same_state_change_twice_raises_one_notice():
    """ "Never repeats" (FR-54) is about a retried propagation, not a second event."""
    change_id = uuid7()

    assert raise_notice(state_change_id=change_id) is True
    assert raise_notice(state_change_id=change_id) is False

    assert notices().count() == 1
    assert pending_sends().count() == 1


def test_a_concurrent_duplicate_is_refused_by_the_constraint_not_a_crash():
    """ "Never repeats" is the database's guarantee, and this is why it has to be.

    Two workers propagating the same state change for the same user both get past the
    version gate — neither has committed, so neither can see the other. A `SELECT` guard
    would read like protection and give none. The unique constraint is the only atomic
    answer, and `raise_state_notice` has to survive it: a refused insert means "already
    raised", not a 500 in the middle of propagation.

    The other worker's commit is simulated by writing its row directly, at a version low
    enough that the version gate does not absorb it — which is the only way to reach the
    constraint from a single thread.
    """
    change_id = uuid7()
    StateChangeNotice.objects.using(PERSONAL).create(
        user_id=USER,
        event_id=EVENT,
        state_change_id=change_id,
        change_kind=ChangeKind.SOLD_OUT.value,
        event_version=1,
        local_date=date_in_la(NOW),
    )

    assert raise_notice(state_change_id=change_id, kind=ChangeKind.CANCELLED, version=9) is False

    assert notices().count() == 1


def test_a_refused_duplicate_does_not_leave_the_caps_deletions_behind():
    """Why the `IntegrityError` is caught **outside** the transaction, not around the insert.

    The cap runs before the insert and *deletes* the day's less important notices, cancelling
    their emails. If the insert then fails, a savepoint around the insert alone would let
    the surrounding block commit — and the user would lose a notice that was already raised
    and already due to be emailed, in exchange for one that was never created.

    The whole block has to roll back together. This test is that rollback.
    """
    # Today's notice, which the cap would supersede because it ranks below `time_moved`.
    doomed_change = uuid7()
    raise_notice(
        kind=ChangeKind.DETAIL_CHANGED,
        version=2,
        state_change_id=doomed_change,
        before=VENUE_MOVED["before"],
        after=VENUE_MOVED["after"],
    )
    assert notices().count() == 1

    # Another event's notice already owns the id the new change will try to claim.
    taken_id = uuid7()
    raise_notice(event_id=uuid7(), kind=ChangeKind.SOLD_OUT, version=2, state_change_id=taken_id)

    # A more important change for the first event, carrying the taken id: the cap fires,
    # then the insert is refused.
    assert raise_notice(kind=ChangeKind.TIME_MOVED, version=3, state_change_id=taken_id) is False

    # The superseded notice is still there, and its email is still pending.
    survivor = notices().get(event_id=EVENT)
    assert survivor.state_change_id == doomed_change
    assert survivor.change_kind == ChangeKind.DETAIL_CHANGED.value
    doomed_key = state_notice_key(user_id=USER, state_change_id=doomed_change)
    assert (
        ScheduledSend.objects.using(PERSONAL).get(send_key=doomed_key).status
        == ScheduledSend.Status.PENDING
    )


def test_the_callers_transaction_survives_a_refused_duplicate():
    """A duplicate is an answer, not a crash.

    AD-17's propagation applies a whole user in one transaction. An `IntegrityError` that
    escaped would take down every other write for that user.
    """
    change_id = uuid7()
    StateChangeNotice.objects.using(PERSONAL).create(
        user_id=USER,
        event_id=EVENT,
        state_change_id=change_id,
        change_kind=ChangeKind.SOLD_OUT.value,
        event_version=1,
        local_date=date_in_la(NOW),
    )

    assert raise_notice(state_change_id=change_id, kind=ChangeKind.CANCELLED, version=9) is False

    # The connection is still usable: a later write in the same test succeeds.
    assert raise_notice(event_id=uuid7(), kind=ChangeKind.CANCELLED, version=2) is True


def test_an_older_version_raises_nothing():
    """AD-17: an out-of-order run can never apply behind a newer one."""
    raise_notice(version=5)

    assert raise_notice(version=4, kind=ChangeKind.CANCELLED) is False
    assert notices().count() == 1


def test_the_same_version_again_raises_nothing():
    """The gate is `>=`, so a re-delivered change at the version already held is refused."""
    raise_notice(version=5)

    assert raise_notice(version=5, kind=ChangeKind.CANCELLED) is False


def test_a_notice_is_scoped_to_its_user():
    other = uuid7()
    DigestPreferenceFactory(user_id=other, timezone=TZ, delivery_time=time(9, 0))

    raise_notice(user_id=USER)

    assert notices(USER).count() == 1
    assert notices(other).count() == 0


# --- The `detail_changed` rule (FR-54's third subject, and FR-53's silence) -------------------


def test_a_detail_change_that_moved_the_venue_is_notified():
    """**The PRD's third subject — "moved to [new location]" — lives here.**

    `domain.lifecycle.classify_change` files a venue move under `detail_changed`, because
    `venue_fingerprint` is one of its detail facts. So the PRD's own subject has no kind of
    its own, and silencing `detail_changed` wholesale would silence the subject the work
    item asks for.

    The rule is therefore about the *change*, not the kind: a `detail_changed` whose venue
    fingerprints differ is notified.
    """
    assert (
        raise_notice(
            kind=ChangeKind.DETAIL_CHANGED,
            before=VENUE_MOVED["before"],
            after=VENUE_MOVED["after"],
        )
        is True
    )

    assert notices().count() == 1
    assert pending_sends().count() == 1


def test_a_detail_change_that_moved_nothing_is_not_notified():
    """FR-53: not every change deserves a notification — "would be engagement-trap".

    A title edit, a description edit, a URL edit and a timezone-label edit are all
    `detail_changed`, and none of them has a reminder consequence:
    `LIFECYCLE_SEND_BEHAVIOUR` maps `detail_changed` to `KEEP`, so the reminders do not
    move. **FR-54's body requirement is "what changed and what it means for the user's
    reminders", and a title edit has no such meaning.**

    **And it is silenced at the source, not in the renderer.** A notice that was raised and
    then refused at render time would still have consumed the day's cap slot and still be
    sitting in the user's in-app strip saying nothing.
    """
    assert (
        raise_notice(
            kind=ChangeKind.DETAIL_CHANGED,
            before={"title": "Rooftop Cinema"},
            after={"title": "Rooftop Cinema: Late Night"},
        )
        is False
    )

    assert notices().count() == 0
    assert pending_sends().count() == 0


def test_a_detail_change_that_did_not_touch_the_venue_is_not_notified():
    """The ordinary case for a `detail_changed` — no fingerprints at all.

    **The two reads are compared rather than the after's presence being tested.** A change
    that *recorded* a fingerprint but did not change it is not a move either, and a change
    that recorded none at all has certainly not moved the venue.
    """
    assert (
        raise_notice(
            kind=ChangeKind.DETAIL_CHANGED,
            before={"venue_fingerprint": "sha256:same"},
            after={"venue_fingerprint": "sha256:same"},
        )
        is False
    )

    assert notices().count() == 0


def test_a_silenced_detail_change_does_not_consume_the_days_cap():
    """**The silence comes before the cap, and that ordering matters.**

    A silenced change must not cancel a newer notice on its way to being refused, and it
    must not consume the day's one slot — otherwise a typo fix would silence the
    cancellation that followed it, which is the one message FR-54 most requires.
    """
    raise_notice(kind=ChangeKind.TIME_MOVED, version=2)

    assert (
        raise_notice(
            kind=ChangeKind.DETAIL_CHANGED,
            version=3,
            before={"title": "Rooftop Cinema"},
            after={"title": "Rooftop Cinema: Late Night"},
        )
        is False
    )

    assert [n.change_kind for n in notices()] == [ChangeKind.TIME_MOVED.value]
    assert pending_sends().count() == 1


# --- The one-per-day cap -----------------------------------------------------------------------


def test_a_less_important_change_the_same_day_raises_nothing():
    """`detail_changed` ranks below `time_moved` in `PRECEDENCE`.

    **The `detail_changed` here moved the venue**, so it is a notice the cap has to
    refuse — not one that was silenced before the cap was ever consulted. A `detail_changed`
    that fixed a title is silenced earlier, and is tested there.
    """
    raise_notice(kind=ChangeKind.TIME_MOVED, version=2)

    assert (
        raise_notice(
            kind=ChangeKind.DETAIL_CHANGED,
            version=3,
            before=VENUE_MOVED["before"],
            after=VENUE_MOVED["after"],
        )
        is False
    )

    assert [n.change_kind for n in notices()] == [ChangeKind.TIME_MOVED.value]
    assert pending_sends().count() == 1


def test_an_equally_important_change_the_same_day_raises_nothing():
    """The boundary. The rule is "at least as important wins", not "strictly more"."""
    raise_notice(kind=ChangeKind.SOLD_OUT, version=2)

    assert raise_notice(kind=ChangeKind.SOLD_OUT, version=3) is False

    assert notices().count() == 1


def test_a_more_important_change_replaces_the_days_notice():
    """FR-54 asks for *a single, calm* notification, not a stack of them."""
    raise_notice(
        kind=ChangeKind.DETAIL_CHANGED,
        version=2,
        before=VENUE_MOVED["before"],
        after=VENUE_MOVED["after"],
    )

    assert raise_notice(kind=ChangeKind.TIME_MOVED, version=3) is True

    assert [n.change_kind for n in notices()] == [ChangeKind.TIME_MOVED.value]


def test_replacing_cancels_the_superseded_email():
    """A replaced notice must not still be sitting in the send ledger, due to go out."""
    first_change = uuid7()
    raise_notice(
        kind=ChangeKind.DETAIL_CHANGED,
        version=2,
        state_change_id=first_change,
        before=VENUE_MOVED["before"],
        after=VENUE_MOVED["after"],
    )
    first_key = state_notice_key(user_id=USER, state_change_id=first_change)

    raise_notice(kind=ChangeKind.TIME_MOVED, version=3)

    superseded = ScheduledSend.objects.using(PERSONAL).get(send_key=first_key)
    assert superseded.status == ScheduledSend.Status.CANCELLED
    assert pending_sends().count() == 1


def test_the_cap_is_per_event():
    """Two different events on one day are two different notices, not spam."""
    other_event = uuid7()

    raise_notice(event_id=EVENT, version=2)
    assert raise_notice(event_id=other_event, version=2) is True

    assert notices().count() == 2


def test_the_cap_is_per_day():
    """Tomorrow is a new day, and the same kind may be raised again."""
    raise_notice(kind=ChangeKind.SOLD_OUT, version=2)

    assert raise_notice(kind=ChangeKind.SOLD_OUT, version=3, now=NOW + timedelta(days=1)) is True

    assert notices().count() == 2


def test_the_day_is_the_users_day_not_the_servers():
    """23:00 UTC and 02:00 UTC the next day are the same Los Angeles date.

    A cap keyed on the server's date would let a second notice through at UTC midnight,
    which for this user is the middle of the same evening.
    """
    evening = datetime(2026, 11, 1, 23, 0, tzinfo=UTC)  # 16:00 in LA
    after_utc_midnight = datetime(2026, 11, 2, 2, 0, tzinfo=UTC)  # 19:00 in LA, same day
    assert date_in_la(evening) == date_in_la(after_utc_midnight)

    raise_notice(kind=ChangeKind.SOLD_OUT, version=2, now=evening)

    assert raise_notice(kind=ChangeKind.SOLD_OUT, version=3, now=after_utc_midnight) is False


def test_an_unknown_change_kind_outranks_nothing_and_does_not_raise():
    """A kind `domain.lifecycle` gained without this module being told must degrade, not crash."""
    raise_notice(
        kind=ChangeKind.DETAIL_CHANGED,
        version=2,
        before=VENUE_MOVED["before"],
        after=VENUE_MOVED["after"],
    )

    assert raise_notice(kind="invented_kind", version=3) is False


# --- The mute (FR-55) --------------------------------------------------------------------------


def test_a_muted_event_raises_nothing():
    mute_event_notices(user_id=USER, event_id=EVENT, actor=Actor.user(USER), now=NOW)

    assert raise_notice(kind=ChangeKind.SOLD_OUT) is False

    assert notices().count() == 0
    assert pending_sends().count() == 0


def test_a_mute_is_scoped_to_its_event():
    other_event = uuid7()
    mute_event_notices(user_id=USER, event_id=EVENT, actor=Actor.user(USER), now=NOW)

    assert raise_notice(event_id=other_event) is True


def test_a_mute_is_scoped_to_its_user():
    other = uuid7()
    DigestPreferenceFactory(user_id=other, timezone=TZ, delivery_time=time(9, 0))
    mute_event_notices(user_id=USER, event_id=EVENT, actor=Actor.user(USER), now=NOW)

    assert raise_notice(user_id=other, event_id=EVENT) is True


# --- The terminal exception --------------------------------------------------------------------
#
# A `cancelled` or `superseded` change overrides both the cap and a mute. This is the one
# place the design departs from the AC's literal wording, so it is tested from both sides.


@pytest.mark.parametrize("kind", [ChangeKind.CANCELLED, ChangeKind.SUPERSEDED])
def test_a_terminal_change_reaches_a_muted_event(kind):
    """A mute means "stop telling me about tweaks", not "do not tell me it is off".

    FR-55 has already removed a cancelled event from the digest, so silence here is the
    one failure with no second channel to catch it.
    """
    mute_event_notices(user_id=USER, event_id=EVENT, actor=Actor.user(USER), now=NOW)

    assert raise_notice(kind=kind, version=3) is True

    assert notices().count() == 1


@pytest.mark.parametrize("kind", [ChangeKind.CANCELLED, ChangeKind.SUPERSEDED])
def test_a_terminal_change_overrides_the_days_cap(kind):
    raise_notice(kind=ChangeKind.SOLD_OUT, version=2)

    assert raise_notice(kind=kind, version=3) is True

    assert notices().count() == 2
    assert pending_sends().count() == 2


def test_a_terminal_change_does_not_cancel_the_earlier_email():
    """Two emails, deliberately: the earlier one may already have gone, and the bound is two.

    The sold-out notice is left alone rather than superseded — the user is told the event
    sold out *and* that it was then cancelled, which is the honest sequence.
    """
    raise_notice(kind=ChangeKind.SOLD_OUT, version=2)

    raise_notice(kind=ChangeKind.CANCELLED, version=3)

    assert pending_sends().count() == 2


def test_postponed_is_not_terminal():
    """The mutation that makes `TERMINAL_KINDS` a decision rather than "anything that cancels".

    A postponement also stops a reminder going out, and is exactly the calm, deferrable
    news the cap exists for — so it is capped like any other change.
    """
    raise_notice(kind=ChangeKind.POSTPONED, version=2)

    assert raise_notice(kind=ChangeKind.POSTPONED, version=3) is False


def test_postponed_does_not_reach_a_muted_event():
    mute_event_notices(user_id=USER, event_id=EVENT, actor=Actor.user(USER), now=NOW)

    assert raise_notice(kind=ChangeKind.POSTPONED, version=3) is False


# --- The email: stream, Quiet Hours, and the lead margin ---------------------------------------


def test_the_email_is_transactional_with_no_unsubscribe_url():
    """AD-20. `ScheduledSend.stream` has no default, so this is a decision, not an inheritance."""
    raise_notice()

    send = pending_sends().get()
    assert send.stream == Stream.TRANSACTIONAL.value


def test_the_email_has_no_slot_and_no_slot_at():
    """A state notice's moment is *now*, not an offset from the event's start."""
    raise_notice()

    send = pending_sends().get()
    assert send.slot == ""
    assert send.slot_at is None


def test_quiet_hours_defer_the_notice():
    """A state notice has no slot, but Quiet Hours still apply to it (AD-7)."""
    set_quiet_hours(
        user_id=USER,
        window=QuietHours(start=time(22, 0), end=time(8, 0)),
        actor=Actor.user(USER),
        now=NOW,
    )
    # 07:00 UTC is 23:00 the previous evening in Los Angeles — inside the window.
    inside = datetime(2026, 11, 2, 7, 0, tzinfo=UTC)

    raise_notice(now=inside, start=START)

    send = pending_sends().get()
    assert send.due_at > inside


def test_a_notice_is_not_deferred_past_the_point_of_being_useful():
    """Decision 8, with the margin being the `1hr` slot rather than the event's start.

    A notice landing ninety seconds before the doors open is technically in time and no use
    at all, so the margin is the tightest reminder a user can choose: a notice that cannot
    beat the `1hr` reminder is not actionable either.
    """
    set_quiet_hours(
        user_id=USER,
        window=QuietHours(start=time(22, 0), end=time(8, 0)),
        actor=Actor.user(USER),
        now=NOW,
    )
    inside = datetime(2026, 11, 2, 7, 0, tzinfo=UTC)  # 23:00 in LA, deferred to 08:00 LA
    # The event starts half an hour after the window ends, so the deferred notice would land
    # inside the `1hr` margin.
    starts_soon = datetime(2026, 11, 2, 16, 30, tzinfo=UTC)  # 08:30 in LA

    raise_notice(now=inside, start=starts_soon)

    send = pending_sends().get()
    assert send.due_at == inside


def test_an_event_starting_inside_the_quiet_window_always_notifies_at_once():
    """Every deferral available is already too late, on both sides of the window."""
    set_quiet_hours(
        user_id=USER,
        window=QuietHours(start=time(22, 0), end=time(8, 0)),
        actor=Actor.user(USER),
        now=NOW,
    )
    inside = datetime(2026, 11, 2, 7, 0, tzinfo=UTC)  # 23:00 in LA
    starts_in_the_window = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)  # 01:00 in LA

    raise_notice(now=inside, start=starts_in_the_window)

    assert pending_sends().get().due_at == inside


def test_a_notice_for_an_event_the_catalog_no_longer_holds_is_still_deferred():
    """With no start there is nothing to be late for, so the quiet window applies in full."""
    set_quiet_hours(
        user_id=USER,
        window=QuietHours(start=time(22, 0), end=time(8, 0)),
        actor=Actor.user(USER),
        now=NOW,
    )
    inside = datetime(2026, 11, 2, 7, 0, tzinfo=UTC)

    raise_notice(kind=ChangeKind.SUPERSEDED, now=inside, start=None)

    assert pending_sends().get().due_at > inside


# --- The reads, and what "seen" means -----------------------------------------------------------


def test_the_strip_lists_undismissed_notices_newest_first():
    raise_notice(kind=ChangeKind.SOLD_OUT, version=2)
    raise_notice(event_id=uuid7(), kind=ChangeKind.CANCELLED, version=2)

    listed = list_undismissed_notices(user_id=USER, limit=10)

    assert len(listed) == 2
    assert listed[0].created_at >= listed[1].created_at


def test_the_strip_read_is_bounded_at_the_service_too():
    """**The bound is in the service, not only at the surface.**

    The API passes `NOTICE_STRIP_LIMIT`, but the limit is the *service's* contract: a
    caller that forgot to pass one would otherwise get every open notice, and "someone
    forgot the limit" is exactly the failure the bound exists to prevent. It is a
    **required** keyword argument, so the unbounded call is not merely discouraged — it
    is inexpressible.
    """
    for _ in range(5):
        raise_notice(event_id=uuid7())

    listed = list_undismissed_notices(user_id=USER, limit=2)

    assert len(listed) == 2


def test_the_strip_keeps_the_newest_when_it_is_bounded():
    """The bound drops the **tail**, not the head — the newest corrections are the ones
    the user has not seen."""
    raise_notice(event_id=uuid7())
    raise_notice(event_id=uuid7())
    newest = notices().order_by("-created_at").first()

    listed = list_undismissed_notices(user_id=USER, limit=1)

    assert len(listed) == 1
    assert listed[0].id == newest.id


def test_dismissing_removes_it_from_the_strip():
    raise_notice()
    notice = notices().get()

    assert dismiss_notice(user_id=USER, notice_id=notice.id, actor=Actor.user(USER), now=NOW)

    assert list_undismissed_notices(user_id=USER, limit=10) == []


def test_dismissing_twice_reports_no_change():
    raise_notice()
    notice = notices().get()
    dismiss_notice(user_id=USER, notice_id=notice.id, actor=Actor.user(USER), now=NOW)

    assert (
        dismiss_notice(user_id=USER, notice_id=notice.id, actor=Actor.user(USER), now=NOW) is False
    )


def test_a_dismissed_notice_still_shows_on_its_own_event():
    """Dismissing a strip on the digest home must not hide "this was cancelled" from the
    event's own page. The banner is about an event the user navigated to on purpose.

    **The rule now lives in `services.notice_state`**, which owns the read that the
    Detail Screen calls — so the test moved with it, to `test_notice_state.py`."""
    raise_notice(kind=ChangeKind.CANCELLED)
    notice = notices().get()
    dismiss_notice(user_id=USER, notice_id=notice.id, actor=Actor.user(USER), now=NOW)

    state = read_event_notice_state(user_id=USER, event_id=EVENT)

    assert state.notice is not None
    assert state.notice.id == notice.id


def test_seen_is_not_dismissed():
    """Two columns because they are two acts: being shown something is not closing it."""
    raise_notice()
    notice = notices().get()

    mark_seen(user_id=USER, notice_ids=[notice.id], now=NOW)

    notice.refresh_from_db()
    assert notice.seen_at == NOW
    assert notice.dismissed_at is None
    assert len(list_undismissed_notices(user_id=USER, limit=10)) == 1


def test_seen_records_the_first_sighting_not_the_last():
    """A column that moved on every render would answer "when did we last draw this"."""
    raise_notice()
    notice = notices().get()
    mark_seen(user_id=USER, notice_ids=[notice.id], now=NOW)

    moved = mark_seen(user_id=USER, notice_ids=[notice.id], now=NOW + timedelta(hours=2))

    notice.refresh_from_db()
    assert moved == 0
    assert notice.seen_at == NOW


def test_marking_another_users_notice_seen_does_nothing():
    raise_notice()
    notice = notices().get()

    assert mark_seen(user_id=uuid7(), notice_ids=[notice.id], now=NOW) == 0


def test_dismissing_another_users_notice_does_nothing():
    raise_notice()
    notice = notices().get()

    assert (
        dismiss_notice(user_id=uuid7(), notice_id=notice.id, actor=Actor.user(uuid7()), now=NOW)
        is False
    )
    notice.refresh_from_db()
    assert notice.dismissed_at is None


# --- The mute's own table ------------------------------------------------------------------------


def test_muting_is_idempotent():
    first = mute_event_notices(user_id=USER, event_id=EVENT, actor=Actor.user(USER), now=NOW)
    second = mute_event_notices(user_id=USER, event_id=EVENT, actor=Actor.user(USER), now=NOW)

    assert first.changed is True
    assert second.changed is False
    assert EventNoticeMute.objects.using(PERSONAL).filter(user_id=USER).count() == 1
