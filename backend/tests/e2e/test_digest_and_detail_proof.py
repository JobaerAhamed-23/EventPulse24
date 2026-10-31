"""The Pulse Digest and the Detail Screen, end to end.

**Why one test and not fifteen.** The point of a proof is that the steps *compose*.
Eleven items of this intent were built and each was tested in isolation; the failures
that matter live in the seams between them. A chain of independent tests proves each
step and not the whole — a digest composed in one test and read in another is not the
same digest, and a row written in one test and counted in another catches nothing.

So the scenario is one test, one user, one database, and one transaction's worth of
shared state.

**What this scenario proves, and what it does not.**

The work item's scenario says the user "opens `/`, sees three cards in three slots with
their trust signals, taps one, and reads a why-this breakdown built from the same
persisted row the card rendered."

**The rendered half was proved by the two frontend items**, and proved better than a
browser could: the digest home's own tests assert the rendered cards, the detail
screen's assert the rendered breakdown, and the *equality* between them is asserted on
the **same persisted row**, because both read the same `DigestComposition`.

**What is proved here is the half a browser cannot see: the rows.** The scenario walks
the whole chain — the preference, the interests, the catalog, the composition, the two
read paths — and asserts that:

- the digest read returns three cards in three slots;
- the detail read returns one of those events;
- **the card's tags, bucket and badge are the breakdown's tags, bucket and badge** —
  two independent services, one persisted row.

**The last point is FR-21's consistency consequence, and it is the claim this whole
intent exists for.** If the card and the detail could disagree, the trust surface would
be decorative: the reader could check the explanation and find a different one.

**The three other scenarios** are separate tests, and each is separate for a reason:

- the **skip-everything** path — no interest chips, no city — because it is the path
  nobody clicks manually, and it is the path most likely to rot;
- the **empty** path — a city with nothing in it — because "there is nothing near you"
  and "we have not built it yet" are different facts that both answer 200;
- the **determinism** path — composing twice — because the second composition must
  write nothing at all.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from apps.ingestion.services.source_badges import SOURCE_BADGE_OFFICIAL
from apps.personalization.models import DigestComposition, Interest
from apps.personalization.services.detail_read import read_event_detail
from apps.personalization.services.digest_composition import compose_digest
from apps.personalization.services.digest_read import read_digest
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory, VenueFactory
from tests.personalization.factories import DigestPreferenceFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

ACTOR = Actor.system("e2e_proof")

#: A Wednesday. 2026-11-04 16:00 UTC is 09:00 in Los Angeles (PST).
NOW = datetime(2026, 11, 4, 16, 0, tzinfo=UTC)

#: The city under test, and its zone.
CITY = "Los Angeles"
ZONE = "America/Los_Angeles"

#: A city with nothing in it. The empty-state scenario uses it.
EMPTY_CITY = "Reykjavik"


def make_user(*, city=CITY, chips=("tech",)):
    """One user with a preference and, optionally, interest chips.

    **The chips are `Interest` rows on the personal side** — the same rows the
    composition reads for the interest term. A user with no chips has *no preference*,
    which is a real state and not the same as "every preference".
    """
    user_id = uuid4()
    DigestPreferenceFactory(
        user_id=user_id,
        timezone=ZONE,
        city=city,
        city_source="choice",
    )
    for chip_key in chips:
        Interest.objects.using(PERSONAL).create(user_id=user_id, chip_key=chip_key)
    return user_id


def make_event(*, hours=2, title="Brooklyn Tech Meetup", city=CITY):
    """A published, eligible public event.

    **`last_seen_at` is pinned to `NOW`.** FR-14's staleness bound is measured from it
    against the test's clock, and the column's default is the wall clock — so an event
    built with the default would be days stale against a `NOW` in the future, and the
    candidate read would drop it before the composition ever saw it.
    """
    return EventFactory(
        title=title,
        venue=VenueFactory(city=city, venue_fingerprint=f"venue-{title}|{city}"),
        start_time_utc=NOW + timedelta(hours=hours),
        last_seen_at=NOW,
    )


def compose(user_id, *, now=NOW):
    return compose_digest(user_id=user_id, actor=ACTOR, now=now)


# ── The scenario ──────────────────────────────────────────────────────────────────────


def test_the_digest_and_the_detail_are_two_projections_of_one_persisted_row():
    """**The whole intent, in one path.**

    The chain: a user with a city and an interest chip, three events in their city, a
    composition by the worker, the digest read, the detail read — and the claim that
    the card and the breakdown are **the same persisted row** read two ways.
    """
    user_id = make_user()
    for hours in (2, 3, 4):
        make_event(hours=hours, title=f"Tech Meetup {hours}")

    # The composition is the **worker's** work (AD-11), and the scenario calls it
    # directly — the same command the worker's task runs.
    result = compose(user_id)

    assert len(result.compositions) == 3, "a standard day holds three cards"
    assert not result.is_empty
    assert [row.slot for row in result.compositions] == ["must_know", "nearby", "serendipity"]

    # The rows are persisted, on the personal side, and there are three of them.
    rows = list(
        DigestComposition.objects.using(PERSONAL)
        .filter(digest_id=result.digest_id)
        .order_by("slot")
    )
    assert len(rows) == 3

    # The digest read projects them.
    digest = read_digest(user_id=user_id, now=NOW)
    assert digest.status == "composed"
    assert len(digest.cards) == 3
    assert [card.slot for card in digest.cards] == ["must_know", "nearby", "serendipity"]

    # The detail read serves one of them.
    card = digest.cards[0]
    detail = read_event_detail(event_id=card.event_id, user_id=user_id, now=NOW)

    assert detail.personal is not None, "a signed-in reader with a composition has one"
    why_this = detail.personal.why_this
    assert why_this is not None, "the detail carries the persisted explanation"

    # **The claim.** The card's trust signals and the breakdown's are the same values,
    # read from the same row by two independent services.
    assert why_this.tags == card.tags, "the tags are the card's tags"
    assert why_this.bucket == card.bucket, "the confidence is the card's confidence"
    assert why_this.source_badge == card.source_badge, "the badge is the card's badge"

    # And they are the **row's** values, not merely equal to each other.
    row = next(row for row in rows if row.event_id == card.event_id)
    assert tuple(row.tags) == tuple(card.tags)
    assert row.bucket == card.bucket
    assert row.source_badge == card.source_badge


def test_the_two_read_paths_agree_on_every_card():
    """**Every** card, not just the first.

    The first card was the one the scenario tapped. A disagreement on the *second*
    card would be just as much a lie, and a test that checked one card would not have
    caught it.
    """
    user_id = make_user()
    for hours in (2, 3, 4):
        make_event(hours=hours, title=f"Tech Meetup {hours}")

    compose(user_id)
    digest = read_digest(user_id=user_id, now=NOW)

    for card in digest.cards:
        detail = read_event_detail(event_id=card.event_id, user_id=user_id, now=NOW)
        assert detail.personal is not None
        why_this = detail.personal.why_this
        assert why_this is not None
        assert why_this.tags == card.tags
        assert why_this.bucket == card.bucket
        assert why_this.source_badge == card.source_badge


# ── The skip-everything path ───────────────────────────────────────────────────────────


def test_a_user_who_skipped_everything_still_gets_a_digest():
    """**No interest chips, no city.** The path nobody clicks manually.

    The danger the work item names is specific: the ranking must score them "without
    dividing by zero and without silently treating 'no preference' as 'every
    preference'".

    So the scenario asserts three things: the composition **completes**, the persisted
    tags carry **no `matches_` tag** — "no preference" is not "every preference" — and
    the digest still has cards.
    """
    # No chips, and a preference with **no city**: the user skipped the city step.
    user_id = uuid4()
    DigestPreferenceFactory(user_id=user_id, timezone=ZONE, city=None, city_source=None)

    for hours in (2, 3, 4):
        make_event(hours=hours, title=f"Meetup {hours}")

    result = compose(user_id)

    # It completes. No ZeroDivisionError, no exception.
    assert not result.is_empty, "a day with events in the catalog is not empty"

    rows = list(DigestComposition.objects.using(PERSONAL).filter(digest_id=result.digest_id))
    assert len(rows) >= 1

    for row in rows:
        # **No preference is not every preference.** An interest tag would be a claim
        # that the event matched something the user picked, and they picked nothing.
        assert not any(tag.startswith("matches_") for tag in row.tags), (
            f"the composition claims an interest match for a user with no interests: {row.tags}"
        )

    # And the digest read serves it.
    digest = read_digest(user_id=user_id, now=NOW)
    assert digest.status == "composed"
    assert len(digest.cards) >= 1


def test_a_user_with_no_preference_at_all_still_composes():
    """**No preference row at all.** The most skipped path there is.

    A user who skipped onboarding has no `DigestPreference` row — not a row with null
    fields, no row. So the composition must fall back to the defaults, and it must do
    so without reaching for a division by zero.
    """
    user_id = uuid4()  # no DigestPreferenceFactory call at all.

    for hours in (2, 3, 4):
        make_event(hours=hours, title=f"Meetup {hours}")

    result = compose(user_id)

    assert not result.is_empty
    digest = read_digest(user_id=user_id, now=NOW)
    assert digest.status == "composed"


# ── The empty-state path ──────────────────────────────────────────────────────────────


def test_a_city_with_nothing_in_it_is_empty_and_not_being_prepared():
    """**A real digest with no cards**, and not the absence of one.

    "There is nothing near you" and "we have not built it yet" are different facts, and
    the frontend renders different documents for them. So the scenario asserts the
    status is `empty` — not `not_composed`.
    """
    user_id = make_user(city=EMPTY_CITY, chips=())

    # Nothing is ingested into Reykjavik.
    result = compose(user_id)

    assert result.is_empty, "a city with no qualifying events is an empty digest"
    assert result.compositions == ()

    digest = read_digest(user_id=user_id, now=NOW)

    assert digest.status == "empty", "the status is empty, not not_composed"
    assert digest.cards == (), "an empty digest has no cards"
    # And the city line is the user's city — FR-8's empty card names it.
    assert digest.city == EMPTY_CITY


# ── The determinism path ───────────────────────────────────────────────────────────────


def test_composing_twice_produces_the_same_rows_and_the_same_digest():
    """**The second composition writes nothing at all.**

    The re-run is a no-op by design: the existing digest is returned, nothing is
    written, and no second audit row appears. So the test asserts three things: the
    rows are the same, the row **count** has not moved, and the read is the same.

    **The composition's `composed_at` is unchanged**, which is the sharpest of the
    three: a second composition that rewrote the rows would produce the same *content*
    with a new timestamp.
    """
    user_id = make_user()
    for hours in (2, 3, 4):
        make_event(hours=hours, title=f"Tech Meetup {hours}")

    first = compose(user_id)
    rows_before = list(
        DigestComposition.objects.using(PERSONAL).filter(digest_id=first.digest_id).order_by("slot")
    )
    digest_before = read_digest(user_id=user_id, now=NOW)

    # The second composition, at a **later** instant — so a rewrite would be visible
    # in the timestamps.
    second = compose(user_id, now=NOW + timedelta(hours=1))

    rows_after = list(
        DigestComposition.objects.using(PERSONAL)
        .filter(digest_id=second.digest_id)
        .order_by("slot")
    )
    digest_after = read_digest(user_id=user_id, now=NOW)

    # The same digest, not a new one.
    assert second.digest_id == first.digest_id
    assert second.created is False, "the re-run creates nothing"

    # The same rows — same count, same content, same timestamps.
    assert len(rows_after) == len(rows_before)
    for before, after in zip(rows_before, rows_after, strict=True):
        assert after.id == before.id
        assert after.slot == before.slot
        assert after.event_id == before.event_id
        assert after.bucket == before.bucket
        assert list(after.tags) == list(before.tags)
        assert after.source_badge == before.source_badge
        assert after.composed_at == before.composed_at, (
            "the second composition rewrote the rows; it is a no-op"
        )

    # And the same read.
    assert digest_after.status == digest_before.status
    assert [card.event_id for card in digest_after.cards] == [
        card.event_id for card in digest_before.cards
    ]
    assert [list(card.tags) for card in digest_after.cards] == [
        list(card.tags) for card in digest_before.cards
    ]


# ── The read generates nothing ─────────────────────────────────────────────────────────


def test_reading_the_digest_writes_no_composition_row():
    """**AD-10's strong half, at the database.** The row count does not move.

    A source check cannot make this claim: a read could call a service that writes, and
    every import check and every call check would stay green. So the count is taken
    before the read and after it.
    """
    user_id = make_user()
    for hours in (2, 3, 4):
        make_event(hours=hours, title=f"Tech Meetup {hours}")

    compose(user_id)
    before = DigestComposition.objects.using(PERSONAL).count()

    for _ in range(3):
        read_digest(user_id=user_id, now=NOW)

    after = DigestComposition.objects.using(PERSONAL).count()
    assert after == before, "the digest read wrote a composition row"


def test_reading_the_detail_writes_no_composition_row():
    """**The same claim for the other read path.**

    The detail read is the one that serves a **breakdown**, so it is the one where a
    view-time explanation would be most tempting — and where the user would most
    easily be shown a plausible reason for an event they were never shown.
    """
    user_id = make_user()
    for hours in (2, 3, 4):
        make_event(hours=hours, title=f"Tech Meetup {hours}")

    compose(user_id)
    digest = read_digest(user_id=user_id, now=NOW)
    before = DigestComposition.objects.using(PERSONAL).count()

    for card in digest.cards:
        read_event_detail(event_id=card.event_id, user_id=user_id, now=NOW)

    after = DigestComposition.objects.using(PERSONAL).count()
    assert after == before, "the detail read wrote a composition row"


def test_an_event_never_shown_gets_no_explanation_at_all():
    """**AD-10, observed.** The event the user was never shown.

    An event in the catalog that is not in the user's digest has no composition. The
    detail read must say so — and it must not make one, and it must not fall back to
    the Event Fit.
    """
    user_id = make_user()
    for hours in (2, 3, 4):
        make_event(hours=hours, title=f"Tech Meetup {hours}")

    compose(user_id)

    # A fourth event, in the same city, that the digest did not take.
    unseen = make_event(hours=5, title="Meetup Nobody Was Shown")

    detail = read_event_detail(event_id=unseen.id, user_id=user_id, now=NOW)

    assert detail.personal is not None, "the user is signed in, so the row is read"
    assert detail.personal.why_this is None, (
        "an event the user was never shown got an explanation. AD-10: no explanation "
        "rather than a recomputed one."
    )
    # **FR-24: exact counts are never exposed.** The neighbour count arrives as a
    # bucket key or `None` (suppressed), and the object it arrives in has **no count
    # field at all** — so the number cannot be read off it even by accident.
    neighbours = detail.personal.neighbors
    assert neighbours.bucket is None or neighbours.bucket in {
        "few",
        "some",
        "many",
        "a_lot",
    }, "the neighbour count is a bucket key or a suppression, never a number"
    assert not hasattr(neighbours, "count"), (
        "the neighbour count object grew a count field. FR-24: exact counts are never "
        "exposed, and the way to keep that true is for the object to have no place to "
        "put one."
    )


def test_the_anonymous_read_is_the_same_event_without_the_personal_half():
    """**The anonymous visitor gets the public facts and nothing else.**

    The same event, the same `now`, and the **same public facts** — and the personal
    half is `None` rather than an empty object, because "you are not signed in" and
    "you are signed in and have nothing here" are different claims.
    """
    user_id = make_user()
    for hours in (2, 3, 4):
        make_event(hours=hours, title=f"Tech Meetup {hours}")

    compose(user_id)
    digest = read_digest(user_id=user_id, now=NOW)
    card = digest.cards[0]

    signed_in = read_event_detail(event_id=card.event_id, user_id=user_id, now=NOW)
    anonymous = read_event_detail(event_id=card.event_id, user_id=None, now=NOW)

    assert anonymous.personal is None
    assert signed_in.personal is not None

    # The public facts are **identical**. The personal half is the only difference.
    assert anonymous.event.id == signed_in.event.id
    assert anonymous.event.title == signed_in.event.title
    assert anonymous.event.start_time_utc == signed_in.event.start_time_utc
    assert anonymous.event.start_time_tz == signed_in.event.start_time_tz


# ── The score is the persisted one ────────────────────────────────────────────────────


def test_the_bucket_is_persisted_and_not_recomputed_at_render():
    """**The bucket the user saw this morning is the bucket they see now.**

    The score is persisted as a `Decimal` and the bucket as an `int`. The read serves
    the bucket. A client that re-bucketed the raw score could flicker — and the
    backend serving a re-bucketed score would be AD-10's substitution one layer down.
    """
    user_id = make_user()
    for hours in (2, 3, 4):
        make_event(hours=hours, title=f"Tech Meetup {hours}")

    result = compose(user_id)
    rows = {
        row.event_id: row
        for row in DigestComposition.objects.using(PERSONAL).filter(digest_id=result.digest_id)
    }

    digest = read_digest(user_id=user_id, now=NOW)

    for card in digest.cards:
        row = rows[card.event_id]
        assert card.bucket == row.bucket, "the card's bucket is the row's bucket"
        assert isinstance(row.score, Decimal)
        assert 1 <= row.bucket <= 5


def test_the_source_badge_is_the_persisted_one():
    """**The Source Badge is a persisted fact, and the read serves it.**

    The badge says how the event was acquired — official, crawled, community. It is
    persisted on the composition, and the card and the breakdown both serve it.

    **The assertion is on the value, not on its type.** The badge is one of four known
    keys, and the events here are ingested from a `VENUE` source — so the badge is
    `official_site` and nothing else. A test that only checked "it is a string" would
    pass for a badge of `"whatever"`, which is the shape of a test that cannot fail.
    """
    user_id = make_user()
    for hours in (2, 3, 4):
        make_event(hours=hours, title=f"Tech Meetup {hours}")

    compose(user_id)
    digest = read_digest(user_id=user_id, now=NOW)

    assert digest.cards, "the digest has cards, so the badge has something to be"

    for card in digest.cards:
        detail = read_event_detail(event_id=card.event_id, user_id=user_id, now=NOW)
        assert detail.personal is not None
        why_this = detail.personal.why_this
        assert why_this is not None

        # The badge is one of the four known keys, and for these events it is
        # specifically the official one — the source is a venue.
        assert card.source_badge == SOURCE_BADGE_OFFICIAL, (
            f"the card's badge is {card.source_badge!r}, not the official badge"
        )
        assert why_this.source_badge == SOURCE_BADGE_OFFICIAL, (
            f"the breakdown's badge is {why_this.source_badge!r}, not the official badge"
        )
        assert why_this.source_badge == card.source_badge, "the badge is the card's badge"
