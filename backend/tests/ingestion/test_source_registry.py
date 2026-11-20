"""Source Registry commands (FR-13) and the acquisition-hierarchy guard (FR-17)."""

import logging
from datetime import timedelta

import pytest

from apps.ingestion.models import AcquisitionMethod, IngestionAuditEntry, Source, TosReview
from apps.ingestion.services import source_registry
from apps.ingestion.services.source_registry import (
    CrawlNeedsTosReviewError,
    SourceAlreadyRegisteredError,
    SourceNotFoundError,
    SourcePausedError,
    TosReviewInput,
    ensure_can_ingest,
    pause_source,
    record_tos_review,
    register_source,
    resume_source,
    update_source,
)
from domain.errors import PermissionDeniedError, ValidationError
from shared.actor import Actor
from shared.constants import DEFAULT_INGESTION_CADENCE
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7
from tests.ingestion.factories import SourceFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

STAFF_ID = uuid7()
STAFF = Actor.user(STAFF_ID)
FEED_URL = "https://fillmore.example.test/events.rss"
TERMS_URL = "https://fillmore.example.test/terms"
APPROVE = TosReviewInput(decision="approved", evidence_url=TERMS_URL, notes="Crawling allowed.")
REJECT = TosReviewInput(decision="rejected", notes="Terms forbid automated access.")


def _register(**overrides) -> Source:
    kwargs = {
        "actor": STAFF,
        "name": "Fillmore listings",
        "source_type": "venue",
        "url": FEED_URL,
        "acquisition_method": "rss",
        "tz_coverage": "full",
    }
    return register_source(**(kwargs | overrides))


def _audit(target_id=None) -> list[IngestionAuditEntry]:
    rows = IngestionAuditEntry.objects.using(CATALOG).order_by("id")
    return list(rows if target_id is None else rows.filter(target_id=target_id))


def _reload(source: Source) -> Source:
    return Source.objects.using(CATALOG).get(pk=source.pk)


def _locs(exc: ValidationError) -> list[list[str]]:
    return [item["loc"] for item in exc.details["errors"]]


def _nothing_written() -> bool:
    return not (
        Source.objects.using(CATALOG).exists()
        or TosReview.objects.using(CATALOG).exists()
        or IngestionAuditEntry.objects.using(CATALOG).exists()
    )


# --- register_source ---------------------------------------------------------------------------


def test_register_source_stores_source_and_one_audit_row():
    source = _register(name="  Fillmore listings  ", city=" San Francisco ")

    stored = _reload(source)
    assert (stored.name, stored.city) == ("Fillmore listings", "San Francisco")
    assert stored.url == FEED_URL
    assert (stored.status, stored.tos_status) == ("active", "not_reviewed")
    [entry] = _audit()
    assert (entry.action, entry.target_type, entry.target_id) == (
        "register_source",
        "source",
        source.id,
    )
    assert (entry.actor_kind, entry.actor_id, entry.actor_label) == ("user", STAFF_ID, "")
    assert entry.details["fields"]["url"] == FEED_URL
    assert entry.details["fields"]["ingestion_cadence"] == "P0DT04H00M00S"


def test_register_source_rss_without_cadence_defaults_to_four_hours():
    assert _reload(_register()).ingestion_cadence == timedelta(hours=4)


@pytest.mark.parametrize("method", AcquisitionMethod.values)
def test_register_source_without_cadence_uses_method_default(method):
    review = APPROVE if method == "crawl" else None

    source = _register(acquisition_method=method, tos_review=review)

    assert _reload(source).ingestion_cadence == DEFAULT_INGESTION_CADENCE[method]


@pytest.mark.parametrize("method", AcquisitionMethod.values)
def test_every_method_default_is_inside_its_own_ceiling(method):
    """A default is a value this code chooses, so it must be a value this code can defend.

    If a method's default were ever above its tier's ceiling, the row would be created and
    then refused by the database constraint — an `IntegrityError` instead of a refusal. This
    test is the invariant that says that cannot happen quietly.
    """
    from domain.sources import cadence_ceiling

    assert DEFAULT_INGESTION_CADENCE[method] <= cadence_ceiling(method)


def test_a_default_above_the_ceiling_is_refused_rather_than_written(monkeypatch):
    """The refusal path, when the default itself breaks the rule.

    The default is monkeypatched to a week — over every tier's ceiling — so the check has
    something to catch. Without the check the row would be created and the *database*
    constraint would refuse it, which is a crash, not a refusal.
    """
    monkeypatch.setitem(DEFAULT_INGESTION_CADENCE, "api", timedelta(days=7))

    with pytest.raises(ValidationError) as excinfo:
        _register(acquisition_method="api")

    assert _locs(excinfo.value) == [["ingestion_cadence"]]
    assert _nothing_written()


def test_the_default_is_measured_against_its_own_tier(monkeypatch):
    """The default is checked against **its own method's** ceiling, not another tier's.

    A 12-hour default is legal in the lower tier (24h) and illegal in the high tier (4h).
    So a high-priority source whose default was 12 hours must be refused, while a
    lower-priority one with the same default must not be. If the check were made against
    the wrong tier, one of those two would go the wrong way.
    """
    monkeypatch.setitem(DEFAULT_INGESTION_CADENCE, "api", timedelta(hours=12))

    with pytest.raises(ValidationError) as excinfo:
        _register(acquisition_method="api")

    assert _locs(excinfo.value) == [["ingestion_cadence"]]
    assert _nothing_written()


def test_the_same_default_is_legal_in_the_lower_tier(monkeypatch):
    """The other half of the previous test — 12 hours is fine for an `rss` source."""
    monkeypatch.setitem(DEFAULT_INGESTION_CADENCE, "rss", timedelta(hours=12))

    source = _register(acquisition_method="rss")

    assert _reload(source).ingestion_cadence == timedelta(hours=12)


def test_register_source_explicit_cadence_kept():
    source = _register(ingestion_cadence=timedelta(hours=1))

    assert _reload(source).ingestion_cadence == timedelta(hours=1)


def test_register_source_cadence_below_floor_refused():
    with pytest.raises(ValidationError) as excinfo:
        _register(ingestion_cadence=timedelta(minutes=14))

    assert _locs(excinfo.value) == [["ingestion_cadence"]]
    assert _nothing_written()


# --- FR-53: the cadence ceilings -------------------------------------------------------------


def test_register_high_priority_source_at_its_ceiling_accepted():
    """A high-priority source may poll exactly every 4 hours — the ceiling, not under it."""
    source = _register(acquisition_method="api", ingestion_cadence=timedelta(hours=4))

    assert _reload(source).ingestion_cadence == timedelta(hours=4)


def test_register_high_priority_source_over_its_ceiling_refused():
    with pytest.raises(ValidationError) as excinfo:
        _register(acquisition_method="api", ingestion_cadence=timedelta(hours=4, seconds=1))

    assert _locs(excinfo.value) == [["ingestion_cadence"]]
    assert _nothing_written()


def test_register_lower_priority_source_at_its_ceiling_accepted():
    source = _register(acquisition_method="rss", ingestion_cadence=timedelta(hours=24))

    assert _reload(source).ingestion_cadence == timedelta(hours=24)


def test_register_lower_priority_source_over_its_ceiling_refused():
    with pytest.raises(ValidationError) as excinfo:
        _register(acquisition_method="rss", ingestion_cadence=timedelta(hours=24, seconds=1))

    assert _locs(excinfo.value) == [["ingestion_cadence"]]
    assert _nothing_written()


def test_register_lower_priority_source_at_the_high_ceiling_accepted():
    """A source may poll *more* often than its tier requires — 4h is inside the 24h ceiling."""
    source = _register(acquisition_method="rss", ingestion_cadence=timedelta(hours=4))

    assert _reload(source).ingestion_cadence == timedelta(hours=4)


@pytest.mark.parametrize("method", ["api", "partnership"])
def test_every_high_priority_method_shares_the_four_hour_ceiling(method):
    with pytest.raises(ValidationError):
        _register(acquisition_method=method, ingestion_cadence=timedelta(hours=4, seconds=1))

    assert not Source.objects.using(CATALOG).exists()


@pytest.mark.parametrize("method", ["jsonld", "rss", "ics", "email_ics", "crawl"])
def test_every_other_method_gets_the_daily_ceiling(method):
    """The lower tier is "not a high-priority method" — so a method added later is in it too."""
    review = APPROVE if method == "crawl" else None

    with pytest.raises(ValidationError):
        _register(
            acquisition_method=method,
            ingestion_cadence=timedelta(hours=24, seconds=1),
            tos_review=review,
        )

    assert not Source.objects.using(CATALOG).exists()


def test_the_refusal_names_the_ceiling_it_broke():
    with pytest.raises(ValidationError) as excinfo:
        _register(acquisition_method="api", ingestion_cadence=timedelta(days=7))

    [error] = excinfo.value.details["errors"]
    assert "4 hours" in error["msg"]


def test_a_high_priority_source_may_not_be_registered_with_a_weekly_cadence():
    """The case FR-53 exists for: a source that would never be polled inside the window."""
    with pytest.raises(ValidationError):
        _register(acquisition_method="partnership", ingestion_cadence=timedelta(days=7))

    assert _nothing_written()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("url", "ftp://fillmore.example.test/feed"),
        ("url", "https://editor:secret@fillmore.example.test/feed"),
        ("url", "fillmore.example.test/feed"),
        ("url", "https://fillmore.example.test:99999/feed"),
        ("url", "https://example.test/" + "a" * 2048),
        ("name", "   "),
        ("name", None),
        ("name", "n" * 201),
        ("source_type", "blog"),
        ("acquisition_method", "scrape"),
        ("tz_coverage", "some"),
        ("city_tz", "Mars/Olympus_Mons"),
        ("city_tz", "EST"),  # loads in zoneinfo, but not a zone an event can happen in
        ("city_tz", "z" * 65),
        ("city_tz", None),
        ("freshness_ttl_hours", 0),
        ("freshness_ttl_hours", True),
        ("ingestion_cadence", 4),
    ],
)
def test_register_source_invalid_field_refused(field, value):
    with pytest.raises(ValidationError) as excinfo:
        _register(**{field: value})

    assert _locs(excinfo.value) == [[field]]
    assert _nothing_written()


def test_register_source_stores_a_city_zone_canonicalized():
    # FR-60 row C1b's input. Canonicalized on the way in, like a venue's tz, so the column
    # holds one spelling per zone and `resolve_tz` reads back exactly what was validated.
    stored = _reload(_register(city="Dhaka", city_tz=" Asia/Dhaka "))

    assert stored.city_tz == "Asia/Dhaka"

    legacy = _register(url="https://two.example.test/f.rss", city_tz="US/Pacific")
    assert _reload(legacy).city_tz == "America/Los_Angeles"


def test_register_source_without_a_city_zone_stores_blank():
    # Every source that predates this field. A blank city_tz changes no resolution at all —
    # `tests/domain/test_timezones.py` asserts that half.
    assert _reload(_register()).city_tz == ""


def test_city_zone_and_tz_coverage_are_unrelated():
    # tz_coverage describes whether the *feed* carries zones; city_tz is a fact about the
    # *city*. The Dhaka seed is honestly both: tz_coverage="none" with a real city zone.
    stored = _reload(_register(tz_coverage="none", city="Dhaka", city_tz="Asia/Dhaka"))

    assert (stored.tz_coverage, stored.city_tz) == ("none", "Asia/Dhaka")


def test_update_source_can_set_and_clear_a_city_zone():
    source = _register()

    update_source(actor=STAFF, source_id=source.id, changes={"city_tz": "Asia/Dhaka"})
    assert _reload(source).city_tz == "Asia/Dhaka"

    update_source(actor=STAFF, source_id=source.id, changes={"city_tz": ""})
    assert _reload(source).city_tz == ""


def test_update_source_invalid_city_zone_refused_and_row_unchanged():
    source = _register(city_tz="Asia/Dhaka")

    with pytest.raises(ValidationError) as excinfo:
        update_source(actor=STAFF, source_id=source.id, changes={"city_tz": "Mars/Olympus_Mons"})

    assert _locs(excinfo.value) == [["city_tz"]]
    assert _reload(source).city_tz == "Asia/Dhaka"


def test_register_source_same_feed_under_another_spelling_refused():
    first = _register(url="http://fillmore.example.test/events.rss")

    with pytest.raises(SourceAlreadyRegisteredError) as excinfo:
        _register(url="https://www.fillmore.example.test/events.rss?utm_source=newsletter")

    assert excinfo.value.details == {"source_id": str(first.id)}
    assert Source.objects.using(CATALOG).count() == 1


def test_register_crawl_source_without_review_refused_and_nothing_written():
    with pytest.raises(CrawlNeedsTosReviewError):
        _register(acquisition_method="crawl")

    assert _nothing_written()


def test_register_crawl_source_with_rejected_review_refused():
    with pytest.raises(CrawlNeedsTosReviewError):
        _register(acquisition_method="crawl", tos_review=REJECT)

    assert _nothing_written()


def test_register_crawl_source_with_approved_review_records_it():
    source = _register(acquisition_method="crawl", tos_review=APPROVE)

    assert _reload(source).tos_status == "approved"
    [review] = TosReview.objects.using(CATALOG).filter(source=source)
    assert (review.acquisition_method, review.decision, review.reviewed_by_id) == (
        "crawl",
        "approved",
        STAFF_ID,
    )
    assert (review.evidence_url, review.notes) == (TERMS_URL, "Crawling allowed.")
    assert [e.action for e in _audit(source.id)] == ["register_source", "record_tos_review"]


def test_register_source_inline_review_by_system_actor_refused():
    with pytest.raises(PermissionDeniedError):
        _register(actor=Actor.system("scheduler"), acquisition_method="crawl", tos_review=APPROVE)

    assert _nothing_written()


# --- update_source -----------------------------------------------------------------------------


def _approved_rss_source() -> Source:
    source = _register()
    record_tos_review(actor=STAFF, source_id=source.id, review=APPROVE)
    return _reload(source)


def test_update_source_changes_fields_and_audits_the_diff():
    source = _approved_rss_source()

    update_source(
        actor=STAFF,
        source_id=source.id,
        changes={"name": "Fillmore SF", "ingestion_cadence": timedelta(hours=2)},
    )

    stored = _reload(source)
    assert (stored.name, stored.ingestion_cadence) == ("Fillmore SF", timedelta(hours=2))
    assert stored.tos_status == "approved"  # name and cadence don't touch the review
    entry = _audit(source.id)[-1]
    assert entry.action == "update_source"
    assert entry.details == {
        "changes": {
            "name": {"from": "Fillmore listings", "to": "Fillmore SF"},
            "ingestion_cadence": {"from": "P0DT04H00M00S", "to": "P0DT02H00M00S"},
        },
        "tos_status_reset": False,
    }


def test_update_source_with_stored_values_writes_nothing():
    source = _register()
    before = _audit(source.id)

    update_source(
        actor=STAFF, source_id=source.id, changes={"name": "Fillmore listings", "url": FEED_URL}
    )

    assert _audit(source.id) == before
    assert _reload(source).updated_at == source.updated_at


@pytest.mark.parametrize("field", ["status", "tos_status", "last_ingested_at", "etag", "nope"])
def test_update_source_non_editable_field_refused(field):
    source = _register()

    with pytest.raises(ValidationError) as excinfo:
        update_source(actor=STAFF, source_id=source.id, changes={field: "x"})

    assert _locs(excinfo.value) == [[field]]


def test_update_source_method_change_resets_tos_status():
    source = _approved_rss_source()

    update_source(actor=STAFF, source_id=source.id, changes={"acquisition_method": "ics"})

    assert _reload(source).tos_status == "not_reviewed"
    assert _audit(source.id)[-1].details["tos_status_reset"] is True


def test_update_source_to_crawl_without_review_refused_and_row_unchanged():
    source = _approved_rss_source()
    before = _audit(source.id)

    with pytest.raises(CrawlNeedsTosReviewError):
        update_source(actor=STAFF, source_id=source.id, changes={"acquisition_method": "crawl"})

    stored = _reload(source)
    assert (stored.acquisition_method, stored.tos_status) == ("rss", "approved")
    assert _audit(source.id) == before


def test_update_source_to_crawl_with_approved_review_allowed():
    source = _register()

    update_source(
        actor=STAFF,
        source_id=source.id,
        changes={"acquisition_method": "crawl"},
        tos_review=APPROVE,
    )

    stored = _reload(source)
    assert (stored.acquisition_method, stored.tos_status) == ("crawl", "approved")
    latest = TosReview.objects.using(CATALOG).filter(source=source).latest("reviewed_at")
    assert latest.acquisition_method == "crawl"
    assert [e.action for e in _audit(source.id)][-2:] == ["update_source", "record_tos_review"]


def test_update_source_crawl_to_api_needs_no_review():
    source = _register(acquisition_method="crawl", tos_review=APPROVE)

    update_source(
        actor=STAFF,
        source_id=source.id,
        changes={"acquisition_method": "api", "ingestion_cadence": timedelta(hours=4)},
    )

    stored = _reload(source)
    assert (stored.acquisition_method, stored.tos_status) == ("api", "not_reviewed")


def test_update_source_crawl_source_to_new_host_without_review_refused():
    source = _register(acquisition_method="crawl", tos_review=APPROVE)

    with pytest.raises(CrawlNeedsTosReviewError):
        update_source(
            actor=STAFF, source_id=source.id, changes={"url": "https://other.example.test/"}
        )

    assert _reload(source).url == FEED_URL


def test_update_source_crawl_source_path_change_keeps_review():
    source = _register(acquisition_method="crawl", tos_review=APPROVE)

    update_source(
        actor=STAFF,
        source_id=source.id,
        changes={"url": "https://www.fillmore.example.test/calendar"},
    )

    assert _reload(source).tos_status == "approved"
    assert _audit(source.id)[-1].details["tos_status_reset"] is False


def test_update_source_rss_host_change_resets_tos_status():
    source = _approved_rss_source()

    update_source(
        actor=STAFF, source_id=source.id, changes={"url": "https://feeds.example.test/fillmore"}
    )

    assert _reload(source).tos_status == "not_reviewed"


def test_update_source_to_another_sources_feed_refused():
    _register()
    other = _register(url="https://other.example.test/feed")

    with pytest.raises(SourceAlreadyRegisteredError):
        update_source(
            actor=STAFF,
            source_id=other.id,
            changes={"url": "HTTPS://Fillmore.EXAMPLE.test/events.rss"},
        )


# --- FR-53: a method change re-checks the cadence ---------------------------------------------


def test_update_source_to_a_lower_tier_keeps_a_legal_cadence():
    """Moving down a tier only loosens the ceiling, so the stored cadence is still legal."""
    source = _register(acquisition_method="api", ingestion_cadence=timedelta(hours=4))

    update_source(actor=STAFF, source_id=source.id, changes={"acquisition_method": "rss"})

    assert _reload(source).ingestion_cadence == timedelta(hours=4)


def test_update_source_to_a_higher_tier_without_a_cadence_refused():
    """The stored cadence would be over the new tier's ceiling, so the change is refused."""
    source = _register(acquisition_method="rss", ingestion_cadence=timedelta(hours=24))

    with pytest.raises(ValidationError) as excinfo:
        update_source(actor=STAFF, source_id=source.id, changes={"acquisition_method": "api"})

    assert _locs(excinfo.value) == [["ingestion_cadence"]]
    stored = _reload(source)
    assert (stored.acquisition_method, stored.ingestion_cadence) == ("rss", timedelta(hours=24))


def test_update_source_to_a_higher_tier_with_a_legal_cadence_accepted():
    """Bring the cadence with the method and the row is legal after the write."""
    source = _register(acquisition_method="rss", ingestion_cadence=timedelta(hours=24))

    update_source(
        actor=STAFF,
        source_id=source.id,
        changes={
            "acquisition_method": "api",
            "ingestion_cadence": timedelta(hours=4),
        },
    )

    stored = _reload(source)
    assert (stored.acquisition_method, stored.ingestion_cadence) == ("api", timedelta(hours=4))


def test_update_source_to_a_higher_tier_with_an_illegal_cadence_refused():
    source = _register(acquisition_method="rss", ingestion_cadence=timedelta(hours=24))

    with pytest.raises(ValidationError) as excinfo:
        update_source(
            actor=STAFF,
            source_id=source.id,
            changes={
                "acquisition_method": "api",
                "ingestion_cadence": timedelta(hours=8),
            },
        )

    assert _locs(excinfo.value) == [["ingestion_cadence"]]


def test_update_source_cadence_over_its_own_ceiling_refused():
    source = _register(acquisition_method="api", ingestion_cadence=timedelta(hours=4))

    with pytest.raises(ValidationError) as excinfo:
        update_source(
            actor=STAFF, source_id=source.id, changes={"ingestion_cadence": timedelta(hours=5)}
        )

    assert _locs(excinfo.value) == [["ingestion_cadence"]]
    assert _reload(source).ingestion_cadence == timedelta(hours=4)


def test_a_method_change_that_keeps_the_tier_does_not_re_check_the_cadence():
    """`rss` → `ics` is the same tier, so a 24-hour cadence stays legal."""
    source = _register(acquisition_method="rss", ingestion_cadence=timedelta(hours=24))

    update_source(actor=STAFF, source_id=source.id, changes={"acquisition_method": "ics"})

    assert _reload(source).ingestion_cadence == timedelta(hours=24)


def test_update_source_unknown_id_not_found():
    with pytest.raises(SourceNotFoundError):
        update_source(actor=STAFF, source_id=uuid7(), changes={"name": "x"})


# --- pause_source / resume_source --------------------------------------------------------------


def test_pause_and_resume_source_change_status_with_audit_rows():
    source = _register()

    pause_source(actor=STAFF, source_id=source.id)
    assert _reload(source).status == "paused"
    resume_source(actor=STAFF, source_id=source.id)

    assert _reload(source).status == "active"
    pause, resume = _audit(source.id)[-2:]
    assert (pause.action, pause.details) == ("pause_source", {"from": "active", "to": "paused"})
    assert (resume.action, resume.details) == ("resume_source", {"from": "paused", "to": "active"})


def test_pause_source_already_paused_is_a_noop_without_audit_row():
    source = _register()
    pause_source(actor=STAFF, source_id=source.id)
    before = _audit(source.id)

    pause_source(actor=STAFF, source_id=source.id)
    resume_source(actor=STAFF, source_id=source.id)
    resume_source(actor=STAFF, source_id=source.id)

    assert [e.action for e in _audit(source.id)] == [
        *[e.action for e in before],
        "resume_source",
    ]


def test_pause_source_by_system_actor_logs_warning_with_source_id(caplog):
    source = _register()

    with caplog.at_level(logging.WARNING, logger=source_registry.__name__):
        pause_source(actor=Actor.system("scheduler"), source_id=source.id)

    [record] = [r for r in caplog.records if r.name == source_registry.__name__]
    assert (record.levelno, record.getMessage(), record.source_id) == (
        logging.WARNING,
        "Source paused",
        source.id,
    )
    assert _audit(source.id)[-1].actor_label == "scheduler"


def test_pause_source_unknown_id_not_found():
    with pytest.raises(SourceNotFoundError):
        pause_source(actor=STAFF, source_id=uuid7())


# --- record_tos_review -------------------------------------------------------------------------


def test_record_tos_review_reviews_current_method_and_updates_cache():
    source = _register(acquisition_method="ics")

    review = record_tos_review(actor=STAFF, source_id=source.id, review=REJECT)

    assert (review.acquisition_method, review.decision) == ("ics", "rejected")
    assert _reload(source).tos_status == "rejected"
    entry = _audit(source.id)[-1]
    assert (entry.action, entry.target_type) == ("record_tos_review", "source")
    assert entry.details == {
        "tos_review_id": str(review.id),
        "decision": "rejected",
        "acquisition_method": "ics",
    }


def test_record_tos_review_by_system_actor_refused():
    source = _register()

    with pytest.raises(PermissionDeniedError):
        record_tos_review(actor=Actor.system("scheduler"), source_id=source.id, review=APPROVE)

    assert not TosReview.objects.using(CATALOG).exists()


@pytest.mark.parametrize(
    ("review", "loc"),
    [
        (TosReviewInput(decision="approved"), ["tos_review", "evidence_url"]),
        (TosReviewInput(decision="approved", evidence_url="terms"), ["tos_review", "evidence_url"]),
        (TosReviewInput(decision="maybe", evidence_url=TERMS_URL), ["tos_review", "decision"]),
        (TosReviewInput(decision="rejected", notes=None), ["tos_review", "notes"]),
    ],
)
def test_record_tos_review_invalid_review_refused(review, loc):
    source = _register()

    with pytest.raises(ValidationError) as excinfo:
        record_tos_review(actor=STAFF, source_id=source.id, review=review)

    assert _locs(excinfo.value) == [loc]
    assert _reload(source).tos_status == "not_reviewed"


def test_record_tos_review_rejection_needs_no_evidence():
    source = _register()

    record_tos_review(actor=STAFF, source_id=source.id, review=REJECT)

    assert _reload(source).tos_status == "rejected"


def test_record_tos_review_unknown_source_not_found():
    with pytest.raises(SourceNotFoundError):
        record_tos_review(actor=STAFF, source_id=uuid7(), review=REJECT)


# --- The tos_status invariant (design D13, plan R3) --------------------------------------------


def test_tos_status_is_latest_review_of_current_method_since_it_was_set():
    """Each step's expected value is the latest review of the current method recorded since
    that method was last set, else `not_reviewed`.
    """
    source = _register()
    steps = [
        (lambda: None, "not_reviewed"),
        (lambda: record_tos_review(actor=STAFF, source_id=source.id, review=APPROVE), "approved"),
        (lambda: _switch(source, "api"), "not_reviewed"),
        # An approval of rss exists from step 2, but the switch away invalidated it.
        (lambda: _switch(source, "rss"), "not_reviewed"),
        (lambda: record_tos_review(actor=STAFF, source_id=source.id, review=REJECT), "rejected"),
        (lambda: record_tos_review(actor=STAFF, source_id=source.id, review=APPROVE), "approved"),
        (lambda: _switch(source, "crawl", review=APPROVE), "approved"),
        (lambda: _switch(source, "rss"), "not_reviewed"),
    ]

    observed = []
    for step, _expected in steps:
        step()
        observed.append(_reload(source).tos_status)

    assert observed == [expected for _step, expected in steps]
    assert (
        TosReview.objects.using(CATALOG)
        .filter(source=source, acquisition_method="rss", decision="approved")
        .exists()
    )


def _switch(source: Source, method: str, review: TosReviewInput | None = None) -> None:
    update_source(
        actor=STAFF,
        source_id=source.id,
        changes={"acquisition_method": method},
        tos_review=review,
    )


# --- ensure_can_ingest (FR-13, FR-17) ----------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "method", "tos_status", "error"),
    [
        ("paused", "rss", "approved", SourcePausedError),
        ("paused", "crawl", "approved", SourcePausedError),
        ("active", "crawl", "not_reviewed", CrawlNeedsTosReviewError),
        ("active", "crawl", "rejected", CrawlNeedsTosReviewError),
        ("active", "crawl", "approved", None),
        ("active", "rss", "not_reviewed", None),
        ("active", "api", "rejected", None),
    ],
)
def test_ensure_can_ingest(status, method, tos_status, error):
    source = SourceFactory(status=status, acquisition_method=method, tos_status=tos_status)

    if error is None:
        ensure_can_ingest(source)
    else:
        with pytest.raises(error) as excinfo:
            ensure_can_ingest(source)
        assert excinfo.value.details == {"source_id": str(source.id)}


# --- One transaction: the audit row and the write commit together (AD-5) -----------------------


class AuditBroke(Exception):
    pass


@pytest.fixture
def broken_audit(monkeypatch):
    def fail(**_kwargs):
        raise AuditBroke

    monkeypatch.setattr(source_registry, "write_audit", fail)


@pytest.mark.django_db(databases=[PERSONAL, CATALOG], transaction=True)
@pytest.mark.usefixtures("broken_audit")
def test_register_source_audit_failure_leaves_no_source():
    with pytest.raises(AuditBroke):
        _register()

    assert not Source.objects.using(CATALOG).exists()


@pytest.mark.django_db(databases=[PERSONAL, CATALOG], transaction=True)
@pytest.mark.usefixtures("broken_audit")
def test_update_source_audit_failure_keeps_old_values():
    source = SourceFactory(name="Before", tos_status="approved")

    with pytest.raises(AuditBroke):
        update_source(
            actor=STAFF, source_id=source.id, changes={"name": "After", "acquisition_method": "ics"}
        )

    stored = _reload(source)
    assert (stored.name, stored.acquisition_method, stored.tos_status) == (
        "Before",
        "rss",
        "approved",
    )
