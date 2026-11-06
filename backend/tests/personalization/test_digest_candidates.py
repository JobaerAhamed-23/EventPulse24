"""The digest's personal-side candidates: the user's own events, saves and conflicts.

**The window is 48 hours and both ends are inclusive.** An event starting exactly 48
hours from now is eligible, because FR-5's "within the next 48 hours" includes the
boundary — and because the ranking boost it carries applies at exactly the same boundary,
so the candidate set and the boost cannot disagree about which events are "soon".

**The conflict state comes from the persisted rows.** These tests build `ConflictPair`
rows and read them back; there is no overlap computed at render anywhere in the read
(AD-21). A read that computed an overlap would produce a *different* answer from the
persisted pair whenever the two disagreed, and they disagree the moment an event moves
without the propagation running.

**The wall holds.** The saved-event read resolves the catalog's facts through
`catalog_read`, never a join, and the alias separation is asserted rather than assumed.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from apps.ingestion.models import Event
from apps.personalization.models import ConflictPair, PersonalEvent
from apps.personalization.services.digest_candidates import (
    list_conflict_pairs,
    list_personal_candidates,
    list_saved_candidates,
)
from shared.constants import RANKING_PERSONAL_EVENT_WINDOW
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory
from tests.personalization.factories import (
    ConflictPairFactory,
    PersonalEventFactory,
    SavedEventFactory,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)
USER = uuid4()


def at(hours: int) -> datetime:
    return NOW + timedelta(hours=hours)


# --- the personal window ---------------------------------------------------------------


def test_an_event_starting_exactly_now_is_a_candidate():
    """The near end is inclusive: an event that starts now is still ahead of the user."""
    event = PersonalEventFactory(user_id=USER, start_utc=NOW)

    candidates = list_personal_candidates(user_id=USER, now=NOW)

    assert [c.id for c in candidates] == [event.id]


def test_an_event_starting_exactly_at_the_window_end_is_a_candidate():
    """The far end is inclusive, and it is the same boundary the ranking boost uses."""
    event = PersonalEventFactory(user_id=USER, start_utc=NOW + RANKING_PERSONAL_EVENT_WINDOW)

    candidates = list_personal_candidates(user_id=USER, now=NOW)

    assert [c.id for c in candidates] == [event.id]


def test_an_event_one_second_past_the_window_is_not_a_candidate():
    PersonalEventFactory(
        user_id=USER, start_utc=NOW + RANKING_PERSONAL_EVENT_WINDOW + timedelta(seconds=1)
    )

    assert list_personal_candidates(user_id=USER, now=NOW) == []


def test_an_event_that_already_started_is_not_a_candidate():
    """The window is "starting within the next 48 hours", not "running"."""
    PersonalEventFactory(user_id=USER, start_utc=NOW - HOUR)

    assert list_personal_candidates(user_id=USER, now=NOW) == []


def test_the_window_is_the_named_constant():
    assert RANKING_PERSONAL_EVENT_WINDOW == timedelta(hours=48)


def test_the_candidates_are_ordered_by_start_time_then_id():
    first = PersonalEventFactory(user_id=USER, start_utc=at(5))
    second = PersonalEventFactory(user_id=USER, start_utc=at(2))
    third = PersonalEventFactory(user_id=USER, start_utc=at(5))

    candidates = list_personal_candidates(user_id=USER, now=NOW)

    assert [c.id for c in candidates] == [second.id, first.id, third.id]


def test_another_users_events_are_never_returned():
    PersonalEventFactory(user_id=USER, start_utc=at(2))
    PersonalEventFactory(user_id=uuid4(), start_utc=at(3))

    candidates = list_personal_candidates(user_id=USER, now=NOW)

    assert len(candidates) == 1


def test_an_imported_calendar_event_is_a_candidate():
    """Both sources are the user's own agenda. Slot 1 is about the user's events, not
    about who typed the row."""
    event = PersonalEventFactory(
        user_id=USER,
        start_utc=at(2),
        source=PersonalEvent.Source.CALENDAR_IMPORT,
        calendar_connection_id=uuid4(),
    )

    candidates = list_personal_candidates(user_id=USER, now=NOW)

    assert [c.id for c in candidates] == [event.id]
    assert candidates[0].source == PersonalEvent.Source.CALENDAR_IMPORT


def test_the_candidate_carries_the_users_own_facts():
    event = PersonalEventFactory(
        user_id=USER, start_utc=at(2), name="Dentist", location="12 Example Street"
    )

    candidate = list_personal_candidates(user_id=USER, now=NOW)[0]

    assert candidate.name == "Dentist"
    assert candidate.location == "12 Example Street"
    assert candidate.user_id == USER
    assert candidate.start_utc == event.start_utc


# --- the conflict state ----------------------------------------------------------------


def test_a_personal_event_in_a_conflict_carries_the_pairs_id():
    """The pair's id is what the resolution command takes, so a boolean would lose
    something the frontend needs."""
    event = PersonalEventFactory(user_id=USER, start_utc=at(2))
    other = PersonalEventFactory(user_id=USER, start_utc=at(3))
    pair = ConflictPairFactory(
        user_id=USER,
        left_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        left_id=event.id,
        right_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        right_id=other.id,
    )

    candidates = list_personal_candidates(user_id=USER, now=NOW)
    by_id = {c.id: c for c in candidates}

    assert by_id[event.id].conflict_ids == (pair.id,)
    assert by_id[other.id].conflict_ids == (pair.id,)


def test_a_personal_event_with_no_conflict_carries_an_empty_tuple():
    """'No conflict' and 'we did not look' must not be the same value."""
    PersonalEventFactory(user_id=USER, start_utc=at(2))

    candidate = list_personal_candidates(user_id=USER, now=NOW)[0]

    assert candidate.conflict_ids == ()


def test_a_resolved_conflict_is_not_carried():
    """A resolved pair is answered; showing it would put a prompt on a card for a
    conflict the user has already settled."""
    event = PersonalEventFactory(user_id=USER, start_utc=at(2))
    other = PersonalEventFactory(user_id=USER, start_utc=at(3))
    ConflictPairFactory(
        user_id=USER,
        left_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        left_id=event.id,
        right_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        right_id=other.id,
        status=ConflictPair.Status.RESOLVED,
        resolution=ConflictPair.Resolution.KEEP_BOTH,
        resolved_at=NOW,
    )

    candidate = list_personal_candidates(user_id=USER, now=NOW)[0]

    assert candidate.conflict_ids == ()


def test_a_conflict_cleared_by_a_state_change_is_not_carried():
    event = PersonalEventFactory(user_id=USER, start_utc=at(2))
    other = PersonalEventFactory(user_id=USER, start_utc=at(3))
    ConflictPairFactory(
        user_id=USER,
        left_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        left_id=event.id,
        right_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        right_id=other.id,
        status=ConflictPair.Status.CLEARED_BY_STATE_CHANGE,
        resolved_at=NOW,
    )

    candidate = list_personal_candidates(user_id=USER, now=NOW)[0]

    assert candidate.conflict_ids == ()


def test_another_users_conflict_is_never_carried():
    event = PersonalEventFactory(user_id=USER, start_utc=at(2))
    other = PersonalEventFactory(user_id=USER, start_utc=at(3))
    ConflictPairFactory(
        user_id=uuid4(),
        left_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        left_id=event.id,
        right_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        right_id=other.id,
    )

    candidate = list_personal_candidates(user_id=USER, now=NOW)[0]

    assert candidate.conflict_ids == ()


def test_a_conflict_against_a_saved_event_is_carried_by_the_personal_side_only():
    """A pair names two sides of **different** kinds — a personal event can clash with a
    saved event. The personal candidate carries the pair; the saved candidate carries
    it too, and neither reads the other's side."""
    event = PersonalEventFactory(user_id=USER, start_utc=at(2))
    saved = SavedEventFactory(user_id=USER, event_id=uuid4(), start_utc=at(3))
    pair = ConflictPairFactory(
        user_id=USER,
        left_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        left_id=event.id,
        right_kind=ConflictPair.SideKind.SAVED_EVENT,
        right_id=saved.id,
    )

    personal = list_personal_candidates(user_id=USER, now=NOW)[0]
    saved_candidate = list_saved_candidates(user_id=USER, now=NOW)[0]

    assert personal.conflict_ids == (pair.id,)
    assert saved_candidate.conflict_ids == (pair.id,)


def test_a_pair_does_not_attach_to_a_candidate_of_the_other_kind():
    """The `kind` filter is what stops a pair's *other* side from attaching to the wrong
    candidate. The two tables have separate id sequences, so a collision is unlikely —
    but a collision is exactly what a data migration or a fixture-based backfill can
    produce, and then the wrong record would carry the conflict.

    The ids are deliberately **the same** here, so the kind is the only thing that can
    tell the two records apart.
    """
    shared_id = uuid4()
    event = PersonalEventFactory(user_id=USER, start_utc=at(2), id=shared_id)
    saved = SavedEventFactory(user_id=USER, event_id=uuid4(), start_utc=at(3), id=shared_id)
    assert event.id == saved.id

    # The pair's saved-event side is the one the personal candidate must NOT pick up.
    ConflictPairFactory(
        user_id=USER,
        left_kind=ConflictPair.SideKind.SAVED_EVENT,
        left_id=shared_id,
        right_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        right_id=uuid4(),
    )

    personal = list_personal_candidates(user_id=USER, now=NOW)[0]

    assert personal.conflict_ids == ()


# --- the saved events -------------------------------------------------------------------


def test_a_saved_event_reads_its_own_snapshot_for_the_time():
    """AD-21: the snapshot is what the user's own calendar shows. The catalog's current
    time may have moved, and AD-17's propagation is what reconciles them."""
    catalog_event = EventFactory(start_time_utc=at(5))
    saved = SavedEventFactory(
        user_id=USER,
        event_id=catalog_event.id,
        start_utc=at(2),
        end_utc=at(3),
        event_version=1,
    )

    candidates = list_saved_candidates(user_id=USER, now=NOW)

    assert candidates[0].start_utc == saved.start_utc
    assert candidates[0].start_utc != catalog_event.start_time_utc


def test_a_saved_event_carries_the_catalogs_current_facts():
    catalog_event = EventFactory(start_time_utc=at(5), title="Jazz Night")
    SavedEventFactory(user_id=USER, event_id=catalog_event.id, start_utc=at(2))

    candidate = list_saved_candidates(user_id=USER, now=NOW)[0]

    assert candidate.public is not None
    assert candidate.public.title == "Jazz Night"
    assert candidate.public.id == catalog_event.id


def test_a_saved_event_whose_catalog_event_is_gone_is_still_a_candidate():
    """The save is real. Dropping it would make a user's save vanish from their digest
    because a source dropped the event, with no way for the user to know why."""
    SavedEventFactory(user_id=USER, event_id=uuid4(), start_utc=at(2))

    candidates = list_saved_candidates(user_id=USER, now=NOW)

    assert len(candidates) == 1
    assert candidates[0].public is None


def test_a_saved_event_the_catalog_says_is_cancelled_is_not_a_candidate():
    """FR-55: "event is removed from the digest".

    The digest answers "what is worth your attention today", and a cancelled event is
    not. The state is read from the catalog's `status` on the `PublicEvent` the read
    already fetches — `_public_events()` excludes `superseded` but keeps `cancelled`, so
    a cancelled event is still in the map and still has a fact to state.
    """
    catalog_event = EventFactory(status=Event.Status.CANCELLED, start_time_utc=at(5))
    SavedEventFactory(user_id=USER, event_id=catalog_event.id, start_utc=at(2))

    assert list_saved_candidates(user_id=USER, now=NOW) == []


def test_a_cancelled_save_is_dropped_but_its_neighbours_are_kept():
    """The drop is per candidate, not a short-circuit on the whole list."""
    cancelled = EventFactory(status=Event.Status.CANCELLED, start_time_utc=at(5))
    live = EventFactory(start_time_utc=at(6), title="Jazz Night")
    SavedEventFactory(user_id=USER, event_id=cancelled.id, start_utc=at(2))
    SavedEventFactory(user_id=USER, event_id=live.id, start_utc=at(3))

    candidates = list_saved_candidates(user_id=USER, now=NOW)

    assert [c.event_id for c in candidates] == [live.id]


def test_a_postponed_save_is_still_a_candidate():
    """Only `cancelled` is dropped. A postponed event is still happening.

    This is the mutation that makes the drop a *decision* rather than "anything whose
    status is not scheduled": `postponed` and `cancelled` are both non-scheduled, and
    only one of them means the event is off.
    """
    catalog_event = EventFactory(status=Event.Status.POSTPONED, start_time_utc=at(5))
    SavedEventFactory(user_id=USER, event_id=catalog_event.id, start_utc=at(2))

    candidates = list_saved_candidates(user_id=USER, now=NOW)

    assert [c.event_id for c in candidates] == [catalog_event.id]


def test_a_save_whose_catalog_event_is_absent_is_kept_though_a_cancelled_one_is_not():
    """The two absences are different claims, and the difference is the whole rule.

    *Missing* means the catalog has stopped describing the event and cannot say why — a
    guess, and the save is kept. *Cancelled* is the catalog stating a fact, and it is
    acted on. A reader that treated them alike would drop a user's save because a source
    went quiet.
    """
    cancelled = EventFactory(status=Event.Status.CANCELLED, start_time_utc=at(5))
    SavedEventFactory(user_id=USER, event_id=cancelled.id, start_utc=at(2))
    SavedEventFactory(user_id=USER, event_id=uuid4(), start_utc=at(3))

    candidates = list_saved_candidates(user_id=USER, now=NOW)

    assert len(candidates) == 1
    assert candidates[0].public is None


def test_a_save_that_has_already_started_is_not_a_candidate():
    """A digest's slots hold upcoming events."""
    SavedEventFactory(user_id=USER, event_id=uuid4(), start_utc=NOW - HOUR)

    assert list_saved_candidates(user_id=USER, now=NOW) == []


def test_a_save_whose_catalog_event_has_already_started_still_carries_its_facts():
    """`get_public_event` is called **without** `now`, deliberately: a save stays
    readable after its event has started, because the user's own calendar does not
    un-save an event because it began. A future refactor that "tidies up" the call by
    threading `now` through would silently start dropping these saves."""
    catalog_event = EventFactory(start_time_utc=NOW - HOUR, title="Jazz Night")
    SavedEventFactory(user_id=USER, event_id=catalog_event.id, start_utc=at(2))

    candidates = list_saved_candidates(user_id=USER, now=NOW)

    assert len(candidates) == 1
    assert candidates[0].public is not None
    assert candidates[0].public.title == "Jazz Night"


def test_the_saved_read_resolves_the_catalog_in_one_batched_query():
    """Five saves must cost one query against the catalog, not five. The read runs once
    per user per day, so a round-trip per save is a round-trip per save per user."""
    from django.db import connections

    for hour in range(2, 7):
        catalog_event = EventFactory(start_time_utc=at(hour))
        SavedEventFactory(user_id=USER, event_id=catalog_event.id, start_utc=at(hour))

    recorder = _record()
    with connections[CATALOG].execute_wrapper(recorder):
        candidates = list_saved_candidates(user_id=USER, now=NOW)

    assert len(candidates) == 5
    catalog_queries = [query for query in recorder.recorded if "ingestion_event" in query.lower()]
    assert len(catalog_queries) == 1, (
        f"the saved read must resolve the catalog in one query, not one per save; "
        f"saw {len(catalog_queries)}"
    )


def test_a_limit_of_zero_returns_no_saved_candidates():
    SavedEventFactory(user_id=USER, event_id=uuid4(), start_utc=at(2))

    assert list_saved_candidates(user_id=USER, now=NOW, limit=0) == []


def test_the_saved_pool_is_bounded():
    for hour in range(2, 12):
        SavedEventFactory(user_id=USER, event_id=uuid4(), start_utc=at(hour))

    candidates = list_saved_candidates(user_id=USER, now=NOW, limit=3)

    assert len(candidates) == 3


def test_another_users_saves_are_never_returned():
    SavedEventFactory(user_id=USER, event_id=uuid4(), start_utc=at(2))
    SavedEventFactory(user_id=uuid4(), event_id=uuid4(), start_utc=at(3))

    assert len(list_saved_candidates(user_id=USER, now=NOW)) == 1


def test_a_saved_event_in_a_conflict_carries_the_pairs_id():
    saved = SavedEventFactory(user_id=USER, event_id=uuid4(), start_utc=at(2))
    other = SavedEventFactory(user_id=USER, event_id=uuid4(), start_utc=at(3))
    pair = ConflictPairFactory(
        user_id=USER,
        left_kind=ConflictPair.SideKind.SAVED_EVENT,
        left_id=saved.id,
        right_kind=ConflictPair.SideKind.SAVED_EVENT,
        right_id=other.id,
    )

    candidates = list_saved_candidates(user_id=USER, now=NOW)
    by_id = {c.id: c for c in candidates}

    assert by_id[saved.id].conflict_ids == (pair.id,)


# --- the conflict pair list ---------------------------------------------------------------


def test_the_pair_list_returns_the_open_pairs():
    pair = ConflictPairFactory(user_id=USER)

    pairs = list_conflict_pairs(user_id=USER)

    assert [p.id for p in pairs] == [pair.id]


def test_the_pair_list_omits_resolved_and_cleared_pairs():
    ConflictPairFactory(
        user_id=USER,
        status=ConflictPair.Status.RESOLVED,
        resolution=ConflictPair.Resolution.KEEP_BOTH,
        resolved_at=NOW,
    )
    ConflictPairFactory(
        user_id=USER,
        status=ConflictPair.Status.CLEARED_BY_STATE_CHANGE,
        resolved_at=NOW,
    )

    assert list_conflict_pairs(user_id=USER) == []


def test_the_pair_list_carries_both_sides():
    left = uuid4()
    right = uuid4()
    pair = ConflictPairFactory(
        user_id=USER,
        left_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        left_id=left,
        right_kind=ConflictPair.SideKind.SAVED_EVENT,
        right_id=right,
    )

    snapshot = list_conflict_pairs(user_id=USER)[0]

    assert snapshot.id == pair.id
    assert snapshot.left_kind == ConflictPair.SideKind.PERSONAL_EVENT
    assert snapshot.left_id == left
    assert snapshot.right_kind == ConflictPair.SideKind.SAVED_EVENT
    assert snapshot.right_id == right


def test_another_users_pairs_are_never_returned():
    ConflictPairFactory(user_id=USER)
    ConflictPairFactory(user_id=uuid4())

    assert len(list_conflict_pairs(user_id=USER)) == 1


# --- the wall -----------------------------------------------------------------------------


def test_the_personal_reads_never_touch_the_catalog_alias():
    """The personal reads are queries against `personal` only. The saved read resolves
    the catalog's facts through `catalog_read` — a lookup, not a join.

    The assertion is on the **table names**, not on a substring that could never appear
    in a personal query. `"public" not in query` would be true of every possible
    personal statement, because the `personalization` app has no table or column whose
    name contains it — so it would pass even if the read joined `catalog`.
    """
    from django.db import connections

    catalog_event = EventFactory(start_time_utc=at(5))
    SavedEventFactory(user_id=USER, event_id=catalog_event.id, start_utc=at(2))
    PersonalEventFactory(user_id=USER, start_utc=at(3))

    recorder = _record(PERSONAL)
    with connections[PERSONAL].execute_wrapper(recorder):
        list_personal_candidates(user_id=USER, now=NOW)
        list_conflict_pairs(user_id=USER)

    assert recorder.recorded, "the personal reads must query the personal alias"
    for query in recorder.recorded:
        lowered = query.lower()
        assert "ingestion_event" not in lowered, (
            "the personal read must never touch the catalog's event table; the two "
            "sides are read separately and joined in the application layer (AD-3)"
        )
        assert "ingestion_source" not in lowered
        assert "ingestion_venue" not in lowered
        # And the statements it *does* run are the personal ones.
        assert "personalization_" in lowered, (
            f"a personal read must query the personal tables; saw: {query[:200]}"
        )


def test_the_saved_read_resolves_the_catalog_through_the_published_interface():
    """One batched lookup, against the `catalog` alias, through `catalog_read`."""
    from django.db import connections

    catalog_event = EventFactory(start_time_utc=at(5))
    SavedEventFactory(user_id=USER, event_id=catalog_event.id, start_utc=at(2))

    recorder = _record(CATALOG)
    with connections[CATALOG].execute_wrapper(recorder):
        list_saved_candidates(user_id=USER, now=NOW)

    assert recorder.recorded, "the saved read must resolve the catalog's facts"
    for query in recorder.recorded:
        lowered = query.lower()
        assert "personalization_" not in lowered, (
            "the catalog read must never touch the personal tables; the two sides are "
            "read separately and joined in the application layer (AD-3)"
        )
        assert "ingestion_event" in lowered, (
            f"the catalog read must query the catalog's event table; saw: {query[:200]}"
        )


def _record(alias=None):
    """Capture the SQL executed against one alias.

    Returns the wrapper; `execute_wrapper` hands back the wrapper itself, so the
    recorded statements live on it.
    """
    recorded: list[str] = []

    def wrapper(execute, sql, params, many, context):
        recorded.append(sql)
        return execute(sql, params, many, context)

    wrapper.recorded = recorded
    return wrapper
