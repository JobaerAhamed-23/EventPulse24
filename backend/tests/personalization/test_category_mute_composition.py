"""The category mute at the composition seam: what a muted category excludes (FR-25).

**The mute is a filter, not a sixth term in FR-22's formula.** The Relevance Pulse is
exactly five weighted terms summing to 1.00, and CI pins those five weights against
ADR-0025. A mute cannot be a sixth term — that would change the published formula and the
pin with it. So the mute is applied to the **candidate set**, before anything is scored: a
muted category's events are *absent*, not scored and discarded.

**The filter runs before the scorers.** A mute is a statement about the candidate *set*,
not about an event's rank. A muted category's events should not be scored and then thrown
away — that is work spent on an event the user will never see.

**Browse agrees with Digest.** The same filter runs in `read_browse_page`, so the two
surfaces cannot disagree about what a muted category means.

**An event with no chips is never muted.** The chip keys are matched from the event's own
text, so an event matching no keyword belongs to no category — and excluding it would be
the product deciding what it is on the user's behalf.
"""

from datetime import UTC, datetime, timedelta

import pytest

from apps.personalization.services.browse_read import read_browse_page
from apps.personalization.services.digest_composition import compose_digest
from apps.personalization.services.taste_mutes import set_category_mute
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7
from tests.ingestion.factories import EventFactory, VenueFactory
from tests.personalization.factories import DigestPreferenceFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

ACTOR = Actor.system("category_mute_composition")

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
CITY = "Brooklyn"
ZONE = "America/Los_Angeles"


def make_preference(user_id):
    return DigestPreferenceFactory(user_id=user_id, timezone=ZONE, city=CITY, city_source="choice")


def make_event(
    *, hours=2, title="Gallery night", description="An art exhibition", source=None, now=NOW
):
    """A published, eligible public event whose chips are known."""
    fields = {
        "title": title,
        "description": description,
        "venue": VenueFactory(city=CITY, venue_fingerprint=f"venue-{title}|{CITY}"),
        "start_time_utc": now + timedelta(hours=hours),
        "last_seen_at": now,
    }
    if source is not None:
        fields["source"] = source
    return EventFactory(**fields)


def compose(user_id):
    return compose_digest(user_id=user_id, actor=ACTOR, now=NOW)


def event_ids(result):
    return {row.event_id for row in result.compositions}


def mute(user_id, category_key="arts_culture", duration_days=30):
    set_category_mute(
        user_id=user_id,
        category_key=category_key,
        duration_days=duration_days,
        actor=ACTOR,
        now=NOW,
    )


# ── The mute excludes ─────────────────────────────────────────────────────────────


def test_a_muted_categorys_events_are_absent_from_the_digest():
    """The user asked not to see them, so they are not there."""
    user_id = make_preference(uuid7()).user_id
    muted_event = make_event(hours=2, title="Gallery night", description="An art exhibition")
    kept_event = make_event(hours=3, title="Brooklyn Tech Meetup", description="A developer meetup")

    mute(user_id, "arts_culture")
    result = compose(user_id)

    assert muted_event.id not in event_ids(result)
    assert kept_event.id in event_ids(result)


def test_a_muted_category_does_not_merely_lose_its_rank():
    """**A mute is an exclusion, not a demotion.**

    The muted event is the *highest-scoring* one in the pool — it is the only candidate,
    so if the mute were a penalty the digest would still show it, just lower. The test
    asserts it is not there at all.
    """
    user_id = make_preference(uuid7()).user_id
    muted_event = make_event(hours=2, title="Gallery night", description="An art exhibition")

    mute(user_id, "arts_culture")
    result = compose(user_id)

    assert muted_event.id not in event_ids(result)
    assert result.is_empty is True


def test_an_event_with_no_chips_is_never_excluded():
    """**The chip keys are matched from the event's own text.** An event matching no
    keyword belongs to no category, so a muted category cannot exclude it — and excluding
    it would be the product deciding what it is on the user's behalf."""
    user_id = make_preference(uuid7()).user_id
    unclassifiable = make_event(hours=2, title="Zzz", description="Qq")

    mute(user_id, "arts_culture")
    result = compose(user_id)

    assert unclassifiable.id in event_ids(result)


def test_an_event_in_two_categories_is_excluded_when_either_is_muted():
    """The intersection is what makes this a category mute: the event *is* in a muted
    category, so it goes."""
    user_id = make_preference(uuid7()).user_id
    both = make_event(hours=2, title="Gallery night", description="An art exhibition and a concert")

    mute(user_id, "arts_culture")
    result = compose(user_id)

    assert both.id not in event_ids(result)


def test_an_expired_mute_does_not_exclude():
    """The row is still there — it is the user's data — but it no longer mutes anything.

    **The event moves with the day.** The digest's window reaches forward from its own
    local day, so an event of yesterday is not in tomorrow's digest. A test comparing two
    digests therefore compares two *days*, and the event it is looking at has to be an
    event of the day it is comparing.
    """
    user_id = make_preference(uuid7()).user_id
    later_now = NOW + timedelta(days=8)
    event = make_event(
        hours=2, title="Gallery night", description="An art exhibition", now=later_now
    )

    mute(user_id, "arts_culture", duration_days=7)
    later = compose_digest(user_id=user_id, actor=ACTOR, now=later_now)

    assert event.id in event_ids(later)


def test_another_users_mute_does_not_affect_this_users_digest():
    """The mute is the user's, and scoping is by the session's user."""
    mine = make_preference(uuid7()).user_id
    theirs = make_preference(uuid7()).user_id
    event = make_event(hours=2, title="Gallery night", description="An art exhibition")

    mute(theirs, "arts_culture")
    result = compose(mine)

    assert event.id in event_ids(result)


def test_a_muted_category_is_not_a_qualifying_event():
    """The counts answer "is there something for this user". Counting a muted category
    would keep a Ping alive for a category the user muted, and the Ping would then
    arrive with nothing in it."""
    user_id = make_preference(uuid7()).user_id
    make_event(hours=2, title="Gallery night", description="An art exhibition")

    mute(user_id, "arts_culture")
    result = compose(user_id)

    assert result.public_qualifying_count == 0


# ── Browse agrees ────────────────────────────────────────────────────────────────


def test_browse_agrees_with_the_digest():
    """**Browse and the Digest must agree.** They read the same service helper, so they
    cannot drift."""
    user_id = make_preference(uuid7()).user_id
    muted_event = make_event(hours=2, title="Gallery night", description="An art exhibition")
    kept_event = make_event(hours=3, title="Brooklyn Tech Meetup", description="A developer meetup")

    mute(user_id, "arts_culture")
    page = read_browse_page(user_id=user_id, now=NOW, limit=20, offset=0)

    ids = {card.event_id for card in page.cards}
    assert muted_event.id not in ids
    assert kept_event.id in ids


def test_the_browse_total_counts_only_the_eligible_candidates():
    """A total that counted a muted event would tell the user there is more to see than
    there is."""
    user_id = make_preference(uuid7()).user_id
    make_event(hours=2, title="Gallery night", description="An art exhibition")

    mute(user_id, "arts_culture")
    page = read_browse_page(user_id=user_id, now=NOW, limit=20, offset=0)

    assert page.total == 0
