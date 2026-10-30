"""The composition command: candidates in, one persisted Pulse Digest out (FR-5, FR-8).

**The interesting properties are the ones a user would notice if they broke.**

- the three slots hold the right *kinds* of thing — a personal event in "must-know", a
  nearby event in "nearby", something the user's own signals would not have picked in
  "serendipity";
- the three are **distinct** — the same event in two slots would be a card that appears
  twice on the digest;
- composing twice for the same day produces **the same rows**, and the second call
  writes nothing at all;
- the day is the **user's** day, not the server's — so two users sharing one UTC
  minute get two different digests, and a DST transition does not produce two digests
  for one day;
- a day with nothing to show is the **empty state** — a real digest with no cards, and
  not the absence of a digest;
- a user who told us nothing is **not punished** for it: the interest term scores
  zero, and the other three terms still rank.

**The chips are the newly-built half.** The interest term is the largest weight in the
Relevance Pulse, and it needs the event's chips as well as the user's — so the
candidate read now computes them, and these tests are what prove the term is alive.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from apps.ingestion.services.source_badges import SOURCE_BADGE_OFFICIAL
from apps.personalization.models import (
    DigestComposition,
    Interest,
    PersonalizationAuditEntry,
    PulseDigest,
)
from apps.personalization.services.digest_composition import compose_digest
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory, VenueFactory
from tests.personalization.factories import (
    DigestPreferenceFactory,
    PersonalEventFactory,
    SavedEventFactory,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

ACTOR = Actor.system("digest_composition")

#: A Wednesday. 2026-11-04 16:00 UTC is 09:00 in Los Angeles (PST), and 08:00 in New
#: York (EST).
NOW = datetime(2026, 11, 4, 16, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)

CITY = "Los Angeles"
ZONE = "America/Los_Angeles"


def make_preference(user_id, **overrides):
    fields = {"user_id": user_id, "timezone": ZONE, "city": CITY, "city_source": "choice"}
    fields.update(overrides)
    return DigestPreferenceFactory(**fields)


def make_event(*, hours=2, title="Brooklyn Tech Meetup", city=CITY, **overrides):
    """A published, eligible public event.

    **The title carries a chip keyword** ("tech") by default, so the interest term has
    something to match. The city is the user's, so the city band is `1.00`.

    **`last_seen_at` is pinned to `NOW`.** FR-14's staleness bound is measured from it
    against the *test's* clock, and the column's default is the wall clock — so an
    event built with the default would be days stale against a `NOW` in the future, and
    the candidate read would drop it before the composition ever saw it. Pinning it
    makes "seen by the catalog right now" the default, which is what a fresh event is.
    """
    fields = {
        "title": title,
        "venue": VenueFactory(city=city, venue_fingerprint=f"venue-{title}|{city}"),
        "start_time_utc": NOW + timedelta(hours=hours),
        "last_seen_at": NOW,
    }
    fields.update(overrides)
    return EventFactory(**fields)


def make_interest(user_id, chip_key):
    return Interest.objects.using(PERSONAL).create(user_id=user_id, chip_key=chip_key)


def make_personal(user_id, *, hours=3, **overrides):
    """A personal event on the user's own agenda.

    **`end_utc` is derived from `start_utc`.** The factory's default end is a fixed
    instant from the factory module's own clock, so overriding only `start_utc` would
    leave the end *before* the start and trip the model's `end_after_start_ck`. Deriving
    it here keeps every personal event self-consistent no matter when it starts.
    """
    start = NOW + timedelta(hours=hours)
    fields = {"user_id": user_id, "start_utc": start, "end_utc": start + timedelta(hours=2)}
    fields.update(overrides)
    return PersonalEventFactory(**fields)


def compose(user_id, *, now=NOW, actor=ACTOR):
    return compose_digest(user_id=user_id, actor=actor, now=now)


def rows_of(result):
    return {row.slot: row for row in result.compositions}


# --- the three slots ----------------------------------------------------------------


def test_a_standard_day_holds_three_cards():
    user_id = make_preference(_user_id()).user_id
    for hours in (2, 3, 4):
        make_event(hours=hours, title=f"Event {hours}")

    result = compose(user_id)

    assert len(result.compositions) == 3
    assert not result.is_empty
    assert [row.slot for row in result.compositions] == [
        "must_know",
        "nearby",
        "serendipity",
    ]


def test_the_slots_are_the_three_named_ones():
    user_id = make_preference(_user_id()).user_id
    for hours in (2, 3, 4):
        make_event(hours=hours, title=f"Event {hours}")

    result = compose(user_id)

    assert set(rows_of(result)) == {"must_know", "nearby", "serendipity"}


def test_the_three_cards_are_three_distinct_events():
    """FR-5: "a Pulse Card in the digest is not a duplicate of another".

    **The pool is built so the same event would win two slots** — one event that
    outscores the others. The service must not let it take two slots.
    """
    user_id = make_preference(_user_id()).user_id
    make_event(hours=2, title="The One Event")
    make_event(hours=20, title="A Distant Event")
    make_event(hours=40, title="A Later Event")

    result = compose(user_id)

    event_ids = [row.event_id for row in result.compositions]
    assert len(event_ids) == 3
    assert len(set(event_ids)) == 3


def test_the_nearby_slot_takes_the_next_best_not_the_best():
    """Slot 2 draws from what Slot 1 left, so it cannot repeat the winner."""
    user_id = make_preference(_user_id()).user_id
    soon = make_event(hours=2, title="Soonest Event")
    later = make_event(hours=6, title="Later Event")
    make_event(hours=30, title="Distant Event")

    result = compose(user_id)
    rows = rows_of(result)

    assert rows["must_know"].event_id == soon.id
    assert rows["nearby"].event_id == later.id


def test_the_serendipity_slot_is_not_the_same_pick_as_the_nearby_slot():
    """Slot 3 draws from what Slots 1 and 2 left."""
    user_id = make_preference(_user_id()).user_id
    make_event(hours=2, title="Event A")
    make_event(hours=6, title="Event B")
    make_event(hours=30, title="Event C")

    result = compose(user_id)
    rows = rows_of(result)

    assert rows["nearby"].event_id != rows["serendipity"].event_id


# --- Slot 1: the personal event -----------------------------------------------------


def test_slot_1_is_the_personal_event_when_there_is_one():
    user_id = make_preference(_user_id()).user_id
    personal = make_personal(user_id, hours=3)
    make_event(hours=2, title="A Very Good Public Event")

    result = compose(user_id)
    rows = rows_of(result)

    assert rows["must_know"].event_id == personal.id
    assert rows["must_know"].event_kind == "personal"


def test_the_personal_event_wins_slot_1_even_when_a_public_event_outscores_it():
    """FR-5 makes the public event a *fallback*, not a competitor.

    The personal event is not competing for Slot 1 — it **is** Slot 1 when one is
    eligible. A "highest score wins" implementation would get this wrong.
    """
    user_id = make_preference(_user_id()).user_id
    make_interest(user_id, "tech_meetups")
    personal = make_personal(user_id, hours=3)
    public = make_event(hours=1, title="Tech Meetup")

    result = compose(user_id)
    rows = rows_of(result)

    assert rows["must_know"].event_id == personal.id
    assert public.id in {row.event_id for row in result.compositions}


def test_slot_1_falls_back_to_the_public_event_when_there_is_no_personal_event():
    user_id = make_preference(_user_id()).user_id
    public = make_event(hours=2, title="Only Public Event")

    result = compose(user_id)

    assert rows_of(result)["must_know"].event_id == public.id
    assert rows_of(result)["must_know"].event_kind == "public"


def test_a_personal_event_outside_the_window_does_not_take_slot_1():
    """FR-5's window is 48 hours, and the candidate read already bounded it."""
    user_id = make_preference(_user_id()).user_id
    make_personal(user_id, hours=49)
    public = make_event(hours=2, title="Public Event")

    result = compose(user_id)

    assert rows_of(result)["must_know"].event_id == public.id


def test_a_personal_event_has_no_badge_and_no_version():
    """The model's check constraint says so, and it is right — a personal event has no
    source, so there is no badge to state."""
    user_id = make_preference(_user_id()).user_id
    make_personal(user_id, hours=3)

    result = compose(user_id)
    row = rows_of(result)["must_know"]

    assert row.source_badge is None
    assert row.event_version is None


def test_a_public_composition_carries_the_badge_and_the_version():
    user_id = make_preference(_user_id()).user_id
    make_event(hours=2, title="Public Event")

    result = compose(user_id)
    row = rows_of(result)["must_know"]

    assert row.source_badge == SOURCE_BADGE_OFFICIAL
    assert row.event_version is not None


# --- the opt-out ---------------------------------------------------------------------


def test_an_opted_out_users_digest_has_no_personal_event():
    user_id = make_preference(_user_id(), include_personal_events=False).user_id
    make_personal(user_id, hours=3)
    public = make_event(hours=2, title="Public Event")

    result = compose(user_id)
    rows = rows_of(result)

    assert rows["must_know"].event_id == public.id
    assert all(row.event_kind == "public" for row in result.compositions)


def test_an_opted_out_user_with_no_public_events_gets_the_empty_state():
    """The opt-out removes the personal half of the empty-state trigger."""
    user_id = make_preference(_user_id(), include_personal_events=False).user_id
    make_personal(user_id, hours=3)

    result = compose(user_id)

    assert result.is_empty
    assert result.compositions == ()


# --- the empty state -----------------------------------------------------------------


def test_the_empty_state_is_a_real_digest_with_no_cards():
    """FR-8's empty digest is a fact the user is shown, not the absence of a digest."""
    user_id = make_preference(_user_id()).user_id

    result = compose(user_id)

    digest = PulseDigest.objects.using(PERSONAL).get(id=result.digest_id)
    assert digest.is_empty
    assert not DigestComposition.objects.using(PERSONAL).filter(digest_id=digest.id).exists()


def test_the_empty_state_needs_both_halves():
    """No public events **and** no personal events. Either half alone is not empty."""
    user_id = make_preference(_user_id()).user_id
    make_personal(user_id, hours=3)

    result = compose(user_id)

    assert not result.is_empty
    assert len(result.compositions) == 1


def test_a_user_with_public_events_is_not_in_the_empty_state():
    user_id = make_preference(_user_id()).user_id
    make_event(hours=2, title="Public Event")

    result = compose(user_id)

    assert not result.is_empty


def test_an_event_the_user_opted_out_of_still_counts_as_a_public_event():
    """The opt-out is about *personal* events. It does not remove public ones."""
    user_id = make_preference(_user_id(), include_personal_events=False).user_id
    make_event(hours=2, title="Public Event")

    result = compose(user_id)

    assert not result.is_empty
    assert len(result.compositions) == 1


# --- the shorter-than-three digest ---------------------------------------------------


def test_a_pool_of_one_holds_one_card():
    user_id = make_preference(_user_id()).user_id
    make_event(hours=2, title="Only Event")

    result = compose(user_id)

    assert len(result.compositions) == 1
    assert not result.is_empty


def test_a_pool_of_two_holds_two_cards():
    """FR-5's "exactly 3" describes a standard day. A short day is not the empty state —
    falling to the empty state would tell the user there is nothing happening when
    there are two things happening."""
    user_id = make_preference(_user_id()).user_id
    make_event(hours=2, title="Event One")
    make_event(hours=6, title="Event Two")

    result = compose(user_id)

    assert len(result.compositions) == 2
    assert not result.is_empty


def test_a_short_digest_is_not_padded_with_an_ineligible_event():
    """An event below the confidence gate must not be published to fill a slot."""
    user_id = make_preference(_user_id()).user_id
    make_event(hours=2, title="Event One")
    make_event(
        hours=6,
        title="Low Confidence Event",
        extraction_confidence=Decimal("0.10"),
    )

    result = compose(user_id)

    assert len(result.compositions) == 1


# --- determinism ---------------------------------------------------------------------


def test_composing_twice_returns_the_identical_rows():
    user_id = make_preference(_user_id()).user_id
    for hours in (2, 3, 4):
        make_event(hours=hours, title=f"Event {hours}")

    first = compose(user_id)
    second = compose(user_id)

    assert [row.event_id for row in first.compositions] == [
        row.event_id for row in second.compositions
    ]
    assert [row.score for row in first.compositions] == [row.score for row in second.compositions]
    assert [row.bucket for row in first.compositions] == [row.bucket for row in second.compositions]
    assert [row.tags for row in first.compositions] == [row.tags for row in second.compositions]


def test_the_second_call_writes_nothing():
    """The re-run is a no-op: not a second composition, and not an update."""
    user_id = make_preference(_user_id()).user_id
    make_event(hours=2, title="Event One")

    first = compose(user_id)
    second = compose(user_id)

    assert first.created
    assert not second.created
    assert first.digest_id == second.digest_id
    assert PulseDigest.objects.using(PERSONAL).filter(user_id=user_id).count() == 1
    assert DigestComposition.objects.using(PERSONAL).filter(digest_id=first.digest_id).count() == 1


def test_the_second_call_writes_no_second_audit_row():
    """A re-run decides nothing, and the audit table records decisions."""
    user_id = make_preference(_user_id()).user_id
    make_event(hours=2, title="Event One")

    compose(user_id)
    compose(user_id)

    audits = PersonalizationAuditEntry.objects.using(PERSONAL).filter(action="digest.composed")
    assert audits.count() == 1


def test_two_users_get_different_digests_from_the_same_pool():
    """The composition is per user — the same events, different days or different cards."""
    one = make_preference(_user_id()).user_id
    two = make_preference(_user_id(), timezone="America/New_York").user_id
    make_event(hours=2, title="Event One")

    first = compose(one)
    second = compose(two)

    assert first.digest_id != second.digest_id


# --- the local date ------------------------------------------------------------------


def test_the_local_date_is_the_users_day_not_utc():
    """2026-11-04 16:00 UTC is the 4th in Los Angeles and the 4th in New York, but it
    is the 5th in Tokyo."""
    user_id = make_preference(_user_id(), timezone="Asia/Tokyo").user_id
    make_event(hours=2, title="Event One")

    result = compose(user_id)

    assert result.local_date == datetime(2026, 11, 5, 1, 0, tzinfo=UTC).date()


def test_two_users_in_different_zones_get_different_local_dates():
    """One UTC minute; two digests."""
    tokyo = make_preference(_user_id(), timezone="Asia/Tokyo").user_id
    los_angeles = make_preference(_user_id(), timezone="America/Los_Angeles").user_id
    make_event(hours=2, title="Event One")

    assert compose(tokyo).local_date != compose(los_angeles).local_date


def test_a_dst_fall_back_does_not_produce_two_digests_for_one_day():
    """In `America/New_York`, 2026-11-01 has two 01:00s. Two instants an hour apart in
    UTC are the same local day, so they are the same digest."""
    user_id = make_preference(_user_id(), timezone="America/New_York").user_id
    make_event(hours=2, title="Event One")

    first = compose(user_id, now=datetime(2026, 11, 1, 5, 30, tzinfo=UTC))
    second = compose(user_id, now=datetime(2026, 11, 1, 6, 30, tzinfo=UTC))

    assert first.local_date == second.local_date
    assert first.digest_id == second.digest_id
    assert not second.created


def test_an_unknown_zone_falls_back_to_utc_rather_than_failing():
    """The zone is validated at write time, so an unknown name here is hand-edited data.

    A composition that raised would leave the user with **no digest at all** — which is
    worse than a digest whose day is computed in the fallback zone. The failure mode is
    a wrong day, not a missing card.
    """
    user_id = make_preference(_user_id(), timezone="Mars/Olympus_Mons").user_id
    make_event(hours=2, title="Event One")

    result = compose(user_id)

    assert result.local_date == NOW.date()
    assert result.timezone == "Mars/Olympus_Mons"


def test_the_digest_records_the_zone_it_was_computed_in():
    user_id = make_preference(_user_id(), timezone="Asia/Tokyo").user_id
    make_event(hours=2, title="Event One")

    result = compose(user_id)

    digest = PulseDigest.objects.using(PERSONAL).get(id=result.digest_id)
    assert digest.timezone == "Asia/Tokyo"


def test_a_user_with_no_preference_gets_a_utc_digest():
    """A user who never went through onboarding has no zone and no city."""
    user_id = _user_id()
    make_event(hours=2, title="Event One")

    result = compose(user_id)

    assert result.timezone == "UTC"
    assert result.local_date == NOW.date()


# --- the city filter -----------------------------------------------------------------


def test_the_pool_is_filtered_to_the_users_city():
    user_id = make_preference(_user_id(), city="Brooklyn").user_id
    brooklyn = make_event(hours=2, title="Brooklyn Event", city="Brooklyn")
    make_event(hours=3, title="Queens Event", city="Queens")

    result = compose(user_id)

    assert brooklyn.id in {row.event_id for row in result.compositions}
    assert len(result.compositions) == 1


def test_a_user_with_no_city_is_not_filtered_to_the_fallback():
    """The fallback city is not the user's city, and ranking them on it would be the
    failure the `city_source` column exists to prevent."""
    user_id = make_preference(_user_id(), city=None, city_source=None).user_id
    make_event(hours=2, title="Event One")

    result = compose(user_id)

    assert len(result.compositions) == 1


# --- the interest term (the chips) ---------------------------------------------------


def test_the_interest_term_is_alive():
    """The interest term is the largest weight in the formula, and it needs the event's
    chips as well as the user's. Without the event's half it would be pinned to zero."""
    user_id = make_preference(_user_id()).user_id
    make_interest(user_id, "tech_meetups")
    matching = make_event(hours=2, title="Brooklyn Tech Meetup")

    result = compose(user_id)
    row = rows_of(result)["must_know"]

    assert row.event_id == matching.id
    assert "matches_tech_meetups" in row.tags


def test_a_matching_event_outscores_a_non_matching_one():
    """The interest term has to actually move the number, or it is an inert weight."""
    user_id = make_preference(_user_id()).user_id
    make_interest(user_id, "tech_meetups")
    make_event(hours=2, title="Tech Meetup")
    make_event(hours=3, title="Zzzz Quiet Evening")

    result = compose(user_id)
    rows = rows_of(result)

    assert rows["must_know"].score > rows["nearby"].score


def test_a_user_with_no_chips_is_not_punished_for_it():
    """The skip-everything path. The interest term scores zero and the other three
    terms still rank."""
    user_id = make_preference(_user_id()).user_id
    make_event(hours=2, title="Brooklyn Tech Meetup")

    result = compose(user_id)
    row = rows_of(result)["must_know"]

    assert row.score > Decimal("0.00")
    assert not any(tag.startswith("matches_") for tag in row.tags)


def test_a_chip_the_event_does_not_match_produces_no_tag():
    user_id = make_preference(_user_id()).user_id
    make_interest(user_id, "sports_fitness")
    make_event(hours=2, title="Brooklyn Tech Meetup")

    result = compose(user_id)

    assert not any(tag.startswith("matches_") for tag in rows_of(result)["must_know"].tags)


def test_the_serendipity_slot_suppresses_the_chip_tags():
    """Slot 3's tag is `discovery` — never a category name."""
    user_id = make_preference(_user_id()).user_id
    make_interest(user_id, "tech_meetups")
    for hours in (2, 3, 4):
        make_event(hours=hours, title=f"Tech Event {hours}")

    result = compose(user_id)
    row = rows_of(result)["serendipity"]

    assert "discovery" in row.tags
    assert not any(tag.startswith("matches_") for tag in row.tags)


# --- hysteresis ----------------------------------------------------------------------


def test_no_bucket_is_inherited_across_days():
    """EXPERIENCE.md §4: "Across days, hysteresis resets... No persistent bucket is
    stored between days."

    The same event, the same score, two days: two independent buckets.

    **The event starts after the second day.** A candidate is only a candidate while it
    has not started, so an event that started on the first day would have fallen out of
    the pool by the second — and the test would be measuring the *pool*, not the
    hysteresis. One event that is eligible on both days is what isolates the rule.
    """
    user_id = make_preference(_user_id()).user_id
    make_event(hours=50, title="Event One")

    first = compose(user_id)
    second = compose(user_id, now=NOW + DAY)

    assert rows_of(first)["must_know"].bucket == rows_of(second)["must_know"].bucket


def test_a_second_day_is_a_second_digest():
    user_id = make_preference(_user_id()).user_id
    make_event(hours=50, title="Event One")

    first = compose(user_id)
    second = compose(user_id, now=NOW + DAY)

    assert first.digest_id != second.digest_id
    assert second.created


# --- the saves -----------------------------------------------------------------------


def test_a_saved_event_carries_the_saved_tag():
    user_id = make_preference(_user_id()).user_id
    event = make_event(hours=2, title="Event One")
    SavedEventFactory(
        user_id=user_id,
        event_id=event.id,
        start_utc=event.start_time_utc,
        event_version=event.event_version,
    )

    result = compose(user_id)

    assert "saved" in rows_of(result)["must_know"].tags


def test_an_unsaved_event_has_no_saved_tag():
    user_id = make_preference(_user_id()).user_id
    make_event(hours=2, title="Event One")

    result = compose(user_id)

    assert "saved" not in rows_of(result)["must_know"].tags


# --- the conflicts -------------------------------------------------------------------


def test_a_conflicted_event_still_appears():
    """FR-58: a conflict is an indicator on a card, not an exclusion."""
    from apps.personalization.models import ConflictPair

    user_id = make_preference(_user_id()).user_id
    personal = make_personal(user_id, hours=3)
    other = make_personal(user_id, hours=4)
    ConflictPair.objects.using(PERSONAL).create(
        user_id=user_id,
        kind=ConflictPair.Kind.TIME,
        left_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        left_id=personal.id,
        right_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        right_id=other.id,
    )

    result = compose(user_id)

    assert personal.id in {row.event_id for row in result.compositions}


# --- the audit -----------------------------------------------------------------------


def test_the_audit_row_records_the_composition():
    user_id = make_preference(_user_id()).user_id
    make_event(hours=2, title="Event One")

    result = compose(user_id)

    audit = PersonalizationAuditEntry.objects.using(PERSONAL).get(action="digest.composed")
    assert audit.target_id == result.digest_id
    assert audit.details["composition_count"] == 1
    assert audit.details["is_empty"] is False
    assert audit.details["local_date"] == result.local_date.isoformat()


def test_the_audit_row_carries_no_event_content():
    """AD-13: no titles, no cities, no tag lists, no event ids."""
    user_id = make_preference(_user_id()).user_id
    make_event(hours=2, title="A Very Distinctive Event Title")

    compose(user_id)

    audit = PersonalizationAuditEntry.objects.using(PERSONAL).get(action="digest.composed")
    assert "A Very Distinctive Event Title" not in str(audit.details)
    assert "event_id" not in audit.details
    assert "tags" not in audit.details
    assert "city" not in audit.details


# --- the transaction and the wall ----------------------------------------------------


def test_the_catalog_is_read_outside_the_personal_transaction():
    """AD-3: no transaction spans both schemas."""
    from django.db import connections

    user_id = make_preference(_user_id()).user_id
    make_event(hours=2, title="Event One")

    seen = []

    class _Recorder:
        def __call__(self, execute, sql, params, many, context):
            if "INSERT" in sql.upper() or "SAVEPOINT" in sql.upper():
                seen.append(sql)
            return execute(sql, params, many, context)

    with connections[PERSONAL].execute_wrapper(_Recorder()):
        compose(user_id)

    assert not any("ingestion_event" in sql.lower() for sql in seen)


def test_the_composition_never_touches_the_catalog_for_writes():
    """The catalog is read; it is never written."""
    from django.db import connections

    user_id = make_preference(_user_id()).user_id
    make_event(hours=2, title="Event One")

    writes = []

    class _Recorder:
        def __call__(self, execute, sql, params, many, context):
            if sql.strip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                writes.append(sql)
            return execute(sql, params, many, context)

    with connections[CATALOG].execute_wrapper(_Recorder()):
        compose(user_id)

    assert not writes


# --- the command's shape -------------------------------------------------------------


def test_the_command_takes_an_actor_and_writes_it_to_the_audit_row():
    user_id = make_preference(_user_id()).user_id
    make_event(hours=2, title="Event One")

    compose(user_id, actor=Actor.system("digest_worker"))

    audit = PersonalizationAuditEntry.objects.using(PERSONAL).get(action="digest.composed")
    assert audit.actor_kind == "system"
    assert audit.actor_label == "digest_worker"


def test_the_result_carries_the_composition_count():
    user_id = make_preference(_user_id()).user_id
    for hours in (2, 3):
        make_event(hours=hours, title=f"Event {hours}")

    result = compose(user_id)

    assert len(result.compositions) == 2


def _user_id():
    from shared.ids import uuid7

    return uuid7()
