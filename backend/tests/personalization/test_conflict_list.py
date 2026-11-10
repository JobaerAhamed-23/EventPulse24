"""The conflict list (FR-33): every pair, both sides, by name.

`ConflictPair`'s own docstring says the Pulse Card indicator, the Timeline indicator and
`/conflicts` all read these rows — so these tests pin what that read has to give back.

**What is pinned here:**

- **Ownership.** The list is the caller's alone. Another user's pairs are not in it, and
  an anonymous caller is refused.
- **Both sides, named.** A pair shows both sides; a saved side is named by its **catalog**
  title, not by the placeholder the personal side carries.
- **A side that is gone.** A saved event whose catalog event has disappeared reads as an
  explicit "event no longer available" — not a crash, and not a blank name.
- **The status split.** `cleared_by_state_change` pairs are not the user's history, so
  they are not listed.
- **Ordering.** Active pairs soonest-first by the earlier side's start; resolved pairs
  newest-first by resolution time.
- **The query bound.** The list costs a constant number of queries, whatever the number of
  pairs — the property that lets the whole list be read in one pass.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.test.utils import CaptureQueriesContext

from apps.personalization.models import ConflictPair
from apps.personalization.services.conflict_list import list_conflict_pairs
from shared.db import CATALOG, PERSONAL
from tests.csrf import CsrfClient
from tests.ingestion.factories import EventFactory
from tests.personalization.factories import (
    ConflictPairFactory,
    PersonalEventFactory,
    SavedEventFactory,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()

START = datetime(2026, 11, 6, 3, 30, tzinfo=UTC)
HOUR = timedelta(hours=1)
TZ = "America/Los_Angeles"


def make_user(email="sam@example.test"):
    """A real user with a real pk — the session resolves to this one."""
    return User.objects.create_user(email=email, password="pw")


def signed_in(user=None):
    """A client whose session identifies `user`."""
    client = CsrfClient()
    client.force_login(user or make_user())
    return client


def personal_event(user, *, name="Coffee with Sam", start=START):
    """A personal event on the user's calendar."""
    return PersonalEventFactory(
        user_id=user.pk,
        name=name,
        start_utc=start,
        end_utc=start + timedelta(hours=2),
        start_time_tz=TZ,
    )


def saved_event(user, *, event=None, start=START):
    """A save of a public catalog event, with the catalog event behind it.

    The catalog event is created first so the save has a real title to be named by — the
    whole point of the saved side's name.
    """
    if event is None:
        event = EventFactory(start_time_utc=start, end_time_utc=start + timedelta(hours=2))
    saved = SavedEventFactory(
        user_id=user.pk,
        event_id=event.id,
        start_utc=start,
        end_utc=start + timedelta(hours=2),
        event_version=1,
    )
    return saved, event


def pair(user, *, left_kind, left_id, right_kind, right_id, kind="time", **extra):
    """A conflict pair for the user, with the sides in the row's normalised order.

    The row is normalised on `(kind, id)`, so the test sorts the sides the same way the
    command layer does — otherwise the factory writes a row the unique constraint would
    reject, or a row whose `left`/`right` do not match the pair the test means.
    """
    sides = sorted(
        [(left_kind, left_id), (right_kind, right_id)],
        key=lambda side: (side[0], str(side[1])),
    )
    return ConflictPairFactory(
        user_id=user.pk,
        kind=kind,
        left_kind=sides[0][0],
        left_id=sides[0][1],
        right_kind=sides[1][0],
        right_id=sides[1][1],
        **extra,
    )


# --- Ownership -------------------------------------------------------------------------------


def test_the_list_holds_only_the_callers_pairs():
    user = make_user("sam@example.test")
    other = make_user("other@example.test")
    mine = personal_event(user, name="Mine")
    theirs = personal_event(other, name="Theirs")
    pair(
        user,
        left_kind="personal_event",
        left_id=mine.id,
        right_kind="personal_event",
        right_id=theirs.id,
    )

    result = list_conflict_pairs(user_id=user.pk)

    names = {view.left.name for view in result.active} | {view.right.name for view in result.active}
    assert "Mine" in names
    assert "Theirs" not in names


def test_another_users_pairs_are_not_in_the_list():
    user = make_user("sam@example.test")
    other = make_user("other@example.test")
    event = personal_event(other, name="Theirs")
    pair(
        other,
        left_kind="personal_event",
        left_id=event.id,
        right_kind="personal_event",
        right_id=uuid4(),
    )

    result = list_conflict_pairs(user_id=user.pk)

    assert result.active == ()
    assert result.resolved == ()


def test_an_anonymous_caller_is_refused():
    client = CsrfClient()

    response = client.get("/api/personal/conflicts")

    assert response.status_code == 401


# --- Both sides, named ------------------------------------------------------------------------


def test_a_pair_carries_both_sides():
    user = make_user()
    first = personal_event(user, name="Coffee with Sam")
    second = personal_event(user, name="Coffee with Alex", start=START + timedelta(minutes=30))
    pair(
        user,
        left_kind="personal_event",
        left_id=first.id,
        right_kind="personal_event",
        right_id=second.id,
    )

    result = list_conflict_pairs(user_id=user.pk)

    assert len(result.active) == 1
    view = result.active[0]
    assert {view.left.name, view.right.name} == {"Coffee with Sam", "Coffee with Alex"}
    assert {view.left.kind, view.right.kind} == {"personal_event"}


def test_a_saved_side_is_named_by_its_catalog_title():
    # The whole point: a save has no title in `personal` — the title lives in `catalog`.
    user = make_user()
    event = personal_event(user, name="Coffee with Sam")
    saved, public = saved_event(user)
    pair(
        user,
        left_kind="personal_event",
        left_id=event.id,
        right_kind="saved_event",
        right_id=saved.id,
    )

    result = list_conflict_pairs(user_id=user.pk)

    view = result.active[0]
    saved_view = view.left if view.left.kind == "saved_event" else view.right
    assert saved_view.name == public.title
    assert saved_view.kind == "saved_event"
    assert saved_view.available is True


def test_both_side_kinds_appear_in_both_positions_of_the_normalised_pair():
    # The row stores the sides sorted on `(kind, id)`, so a personal side can land on
    # either side of the row. Both positions must be read correctly.
    user = make_user()
    personal = personal_event(user, name="Coffee with Sam")
    saved, public = saved_event(user)

    # `personal_event` sorts before `saved_event`, so this pair puts the personal side
    # on the left.
    pair(
        user,
        left_kind="personal_event",
        left_id=personal.id,
        right_kind="saved_event",
        right_id=saved.id,
    )
    # And a second pair, written with the sides the other way round, must normalise to the
    # same shape — so the saved side is still read correctly.
    personal2 = personal_event(user, name="Dinner", start=START + timedelta(hours=4))
    saved2, public2 = saved_event(user, start=START + timedelta(hours=4))
    pair(
        user,
        left_kind="saved_event",
        left_id=saved2.id,
        right_kind="personal_event",
        right_id=personal2.id,
    )

    result = list_conflict_pairs(user_id=user.pk)

    titles = set()
    for view in result.active:
        for side in (view.left, view.right):
            if side.kind == "saved_event":
                titles.add(side.name)
    assert titles == {public.title, public2.title}


def test_a_deleted_saved_event_reads_as_no_longer_available():
    # The catalog event is gone — superseded, unpublished or in review. The save is still
    # here, so the side is still listed: with no name, and explicitly unavailable.
    user = make_user()
    event = personal_event(user, name="Coffee with Sam")
    saved, public = saved_event(user)
    pair(
        user,
        left_kind="personal_event",
        left_id=event.id,
        right_kind="saved_event",
        right_id=saved.id,
    )
    public.delete()

    result = list_conflict_pairs(user_id=user.pk)

    view = result.active[0]
    saved_view = view.left if view.left.kind == "saved_event" else view.right
    assert saved_view.available is False
    assert saved_view.name is None


def test_a_deleted_saved_row_reads_as_no_longer_available():
    # The save itself is gone — deleted outside the close path — while the pair still
    # names it. The pair is real history, so the side is still listed: with no name, and
    # explicitly unavailable.
    user = make_user()
    event = personal_event(user, name="Coffee with Sam")
    saved, _public = saved_event(user)
    pair(
        user,
        left_kind="personal_event",
        left_id=event.id,
        right_kind="saved_event",
        right_id=saved.id,
    )
    saved.delete()

    result = list_conflict_pairs(user_id=user.pk)

    view = result.active[0]
    saved_view = view.left if view.left.kind == "saved_event" else view.right
    assert saved_view.available is False
    assert saved_view.name is None


def test_a_deleted_personal_event_reads_as_no_longer_available():
    user = make_user()
    kept = personal_event(user, name="Kept")
    gone = personal_event(user, name="Gone", start=START + timedelta(hours=4))
    pair(
        user,
        left_kind="personal_event",
        left_id=kept.id,
        right_kind="personal_event",
        right_id=gone.id,
    )
    gone.delete()

    result = list_conflict_pairs(user_id=user.pk)

    view = result.active[0]
    gone_view = view.left if view.left.id == gone.id else view.right
    assert gone_view.available is False
    assert gone_view.name is None


# --- Statuses --------------------------------------------------------------------------------


def test_an_active_pair_offers_the_actions_for_its_kind():
    user = make_user()
    first = personal_event(user, name="Coffee with Sam")
    second = personal_event(user, name="Coffee with Alex")
    pair(
        user,
        left_kind="personal_event",
        left_id=first.id,
        right_kind="personal_event",
        right_id=second.id,
        kind="time",
    )

    result = list_conflict_pairs(user_id=user.pk)

    assert sorted(result.active[0].actions) == ["delete_new", "edit_new", "keep_both"]


def test_a_duplicate_pair_offers_the_actions_for_its_kind():
    user = make_user()
    first = personal_event(user, name="Coffee with Sam")
    second = personal_event(user, name="Coffee with Alex")
    pair(
        user,
        left_kind="personal_event",
        left_id=first.id,
        right_kind="personal_event",
        right_id=second.id,
        kind="duplicate",
    )

    result = list_conflict_pairs(user_id=user.pk)

    assert sorted(result.active[0].actions) == ["delete_new", "keep_both", "update_existing"]


def test_a_resolved_pair_carries_its_resolution_and_no_actions():
    user = make_user()
    first = personal_event(user, name="Coffee with Sam")
    second = personal_event(user, name="Coffee with Alex")
    resolved_at = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
    pair(
        user,
        left_kind="personal_event",
        left_id=first.id,
        right_kind="personal_event",
        right_id=second.id,
        status=ConflictPair.Status.RESOLVED,
        resolution="keep_both",
        resolved_at=resolved_at,
    )

    result = list_conflict_pairs(user_id=user.pk)

    assert result.active == ()
    assert len(result.resolved) == 1
    view = result.resolved[0]
    assert view.resolution == "keep_both"
    assert view.resolved_at == resolved_at
    assert view.actions == ()


def test_cancelling_a_saved_event_takes_its_conflict_off_the_list():
    """The `/conflicts` surface needs no cancellation rule of its own, and this proves it.

    AD-17 has a cancellation close the pair, and this list already shows only `active`
    pairs — so the prompt stops being asked without the list ever reading a lifecycle
    state. The behaviour is pinned here rather than assumed, because "nothing to change"
    is a claim, not an absence of one.

    The whole path runs: a real save, a real overlap, and the real propagation service —
    not a hand-written `cleared_by_state_change` row, which would only re-test the filter
    `test_a_cleared_pair_is_not_listed` already covers.
    """
    from apps.personalization.services.saved_events import cancel_saved_event, save_event
    from shared.actor import Actor

    now = START - timedelta(days=7)
    user = make_user()
    personal_event(user, name="Coffee with Sam")
    catalog_event = EventFactory(
        start_time_utc=START, end_time_utc=START + timedelta(hours=2), title="Jazz Night"
    )
    result = save_event(
        user_id=user.pk, event_id=catalog_event.id, actor=Actor.user(user.pk), now=now
    )
    assert len(result.conflicts) == 1
    assert len(list_conflict_pairs(user_id=user.pk).active) == 1

    cancel_saved_event(
        event_id=catalog_event.id,
        user_id=user.pk,
        new_version=catalog_event.event_version + 1,
        actor=Actor.system("propagation"),
        now=now,
    )

    listed = list_conflict_pairs(user_id=user.pk)
    assert listed.active == ()
    assert listed.resolved == ()


def test_a_cleared_pair_is_not_listed():
    # `cleared_by_state_change` is not a user choice, so it is not the user's history to
    # read. It appears in neither group.
    user = make_user()
    first = personal_event(user, name="Coffee with Sam")
    second = personal_event(user, name="Coffee with Alex")
    pair(
        user,
        left_kind="personal_event",
        left_id=first.id,
        right_kind="personal_event",
        right_id=second.id,
        status=ConflictPair.Status.CLEARED_BY_STATE_CHANGE,
        resolution=None,
        resolved_at=datetime(2026, 10, 30, 9, 0, tzinfo=UTC),
    )

    result = list_conflict_pairs(user_id=user.pk)

    assert result.active == ()
    assert result.resolved == ()


# --- Ordering --------------------------------------------------------------------------------


def test_active_pairs_are_ordered_by_the_earlier_side_soonest_first():
    user = make_user()
    late_first = personal_event(user, name="Late", start=START + timedelta(days=2))
    late_second = personal_event(user, name="Late Two", start=START + timedelta(days=2, hours=1))
    early_first = personal_event(user, name="Early", start=START)
    early_second = personal_event(user, name="Early Two", start=START + timedelta(hours=1))
    pair(
        user,
        left_kind="personal_event",
        left_id=late_first.id,
        right_kind="personal_event",
        right_id=late_second.id,
    )
    pair(
        user,
        left_kind="personal_event",
        left_id=early_first.id,
        right_kind="personal_event",
        right_id=early_second.id,
    )

    result = list_conflict_pairs(user_id=user.pk)

    assert [view.left.name for view in result.active] == ["Early", "Late"]


def test_active_pairs_are_ordered_by_the_earlier_side_not_the_left_one():
    # The row stores the sides normalised on `(kind, id)`, so the **left** side is the
    # personal one, always — it is not the earlier one. A pair whose saved side starts
    # first is the case that tells the two rules apart: ordering by `left` would put it
    # after a pair whose personal side starts first.
    user = make_user()
    saved_early, _public = saved_event(user, start=START)
    personal_late = personal_event(user, name="Personal Late", start=START + timedelta(hours=5))
    pair(
        user,
        left_kind="personal_event",
        left_id=personal_late.id,
        right_kind="saved_event",
        right_id=saved_early.id,
    )

    personal_early = personal_event(user, name="Personal Early", start=START + timedelta(hours=1))
    saved_late, _public2 = saved_event(user, start=START + timedelta(hours=6))
    pair(
        user,
        left_kind="personal_event",
        left_id=personal_early.id,
        right_kind="saved_event",
        right_id=saved_late.id,
    )

    result = list_conflict_pairs(user_id=user.pk)

    # The **left** side is the personal one in both pairs (the row normalises on
    # `(kind, id)`, and `personal_event` sorts first). What differs is the *earlier*
    # side: the first pair's saved side starts at START, while the second pair's personal
    # side starts an hour later — so the first pair is the earlier one, even though its
    # personal side is later. Ordering by `left` would put the first pair second.
    assert [view.left.name for view in result.active] == ["Personal Late", "Personal Early"]


def test_resolved_pairs_are_ordered_by_resolution_time_newest_first():
    user = make_user()
    older = personal_event(user, name="Older")
    newer = personal_event(user, name="Newer", start=START + timedelta(hours=3))
    older_other = personal_event(user, name="Older Two", start=START + timedelta(hours=1))
    newer_other = personal_event(user, name="Newer Two", start=START + timedelta(hours=4))
    pair(
        user,
        left_kind="personal_event",
        left_id=older.id,
        right_kind="personal_event",
        right_id=older_other.id,
        status=ConflictPair.Status.RESOLVED,
        resolution="keep_both",
        resolved_at=datetime(2026, 10, 29, 9, 0, tzinfo=UTC),
    )
    pair(
        user,
        left_kind="personal_event",
        left_id=newer.id,
        right_kind="personal_event",
        right_id=newer_other.id,
        status=ConflictPair.Status.RESOLVED,
        resolution="keep_both",
        resolved_at=datetime(2026, 10, 31, 9, 0, tzinfo=UTC),
    )

    result = list_conflict_pairs(user_id=user.pk)

    assert [view.left.name for view in result.resolved] == ["Newer", "Older"]


# --- The query bound -------------------------------------------------------------------------


def test_the_query_count_does_not_grow_with_the_number_of_pairs():
    # The list reads the catalog once, in a batch, and the personal sides once each — so
    # a user with one pair and a user with ten cost the same.
    #
    # **Both aliases are captured.** The personal reads and the catalog read run on
    # separate connections, so counting only one of them would miss a fan-out in the
    # other.
    user = make_user()

    # One pair.
    first = personal_event(user, name="One")
    second = personal_event(user, name="Two")
    pair(
        user,
        left_kind="personal_event",
        left_id=first.id,
        right_kind="personal_event",
        right_id=second.id,
    )
    with (
        CaptureQueriesContext(connections[PERSONAL]) as one_personal,
        CaptureQueriesContext(connections[CATALOG]) as one_catalog,
    ):
        list_conflict_pairs(user_id=user.pk)

    # Ten pairs.
    for index in range(9):
        a = personal_event(user, name=f"Extra {index}", start=START + timedelta(days=index + 1))
        b = personal_event(
            user,
            name=f"Extra {index} Two",
            start=START + timedelta(days=index + 1, hours=1),
        )
        pair(
            user,
            left_kind="personal_event",
            left_id=a.id,
            right_kind="personal_event",
            right_id=b.id,
        )
    with (
        CaptureQueriesContext(connections[PERSONAL]) as ten_personal,
        CaptureQueriesContext(connections[CATALOG]) as ten_catalog,
    ):
        list_conflict_pairs(user_id=user.pk)

    assert len(ten_personal.captured_queries) == len(one_personal.captured_queries)
    assert len(ten_catalog.captured_queries) == len(one_catalog.captured_queries)
    # And the count is small: a constant, not a per-pair fan-out.
    assert len(ten_personal.captured_queries) + len(ten_catalog.captured_queries) <= 6


def test_the_list_costs_one_catalog_read_for_every_saved_side():
    # The saved sides are named in **one** batched catalog read, not one per pair.
    #
    # The catalog is a **separate connection** (`CATALOG = "catalog"`, and `PERSONAL =
    # "default"`), so the catalog's SQL never appears on the default connection's log. The
    # catalog alias is captured explicitly, or the assertion would be vacuous: an empty
    # list satisfies `<= 1` just as well as a batched read does.
    user = make_user()
    for index in range(3):
        event = personal_event(user, name=f"Personal {index}", start=START + timedelta(days=index))
        saved, _public = saved_event(user, start=START + timedelta(days=index))
        pair(
            user,
            left_kind="personal_event",
            left_id=event.id,
            right_kind="saved_event",
            right_id=saved.id,
        )

    with CaptureQueriesContext(connections[CATALOG]) as catalog_queries:
        result = list_conflict_pairs(user_id=user.pk)

    assert len(catalog_queries.captured_queries) == 1
    assert len(result.active) == 3


# --- The API surface --------------------------------------------------------------------------


def test_the_endpoint_returns_both_groups():
    user = make_user()
    first = personal_event(user, name="Coffee with Sam")
    second = personal_event(user, name="Coffee with Alex")
    pair(
        user,
        left_kind="personal_event",
        left_id=first.id,
        right_kind="personal_event",
        right_id=second.id,
    )

    payload = signed_in(user).get("/api/personal/conflicts").json()

    assert len(payload["active"]) == 1
    assert payload["resolved"] == []
    assert payload["active"][0]["kind"] == "time"
    assert {payload["active"][0]["left"]["name"], payload["active"][0]["right"]["name"]} == {
        "Coffee with Sam",
        "Coffee with Alex",
    }


def test_the_endpoint_shows_the_saved_side_with_its_catalog_title():
    user = make_user()
    event = personal_event(user, name="Coffee with Sam")
    saved, public = saved_event(user)
    pair(
        user,
        left_kind="personal_event",
        left_id=event.id,
        right_kind="saved_event",
        right_id=saved.id,
    )

    payload = signed_in(user).get("/api/personal/conflicts").json()

    sides = [payload["active"][0]["left"], payload["active"][0]["right"]]
    saved_side = next(side for side in sides if side["kind"] == "saved_event")
    assert saved_side["name"] == public.title
    assert saved_side["available"] is True


def test_the_endpoint_does_not_reveal_another_users_pairs():
    user = make_user()
    other = make_user("other@example.test")
    theirs = personal_event(other, name="Theirs")
    pair(
        other,
        left_kind="personal_event",
        left_id=theirs.id,
        right_kind="personal_event",
        right_id=uuid4(),
    )

    payload = signed_in(user).get("/api/personal/conflicts").json()

    assert payload["active"] == []
    assert payload["resolved"] == []
