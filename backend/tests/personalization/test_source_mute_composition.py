"""The source mute at the composition seam: what a mute excludes and what show-less
deprioritises (FR-13, FR-22).

**The two promises are different, and the difference is the whole point.**

- **`mute` excludes.** The source's events are *absent* from the digest — not scored and
  discarded, but never candidates. A user who muted a source must not see its events.
- **`show_less` deprioritises.** The source's events are *present* and score lower. "Show
  less" that hid the events would be indistinguishable from a mute on the wire, and would
  be a lie to the user who asked for fewer rather than none.

**Why the penalty is outside FR-22's formula.** The Relevance Pulse is exactly five
weighted terms summing to 1.00, and CI pins those five weights against ADR-0025. A
penalty cannot be a sixth term — that would change the published formula and the pin with
it. So the penalty is a **post-score adjustment**, applied to the computed score *before*
ordering: the formula and its pin stay byte-identical, and the user's preference is
honoured on top of it.

**Why the filter runs before the scorers.** A mute is a statement about the candidate
*set*, not about an event's rank. A muted source's events should not be scored and then
thrown away — that is work spent on an event the user will never see.

**Browse agrees with Digest.** The same filter and the same penalty run in
`read_browse_page`, so the two surfaces cannot disagree about what a mute means.
"""

from datetime import UTC, datetime, timedelta

import pytest

from apps.personalization.services.digest_composition import compose_digest
from apps.personalization.services.source_mutes import (
    STATE_MUTE,
    STATE_SHOW_LESS,
    set_source_mute,
)
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory, SourceFactory, VenueFactory
from tests.personalization.factories import DigestPreferenceFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

ACTOR = Actor.system("digest_composition")

NOW = datetime(2026, 11, 4, 16, 0, tzinfo=UTC)
CITY = "Los Angeles"
ZONE = "America/Los_Angeles"


def make_preference(user_id):
    return DigestPreferenceFactory(user_id=user_id, timezone=ZONE, city=CITY, city_source="choice")


def make_event(*, hours=2, title="Brooklyn Tech Meetup", source=None, **overrides):
    """A published, eligible public event from `source`."""
    fields = {
        "title": title,
        "venue": VenueFactory(city=CITY, venue_fingerprint=f"venue-{title}|{CITY}"),
        "start_time_utc": NOW + timedelta(hours=hours),
        "last_seen_at": NOW,
    }
    if source is not None:
        fields["source"] = source
    fields.update(overrides)
    return EventFactory(**fields)


def compose(user_id):
    return compose_digest(user_id=user_id, actor=ACTOR, now=NOW)


def recompose(user_id, *, now=NOW + timedelta(days=1)):
    """Compose again, on a **different local day**.

    **A digest is keyed on `(user, local_date)` and a re-run returns the existing one**
    without recomposing — that is the idempotence the composition guarantees. The
    composition rows are append-only, so the old digest cannot be cleared to force a
    recomposition. Advancing the day is the honest way to ask the question again: it is
    a *different* digest, composed by the same command, and the only thing that changed
    between them is the user's preference.

    **The event has to move with it.** The digest's window reaches forward from its own
    day, so an event that was in yesterday's digest is not in tomorrow's. A test that
    wants to compare two digests therefore compares two *days*, and the event it is
    looking at has to be an event of the day it is comparing.
    """
    return compose_digest(user_id=user_id, actor=ACTOR, now=now)


def event_ids(result):
    return {row.event_id for row in result.compositions}


def mute(user_id, source_id, state):
    set_source_mute(
        user_id=user_id,
        source_id=source_id,
        state=state,
        actor=ACTOR,
        now=NOW,
    )


# ── The mute excludes ─────────────────────────────────────────────────────────────


def test_a_muted_sources_events_are_absent_from_the_digest():
    """The user asked not to see them, so they are not there."""
    user_id = make_preference(_user_id()).user_id
    muted = SourceFactory()
    kept = SourceFactory()
    muted_event = make_event(hours=2, title="Muted Gig", source=muted)
    kept_event = make_event(hours=3, title="Kept Gig", source=kept)

    mute(user_id, muted.id, STATE_MUTE)
    result = compose(user_id)

    assert muted_event.id not in event_ids(result)
    assert kept_event.id in event_ids(result)


def test_a_muted_source_does_not_merely_lose_its_rank():
    """**A mute is an exclusion, not a demotion.**

    The muted event is the *highest-scoring* one in the pool — it is the only candidate,
    so if the mute were a penalty the digest would still show it, just lower. The test
    asserts it is not there at all.
    """
    user_id = make_preference(_user_id()).user_id
    muted = SourceFactory()
    muted_event = make_event(hours=2, title="Only Gig", source=muted)

    mute(user_id, muted.id, STATE_MUTE)
    result = compose(user_id)

    assert muted_event.id not in event_ids(result)
    assert result.is_empty is True


def test_muting_one_source_leaves_the_others_alone():
    user_id = make_preference(_user_id()).user_id
    muted = SourceFactory()
    other = SourceFactory()
    muted_event = make_event(hours=2, title="Muted Gig", source=muted)
    other_event = make_event(hours=3, title="Other Gig", source=other)

    mute(user_id, muted.id, STATE_MUTE)
    result = compose(user_id)

    assert event_ids(result) == {other_event.id}
    assert muted_event.id not in event_ids(result)


def test_another_users_mute_does_not_affect_this_users_digest():
    """The mute is the user's, and scoping is by the session's user."""
    mine = make_preference(_user_id()).user_id
    theirs = make_preference(_user_id()).user_id
    source = SourceFactory()
    event = make_event(hours=2, title="Gig", source=source)

    mute(theirs, source.id, STATE_MUTE)
    result = compose(mine)

    assert event.id in event_ids(result)


# ── The show-less deprioritises ───────────────────────────────────────────────────


def test_a_show_less_sources_events_are_still_in_the_digest():
    """**"Show less" means fewer, not none.** The event is present."""
    user_id = make_preference(_user_id()).user_id
    source = SourceFactory()
    event = make_event(hours=2, title="Gig", source=source)

    mute(user_id, source.id, STATE_SHOW_LESS)
    result = compose(user_id)

    assert event.id in event_ids(result)


def test_a_show_less_source_scores_lower_than_it_would():
    """The penalty is real, and it is applied to the score.

    The two compositions are otherwise identical — same user, same kind of event, same
    catalog — so the only difference is the preference. (They are on different days
    because a digest is keyed on its local day and cannot be recomposed; the event moves
    with the day, so the comparison is like for like.)
    """
    user_id = make_preference(_user_id()).user_id
    source = SourceFactory()
    event = make_event(hours=2, title="Gig", source=source)

    plain = compose(user_id)
    plain_score = next(row.score for row in plain.compositions if row.event_id == event.id)

    mute(user_id, source.id, STATE_SHOW_LESS)
    later = make_event(
        hours=2,
        title="Gig Tomorrow",
        source=source,
        start_time_utc=NOW + timedelta(days=1, hours=2),
    )
    penalised = recompose(user_id)
    penalised_score = next(row.score for row in penalised.compositions if row.event_id == later.id)

    assert penalised_score < plain_score


def test_a_show_less_source_is_ordered_below_an_equally_scored_other():
    """The penalty moves the event *down the order*, which is the promise."""
    user_id = make_preference(_user_id()).user_id
    shown_less = SourceFactory()
    normal = SourceFactory()
    less_event = make_event(hours=2, title="Less Gig", source=shown_less)
    normal_event = make_event(hours=3, title="Normal Gig", source=normal)

    mute(user_id, shown_less.id, STATE_SHOW_LESS)
    result = compose(user_id)

    order = [row.event_id for row in result.compositions]
    assert order.index(normal_event.id) < order.index(less_event.id)


def test_show_lessing_does_not_exclude_the_events():
    """A show-less is not a mute in disguise. The event is in the pool and outranks
    nothing — but it is there."""
    user_id = make_preference(_user_id()).user_id
    source = SourceFactory()
    event = make_event(hours=2, title="Only Gig", source=source)

    mute(user_id, source.id, STATE_SHOW_LESS)
    result = compose(user_id)

    assert event.id in event_ids(result)
    assert result.is_empty is False


def test_show_lessing_does_not_lower_the_confidence_pulse():
    """**The preference moves the ordering; it does not move the pulse.**

    The Confidence Pulse is the score's own 1-5 reading, and it is persisted on the
    composition row (AD-10). A user's preference for one source is not a statement about
    the confidence of an event from it — so "show less" must leave the bucket exactly as
    the formula produced it.

    The two compositions are otherwise identical — same user, same kind of event, same
    catalog — and the only difference is the preference. (They are on different days
    because a digest is keyed on its local day and cannot be recomposed; the event moves
    with the day, so the comparison is like for like.)
    """
    user_id = make_preference(_user_id()).user_id
    source = SourceFactory()
    event = make_event(hours=2, title="Gig", source=source)

    plain = compose(user_id)
    plain_bucket = next(row.bucket for row in plain.compositions if row.event_id == event.id)

    mute(user_id, source.id, STATE_SHOW_LESS)
    later = make_event(
        hours=2,
        title="Gig Tomorrow",
        source=source,
        start_time_utc=NOW + timedelta(days=1, hours=2),
    )
    penalised = recompose(user_id)
    penalised_bucket = next(
        row.bucket for row in penalised.compositions if row.event_id == later.id
    )

    assert penalised_bucket == plain_bucket


def test_show_lessing_lowers_the_score_without_lowering_the_pulse():
    """**The two numbers move independently, and only one of them moves.**

    The score is what the ordering reads, and "show less" lowers it. The bucket is what
    the card shows, and "show less" leaves it alone. If the penalty were folded into the
    bucket, the score and the pulse would drift apart — the card would claim a confidence
    the formula never produced.
    """
    user_id = make_preference(_user_id()).user_id
    source = SourceFactory()
    event = make_event(hours=2, title="Gig", source=source)

    plain = compose(user_id)
    plain_row = next(row for row in plain.compositions if row.event_id == event.id)

    mute(user_id, source.id, STATE_SHOW_LESS)
    later = make_event(
        hours=2,
        title="Gig Tomorrow",
        source=source,
        start_time_utc=NOW + timedelta(days=1, hours=2),
    )
    penalised = recompose(user_id)
    penalised_row = next(row for row in penalised.compositions if row.event_id == later.id)

    assert penalised_row.score < plain_row.score
    assert penalised_row.bucket == plain_row.bucket


# ── The two states are not the same promise ───────────────────────────────────────


def test_a_mute_and_a_show_less_give_different_digests():
    """The difference the whole design rests on, stated as one test."""
    user_id = make_preference(_user_id()).user_id
    source = SourceFactory()
    event = make_event(hours=2, title="Gig", source=source)

    mute(user_id, source.id, STATE_MUTE)
    muted_result = compose(user_id)

    mute(user_id, source.id, STATE_SHOW_LESS)
    later = make_event(
        hours=2,
        title="Gig Tomorrow",
        source=source,
        start_time_utc=NOW + timedelta(days=1, hours=2),
    )
    shown_less_result = recompose(user_id)

    assert event.id not in event_ids(muted_result)
    assert later.id in event_ids(shown_less_result)


def test_setting_default_restores_the_source_to_the_digest():
    user_id = make_preference(_user_id()).user_id
    source = SourceFactory()
    event = make_event(hours=2, title="Gig", source=source)

    mute(user_id, source.id, STATE_MUTE)
    assert event.id not in event_ids(compose(user_id))

    mute(user_id, source.id, "default")
    later = make_event(
        hours=2,
        title="Gig Tomorrow",
        source=source,
        start_time_utc=NOW + timedelta(days=1, hours=2),
    )
    assert later.id in event_ids(recompose(user_id))


# ── Browse agrees with Digest ─────────────────────────────────────────────────────


def test_browse_excludes_a_muted_sources_events():
    """The two surfaces must not disagree about what a mute means."""
    from apps.personalization.services.browse_read import read_browse_page

    user_id = make_preference(_user_id()).user_id
    muted = SourceFactory()
    kept = SourceFactory()
    muted_event = make_event(hours=2, title="Muted Gig", source=muted)
    kept_event = make_event(hours=3, title="Kept Gig", source=kept)

    mute(user_id, muted.id, STATE_MUTE)
    page = read_browse_page(user_id=user_id, now=NOW, limit=20, offset=0)

    listed = {card.event_id for card in page.cards}
    assert muted_event.id not in listed
    assert kept_event.id in listed


def test_browse_keeps_a_show_less_sources_events():
    from apps.personalization.services.browse_read import read_browse_page

    user_id = make_preference(_user_id()).user_id
    source = SourceFactory()
    event = make_event(hours=2, title="Gig", source=source)

    mute(user_id, source.id, STATE_SHOW_LESS)
    page = read_browse_page(user_id=user_id, now=NOW, limit=20, offset=0)

    assert event.id in {card.event_id for card in page.cards}


def test_browse_deprioritises_a_show_less_source():
    """**Browse applies the penalty too, not only the exclusion.**

    A "show less" that excluded in Browse and merely demoted in the Digest would make
    the two surfaces disagree about the same preference — and the user would see fewer of
    that source's events on one screen and the same number on the other.
    """
    from apps.personalization.services.browse_read import read_browse_page

    user_id = make_preference(_user_id()).user_id
    shown_less = SourceFactory()
    normal = SourceFactory()
    less_event = make_event(hours=2, title="Less Gig", source=shown_less)
    normal_event = make_event(hours=3, title="Normal Gig", source=normal)

    mute(user_id, shown_less.id, STATE_SHOW_LESS)
    page = read_browse_page(user_id=user_id, now=NOW, limit=20, offset=0)

    order = [card.event_id for card in page.cards]
    assert order.index(normal_event.id) < order.index(less_event.id)


def _user_id():
    from shared.ids import uuid7

    return uuid7()
