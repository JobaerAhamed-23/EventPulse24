"""Event Fit: the writer, the recompute hooks, the backfill and the read (AD-10, FR-26).

The **domain** rules — the score bands, the tag boundaries, the local-day computation
across a DST transition and across the date line — are in `tests/domain/test_event_fit.py`.
This file is about the catalog side: that the fit is written when the event is, that it is
recomputed when the event changes, that a stale row is never served, that the backfill is
idempotent, and that the preview's top N comes back in the right order.

Every clock is an explicit `now`, like everywhere else in this codebase.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.db.models import F

from apps.ingestion.event_fit.reads import (
    DEFAULT_PREVIEW_SIZE,
    list_event_fit_for_city,
)
from apps.ingestion.event_fit.writes import (
    backfill_event_fits,
    compute_fit_for_event,
    refresh_stale_event_fits,
    write_event_fit,
)
from apps.ingestion.models import Event, EventFit, IngestionAuditEntry
from shared.actor import Actor
from shared.db import CATALOG
from tests.ingestion.factories import EventFactory, VenueFactory

pytestmark = pytest.mark.django_db(databases=[CATALOG])

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
ACTOR = Actor.system("event_fit_test")
# The factories put events in Los Angeles. "Los Angeles" is the venue's city, so that is
# the city the fit rows are keyed by.
CITY = "Los Angeles"


def _event(**overrides) -> Event:
    return EventFactory(**overrides)


def _fits() -> list[EventFit]:
    return list(EventFit.objects.using(CATALOG).order_by("pk"))


def _fit_for(event: Event) -> EventFit | None:
    return EventFit.objects.using(CATALOG).filter(event_id=event.pk, city=event.venue.city).first()


# ── The write ───────────────────────────────────────────────────────────────────────


def test_writing_a_fit_persists_the_score_and_the_tags():
    # 16 hours after 12:00 UTC is 04:00 the next day in Los Angeles (UTC-8 in November) —
    # the evening boundary is 17:00 local, so this is "tonight" and not merely "today".
    event = _event(start_time_utc=NOW + timedelta(hours=16))

    row = write_event_fit(event=event, now=NOW, actor=ACTOR)

    assert row is not None
    assert row.score == 5
    assert row.tags == ["tonight", "in_los_angeles"]
    assert row.city == CITY
    assert row.event_version == event.event_version
    assert row.computed_at == NOW


def test_the_write_leaves_an_audit_row():
    event = _event(start_time_utc=NOW + timedelta(hours=6))

    write_event_fit(event=event, now=NOW, actor=ACTOR)

    audit = IngestionAuditEntry.objects.using(CATALOG).filter(action="event_fit.recomputed")
    assert audit.count() == 1
    assert audit.first().actor_label == "event_fit_test"


def test_an_event_with_no_venue_city_gets_no_fit_row():
    """The city is not guessed. An event in an unknown city is in no city's preview."""
    event = _event(venue=None, venue_fingerprint="venue-x|unknown")

    assert write_event_fit(event=event, now=NOW, actor=ACTOR) is None
    assert _fits() == []


def test_the_fit_is_written_where_the_venue_city_says():
    event = _event(venue=VenueFactory(city="Brooklyn"))

    row = write_event_fit(event=event, now=NOW, actor=ACTOR)

    assert row.city == "Brooklyn"
    assert "in_brooklyn" in row.tags


def test_writing_the_fit_twice_replaces_the_row():
    """The write is an upsert, which is what makes the backfill idempotent."""
    event = _event(start_time_utc=NOW + timedelta(hours=6))

    first = write_event_fit(event=event, now=NOW, actor=ACTOR)
    second = write_event_fit(event=event, now=NOW + timedelta(hours=1), actor=ACTOR)

    assert first.pk == second.pk, "the same row, not a second one"
    assert len(_fits()) == 1


def test_compute_fit_for_event_writes_nothing():
    """The seam between the domain function and the row is a pure read."""
    event = _event(start_time_utc=NOW + timedelta(hours=6))

    computed = compute_fit_for_event(event, now=NOW)

    assert computed is not None
    assert computed[0] == 5
    assert _fits() == []


def test_compute_fit_for_event_returns_nothing_for_a_city_less_event():
    """There is no fit to compute without a city, and that is not an error."""
    event = _event(venue=None, venue_fingerprint="venue-x|unknown")

    assert compute_fit_for_event(event, now=NOW) is None


# ── The ingest hooks: recompute when the event is created or changes ────────────────


def _ingest_source_with_a_venue():
    """A source whose events land on a known venue, so the fit has a city.

    The ICS parser takes the venue's name from `LOCATION` and the city from the source,
    and the pipeline binds the event to the registry venue whose fingerprint matches. A
    venue that is not in the registry means no bound venue, and an event with no venue
    city gets no fit row at all — so the registry entry is what makes this test about the
    *hook* rather than about the missing venue.
    """
    from apps.ingestion.services.venue_registry import register_venue
    from tests.ingestion.pipeline_support import ics_source

    source = ics_source()
    source.city = "Brooklyn"
    source.save(using=CATALOG)
    register_venue(
        actor=ACTOR,
        name="The Troubadour",
        city="Brooklyn",
        country_code="US",
        tz="America/New_York",
    )
    return source


def _run_ingest(source, *events: str):
    from apps.ingestion.services.ingest_source import ingest_source
    from tests.ingestion.pipeline_support import ScriptedFetchPort, calendar

    return ingest_source(source.id, fetch_port=ScriptedFetchPort().serve(calendar(*events)))


def test_a_new_event_gets_a_fit_from_the_ingest_path():
    """A new event has a fit from the moment it exists.

    This is the ingest path's own hook, not the writer called by hand: the fit is part of
    the event's creation, inside the same transaction.
    """
    from tests.ingestion.pipeline_support import vevent

    source = _ingest_source_with_a_venue()
    _run_ingest(
        source,
        vevent("new@club.example.test", "20261106T200000", location="The Troubadour"),
    )

    fits = _fits()
    assert len(fits) == 1
    assert fits[0].city == "Brooklyn"
    assert fits[0].event_version == 1


def test_a_changed_event_gets_a_recomputed_fit():
    """A lifecycle change moves the event, so its fit is recomputed against the new facts.

    The version is the point: the fit records the version it was computed from, and a
    fit stamped with the old version would be skipped by the read as stale — the event
    would vanish from the preview rather than show a wrong tag.
    """
    from tests.ingestion.pipeline_support import vevent

    source = _ingest_source_with_a_venue()
    uid = "moving@club.example.test"
    _run_ingest(source, vevent(uid, "20261106T200000", location="The Troubadour"))
    _run_ingest(source, vevent(uid, "20261112T200000", location="The Troubadour"))

    event = Event.objects.using(CATALOG).get(source=source)
    fit = _fit_for(event)
    assert event.event_version == 2
    assert fit is not None
    assert fit.event_version == 2, "the fit records the version it was computed from"


def test_the_recomputed_fit_is_not_stale():
    """The regression this pins: a fit stamped with the *old* version is never served.

    The write bumps `event_version` in the database with `F()`, so the in-memory event
    still holds the old number. A fit computed from that stale instance would record the
    old version and the read would skip it — the event would silently disappear from the
    preview.
    """
    from tests.ingestion.pipeline_support import vevent

    source = _ingest_source_with_a_venue()
    uid = "stale@club.example.test"
    _run_ingest(source, vevent(uid, "20261106T200000", location="The Troubadour"))
    _run_ingest(source, vevent(uid, "20261112T200000", location="The Troubadour"))

    event = Event.objects.using(CATALOG).get(source=source)
    fit = _fit_for(event)
    assert fit.event_version == event.event_version
    assert list_event_fit_for_city(city="Brooklyn", now=NOW), "the event is in the preview"


# ── The read ────────────────────────────────────────────────────────────────────────


def _fit_row(event: Event, *, score: int, tags: list[str], version: int | None = None):
    return EventFit.objects.using(CATALOG).create(
        event=event,
        city=event.venue.city,
        score=score,
        tags=tags,
        event_version=version if version is not None else event.event_version,
        computed_at=NOW,
    )


def test_the_read_returns_the_best_fit_first():
    """The fit is the reason an event is in the preview, so the score leads.

    The better-fit event is deliberately the **later** one: a soon event that also
    happens to be the best fit would not tell the two orderings apart. A test that
    cannot distinguish "best fit first" from "soonest first" is a test that passes
    whichever way the query is written.
    """
    sooner = _event(start_time_utc=NOW + timedelta(hours=2))
    better_fit_but_later = _event(start_time_utc=NOW + timedelta(days=5))
    _fit_row(sooner, score=3, tags=["tonight"])
    _fit_row(better_fit_but_later, score=5, tags=["this_weekend"])

    entries = list_event_fit_for_city(city=CITY, now=NOW)

    assert [entry.id for entry in entries] == [better_fit_but_later.pk, sooner.pk]


def test_the_read_breaks_a_score_tie_on_the_start_time():
    """Two events with the same fit: the sooner one is the more useful one."""
    later = _event(start_time_utc=NOW + timedelta(days=5))
    sooner = _event(start_time_utc=NOW + timedelta(hours=2))
    _fit_row(later, score=3, tags=[])
    _fit_row(sooner, score=3, tags=[])

    entries = list_event_fit_for_city(city=CITY, now=NOW)

    assert [entry.id for entry in entries] == [sooner.pk, later.pk]


def test_the_read_returns_three_by_default():
    events = [_event(start_time_utc=NOW + timedelta(hours=n)) for n in range(1, 6)]
    for event in events:
        _fit_row(event, score=5, tags=[])

    entries = list_event_fit_for_city(city=CITY, now=NOW)

    assert len(entries) == DEFAULT_PREVIEW_SIZE == 3


def test_the_read_honours_an_explicit_limit():
    events = [_event(start_time_utc=NOW + timedelta(hours=n)) for n in range(1, 6)]
    for event in events:
        _fit_row(event, score=5, tags=[])

    entries = list_event_fit_for_city(city=CITY, now=NOW, limit=5)

    assert len(entries) == 5


def test_a_stale_fit_is_never_served():
    """The Event moved on since the fit was computed, so the fit describes an event that
    no longer exists. It is skipped, not served."""
    event = _event(start_time_utc=NOW + timedelta(hours=2))
    _fit_row(event, score=5, tags=["tonight"], version=1)
    Event.objects.using(CATALOG).filter(pk=event.pk).update(event_version=F("event_version") + 1)

    assert list_event_fit_for_city(city=CITY, now=NOW) == []


def test_the_read_skips_an_event_that_has_already_started():
    event = _event(start_time_utc=NOW - timedelta(hours=1))
    _fit_row(event, score=5, tags=[])

    assert list_event_fit_for_city(city=CITY, now=NOW) == []


def test_the_read_skips_an_unpublished_event():
    event = _event(start_time_utc=NOW + timedelta(hours=2))
    _fit_row(event, score=5, tags=[])
    Event.objects.using(CATALOG).filter(pk=event.pk).update(
        publication_status=Event.PublicationStatus.IN_REVIEW
    )

    assert list_event_fit_for_city(city=CITY, now=NOW) == []


def test_the_read_is_case_insensitive_on_the_city():
    event = _event(start_time_utc=NOW + timedelta(hours=2))
    _fit_row(event, score=5, tags=[])

    assert len(list_event_fit_for_city(city="los angeles", now=NOW)) == 1
    assert len(list_event_fit_for_city(city="  LOS ANGELES ", now=NOW)) == 1


def test_the_read_returns_the_persisted_tags_untouched():
    """The read serves the row as it stands. It does not re-derive the tags."""
    event = _event(start_time_utc=NOW + timedelta(hours=2))
    _fit_row(event, score=4, tags=["tomorrow", "in_brooklyn"])

    entry = list_event_fit_for_city(city=CITY, now=NOW)[0]

    assert entry.tags == ("tomorrow", "in_brooklyn")
    assert entry.score == 4


def test_the_read_does_not_compute_anything():
    """The score on the row is the score that is served, even when it disagrees with what
    a fresh computation would say.

    This is the AD-10 rule made testable: the read is not a calculator.
    """
    event = _event(start_time_utc=NOW + timedelta(hours=2))
    _fit_row(event, score=1, tags=[])

    entry = list_event_fit_for_city(city=CITY, now=NOW)[0]

    assert entry.score == 1, "the persisted score, not a recomputed one"


# ── The city the fit belongs to ─────────────────────────────────────────────────────


def test_a_fit_is_retired_when_the_venue_moves_city():
    """An event belongs to exactly one city, and the fit follows it there.

    The key is `(event, city)`, so a venue whose city changes would otherwise leave
    the old city's row behind — and the event would appear in **two** previews, one of
    them carrying the place tag of a city it has left.

    Nothing else catches this. A venue edit does not bump the event's `event_version`,
    so the old row's version still matches and the read's staleness guard passes it
    straight through.
    """
    event = _event(venue=VenueFactory(city="Brooklyn"))
    write_event_fit(event=event, now=NOW, actor=ACTOR)

    event.venue.city = "Manhattan"
    event.venue.save(using=CATALOG)
    event.refresh_from_db(using=CATALOG)
    write_event_fit(event=event, now=NOW, actor=ACTOR)

    assert [row.city for row in _fits()] == ["Manhattan"]
    assert list_event_fit_for_city(city="Brooklyn", now=NOW) == [], "not in the old city"
    assert list_event_fit_for_city(city="Manhattan", now=NOW), "in the new one"


def test_a_fit_is_not_duplicated_by_a_city_spelled_differently():
    """The read is case-insensitive, so the write has to be too.

    "Brooklyn" and "brooklyn" are the same city. Two rows for one event in one city
    would put the event in that city's preview twice.
    """
    event = _event(venue=VenueFactory(city="Brooklyn"))
    write_event_fit(event=event, now=NOW, actor=ACTOR)

    event.venue.city = "brooklyn"
    event.venue.save(using=CATALOG)
    event.refresh_from_db(using=CATALOG)
    write_event_fit(event=event, now=NOW, actor=ACTOR)

    assert len(_fits()) == 1
    assert len(list_event_fit_for_city(city="Brooklyn", now=NOW)) == 1


# ── The backfill ────────────────────────────────────────────────────────────────────


def test_the_backfill_writes_a_row_for_every_published_event():
    for n in range(1, 4):
        _event(start_time_utc=NOW + timedelta(hours=n))

    written, seen = backfill_event_fits(now=NOW, actor=ACTOR)

    assert (written, seen) == (3, 3)
    assert len(_fits()) == 3


def test_the_backfill_is_idempotent():
    """Running it twice writes the same rows, not twice as many."""
    _event(start_time_utc=NOW + timedelta(hours=2))
    _event(start_time_utc=NOW + timedelta(hours=3))

    first_written, _ = backfill_event_fits(now=NOW, actor=ACTOR)
    second_written, _ = backfill_event_fits(now=NOW + timedelta(hours=1), actor=ACTOR)

    assert first_written == second_written == 2
    assert len(_fits()) == 2


def test_the_backfill_does_not_move_the_computed_at_of_a_row_that_did_not_change():
    """The strong sense of idempotence: nothing about the row changes.

    "The row count does not grow" is a weak property — it holds whether the row was
    rewritten or not. The plan asks for the stronger one: "a row that already matches
    is not rewritten (the `computed_at` does not move, so a test can assert that)".

    It matters for two reasons. `computed_at` says when the fit was last *computed*,
    and a row that was not recomputed must not claim otherwise. And the refresh runs
    every fifteen minutes over the whole published catalog — a writer that rewrote
    every row every time would write the entire catalog four times an hour to say
    nothing had changed.
    """
    _event(start_time_utc=NOW + timedelta(hours=2))

    backfill_event_fits(now=NOW, actor=ACTOR)
    first_computed_at = _fits()[0].computed_at

    backfill_event_fits(now=NOW + timedelta(hours=1), actor=ACTOR)

    assert _fits()[0].computed_at == first_computed_at, "the row was not rewritten"


def test_a_fit_whose_tags_changed_is_rewritten():
    """The other half: a row that no longer matches **is** rewritten.

    Skipping the write unconditionally would be the opposite bug — "tonight" would
    never become "tomorrow" as time passes, and the refresh would do nothing at all.

    The event is at 21:00 on Saturday in Los Angeles. At `NOW` — 04:00 on Friday — it
    is "tomorrow"; a day later, at 04:00 on Saturday, the same event is "tonight".
    The tags and the score both move, so the row must be rewritten.
    """
    saturday_evening = datetime(2026, 11, 7, 21, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    event = _event(start_time_utc=saturday_evening.astimezone(UTC))
    write_event_fit(event=event, now=NOW, actor=ACTOR)
    first = _fits()[0]
    first_computed_at = first.computed_at
    first_tags = list(first.tags)
    assert "tomorrow" in first_tags, first_tags

    write_event_fit(event=event, now=NOW + timedelta(days=1), actor=ACTOR)

    assert list(_fits()[0].tags) != first_tags, "the tags moved"
    assert "tonight" in _fits()[0].tags, list(_fits()[0].tags)
    assert "tomorrow" not in _fits()[0].tags, list(_fits()[0].tags)
    assert _fits()[0].computed_at > first_computed_at, "the row was rewritten"


def test_the_backfill_skips_an_unpublished_event():
    event = _event(start_time_utc=NOW + timedelta(hours=2))
    Event.objects.using(CATALOG).filter(pk=event.pk).update(
        publication_status=Event.PublicationStatus.IN_REVIEW
    )

    written, seen = backfill_event_fits(now=NOW, actor=ACTOR)

    assert (written, seen) == (0, 0)


def test_the_backfill_batches():
    """The batching is the bound on the refresh cost (the work item's note)."""
    for n in range(5):
        _event(start_time_utc=NOW + timedelta(hours=n))

    written, seen = backfill_event_fits(now=NOW, actor=ACTOR, batch_size=2)

    assert (written, seen) == (5, 5)
    assert len(_fits()) == 5


# ── The staleness refresh ───────────────────────────────────────────────────────────


def test_the_refresh_recomputes_the_fits():
    """The refresh is what keeps "tonight" from going stale: the tick's answer to time
    passing."""
    event = _event(start_time_utc=NOW + timedelta(hours=2))
    _fit_row(event, score=1, tags=[])

    written = refresh_stale_event_fits(now=NOW, actor=ACTOR)

    assert written == 1
    assert _fit_for(event).score == 5


def test_the_refresh_batches():
    for n in range(5):
        _event(start_time_utc=NOW + timedelta(hours=n))

    written = refresh_stale_event_fits(now=NOW, actor=ACTOR, batch_size=2)

    assert written == 5
    assert len(_fits()) == 5


def test_the_refresh_skips_an_event_with_no_venue_city():
    _event(venue=None, venue_fingerprint="venue-x|unknown")

    assert refresh_stale_event_fits(now=NOW, actor=ACTOR) == 0


def test_the_refresh_leaves_an_unpublished_event_alone():
    """A fit nobody will ever read is not worth recomputing."""
    event = _event(start_time_utc=NOW + timedelta(hours=2))
    Event.objects.using(CATALOG).filter(pk=event.pk).update(
        publication_status=Event.PublicationStatus.IN_REVIEW
    )

    assert refresh_stale_event_fits(now=NOW, actor=ACTOR) == 0


# ── The score the fit carries is the domain function's ──────────────────────────────


def test_the_written_score_is_the_domains():
    """The writer does not have a score of its own; it calls the pure function."""
    event = _event(start_time_utc=NOW + timedelta(days=3), extraction_confidence=Decimal("0.60"))

    row = write_event_fit(event=event, now=NOW, actor=ACTOR)

    # Three days out is the "within a week" band (3); 0.60 confidence is the "fair"
    # band (3). The lower of the two is 3.
    assert row.score == 3
