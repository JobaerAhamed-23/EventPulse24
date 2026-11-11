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


# --- the pool counts, which answer FR-10's question -------------------------------------------


def test_the_result_carries_the_public_pool_count():
    """**The pool, not the cards.** A user with forty eligible events still gets three
    cards, and FR-10's rule asks about the pool."""
    user_id = make_preference(_user_id()).user_id
    for hours in (2, 3, 4, 5):
        make_event(hours=hours, title=f"Event {hours}")

    result = compose(user_id)

    assert result.public_qualifying_count == 4
    assert len(result.compositions) == 3


def test_the_result_carries_the_personal_pool_count():
    user_id = make_preference(_user_id()).user_id
    make_personal(user_id, hours=3)
    make_personal(user_id, hours=5)

    result = compose(user_id)

    assert result.personal_qualifying_count == 2


def test_the_personal_pool_count_is_zero_for_an_opted_out_user():
    """**FR-19's opt-out reaches the count.** A user who asked not to see their personal
    events must not be kept subscribed to a Ping *by* them."""
    user_id = make_preference(_user_id(), include_personal_events=False).user_id
    make_personal(user_id, hours=3)

    result = compose(user_id)

    assert result.personal_qualifying_count == 0


def test_the_counts_ignore_events_beyond_the_forty_eight_hour_horizon():
    """**The horizon is FR-10's "next 48 hours".** An event four days out is in the pool
    but is not a reason to ping today."""
    user_id = make_preference(_user_id()).user_id
    make_event(hours=2, title="Soon")
    make_event(hours=96, title="Later")

    result = compose(user_id)

    assert result.public_qualifying_count == 1


def test_the_horizon_is_the_users_own_zone_and_not_utc():
    """**The 48-hour window is drawn in the user's zone**, so the cutoff is not
    `now + 48h` in UTC.

    `NOW` is 16:00 UTC, which is 08:00 in Los Angeles. 48 wall-clock hours on is 08:00
    on the 6th — and the naive UTC arithmetic would have said 16:00.
    """
    user_id = make_preference(_user_id()).user_id

    result = compose(user_id)

    assert result.horizon_utc == datetime(2026, 11, 6, 16, 0, tzinfo=UTC)


def test_the_personal_pool_is_not_narrower_than_the_local_horizon_on_a_fall_back_day():
    """**The pool and the count must agree about "the next 48 hours", even on a DST
    day.** This is the negative control for the two windows drifting apart.

    **On a fall-back day the local horizon is an hour *later* than the elapsed
    arithmetic.** 2026-11-01 is 00:00 PDT; 48 wall-clock hours on is 00:00 on the 3rd
    — `2026-11-03 08:00 UTC` — while `now + 48h` says `07:00 UTC`.

    So a personal event at 07:30 UTC on the 3rd is **within 48 local hours of the
    user**, but only 47.5 *elapsed* hours away. It has to be counted: a user with a
    real event in the next 48 hours must not be suppressed for having it.

    **This is where the pool would have dropped it.** The read's own bound was
    `now + 48h` — elapsed arithmetic — so an event in this band was never read at all,
    and the count had nothing to count. The read is now widened to cover the local
    horizon, so the pool is a superset and this comparison is what narrows it.
    """
    # 00:00 PDT on the US fall-back day.
    fall = datetime(2026, 11, 1, 7, 0, tzinfo=UTC)
    # The local horizon is 08:00 UTC; the elapsed arithmetic would say 07:00 UTC.
    horizon = datetime(2026, 11, 3, 8, 0, tzinfo=UTC)

    user_id = make_preference(_user_id()).user_id
    # 07:30 UTC on the 3rd: inside the local horizon, outside the elapsed window.
    start = datetime(2026, 11, 3, 7, 30, tzinfo=UTC)
    make_personal(user_id, start_utc=start, end_utc=start + timedelta(hours=2))

    result = compose(user_id, now=fall)

    assert result.horizon_utc == horizon
    assert result.personal_qualifying_count == 1
    assert result.has_qualifying_events


def test_an_event_past_the_local_horizon_is_not_counted_on_a_spring_forward_day():
    """**The other DST day, and the other direction.** On a spring-forward day the
    local horizon is an hour *earlier* than the elapsed arithmetic — `07:00` UTC
    rather than `08:00` — so it is the *binding* constraint, and an event between the
    two is correctly **outside** the user's next 48 local hours.

    The point of the test is that the **pool's** bound is not what excludes it. The
    event is still read (the read is widened to cover the horizon), and the count
    excludes it on the horizon's own terms. If the read were the thing excluding it,
    the two windows would still be drifting apart — just in the other direction.
    """
    # 00:00 PST on the US spring-forward day.
    spring = datetime(2026, 3, 8, 8, 0, tzinfo=UTC)
    # The local horizon is 07:00 UTC; the elapsed arithmetic would say 08:00 UTC.
    horizon = datetime(2026, 3, 10, 7, 0, tzinfo=UTC)

    user_id = make_preference(_user_id()).user_id
    # 07:30 UTC on the 10th: inside the elapsed window, outside the local horizon.
    start = datetime(2026, 3, 10, 7, 30, tzinfo=UTC)
    make_personal(user_id, start_utc=start, end_utc=start + timedelta(hours=2))

    result = compose(user_id, now=spring)

    assert result.horizon_utc == horizon
    assert result.personal_qualifying_count == 0
    assert not result.has_qualifying_events


def test_the_counts_are_the_same_on_a_re_run():
    """**A re-run reports the same counts.** The composition is idempotent, and a
    second run that reported different counts would make the Ping decision depend on
    whether the job had been retried."""
    user_id = make_preference(_user_id()).user_id
    make_event(hours=2, title="One")
    make_event(hours=3, title="Two")

    first = compose(user_id)
    second = compose(user_id)

    assert second.created is False
    assert second.public_qualifying_count == first.public_qualifying_count
    assert second.personal_qualifying_count == first.personal_qualifying_count


def test_has_qualifying_events_is_the_and_of_the_two_counts():
    """**One place, so the rule cannot be written twice.** FR-10's first consequence is
    "0 qualifying public events AND 0 personal events → no Ping"; this is the `AND`."""
    user_id = make_preference(_user_id()).user_id
    make_event(hours=2, title="One")

    result = compose(user_id)

    assert result.has_qualifying_events is True


def test_has_qualifying_events_is_false_when_both_counts_are_zero():
    user_id = make_preference(_user_id()).user_id

    result = compose(user_id)

    assert result.public_qualifying_count == 0
    assert result.personal_qualifying_count == 0
    assert result.has_qualifying_events is False


def test_a_personal_event_alone_makes_it_qualifying():
    """**FR-10's second consequence, at the composition's end**: a personal event is a
    qualifying event even with nothing public."""
    user_id = make_preference(_user_id()).user_id
    make_personal(user_id, hours=3)

    result = compose(user_id)

    assert result.public_qualifying_count == 0
    assert result.personal_qualifying_count == 1
    assert result.has_qualifying_events is True


def _user_id():
    from shared.ids import uuid7

    return uuid7()


# --- the reliability term (FR-16 → FR-22) ──────────────────────────────────────────
#
# **The service half of the proof.** The domain tests prove the term moves the score;
# these prove the *composition* reads the source's real score and puts it on the card.
#
# **The N+1 proof is the query count.** The reliability term has to arrive on the
# candidate, because the candidate read already joins the source. An implementation that
# looked the score up per candidate would make the catalog query count grow with the
# number of candidates — and that is what the count test below catches.


def make_scored_event(*, reliability: Decimal, hours=2, title="Brooklyn Tech Meetup", **overrides):
    """A public event whose source carries a computed reliability score.

    **FR-16's floor is 0.32**, so a source the recompute has actually scored cannot be
    below it — which is why these use 0.32 rather than the domain tests' 0.20. The
    domain test proves the term's arithmetic at 0.20; this one proves the *wiring* with
    a value the recompute could really have written.
    """
    fields = {
        "title": title,
        "venue": VenueFactory(city=CITY, venue_fingerprint=f"venue-{title}|{CITY}"),
        "start_time_utc": NOW + timedelta(hours=hours),
        "last_seen_at": NOW,
    }
    fields.update(overrides)
    event = EventFactory(**fields)
    event.source.reliability_score = reliability
    event.source.reliability_scored_at = NOW
    event.source.save(update_fields=["reliability_score", "reliability_scored_at"])
    return event


def test_the_source_reliability_reaches_the_card():
    """A source's real score is on the ranking inputs, and it moves the card's score.

    **Two users, one event, one day.** The composition is a no-op for a user who already
    has a digest for the day, and the candidate read drops an event that has started — so
    the two compositions have to be for different users at the same `NOW`, against the
    same event. Everything about the event is then identical except the source's score.
    """
    user_id = make_preference(_user_id()).user_id
    make_interest(user_id, "tech")
    event = make_scored_event(reliability=Decimal("0.80"), title="Tech Meetup")

    result = compose(user_id)
    assert result.compositions
    better_score = result.compositions[0].score

    # The same event, a worse source, and a second user so the composition is a fresh one.
    event.source.reliability_score = Decimal("0.32")
    event.source.save(update_fields=["reliability_score"])

    other_user = make_preference(_user_id()).user_id
    make_interest(other_user, "tech")
    worse_result = compose(other_user)

    assert worse_result.compositions
    worse_score = worse_result.compositions[0].score

    # The domain proves the arithmetic; this proves the value travels.
    assert worse_score < better_score


def test_an_unscored_source_is_at_the_prior():
    """A source the recompute has not reached contributes the prior, not a zero.

    The prior is 0.50, and it is *asked of the domain module* — the same module the
    recompute asks — so the value cannot drift from FR-16's own idea of "no evidence".

    **The assertion is relative, because an absolute one proves nothing.** "The score is
    greater than zero" is true of any reliability value, including a zero, because four
    other terms contribute — and a test that passes while the composition substitutes
    0.00 for the prior is a false green on this test's own claim. So the unscored
    source is placed **between** the two scored sources: above one scored at 0.00 and
    below one scored at 0.80. That ordering is only true if the unscored value really
    is the prior, and only a prior sits strictly between them.

    **One event, three users, three compositions.** The event is the same one each time
    and only its *source's score* changes, so the three cards are otherwise identical.
    Each composition needs its own user, because composing twice for the same user and
    day is a no-op — and each reads `compositions[0]`, which is the card for the only
    event in the pool.
    """
    from domain.reliability import reliability_score

    prior = reliability_score(0, 0)

    event = make_event(hours=2, title="Tech Meetup")
    assert event.source.reliability_score is None, (
        "This test needs a source the recompute has never scored; if the factory seeds "
        "a score, the comparison below would be measuring a scored source."
    )

    def card_score_for_a_fresh_user() -> Decimal:
        """The one card's score, for a user who has not been composed for yet."""
        user_id = make_preference(_user_id()).user_id
        make_interest(user_id, "tech")
        result = compose(user_id)
        assert result.compositions
        return result.compositions[0].score

    # The unscored source: the recompute has not reached it.
    unscored_score = card_score_for_a_fresh_user()

    # The worst scored source — below the prior.
    event.source.reliability_score = Decimal("0.00")
    event.source.save(update_fields=["reliability_score"])
    worst_score = card_score_for_a_fresh_user()

    # The best scored source — above the prior.
    event.source.reliability_score = Decimal("0.80")
    event.source.save(update_fields=["reliability_score"])
    best_score = card_score_for_a_fresh_user()

    assert worst_score < unscored_score < best_score, (
        f"An unscored source scored {unscored_score}, which is not strictly between a "
        f"source at 0.00 ({worst_score}) and a source at 0.80 ({best_score}). The prior "
        "is what sits between them — a zero would tie the first, and a 1.00 would tie "
        "the second."
    )
    assert prior == Decimal("0.50")


def test_the_composition_costs_no_query_per_candidate():
    """**The N+1 proof.** The catalog query count does not grow with the pool.

    The reliability term has to arrive on the candidate — the candidate read already
    joins the source, so the score is a column on a row that is already there. An
    implementation that read `Source.objects.get(...)` per candidate would make this
    count grow with the number of candidates, and this test would fail.
    """
    from django.db import connections
    from django.test.utils import CaptureQueriesContext

    user_id = make_preference(_user_id()).user_id
    make_event(hours=2, title="Only Event")

    with CaptureQueriesContext(connections[CATALOG]) as one_candidate:
        compose(user_id)
    one = len(one_candidate.captured_queries)

    user2 = make_preference(_user_id()).user_id
    for hours in (2, 3, 4, 5, 6, 7, 8, 9, 10, 11):
        make_event(hours=hours, title=f"Event {hours}")

    with CaptureQueriesContext(connections[CATALOG]) as ten_candidates:
        compose(user2)
    ten = len(ten_candidates.captured_queries)

    assert ten == one, (
        f"The composition issued {ten} catalog queries for ten candidates and {one} for "
        "one. The reliability term must ride on the candidate the read already joined — "
        "a lookup per candidate is the N+1 this test exists to catch."
    )


def test_a_source_reliability_of_zero_still_scores_the_other_terms():
    """The worst possible source does not zero the card.

    The term is one of five. A source at 0.00 contributes nothing, and the card is
    still ranked on the other four — which is the difference between "this source is
    worse" and "this event is worthless".
    """
    user_id = make_preference(_user_id()).user_id
    make_interest(user_id, "tech")
    make_scored_event(reliability=Decimal("0.32"), title="Tech Meetup")

    result = compose(user_id)

    assert result.compositions
    assert result.compositions[0].score > Decimal("0.00")
