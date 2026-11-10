"""The combined notice-and-mute read (FR-54, FR-55).

The Detail Screen needs two facts about one event — is it muted, and what is the newest
notice about it — and it needs them **together**, because the banner and the mute control
render from one response and two snapshots could disagree.

**What these tests pin:**

- the read returns **both** facts in one call;
- **`None` is an explicit absence** — no notice for the event is not "an empty notice";
- **a dismissed notice is still reported** — the banner is about *this* event, and
  dismissing the strip on the digest home must not hide "this event was cancelled" from
  the event's own page;
- **the read hands over plain data** — no model instance crosses the app boundary (the
  convention `test_ownership.py` exists to protect);
- **the read is two queries**, and it does not grow with the number of notices;
- **the read is scoped to the user**;
- **the order has a tiebreaker**, so the strip's list and this banner cannot pick
  different rows for the same tie.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.db import connections
from django.test.utils import CaptureQueriesContext

from apps.delivery.models import EventNoticeMute, StateChangeNotice
from apps.delivery.services.notice_state import read_event_notice_state
from apps.delivery.services.state_notices import list_undismissed_notices
from shared.db import PERSONAL
from shared.ids import uuid7

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)

USER = uuid7()
EVENT = uuid7()


def make_notice(
    *, user_id=USER, event_id=EVENT, created_at=NOW, dismissed_at=None, kind="sold_out"
):
    """One notice row, written directly.

    **`created_at` is set after the insert** because the column is `auto_now_add` — the
    database stamps it, and the ordering the read pins is the ordering by that column.
    """
    notice = StateChangeNotice.objects.using(PERSONAL).create(
        user_id=user_id,
        event_id=event_id,
        state_change_id=uuid7(),
        change_kind=kind,
        event_version=2,
        local_date=created_at.date(),
        dismissed_at=dismissed_at,
    )
    StateChangeNotice.objects.using(PERSONAL).filter(pk=notice.pk).update(created_at=created_at)
    notice.refresh_from_db()
    return notice


def mute(*, user_id=USER, event_id=EVENT):
    EventNoticeMute.objects.using(PERSONAL).create(user_id=user_id, event_id=event_id)


# --- The read -----------------------------------------------------------------------------------


def test_the_read_returns_the_mute_and_the_notice_together():
    notice = make_notice()
    mute()

    state = read_event_notice_state(user_id=USER, event_id=EVENT)

    assert state.event_id == EVENT
    assert state.muted is True
    assert state.notice is not None
    assert state.notice.id == notice.id


def test_the_read_reports_no_notice_as_none():
    """**An explicit absence**, not an empty notice. The client has to be able to tell
    "we looked and there is nothing" from "we did not look"."""
    mute()

    state = read_event_notice_state(user_id=USER, event_id=EVENT)

    assert state.notice is None
    assert state.muted is True


def test_the_read_reports_a_dismissed_notice_too():
    """**The banner's rule.** `latest_notice_for_event` ignores `dismissed_at` on
    purpose: the user navigated to this event on purpose, so dismissing the strip on the
    digest home must not hide "this event was cancelled" from the event's own page."""
    make_notice(dismissed_at=NOW)

    state = read_event_notice_state(user_id=USER, event_id=EVENT)

    assert state.notice is not None
    assert state.notice.dismissed_at is not None


def test_the_read_hands_over_plain_data():
    """**No model instance crosses the app boundary.**

    The convention is pinned by `test_ownership.py`, and this is the second place it
    could be broken: `latest_notice_for_event` returns a `StateChangeNotice`, and a
    caller that handed it straight to `personalization` would put a reference to
    `apps.delivery.models` in another app's hands.
    """
    make_notice()

    state = read_event_notice_state(user_id=USER, event_id=EVENT)

    notice = state.notice
    assert notice is not None
    assert not hasattr(notice, "objects")
    assert not hasattr(notice, "save")
    assert not hasattr(notice, "delete")
    assert not hasattr(notice, "pk")


def test_the_read_is_two_queries():
    """**A constant, not a loop.** Two tables, so two reads — and the count does not
    grow with the number of notices."""
    for i in range(10):
        make_notice(created_at=NOW - timedelta(minutes=i))
    mute()

    with CaptureQueriesContext(connections[PERSONAL]) as captured:
        read_event_notice_state(user_id=USER, event_id=EVENT)

    assert len(captured) == 2, "; ".join(str(q["sql"]) for q in captured)


def test_the_read_is_scoped_to_the_user():
    """Another user's notice and another user's mute are both invisible."""
    other = uuid7()
    make_notice(user_id=other)
    mute(user_id=other)

    state = read_event_notice_state(user_id=USER, event_id=EVENT)

    assert state.notice is None
    assert state.muted is False


def test_the_read_reports_the_newest_notice():
    """**Newest first.** The banner names the latest correction, not the first one."""
    make_notice(created_at=NOW - timedelta(hours=2))
    newest = make_notice(created_at=NOW - timedelta(hours=1))

    state = read_event_notice_state(user_id=USER, event_id=EVENT)

    assert state.notice is not None
    assert state.notice.id == newest.id


def test_the_read_carries_the_notices_own_facts():
    """The projection is the whole fact — the id, the kind, the version, the date, and
    the two different acts."""
    notice = make_notice(kind="cancelled")

    state = read_event_notice_state(user_id=USER, event_id=EVENT)

    summary = state.notice
    assert summary is not None
    assert summary.id == notice.id
    assert summary.event_id == EVENT
    assert summary.change_kind == "cancelled"
    assert summary.event_version == 2
    assert summary.local_date == NOW.date()
    assert summary.seen_at is None
    assert summary.dismissed_at is None
    assert summary.created_at == NOW


def test_the_read_does_not_need_the_event_to_exist():
    """AD-3: the `event_id` names a row in `catalog`, and this read never crosses the
    wall to check. A notice for an event that has since gone still reads."""
    gone = uuid4()
    make_notice(event_id=gone)

    state = read_event_notice_state(user_id=USER, event_id=gone)

    assert state.notice is not None
    assert state.notice.event_id == gone


def test_the_banner_is_empty_for_an_event_with_no_notice():
    """An explicit absence, not a default."""
    state = read_event_notice_state(user_id=USER, event_id=uuid4())

    assert state.notice is None


def test_two_notices_raised_at_the_same_instant_have_one_stable_winner():
    """**The tiebreaker, and why it is needed.**

    `created_at` is `auto_now_add` with microsecond resolution, and a single ingestion
    poll can raise several notices at once — so two rows can share a `created_at`. The
    order is `("-created_at", "-id")`, and `-id` is the natural tiebreak because the
    primary key is a UUIDv7, which is time-ordered by construction: of two notices
    raised in the same instant, the later one has the larger id.

    **Without the tiebreaker the strip and the banner could disagree.** The strip's read
    and the banner's read are two queries; the database is free to return either row
    from an unordered tie, and it is free to make a different choice each time. Two
    rules for one question.

    The assertion is that the answer is *stable* — the same row, twice — and that it is
    the larger id, so the rule is stated rather than merely observed.
    """
    first = make_notice(created_at=NOW)
    second = make_notice(created_at=NOW)

    assert first.created_at == second.created_at

    state = read_event_notice_state(user_id=USER, event_id=EVENT)

    assert state.notice is not None
    assert state.notice.id == max(first.id, second.id)

    # And it is stable: the same row, read again.
    again = read_event_notice_state(user_id=USER, event_id=EVENT)
    assert again.notice is not None
    assert again.notice.id == state.notice.id


def test_the_strip_and_the_banner_agree_on_the_newest_notice():
    """**One rule, two reads.** The strip's list and the banner's read must not be able
    to pick different rows for the same event."""
    make_notice(created_at=NOW)
    make_notice(created_at=NOW)

    state = read_event_notice_state(user_id=USER, event_id=EVENT)
    listed = list_undismissed_notices(user_id=USER, limit=10)

    assert state.notice is not None
    assert listed[0].id == state.notice.id
