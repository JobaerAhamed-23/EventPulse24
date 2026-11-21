"""The city probation: a city that yields nothing is told so (FR-13, FR-16, AD-16).

**What this file holds.** The rules about *what a run means* are pure and live in
`TestTheClassification` below — no database, no clock, no actor. The rules about *what a
city becomes* need rows, and live in the rest of the file.

**The three promises this file defends.**

1. **A published city is `live`.** A city whose source put an event into the catalogue
   has events, and the surface may say so.
2. **A city that yields nothing is told so.** Three consecutive successful-but-empty
   runs pause the source, and a city whose every source is paused that way is
   `yielded_nothing` — never `collecting` forever.
3. **A hand-pause is not a drought.** An editor's pause is a decision and the city says
   `paused`; only the probation's own pauses say `yielded_nothing`.

**The trap worth naming.** `unchanged` — an event a source re-reports that is already in
the catalogue — counts as *yield*. It is what a healthy source returns on every poll
after the first, so without it every healthy source would accrue a zero-yield run per
poll and be paused after twelve hours of doing its job perfectly. The mutation check at
the bottom of this file proves the tests fail when that is taken out.
"""

from dataclasses import FrozenInstanceError
from uuid import UUID

import pytest

from apps.ingestion.models import City, CityProvisioning, IngestionAuditEntry, Source
from apps.ingestion.services.city_probation import (
    ACTOR_LABEL,
    PROBATION_ACTION,
    CounterEffect,
    ProbationOutcome,
    classify_run,
    probate_after_run,
    published_something,
    yielded_something,
)
from apps.ingestion.services.ingest_source import ingest_source
from apps.ingestion.services.source_registry import pause_source, register_source
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7
from tests.ingestion.factories import SourceFactory
from tests.ingestion.pipeline_support import ScriptedFetchPort, calendar, ok, vevent

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

#: A city in the curated catalog that a provider template covers.
CITY = "Portland, OR"

#: The actor the probation writes under.
ACTOR = Actor.system(ACTOR_LABEL)


@pytest.fixture(autouse=True)
def _a_deployment_with_a_key(settings):
    """Give this deployment a Ticketmaster key.

    **A deployment with no key provisions nothing** — a real behaviour, and
    `tests/ingestion/test_city_provisioning.py` tests it directly. But this file is about
    what happens *when* a city has sources, so the default here is the usable
    deployment.
    """
    settings.TICKETMASTER_API_KEY = "test-key"


# --- helpers ---------------------------------------------------------------------------------


def _provisioned_city(sources: int = 1) -> tuple[City, CityProvisioning, list[Source]]:
    """A city with a provisioning row and exactly `sources` active sources linked to it.

    **The extra sources are registered here, not by the provisioning.** The provisioning
    registers what the provider templates say — one Ticketmaster source for this city —
    and a test that wanted two sources would otherwise be testing the templates.
    """
    from apps.ingestion.services.city_provisioning import provision_city

    outcome = provision_city(city_name=CITY)
    city = City.objects.using(CATALOG).get(pk=outcome.city_id)
    provisioning = CityProvisioning.objects.using(CATALOG).get(city=city)
    linked = list(Source.objects.using(CATALOG).filter(city_ref=city))
    while len(linked) < sources:
        linked.append(
            register_source(
                actor=ACTOR,
                name=f"Extra source {len(linked)}",
                source_type="venue",
                url=f"https://feeds.example.test/extra-{len(linked)}.ics",
                acquisition_method="ics",
                tz_coverage="none",
                city=CITY,
                city_ref=city,
            )
        )
    return city, provisioning, linked


def _pause_all(sources: list[Source], reason: str = Source.PausedReason.ZERO_YIELD) -> None:
    """Pause every source of a city, by the given reason."""
    for source in sources:
        pause_source(actor=ACTOR, source_id=source.id, reason=reason)


def _status(city: City) -> str:
    row = CityProvisioning.objects.using(CATALOG).filter(city=city).first()
    return row.status if row is not None else ""


def _counter(source: Source) -> int:
    source.refresh_from_db(using=CATALOG)
    return source.consecutive_zero_yield_runs


def _audits(action: str = PROBATION_ACTION) -> list[IngestionAuditEntry]:
    return list(IngestionAuditEntry.objects.using(CATALOG).filter(action=action).order_by("id"))


# --- the pure classification ------------------------------------------------------------------


class TestTheClassification:
    """What one run's outcome means for the zero-yield counter.

    **A pure function, so it can be tested exhaustively.** No database, no clock, no
    actor — which is why the rules can be stated as a table rather than as a story.
    """

    def test_a_run_that_published_resets_the_counter(self):
        classification = classify_run("ok", {"new": 1})

        assert classification.counter_effect is CounterEffect.RESET
        assert classification.published is True
        assert classification.yielded is True

    def test_a_run_that_only_updated_does_not_reset_but_still_yields(self):
        """`updated` re-affirms a row that is already there — yield, not publication."""
        classification = classify_run("ok", {"updated": 3})

        assert classification.counter_effect is CounterEffect.RESET
        assert classification.published is False
        assert classification.yielded is True

    def test_a_run_that_only_recognised_known_events_does_not_reset_but_still_yields(self):
        """**`unchanged` is the trap.** A healthy source returns this on every poll."""
        classification = classify_run("ok", {"unchanged": 5})

        assert classification.counter_effect is CounterEffect.RESET
        assert classification.published is False
        assert classification.yielded is True

    def test_a_run_that_yielded_nothing_increments_the_counter(self):
        classification = classify_run("ok", {})

        assert classification.counter_effect is CounterEffect.INCREMENT
        assert classification.published is False
        assert classification.yielded is False

    def test_a_run_that_only_rejected_everything_increments_the_counter(self):
        """A fetch that reached the feed and produced nothing usable is a zero-yield run."""
        classification = classify_run("ok", {"rejected:tz_unresolvable": 2})

        assert classification.counter_effect is CounterEffect.INCREMENT

    def test_a_run_that_only_skipped_everything_increments_the_counter(self):
        classification = classify_run("ok", {"skipped:no_event_start": 1})

        assert classification.counter_effect is CounterEffect.INCREMENT

    def test_a_304_leaves_the_counter_alone(self):
        """**Leave, not reset.** A 304 proves neither emptiness nor content.

        Resetting on a 304 would let a source alternate "empty" and "304" forever and
        never be condemned.
        """
        classification = classify_run("not_modified", {})

        assert classification.counter_effect is CounterEffect.LEAVE
        assert classification.published is False

    def test_a_fetch_failure_leaves_the_counter_alone(self):
        """The run never reached the feed, so it says nothing about the feed's contents."""
        classification = classify_run("fetch_failed", {})

        assert classification.counter_effect is CounterEffect.LEAVE
        assert classification.yielded is False

    def test_a_parse_failure_leaves_the_counter_alone(self):
        classification = classify_run("parse_failed", {})

        assert classification.counter_effect is CounterEffect.LEAVE
        assert classification.yielded is False

    @pytest.mark.parametrize("outcome", ["fetch_failed", "parse_failed", "not_modified"])
    def test_no_failed_run_publishes(self, outcome):
        assert classify_run(outcome, {"new": 1}).published is False

    def test_only_new_and_superseded_are_publication(self):
        """Every other count key is yield at best — a row that was already there."""
        for key in ("updated", "silent_updated", "unchanged", "bound_other_source"):
            assert published_something({key: 1}) is False, key
            assert yielded_something({key: 1}) is True, key

    def test_new_and_superseded_are_publication(self):
        for key in ("new", "superseded"):
            assert published_something({key: 1}) is True, key

    def test_a_bound_other_source_is_yield_but_not_publication(self):
        """The event is in the catalogue because *another* source published it."""
        assert published_something({"bound_other_source": 1}) is False
        assert yielded_something({"bound_other_source": 1}) is True

    def test_the_outcome_is_plain_data(self):
        classification = classify_run("ok", {"new": 1})

        with pytest.raises(FrozenInstanceError):
            classification.published = False  # type: ignore[misc]


# --- the service -----------------------------------------------------------------------------


class TestAPublishedRunMakesTheCityLive:
    """Only publication can say `live`."""

    def test_a_published_run_makes_the_city_live(self):
        city, _provisioning, [source] = _provisioned_city()

        outcome = probate_after_run(
            source=source, outcome="ok", counts={"new": 1}, zero_yield_runs=0, actor=ACTOR
        )

        assert outcome.city_status == CityProvisioning.Status.LIVE
        assert _status(city) == CityProvisioning.Status.LIVE

    def test_the_change_is_audited(self):
        city, _provisioning, [source] = _provisioned_city()

        probate_after_run(
            source=source, outcome="ok", counts={"new": 1}, zero_yield_runs=0, actor=ACTOR
        )

        assert len(_audits()) == 1

    def test_the_audit_row_carries_the_city_id_and_never_the_city_name(self):
        """AD-13: where a reader lives must not reach a log that crosses into `catalog`."""
        city, _provisioning, [source] = _provisioned_city()

        probate_after_run(
            source=source, outcome="ok", counts={"new": 1}, zero_yield_runs=0, actor=ACTOR
        )

        audit = _audits()[0]
        assert audit.details["city_id"] == str(city.id)
        assert CITY not in str(audit.details)
        assert "Portland" not in str(audit.details)

    def test_a_run_that_only_updated_does_not_make_the_city_live(self):
        """Yield is not publication. A city that only re-affirms old events is not `live`."""
        city, _provisioning, [source] = _provisioned_city()

        probate_after_run(
            source=source, outcome="ok", counts={"updated": 1}, zero_yield_runs=0, actor=ACTOR
        )

        assert _status(city) == CityProvisioning.Status.COLLECTING

    def test_a_live_city_stays_live_when_its_source_goes_quiet(self):
        """**State B (covered, quiet) is not state C (never produced anything).**"""
        city, _provisioning, [source] = _provisioned_city()
        probate_after_run(
            source=source, outcome="ok", counts={"new": 1}, zero_yield_runs=0, actor=ACTOR
        )

        probate_after_run(source=source, outcome="ok", counts={}, zero_yield_runs=3, actor=ACTOR)

        assert _status(city) == CityProvisioning.Status.LIVE

    def test_a_second_published_run_writes_no_second_audit_row(self):
        """No change, no audit row — the same rule every status change follows."""
        _city, _provisioning, [source] = _provisioned_city()
        probate_after_run(
            source=source, outcome="ok", counts={"new": 1}, zero_yield_runs=0, actor=ACTOR
        )

        probate_after_run(
            source=source, outcome="ok", counts={"new": 1}, zero_yield_runs=0, actor=ACTOR
        )

        assert len(_audits()) == 1

    def test_a_source_with_no_city_is_not_provisioned(self):
        """A hand-registered seed has no `city_ref`; it gets no city consequence."""
        source = SourceFactory()

        outcome = probate_after_run(
            source=source, outcome="ok", counts={"new": 1}, zero_yield_runs=0, actor=ACTOR
        )

        assert outcome.city_id is None
        assert outcome.city_status == ""


class TestTheGuardsThatShouldNeverFire:
    """Four branches that cannot happen in practice, and what they do when they do.

    **A guard nobody exercises is a guard nobody has read.** Each of these is a
    "cannot happen" branch, and each is here so that the branch is known to work rather
    than merely known to exist.
    """

    def test_a_published_run_for_a_city_with_no_provisioning_row_does_nothing(self):
        """The city row exists but the provisioning row does not — the city was never
        provisioned, so there is no sentence to update."""
        city = City.objects.using(CATALOG).create(
            name="Unprovisioned",
            country_code="US",
            normalized_key="unprovisioned",
            slug="unprovisioned",
        )
        source = SourceFactory(city_ref=city)

        outcome = probate_after_run(
            source=source, outcome="ok", counts={"new": 1}, zero_yield_runs=0, actor=ACTOR
        )

        assert outcome.city_status == ""

    def test_a_published_run_leaves_a_no_providers_city_alone(self):
        """A city with no sources cannot have published an event — so this cannot
        happen, and the guard is here because "unreachable" is a claim, not a proof."""
        city, provisioning, [source] = _provisioned_city()
        provisioning.status = CityProvisioning.Status.NO_PROVIDERS
        provisioning.save(using=CATALOG, update_fields=["status"])

        outcome = probate_after_run(
            source=source, outcome="ok", counts={"new": 1}, zero_yield_runs=0, actor=ACTOR
        )

        assert outcome.city_status == CityProvisioning.Status.NO_PROVIDERS

    def test_a_probation_for_a_city_with_no_provisioning_row_does_nothing(self):
        from apps.ingestion.services.city_probation import _probate_city_status

        status, changed = _probate_city_status(city_id=uuid7(), actor=ACTOR)

        assert status == ""
        assert changed is False

    def test_the_probation_actor_is_a_system_actor(self):
        from apps.ingestion.services.city_probation import probation_actor

        actor = probation_actor()

        assert actor.kind == "system"
        assert actor.label == ACTOR_LABEL


class TestTheZeroYieldThreshold:
    """Three runs, then a pause. Not one, not two."""

    def test_below_the_threshold_the_source_is_not_paused(self):
        _city, _provisioning, [source] = _provisioned_city()

        outcome = probate_after_run(
            source=source, outcome="ok", counts={}, zero_yield_runs=2, actor=ACTOR
        )

        assert outcome.paused is False
        source.refresh_from_db(using=CATALOG)
        assert source.status == Source.Status.ACTIVE

    def test_at_the_threshold_the_source_is_paused(self):
        _city, _provisioning, [source] = _provisioned_city()

        outcome = probate_after_run(
            source=source, outcome="ok", counts={}, zero_yield_runs=3, actor=ACTOR
        )

        assert outcome.paused is True
        source.refresh_from_db(using=CATALOG)
        assert source.status == Source.Status.PAUSED

    def test_the_pause_records_its_reason_on_the_row(self):
        """The reason lives on the row; the audit details stay exactly `{"from", "to"}`."""
        _city, _provisioning, [source] = _provisioned_city()

        probate_after_run(source=source, outcome="ok", counts={}, zero_yield_runs=3, actor=ACTOR)

        source.refresh_from_db(using=CATALOG)
        assert source.paused_reason == Source.PausedReason.ZERO_YIELD

    def test_the_pause_is_audited(self):
        _city, _provisioning, [source] = _provisioned_city()

        probate_after_run(source=source, outcome="ok", counts={}, zero_yield_runs=3, actor=ACTOR)

        assert (
            IngestionAuditEntry.objects.using(CATALOG)
            .filter(action="pause_source", target_id=source.id)
            .count()
            == 1
        )

    def test_the_pause_audit_details_stay_exactly_from_and_to(self):
        """FR-13's contract: the reason is on the row, not in the audit details."""
        _city, _provisioning, [source] = _provisioned_city()

        probate_after_run(source=source, outcome="ok", counts={}, zero_yield_runs=3, actor=ACTOR)

        audit = (
            IngestionAuditEntry.objects.using(CATALOG)
            .filter(action="pause_source", target_id=source.id)
            .get()
        )
        assert audit.details == {"from": "active", "to": "paused"}

    def test_the_pause_does_not_delete_the_source(self):
        """FR-13: sources are paused, never deleted."""
        _city, _provisioning, [source] = _provisioned_city()

        probate_after_run(source=source, outcome="ok", counts={}, zero_yield_runs=3, actor=ACTOR)

        assert Source.objects.using(CATALOG).filter(pk=source.pk).exists()

    def test_an_already_paused_source_is_out_of_scope(self):
        """Its counter is frozen, and the city has already been told about it."""
        _city, _provisioning, [source] = _provisioned_city()
        source.status = Source.Status.PAUSED
        source.paused_reason = Source.PausedReason.MANUAL
        source.save(using=CATALOG, update_fields=["status", "paused_reason"])

        outcome = probate_after_run(
            source=source, outcome="ok", counts={}, zero_yield_runs=3, actor=ACTOR
        )

        assert outcome.paused is False


class TestTheCityStatus:
    """What a city becomes, given its sources."""

    def test_a_city_with_no_sources_is_not_yielded_nothing(self):
        """`no_providers` is "we never tried"; `yielded_nothing` is "we tried and got
        nothing". Overwriting the first with the second would tell the surface a lie."""
        from apps.ingestion.services.city_provisioning import provision_city

        outcome = provision_city(city_name="Dhaka")
        city = City.objects.using(CATALOG).get(pk=outcome.city_id)
        provisioning = CityProvisioning.objects.using(CATALOG).get(city=city)
        provisioning.status = CityProvisioning.Status.COLLECTING
        provisioning.save(using=CATALOG, update_fields=["status"])

        status, changed = _probate(city.id)

        assert status == CityProvisioning.Status.COLLECTING
        assert changed is False

    def test_a_city_with_one_zero_yield_pause_and_one_active_source_stays_collecting(self):
        """Another source may still be working; the city is still collecting."""
        city, _provisioning, sources = _provisioned_city(sources=2)
        pause_source(actor=ACTOR, source_id=sources[0].id, reason=Source.PausedReason.ZERO_YIELD)

        status, _changed = _probate(city.id)

        assert status == CityProvisioning.Status.COLLECTING

    def test_a_city_whose_every_source_is_zero_yield_paused_yields_nothing(self):
        city, _provisioning, sources = _provisioned_city(sources=2)
        _pause_all(list(Source.objects.using(CATALOG).filter(city_ref=city)))

        status, _changed = _probate(city.id)

        assert status == CityProvisioning.Status.YIELDED_NOTHING

    def test_the_change_is_reported_once(self):
        """**No change, no report.** The pause already re-decided the city, so the
        explicit probation finds nothing left to change — and says so."""
        city, _provisioning, sources = _provisioned_city(sources=2)
        _pause_all(list(Source.objects.using(CATALOG).filter(city_ref=city)))

        _status_now, changed = _probate(city.id)

        assert changed is False

    def test_the_provisioned_source_counts_as_a_source_of_the_city(self):
        """**Every** source, not the ones a test happened to register.

        The city's own Ticketmaster source is active, so the city is still collecting
        even after the other source is paused — and it is the other source's pause that
        is examined.
        """
        city, _provisioning, sources = _provisioned_city(sources=2)
        for source in sources[1:]:
            pause_source(actor=ACTOR, source_id=source.id, reason=Source.PausedReason.ZERO_YIELD)

        status, _changed = _probate(city.id)

        assert status == CityProvisioning.Status.COLLECTING

    def test_a_hand_paused_source_makes_the_city_paused_not_yielded_nothing(self):
        """**Somebody stopped this on purpose.** That is a different fact from a drought."""
        city, _provisioning, [source] = _provisioned_city()
        pause_source(actor=ACTOR, source_id=source.id, reason=Source.PausedReason.MANUAL)

        status, _changed = _probate(city.id)

        assert status == CityProvisioning.Status.PAUSED

    def test_a_source_paused_with_no_reason_is_treated_as_a_hand_pause(self):
        """A source paused before the reason column existed has no reason — and "we do
        not know" is read conservatively, as a hand-pause."""
        city, _provisioning, [source] = _provisioned_city()
        source.status = Source.Status.PAUSED
        source.paused_reason = ""
        source.save(using=CATALOG, update_fields=["status", "paused_reason"])

        status, _changed = _probate(city.id)

        assert status == CityProvisioning.Status.PAUSED

    def test_a_live_city_is_untouched(self):
        """`live` is terminal."""
        city, provisioning, _sources = _provisioned_city()
        provisioning.status = CityProvisioning.Status.LIVE
        provisioning.save(using=CATALOG, update_fields=["status"])

        status, changed = _probate(city.id)

        assert status == CityProvisioning.Status.LIVE
        assert changed is False

    def test_a_no_providers_city_is_untouched(self):
        """A fact about coverage cannot be improved on by a probation run."""
        city, provisioning, _sources = _provisioned_city()
        provisioning.status = CityProvisioning.Status.NO_PROVIDERS
        provisioning.save(using=CATALOG, update_fields=["status"])

        status, changed = _probate(city.id)

        assert status == CityProvisioning.Status.NO_PROVIDERS
        assert changed is False

    def test_a_failed_city_is_untouched(self):
        city, provisioning, _sources = _provisioned_city()
        provisioning.status = CityProvisioning.Status.FAILED
        provisioning.save(using=CATALOG, update_fields=["status"])

        status, changed = _probate(city.id)

        assert status == CityProvisioning.Status.FAILED
        assert changed is False

    def test_no_audit_row_is_written_when_the_status_does_not_change(self):
        city, _provisioning, [source] = _provisioned_city()

        _probate(city.id)

        assert _audits() == []

    def test_the_audit_row_carries_the_city_id_and_never_the_city_name(self):
        city, _provisioning, [source] = _provisioned_city()
        pause_source(actor=ACTOR, source_id=source.id, reason=Source.PausedReason.ZERO_YIELD)

        _probate(city.id)

        audit = _audits()[-1]
        assert audit.details["city_id"] == str(city.id)
        assert "Portland" not in str(audit.details)


def _probate(city_id: UUID) -> tuple[str, bool]:
    from apps.ingestion.services.city_probation import _probate_city_status

    return _probate_city_status(city_id=city_id, actor=ACTOR)


# --- the seams --------------------------------------------------------------------------------


class TestTheRegistrySeam:
    """A source's status change re-decides the city — no scheduler involved."""

    def test_a_hand_pause_makes_the_city_paused(self):
        city, _provisioning, [source] = _provisioned_city()

        pause_source(actor=ACTOR, source_id=source.id, reason=Source.PausedReason.MANUAL)

        assert _status(city) == CityProvisioning.Status.PAUSED

    def test_a_resume_puts_the_city_back_to_collecting(self):
        city, _provisioning, [source] = _provisioned_city()
        pause_source(actor=ACTOR, source_id=source.id, reason=Source.PausedReason.MANUAL)

        from apps.ingestion.services.source_registry import resume_source

        resume_source(actor=ACTOR, source_id=source.id)

        assert _status(city) == CityProvisioning.Status.COLLECTING

    def test_a_resume_clears_the_reason_and_the_counter(self):
        """Otherwise the next run would instantly re-pause the source."""
        _city, _provisioning, [source] = _provisioned_city()
        source.consecutive_zero_yield_runs = 2
        source.save(using=CATALOG, update_fields=["consecutive_zero_yield_runs"])
        pause_source(actor=ACTOR, source_id=source.id, reason=Source.PausedReason.ZERO_YIELD)

        from apps.ingestion.services.source_registry import resume_source

        resume_source(actor=ACTOR, source_id=source.id)

        assert _counter(source) == 0
        source.refresh_from_db(using=CATALOG)
        assert source.paused_reason == ""

    def test_a_source_with_no_city_is_not_reprobated(self):
        """A hand-registered seed has no city; nothing to re-decide."""
        source = SourceFactory()

        pause_source(actor=ACTOR, source_id=source.id, reason=Source.PausedReason.MANUAL)

        assert _audits() == []

    def test_a_probation_failure_does_not_undo_the_pause(self):
        """The pause has committed and is audited; a city one step behind is the smaller
        harm.

        **The failure is raised inside the probation, not in place of it.** The guard
        lives in `_reprobate_city`, around the call to `_probate_city_status` — so
        breaking the inner function is what exercises the guard. Replacing
        `_reprobate_city` itself would bypass it and prove nothing.
        """
        import apps.ingestion.services.city_probation as module

        _city, _provisioning, [source] = _provisioned_city()
        original = module._probate_city_status

        def explode(**kwargs):
            raise RuntimeError("the probation is down")

        module._probate_city_status = explode
        try:
            pause_source(actor=ACTOR, source_id=source.id, reason=Source.PausedReason.MANUAL)
        finally:
            module._probate_city_status = original

        source.refresh_from_db(using=CATALOG)
        assert source.status == Source.Status.PAUSED


class TestTheIngestSeam:
    """The counter moves inside the run's own transaction."""

    def test_a_zero_yield_run_increments_the_counter(self):
        source = SourceFactory(acquisition_method="ics")

        ingest_source(source.id, fetch_port=ScriptedFetchPort().serve(ok(calendar())))

        assert _counter(source) == 1

    def test_a_run_that_published_resets_the_counter(self):
        source = SourceFactory(acquisition_method="ics")
        source.consecutive_zero_yield_runs = 2
        source.save(using=CATALOG, update_fields=["consecutive_zero_yield_runs"])
        body = calendar(vevent("a@x", "20261105T193000"))

        ingest_source(source.id, fetch_port=ScriptedFetchPort().serve(body))

        assert _counter(source) == 0

    def test_a_failed_run_leaves_the_counter_alone(self):
        source = SourceFactory(acquisition_method="ics")

        from ports.fetch import FetchTimeoutError

        ingest_source(
            source.id,
            fetch_port=ScriptedFetchPort().serve(FetchTimeoutError("timed out")),
        )

        assert _counter(source) == 0

    def test_a_304_leaves_the_counter_alone(self):
        source = SourceFactory(acquisition_method="ics")

        from ports.fetch import FetchResult

        ingest_source(
            source.id,
            fetch_port=ScriptedFetchPort().serve(
                FetchResult(
                    status=304,
                    final_url="https://feeds.example.test/cal.ics",
                    content_type=None,
                )
            ),
        )

        assert _counter(source) == 0

    def test_a_probation_failure_does_not_fail_a_successful_ingest(self):
        """**The run's outcome is already recorded; the probation is a consequence.**

        The city is one step behind until the next run, which is a smaller harm than a
        failed ingest — the events are in the catalogue either way, and a failed run
        would say the fetch did not work when it did.
        """
        import apps.ingestion.services.ingest_source as module

        source = SourceFactory(acquisition_method="ics")
        original = module.probate_after_run

        def explode(**kwargs):
            raise RuntimeError("the probation is down")

        module.probate_after_run = explode
        try:
            report = ingest_source(source.id, fetch_port=ScriptedFetchPort().serve(ok(calendar())))
        finally:
            module.probate_after_run = original

        assert report.outcome == "ok"

    def test_a_probation_failure_still_records_the_run(self):
        """The audit row and the source's own state are the run's, not the probation's."""
        import apps.ingestion.services.ingest_source as module

        source = SourceFactory(acquisition_method="ics")
        original = module.probate_after_run

        def explode(**kwargs):
            raise RuntimeError("the probation is down")

        module.probate_after_run = explode
        try:
            ingest_source(source.id, fetch_port=ScriptedFetchPort().serve(ok(calendar())))
        finally:
            module.probate_after_run = original

        source.refresh_from_db(using=CATALOG)
        assert source.last_ingested_at is not None
        assert (
            IngestionAuditEntry.objects.using(CATALOG)
            .filter(action="ingest_source", target_id=source.id)
            .count()
            == 1
        )


# --- the end-to-end shape ---------------------------------------------------------------------


class TestThreeEmptyFeedsEndTheCity:
    """**The headline test.** Three empty feeds, and the city says so."""

    def _source(self):
        """A city whose *only* source is an ICS source of its own.

        **Its own source, and the only one.** The provisioned source for this city is a
        Ticketmaster `api` source, and the `api` parser answers `unknown_api_provider`
        to an iCalendar body — so the run would fail to parse rather than yield nothing,
        and a parse failure is not a zero-yield run. The provisioned source is also
        *active*, and a city only yields nothing when **every** one of its sources is
        paused — so it is removed, and the city is left with the one source this test is
        about.
        """
        from apps.ingestion.services.city_provisioning import provision_city

        outcome = provision_city(city_name=CITY)
        city = City.objects.using(CATALOG).get(pk=outcome.city_id)
        for provisioned in Source.objects.using(CATALOG).filter(city_ref=city):
            provisioned.city_ref = None
            provisioned.save(using=CATALOG, update_fields=["city_ref"])
        source = register_source(
            actor=ACTOR,
            name="An empty calendar",
            source_type="venue",
            url="https://feeds.example.test/empty.ics",
            acquisition_method="ics",
            tz_coverage="none",
            city=CITY,
            city_ref=city,
        )
        return city, source

    def test_the_first_two_runs_leave_the_source_active(self):
        """The threshold is three. A test that only checked the end would pass with a
        threshold of one."""
        _city, source = self._source()
        port = ScriptedFetchPort().serve(ok(calendar()))

        ingest_source(source.id, fetch_port=port)
        assert source.status == Source.Status.ACTIVE

        ingest_source(source.id, fetch_port=port)
        source.refresh_from_db(using=CATALOG)
        assert source.status == Source.Status.ACTIVE
        assert _counter(source) == 2

    def test_the_third_run_pauses_the_source(self):
        city, source = self._source()
        port = ScriptedFetchPort().serve(ok(calendar()))

        for _ in range(3):
            ingest_source(source.id, fetch_port=port)

        source.refresh_from_db(using=CATALOG)
        assert source.status == Source.Status.PAUSED
        assert source.paused_reason == Source.PausedReason.ZERO_YIELD

    def test_the_city_ends_at_yielded_nothing(self):
        city, source = self._source()
        port = ScriptedFetchPort().serve(ok(calendar()))

        for _ in range(3):
            ingest_source(source.id, fetch_port=port)

        assert _status(city) == CityProvisioning.Status.YIELDED_NOTHING

    def test_the_source_is_not_deleted(self):
        """FR-13: sources are paused, never deleted."""
        city, source = self._source()
        port = ScriptedFetchPort().serve(ok(calendar()))

        for _ in range(3):
            ingest_source(source.id, fetch_port=port)

        assert Source.objects.using(CATALOG).filter(pk=source.pk).exists()

    def test_the_pause_is_audited(self):
        city, source = self._source()
        port = ScriptedFetchPort().serve(ok(calendar()))

        for _ in range(3):
            ingest_source(source.id, fetch_port=port)

        assert (
            IngestionAuditEntry.objects.using(CATALOG)
            .filter(action="pause_source", target_id=source.id)
            .count()
            == 1
        )

    def test_a_published_feed_makes_the_city_live_instead(self):
        """The other end of the same run: a feed with an event in it is `live`."""
        city, source = self._source()
        body = calendar(vevent("a@x", "20261105T193000"))

        ingest_source(source.id, fetch_port=ScriptedFetchPort().serve(body))

        assert _status(city) == CityProvisioning.Status.LIVE


class TestTheResumePath:
    """A `yielded_nothing` city is resumed by a later pick, not duplicated."""

    def test_a_re_pick_resumes_the_city(self):
        from apps.ingestion.services.city_provisioning import provision_city

        outcome = provision_city(city_name=CITY)
        city = City.objects.using(CATALOG).get(pk=outcome.city_id)
        provisioning = CityProvisioning.objects.using(CATALOG).get(city=city)
        provisioning.status = CityProvisioning.Status.YIELDED_NOTHING
        provisioning.save(using=CATALOG, update_fields=["status"])
        source = Source.objects.using(CATALOG).filter(city_ref=city).first()
        pause_source(actor=ACTOR, source_id=source.id, reason=Source.PausedReason.ZERO_YIELD)

        provision_city(city_name=CITY)

        provisioning.refresh_from_db(using=CATALOG)
        assert provisioning.status == CityProvisioning.Status.COLLECTING

    def test_a_re_pick_resumes_the_source_rather_than_duplicating_it(self):
        from apps.ingestion.services.city_provisioning import provision_city

        outcome = provision_city(city_name=CITY)
        city = City.objects.using(CATALOG).get(pk=outcome.city_id)
        provisioning = CityProvisioning.objects.using(CATALOG).get(city=city)
        provisioning.status = CityProvisioning.Status.YIELDED_NOTHING
        provisioning.save(using=CATALOG, update_fields=["status"])
        source = Source.objects.using(CATALOG).filter(city_ref=city).first()
        pause_source(actor=ACTOR, source_id=source.id, reason=Source.PausedReason.ZERO_YIELD)
        before = Source.objects.using(CATALOG).count()

        provision_city(city_name=CITY)

        assert Source.objects.using(CATALOG).count() == before
        source.refresh_from_db(using=CATALOG)
        assert source.status == Source.Status.ACTIVE

    def test_a_resumed_source_starts_its_probation_afresh(self):
        """Otherwise the next run would instantly re-pause it."""
        from apps.ingestion.services.city_provisioning import provision_city

        outcome = provision_city(city_name=CITY)
        city = City.objects.using(CATALOG).get(pk=outcome.city_id)
        provisioning = CityProvisioning.objects.using(CATALOG).get(city=city)
        provisioning.status = CityProvisioning.Status.YIELDED_NOTHING
        provisioning.save(using=CATALOG, update_fields=["status"])
        source = Source.objects.using(CATALOG).filter(city_ref=city).first()
        source.consecutive_zero_yield_runs = 3
        source.save(using=CATALOG, update_fields=["consecutive_zero_yield_runs"])
        pause_source(actor=ACTOR, source_id=source.id, reason=Source.PausedReason.ZERO_YIELD)

        provision_city(city_name=CITY)

        assert _counter(source) == 0

    def test_a_re_pick_backfills_the_city_ref(self):
        """A source registered before the column existed has no link — and the probation
        would never see it again."""
        from apps.ingestion.services.city_provisioning import provision_city

        outcome = provision_city(city_name=CITY)
        city = City.objects.using(CATALOG).get(pk=outcome.city_id)
        provisioning = CityProvisioning.objects.using(CATALOG).get(city=city)
        provisioning.status = CityProvisioning.Status.YIELDED_NOTHING
        provisioning.save(using=CATALOG, update_fields=["status"])
        source = Source.objects.using(CATALOG).filter(city_ref=city).first()
        source.city_ref = None
        source.save(using=CATALOG, update_fields=["city_ref"])

        provision_city(city_name=CITY)

        source.refresh_from_db(using=CATALOG)
        assert source.city_ref_id == city.id

    def test_a_re_pick_writes_a_resume_audit_row(self):
        from apps.ingestion.services.city_provisioning import provision_city

        outcome = provision_city(city_name=CITY)
        city = City.objects.using(CATALOG).get(pk=outcome.city_id)
        provisioning = CityProvisioning.objects.using(CATALOG).get(city=city)
        provisioning.status = CityProvisioning.Status.YIELDED_NOTHING
        provisioning.save(using=CATALOG, update_fields=["status"])

        provision_city(city_name=CITY)

        audit = IngestionAuditEntry.objects.using(CATALOG).filter(action="city.resumed").get()
        assert audit.details["city_id"] == str(city.id)
        assert "Portland" not in str(audit.details)

    def test_a_live_city_is_not_dragged_back_to_collecting(self):
        from apps.ingestion.services.city_provisioning import provision_city

        outcome = provision_city(city_name=CITY)
        city = City.objects.using(CATALOG).get(pk=outcome.city_id)
        provisioning = CityProvisioning.objects.using(CATALOG).get(city=city)
        provisioning.status = CityProvisioning.Status.LIVE
        provisioning.save(using=CATALOG, update_fields=["status"])

        provision_city(city_name=CITY)

        provisioning.refresh_from_db(using=CATALOG)
        assert provisioning.status == CityProvisioning.Status.LIVE

    def test_a_paused_city_stays_paused(self):
        """An editor's pause is not undone by a reader picking the city."""
        from apps.ingestion.services.city_provisioning import provision_city

        outcome = provision_city(city_name=CITY)
        city = City.objects.using(CATALOG).get(pk=outcome.city_id)
        provisioning = CityProvisioning.objects.using(CATALOG).get(city=city)
        provisioning.status = CityProvisioning.Status.PAUSED
        provisioning.save(using=CATALOG, update_fields=["status"])

        provision_city(city_name=CITY)

        provisioning.refresh_from_db(using=CATALOG)
        assert provisioning.status == CityProvisioning.Status.PAUSED


class TestTheRegistryRefusesAName:
    """`city_ref` is a link, not a text field."""

    def test_a_name_is_refused(self):
        with pytest.raises(TypeError):
            register_source(
                actor=ACTOR,
                name="Named",
                source_type="media",
                url="https://example.test/feed.ics",
                acquisition_method="ics",
                tz_coverage="none",
                city_ref="Portland, OR",  # type: ignore[arg-type]
            )

    def test_an_id_is_refused(self):
        with pytest.raises(TypeError):
            register_source(
                actor=ACTOR,
                name="Identified",
                source_type="media",
                url="https://example.test/feed2.ics",
                acquisition_method="ics",
                tz_coverage="none",
                city_ref=uuid7(),  # type: ignore[arg-type]
            )

    def test_the_link_is_not_in_the_audit_details(self):
        """Every `register_source` audit row has the same shape."""
        city, _provisioning, _sources = _provisioned_city()
        source = Source.objects.using(CATALOG).filter(city_ref=city).first()

        audit = (
            IngestionAuditEntry.objects.using(CATALOG)
            .filter(action="register_source", target_id=source.id)
            .get()
        )
        assert set(audit.details) == {"fields"}
        assert "city_ref" not in audit.details["fields"]


class TestTheOutcomeIsPlainData:
    """The outcome is not the model, and cannot be written back."""

    def test_the_outcome_is_frozen(self):
        outcome = ProbationOutcome(source_id=uuid7())

        with pytest.raises(FrozenInstanceError):
            outcome.paused = True  # type: ignore[misc]

    def test_the_outcome_does_not_expose_the_model(self):
        """A caller holding a `CityProvisioning` could write it; `ingestion` is its sole
        writer (AD-16)."""
        outcome = ProbationOutcome(source_id=uuid7())

        assert not hasattr(outcome, "save")
        assert not hasattr(outcome, "delete")
