"""`ingest_source` runs: fixtures through the fake adapter, fetch and parse outcomes, the 304
path, the guard, the audit row and the log line (pipeline design D3, D16, D17).
"""

import json
import logging
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.apps import apps as django_apps
from django.db import router

from adapters.crawl.fake import FakeFetchAdapter
from adapters.logging.formatter import JsonFormatter
from apps.ingestion.models import Event, EventStateChange, ExtractedRecord, IngestionAuditEntry
from apps.ingestion.services import ingest_source as ingest_module
from apps.ingestion.services.ingest_source import ingest_source
from apps.ingestion.services.source_registry import (
    CrawlNeedsTosReviewError,
    SourceNotFoundError,
    SourcePausedError,
)
from ports.fetch import (
    FetchBlockedError,
    FetchContentError,
    FetchHTTPError,
    FetchNetworkError,
    FetchRedirectError,
    FetchTimeoutError,
    FetchTooLargeError,
)
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7
from tests.ingestion.factories import SourceFactory
from tests.ingestion.pipeline_support import ScriptedFetchPort, calendar, ics_source, ok, vevent

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

FIXTURES = "https://fixtures.example.test"


def _fixture_source(name: str, method: str, **overrides):
    return SourceFactory(url=f"{FIXTURES}/{name}", acquisition_method=method, **overrides)


def _events(source=None):
    rows = Event.objects.using(CATALOG).order_by("start_time_utc", "title")
    return list(rows if source is None else rows.filter(source=source))


def _audit(source):
    return list(
        IngestionAuditEntry.objects.using(CATALOG)
        .filter(target_id=source.id, action="ingest_source")
        .order_by("id")
    )


def _reload(source):
    source.refresh_from_db(using=CATALOG)
    return source


# --- First ingest of each recorded fixture ----------------------------------------------------


def test_ics_fixture_first_ingest_creates_events_and_rejects_zoneless_times():
    source = _fixture_source("calendar.ics", "ics")

    report = ingest_source(source.id, fetch_port=FakeFetchAdapter())

    assert report.outcome == "ok"
    assert report.counts == {
        "new": 6,
        "rejected:tz_unresolvable": 2,  # floating yoga and the all-day fair: no zone, no venue
        "skipped:no_event_start": 1,
        "tz_review_pending": 2,  # the two UTC-only events: Etc zone, 0.85
    }
    titles = {e.title: e for e in _events(source)}
    assert set(titles) == {
        "Library Book Club",
        "Global Webinar",
        "Cancelled Concert",
        "Weekly Run Club (first week moved indoors)",
        "Weekly Run Club (late start)",
        "No UID Here",
    }
    book_club = titles["Library Book Club"]
    assert (book_club.start_time_tz, book_club.start_time_local) == (
        "America/New_York",
        "2026-11-05T19:30:00",
    )
    assert (book_club.tz_inference_confidence, book_club.publication_status) == (
        Decimal("1.00"),
        "published",
    )
    assert book_club.original_start_utc == book_club.start_time_utc
    assert book_club.slug.startswith("library-book-club-2026-11-05-")
    webinar = titles["Global Webinar"]
    assert (webinar.start_time_tz, webinar.tz_review_pending) == ("UTC", True)
    assert titles["Cancelled Concert"].status == "cancelled"
    run_club = [titles[t] for t in titles if t.startswith("Weekly Run Club")]
    assert run_club[0].series_id is not None
    assert run_club[0].series_id == run_club[1].series_id
    assert run_club[0].pk != run_club[1].pk


def test_ics_fixture_rejections_are_recorded_without_events():
    source = _fixture_source("calendar.ics", "ics")

    ingest_source(source.id, fetch_port=FakeFetchAdapter())

    rejected = ExtractedRecord.objects.using(CATALOG).filter(source=source, resolution="rejected")
    assert sorted(r.payload["title"] for r in rejected) == ["Floating Yoga", "Harvest Fair"]
    assert {r.reject_reason for r in rejected} == {"tz_unresolvable"}
    assert all(r.event_id is None and r.tz_inference_confidence is None for r in rejected)
    harvest = rejected.get(payload__title="Harvest Fair")
    assert (harvest.payload["all_day"], harvest.payload["start_raw"]) == (True, "20261114")


@pytest.mark.parametrize(
    ("name", "method"),
    [("venue-events.html", "jsonld"), ("events.rss", "rss"), ("events.atom", "rss")],
)
def test_structured_fixture_first_ingest_binds_every_candidate(name, method):
    source = _fixture_source(name, method)

    report = ingest_source(source.id, fetch_port=FakeFetchAdapter())

    records = ExtractedRecord.objects.using(CATALOG).filter(source=source)
    processed = sum(n for key, n in report.counts.items() if not key.startswith("skipped:"))
    flags = report.counts.get("tz_review_pending", 0) + report.counts.get("in_review", 0)
    assert report.outcome == "ok"
    assert records.count() == processed - flags  # one record per candidate
    assert len(_events(source)) == report.counts.get("new", 0)
    for event in _events(source):
        bound = records.get(event=event)
        assert bound.resolution == "resolved"
        local = event.start_time_utc.astimezone(ZoneInfo(event.start_time_tz))
        assert event.start_time_local == local.strftime("%Y-%m-%dT%H:%M:%S")


def test_reingest_of_the_same_fixture_changes_nothing():
    source = _fixture_source("calendar.ics", "ics")
    ingest_source(source.id, fetch_port=FakeFetchAdapter())
    snapshot = [(e.pk, e.event_version, e.updated_at) for e in _events(source)]
    seen = {r.pk: r.last_seen_at for r in ExtractedRecord.objects.using(CATALOG)}
    _reload(source)
    source.etag, source.last_modified = "", ""  # force a full fetch, not a 304
    source.save(using=CATALOG, update_fields=["etag", "last_modified"])

    report = ingest_source(source.id, fetch_port=FakeFetchAdapter())

    assert report.counts == {"unchanged": 8, "skipped:no_event_start": 1}
    events = _events(source)
    assert [(e.pk, e.event_version) for e in events] == [(p, v) for p, v, _ in snapshot]
    assert not EventStateChange.objects.using(CATALOG).exists()
    later = {r.pk: r.last_seen_at for r in ExtractedRecord.objects.using(CATALOG)}
    assert all(later[pk] > seen[pk] for pk in seen)  # only last_seen moves


# --- Conditional fetch and source state (D16, plan P8) ----------------------------------------


def test_not_modified_is_a_success_without_parsing():
    source = _fixture_source("calendar.ics", "ics")
    ingest_source(source.id, fetch_port=FakeFetchAdapter())
    first = _reload(source).last_ingested_at

    report = ingest_source(source.id, fetch_port=FakeFetchAdapter())

    assert (report.outcome, report.counts) == ("not_modified", {})
    stored = _reload(source)
    assert stored.last_ingested_at > first
    assert stored.last_modified == "Wed, 04 Nov 2026 10:00:00 GMT"  # kept, though not resent
    assert _audit(source)[-1].details == {"outcome": "not_modified", "counts": {}}


def test_success_stores_validators_final_url_and_clears_failure_state():
    source = ics_source(consecutive_failures=3, last_error_code="fetch_timeout")
    source.stale_since = source.created_at
    source.save(using=CATALOG, update_fields=["stale_since"])
    port = ScriptedFetchPort().serve(
        ok(calendar(), url="https://feeds.example.test/moved.ics", etag='"v2"')
    )

    ingest_source(source.id, fetch_port=port)

    stored = _reload(source)
    assert (stored.consecutive_failures, stored.last_error_code, stored.stale_since) == (
        0,
        "",
        None,
    )
    assert (stored.etag, stored.last_modified) == ('"v2"', "")
    assert stored.fetched_url == "https://feeds.example.test/moved.ics"
    assert port.calls == [
        {"url": source.url, "etag": None, "last_modified": None},
    ]


def test_conditional_headers_sent_from_stored_validators():
    source = ics_source(etag='"v1"', last_modified="Wed, 04 Nov 2026 10:00:00 GMT")
    port = ScriptedFetchPort().serve(calendar())

    ingest_source(source.id, fetch_port=port)

    assert port.calls[0]["etag"] == '"v1"'
    assert port.calls[0]["last_modified"] == "Wed, 04 Nov 2026 10:00:00 GMT"


def test_final_url_is_the_base_for_relative_links():
    source = ics_source()
    body = calendar(vevent("a@x", "20261105T193000", url="/events/a"))
    port = ScriptedFetchPort().serve(ok(body, url="https://www.feeds.example.test/new/cal.ics"))

    ingest_source(source.id, fetch_port=port)

    [event] = _events(source)
    assert event.canonical_url == "https://feeds.example.test/events/a"  # normalized (D19)


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (FetchTimeoutError("timeout"), "fetch_timeout"),
        (FetchTooLargeError("too_large"), "fetch_too_large"),
        (FetchBlockedError("private_address"), "fetch_blocked"),
        (FetchBlockedError("cross_host_redirect"), "source_moved"),
        (FetchHTTPError(503), "fetch_http_error"),
        (FetchRedirectError("too_many"), "fetch_too_many_redirects"),
        (FetchContentError("encoding"), "fetch_bad_content"),
        (FetchNetworkError("refused"), "fetch_network_error"),
    ],
)
def test_fetch_error_recorded_on_source_and_audited(error, code):
    source = ics_source(consecutive_failures=2, etag='"v1"')

    report = ingest_source(source.id, fetch_port=ScriptedFetchPort().serve(error))

    assert (report.outcome, report.error_code) == ("fetch_failed", code)
    stored = _reload(source)
    assert (stored.consecutive_failures, stored.last_error_code) == (3, code)
    assert stored.last_ingested_at is None
    assert stored.etag == '"v1"'  # a failed fetch says nothing about the body
    assert _audit(source)[-1].details == {
        "outcome": "fetch_failed",
        "error_code": code,
        "counts": {},
    }


@pytest.mark.parametrize(
    ("name", "code"), [("down", "fetch_http_error"), ("slow", "fetch_timeout")]
)
def test_fake_adapter_simulated_failures(name, code):
    source = _fixture_source(name, "rss")

    report = ingest_source(source.id, fetch_port=FakeFetchAdapter())

    assert report.error_code == code


def test_parse_failure_recorded_and_validators_dropped():
    source = _fixture_source("broken.ics", "ics", etag='"old"')

    report = ingest_source(source.id, fetch_port=FakeFetchAdapter())

    assert report.outcome == "parse_failed"
    assert report.error_code.startswith("parse_")
    stored = _reload(source)
    assert (stored.consecutive_failures, stored.last_error_code) == (1, report.error_code)
    assert (stored.etag, stored.last_modified, stored.last_ingested_at) == ("", "", None)


# --- Guards (FR-13, FR-17; D3) ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"status": "paused"}, SourcePausedError),
        ({"acquisition_method": "crawl", "tos_status": "not_reviewed"}, CrawlNeedsTosReviewError),
        ({"acquisition_method": "crawl", "tos_status": "rejected"}, CrawlNeedsTosReviewError),
    ],
)
def test_refused_source_is_never_fetched_or_audited(overrides, error):
    source = ics_source(**overrides)
    port = ScriptedFetchPort().serve(calendar())

    with pytest.raises(error):
        ingest_source(source.id, fetch_port=port)

    assert port.calls == []
    assert _audit(source) == []
    assert _reload(source).last_attempted_at is None


def test_unknown_source_not_found():
    with pytest.raises(SourceNotFoundError):
        ingest_source(uuid7(), fetch_port=ScriptedFetchPort().serve(calendar()))


def test_default_fetch_port_comes_from_the_registry(settings):
    settings.ADAPTERS = {**settings.ADAPTERS, "fetch": "adapters.crawl.fake.FakeFetchAdapter"}
    source = _fixture_source("calendar.ics", "ics")

    assert ingest_source(source.id).outcome == "ok"


# --- Item isolation, audit, logs, the wall ----------------------------------------------------


def test_one_failing_item_does_not_abort_the_source(monkeypatch):
    source = ics_source()
    body = calendar(vevent("good@x", "20261105T193000"), vevent("bad@x", "20261106T193000"))
    real = ingest_module.ingest_item

    def flaky(run, candidate):
        if candidate.source_event_id == "bad@x":
            raise RuntimeError("boom")
        return real(run, candidate)

    monkeypatch.setattr(ingest_module, "ingest_item", flaky)

    report = ingest_source(source.id, fetch_port=ScriptedFetchPort().serve(body))

    assert report.counts == {"new": 1, "failed:RuntimeError": 1}
    assert [e.source_event_id for e in _events(source)] == ["good@x"]


def test_finished_log_line_carries_counts_and_ids_only(caplog):
    source = ics_source()
    body = calendar(vevent("a@x", "20261105T193000", summary="Secret Title Text"))
    stream = []
    handler = logging.Handler()
    handler.emit = lambda record: stream.append(JsonFormatter().format(record))
    logging.getLogger(ingest_module.__name__).addHandler(handler)
    try:
        ingest_source(source.id, fetch_port=ScriptedFetchPort().serve(body))
    finally:
        logging.getLogger(ingest_module.__name__).removeHandler(handler)

    [line] = [json.loads(s) for s in stream if "Ingest finished" in s]
    assert line["source_id"] == str(source.id)
    assert (line["outcome"], line["new_count"], line["failed_count"]) == ("ok", 1, 0)
    assert all("Secret Title Text" not in s for s in stream)


def test_nothing_is_written_to_personal():
    personal_models = [m for m in django_apps.get_models() if router.db_for_write(m) == PERSONAL]
    before = {m: m.objects.using(PERSONAL).count() for m in personal_models}
    source = _fixture_source("calendar.ics", "ics")

    ingest_source(source.id, fetch_port=FakeFetchAdapter())

    assert {m: m.objects.using(PERSONAL).count() for m in personal_models} == before
