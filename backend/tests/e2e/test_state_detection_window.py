"""FR-53's detection window, end to end: a cancellation introduced upstream is *detected*
inside the stated window.

**What this proves, and why it is not a unit test of a constant.** FR-53 says "The system
re-ingests high-priority sources at least every 4 hours", and its consequence is the thing
that matters: "A cancelled event is detected by the system within 4 hours for high-priority
sources". A test that asserts `HIGH_PRIORITY_CADENCE_MAX == timedelta(hours=4)` proves
nothing about detection — it would still pass if the scheduler ignored the cadence
entirely, or if the ingest that followed found nothing.

So this scenario drives the **real polling loop**, through `claim_due_sources` and
`ingest_source` — not a restatement of the rule.

**The two halves, and why they are two tests.**

FR-53's window is a promise about two things that are wired together but can fail
independently:

1. **The scheduler polls the source inside its window.** This is the tier, the cadence and
   `claim_due_sources`. It is tested on a **high-priority** source (`api`), whose ceiling is
   4 hours.
2. **The poll finds the cancellation.** This is the pipeline — the fetch, the parse, the
   `EventStateChange`. It is tested on a source whose method has a **parser** (`ics`).

**The seam between them is real, and this file says so.** No high-priority method has a
parser yet — `api` and `partnership` have no adapter in this codebase (`PARSERS` holds
`jsonld`, `rss`, `ics` and `email_ics`). So a high-priority source cannot be ingested
today, and a single test that drove both halves at once would have to fake the parser to do
it. **Faking the parser would make the test prove a fiction.** So the halves are proved
separately, each against the real code that implements it, and the composition is proved
where it *can* be: on the `ics` source, at the lower tier's 24-hour window.

**The boundary is asserted from both sides.** At `cadence - 1 second` the source is **not**
yet due; at `cadence` it **is**. A test that only checks the happy path cannot tell a
scheduler that polls too often from one that polls exactly right — and polling too often is
a cost, not a safety, so it is a real failure too.

**The clock is explicit everywhere.** `ingest_source` stamps `last_attempted_at` with the
real clock, so the scenario reads that stamp back and does its arithmetic from it, rather
than pretending the two clocks agree.
"""

from datetime import datetime, timedelta

import pytest

from apps.ingestion.models import Event, EventStateChange, Source
from apps.ingestion.services.ingest_source import ingest_source
from apps.ingestion.services.scheduling import claim_due_sources, release_claim
from ports.fetch import FetchError
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import SourceFactory
from tests.ingestion.pipeline_support import ScriptedFetchPort, calendar, vevent

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

UID = "jazz@club.example.test"
# 2026-11-05 19:30 in New York (EST) = 2026-11-06 00:30 UTC.
START = "20261105T193000"

#: A high-priority source's ceiling (FR-53), and the window the product promises.
WINDOW = timedelta(hours=4)
SECOND = timedelta(seconds=1)


def _high_priority_source() -> Source:
    """A source at its tier's ceiling — the worst case the guarantee still covers.

    **`api` is a high-priority method** (the PRD's "official sites"), so its ceiling is
    4 hours. A source at the ceiling is the *boundary* case: any longer and FR-53 could not
    promise detection inside 4 hours.
    """
    return SourceFactory(
        acquisition_method="api",
        ingestion_cadence=WINDOW,
        url="https://api.example.test/events.ics",
    )


def _ics_source() -> Source:
    """A source whose method has a parser, so a poll can actually find a change.

    **Its cadence is the tier's ceiling** — the worst case the guarantee still covers. A
    source may poll more often, and then the window closes earlier; at the ceiling the
    window is exactly as long as the promise.
    """
    return SourceFactory(
        acquisition_method="ics",
        ingestion_cadence=timedelta(hours=24),
        url="https://feeds.example.test/cal.ics",
    )


def _run(source, *events: str):
    return ingest_source(source.id, fetch_port=ScriptedFetchPort().serve(calendar(*events)))


def _event(source) -> Event:
    return Event.objects.using(CATALOG).get(source=source, source_event_id=UID)


def _changes(event) -> list[EventStateChange]:
    return list(
        EventStateChange.objects.using(CATALOG).filter(event=event).order_by("event_version")
    )


def _attempted_at(source) -> datetime:
    source.refresh_from_db(using=CATALOG)
    assert source.last_attempted_at is not None
    return source.last_attempted_at


# --- Half one: the scheduler polls inside the window -------------------------------------------


def test_a_high_priority_source_is_polled_inside_its_four_hour_window():
    """The tier's ceiling, and the real scheduler.

    The source is claimed at `last_attempted_at + 4h` — the promise FR-53 makes about the
    official sources.
    """
    source = _high_priority_source()
    _run_anything(source)  # one attempt, so there is an attempt stamp to measure from
    attempted_at = _attempted_at(source)

    assert claim_due_sources(now=attempted_at + WINDOW - SECOND) == []
    assert claim_due_sources(now=attempted_at + WINDOW) == [source.pk]


def _run_anything(source):
    """Give the source an attempt stamp. The `api` method has no parser, so the run is
    recorded as a parse failure — but the *attempt* is what the scheduler measures from,
    and it is recorded either way.
    """
    return ingest_source(source.id, fetch_port=ScriptedFetchPort().serve(calendar()))


def test_a_high_priority_source_at_a_shorter_cadence_is_polled_sooner():
    """A source may poll more often than its tier requires — and the scheduler honours it."""
    source = SourceFactory(
        acquisition_method="api",
        ingestion_cadence=timedelta(hours=1),
        url="https://api.example.test/events.ics",
    )
    _run_anything(source)
    attempted_at = _attempted_at(source)

    assert claim_due_sources(now=attempted_at + timedelta(hours=1)) == [source.pk]


# --- Half two: the poll finds the cancellation -------------------------------------------------


def test_a_cancellation_is_detected_inside_the_daily_window_for_a_lower_priority_source():
    """The whole chain, through the real scheduler and the real pipeline.

    The `ics` method is in the lower tier, so its window is 24 hours — and the chain is
    exactly FR-53's: the source is polled inside its window, and the poll finds the
    cancellation and writes the `EventStateChange` that propagation consumes.
    """
    source = _ics_source()

    # 1. The event exists upstream.
    _run(source, vevent(UID, START))
    assert _event(source).status == "scheduled"

    # 2. The source has been polled; the clock starts here.
    attempted_at = _attempted_at(source)

    # 3. Upstream cancels the event. The feed now says CANCELLED.
    upstream_cancelled = vevent(UID, START, status="CANCELLED")

    # 4. The window closes at `attempted_at + cadence`, and the cadence is the ceiling.
    at_the_window = attempted_at + timedelta(hours=24)

    # 5. The real scheduler runs.
    claimed = claim_due_sources(now=at_the_window)

    # 6. The source is claimed — the detection happened inside the window.
    assert claimed == [source.pk]

    # 7. The ingest that follows finds the cancellation and writes the state change.
    release_claim(source.pk)
    report = _run(source, upstream_cancelled)

    assert report.outcome == "ok"
    event = _event(source)
    assert event.status == "cancelled"
    [change] = _changes(event)
    assert (change.kind, change.event_version) == ("cancelled", 2)
    assert change.propagated_at is None  # propagation consumes it later (AD-17)


def test_the_source_is_not_yet_due_one_second_before_the_window():
    """The boundary from the wrong side: a scheduler that polls too often is a cost."""
    source = _ics_source()
    _run(source, vevent(UID, START))
    attempted_at = _attempted_at(source)

    assert claim_due_sources(now=attempted_at + timedelta(hours=24) - SECOND) == []


def test_the_source_is_due_exactly_at_the_window():
    """The boundary from the other side: at the ceiling, the poll is due."""
    source = _ics_source()
    _run(source, vevent(UID, START))
    attempted_at = _attempted_at(source)

    assert claim_due_sources(now=attempted_at + timedelta(hours=24)) == [source.pk]


def test_the_window_is_measured_from_the_last_attempt_not_the_last_success():
    """A source polled on time and failing still has its floor met on the attempt side.

    The floor *check* is about the last success (a failed poll detects nothing), but the
    *scheduler* is keyed on the last attempt — otherwise a failing source would be retried
    on every tick, and the attempt stamp is what the window is measured from.
    """
    source = _ics_source()
    _run(source, vevent(UID, START))
    attempted_at = _attempted_at(source)

    # A failed poll moves the attempt stamp forward.
    report = ingest_source(
        source.id, fetch_port=ScriptedFetchPort().serve(FetchError(reason="http_500"))
    )
    assert report.outcome == "fetch_failed"
    assert _attempted_at(source) > attempted_at

    # The window runs from the *new* attempt, not from the old one.
    assert claim_due_sources(now=attempted_at + timedelta(hours=24)) == []


def test_a_source_that_keeps_failing_breaks_the_detection_floor_even_though_it_is_polled():
    """The two halves come apart, and the floor check is what says so.

    The source is polled on time — so the *attempt* side of the promise is kept — but every
    poll fails, so nothing is detected. FR-53's consequence is about detection, and the
    floor check counts a source whose last **success** is older than its tier's ceiling.
    """
    from apps.ingestion.services.scheduling import report_cadence_floor_breaches

    source = _ics_source()
    _run(source, vevent(UID, START))
    ingest_source(source.id, fetch_port=ScriptedFetchPort().serve(FetchError(reason="http_500")))

    # Polled inside the window, but nothing was ingested since the first run.
    assert claim_due_sources(now=_attempted_at(source) + timedelta(hours=24) - SECOND) == []

    # And the floor check — measured from the last success — does not care about the attempt.
    assert report_cadence_floor_breaches(now=_attempted_at(source)) == 0
    assert report_cadence_floor_breaches(now=_attempted_at(source) + timedelta(hours=24)) == 1
    assert claim_due_sources(now=_attempted_at(source) + timedelta(hours=24)) == [source.pk]
