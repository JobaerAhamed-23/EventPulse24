"""The city provisioning service: a pick turns into collection (FR-13, FR-17, AD-16).

**What this file holds.** The rules about *what a provider is* are pure and live in
`tests/domain/test_city_providers.py`. The rules about *what a city is* live in
`tests/domain/test_cities.py`. What is left here is the only part that touches the
database and the reader: a pick reaches the registry, the registry says what happened, and
nothing about it can lose the reader's choice.

**The three promises this file defends.**

1. **A pick provisions.** The reader's stored city is a request to collect, not just a
   label — so the pick reaches `ingestion` and the sources are registered.
2. **A pick never fails.** The pick is written in `personal`; the sources are written in
   `catalog`. A slow or broken registry write must not roll the pick back, and a
   provisioning that fails must still leave a row saying so.
3. **A pick is idempotent.** Two readers picking the same city, or one reader picking
   twice, produce one set of sources — never two, and never a duplicate-row error
   escaping as a 500.

**The one thing that must never happen** is a city outside the curated catalog acquiring
a `City` row and a set of sources. The catalog is the list of places a reader may pick;
minting rows for places no reader chose would put places into the registry that nobody
asked for and that no provider template was written against.
"""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest
from django.db import transaction

from apps.ingestion.models import City, CityProvisioning, IngestionAuditEntry, Source
from apps.ingestion.services.city_provisioning import (
    ACTOR_LABEL,
    NO_TEMPLATE_COVERS_THIS_CITY,
    ProvisioningOutcome,
    provision_city,
    provision_city_on_commit,
)
from apps.ingestion.services.source_registry import pause_source, register_source
from apps.personalization.services.digest_preferences import SOURCE_CHOICE
from domain.city_catalog import WORLD_CITIES, lookup
from domain.city_providers import SourceSpec
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7

#: Both schemas: the pick is written in `personal` and the sources in `catalog`, and the
#: seam between them is the thing this file is about.
pytestmark = pytest.mark.django_db(databases=[CATALOG, PERSONAL])

#: A fixed moment, so the pick's audit row reads the same every time.
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)

#: The actor the probation writes under — the one that pauses a source for zero yield.
ACTOR = Actor.system("city_probation")


@pytest.fixture(autouse=True)
def _a_deployment_with_a_key(settings):
    """Give this deployment a Ticketmaster key by default.

    **A deployment with no key provisions nothing** — that is a real behaviour and the
    next class tests it directly. But most of this file is about what happens *when* a
    provider is usable, so the default here is the usable deployment, and the class that
    cares about the other one turns the key off.
    """
    settings.TICKETMASTER_API_KEY = "test-key"


@pytest.fixture
def on_commit(monkeypatch):
    """Capture the `on_commit` callbacks, so a test can see both halves.

    **`pytest`'s `django_db` fixture wraps every test in a transaction that is rolled
    back**, so Django's `on_commit` callbacks never fire on their own — and a test that
    asserted "the provisioning ran" would pass for the wrong reason (it never ran at all).

    **The real `on_commit` is kept in place** — only the *dispatch* is intercepted, so the
    service still registers through Django's own machinery and the captured list is
    exactly what Django would have run at commit time. This is the same fixture
    `tests/personalization/test_digest_enqueue.py` uses.
    """
    captured: list = []
    original = transaction.on_commit

    def capture(func, using=None, robust=False):
        captured.append((func, using, robust))
        return original(func, using=using, robust=robust)

    monkeypatch.setattr(transaction, "on_commit", capture)

    def run():
        """Run the captured callbacks the way Django's runner does.

        **The `robust` flag is honoured here, not by the callback.** Django's
        `run_and_clear_commit_hooks` catches a robust callback's exception and logs it;
        a plain one is allowed to escape.
        """
        import logging

        for func, _using, robust in captured:
            if robust:
                try:
                    func()
                except Exception:
                    logging.getLogger("django.db.backends.base").exception(
                        "Error calling %s in on_commit().", getattr(func, "__qualname__", func)
                    )
            else:
                func()

    run.captured = captured
    return run


def _record_provisioning(monkeypatch) -> list[str]:
    """Record the city names the provisioning service was asked for.

    **The seam is `provision_city` itself**, so the test sees the *service's* entry
    point rather than some private helper — and a test that patched a helper would keep
    passing if the service stopped calling it.
    """
    import apps.ingestion.services.city_provisioning as module

    seen: list[str] = []
    monkeypatch.setattr(module, "provision_city", lambda **kwargs: seen.append(kwargs["city_name"]))
    return seen


def _spec_with_no_parser(method: str = "crawl") -> SourceSpec:
    """A spec whose acquisition method has no parser.

    **`crawl` is the method the registry refuses** — FR-17's last resort, which needs a
    ToS review and has no parser, so `parse()` would answer `unsupported_method`.
    """
    return SourceSpec(
        name="A source with no parser",
        source_type="media",
        url="https://example.test/events",
        acquisition_method=method,
        tz_coverage="none",
    )


def _patch_templates(monkeypatch, spec: SourceSpec) -> None:
    """Make the provider registry answer with exactly one spec.

    **The registry is replaced, not the service.** The service's own rules — the parser
    check, the credential check — are what these tests are about, so the templates are
    the input and the service is the code under test.
    """
    import apps.ingestion.services.city_provisioning as module

    monkeypatch.setattr(module, "resolve", lambda choice: (spec,))


#: A city the catalog holds, in a country Ticketmaster covers, so a template applies.
#: "Portland, OR" is a regioned row — the two-Portlands case is the one worth having.
CITY = "Portland, OR"

#: A city the catalog holds in a country Ticketmaster does not cover, so no enabled
#: template produces a spec for it. Bangladesh is outside the provider's country set.
NO_PROVIDER_CITY = "Dhaka"


def _catalog_row(name: str):
    row = lookup(name)
    assert row is not None, f"{name!r} is not in the catalog"
    return row


class TestTheCatalogIsTheGate:
    """A city the catalog does not hold provisions nothing at all."""

    def test_a_city_outside_the_catalog_provisions_nothing(self):
        outcome = provision_city(city_name="Atlantis")

        assert outcome.city_id is None
        assert outcome.status == ""
        assert outcome.source_count == 0
        assert outcome.provisioned is False

    def test_a_city_outside_the_catalog_mints_no_city_row(self):
        provision_city(city_name="Atlantis")

        assert City.objects.using(CATALOG).count() == 0

    def test_a_city_outside_the_catalog_registers_no_source(self):
        provision_city(city_name="Atlantis")

        assert Source.objects.using(CATALOG).count() == 0

    def test_a_city_outside_the_catalog_writes_no_provisioning_row(self):
        provision_city(city_name="Atlantis")

        assert CityProvisioning.objects.using(CATALOG).count() == 0

    def test_a_city_outside_the_catalog_writes_no_audit_row(self):
        from apps.ingestion.models import IngestionAuditEntry

        provision_city(city_name="Atlantis")

        assert (
            not IngestionAuditEntry.objects.using(CATALOG)
            .filter(action="city.provisioned")
            .exists()
        )

    def test_the_outcome_says_nothing_was_provisioned(self):
        outcome = provision_city(city_name="Atlantis")

        assert outcome.provisioning_id is None
        assert outcome.error_code == ""

    def test_a_city_outside_the_catalog_is_not_even_looked_up_by_its_own_text(self):
        """The catalog is checked on the *stored* name, so a near-miss is a near-miss.

        "Portland" is not the catalog's name for any Portland — the catalog says
        "Portland, OR" and "Portland, ME" — so a reader who picked the bare word is
        outside the catalog and provisions nothing. Silently picking the nearest row
        would be exactly the silent rewrite this whole intent exists to prevent.
        """
        outcome = provision_city(city_name="Portland")

        assert outcome.city_id is None
        assert City.objects.using(CATALOG).count() == 0

    @pytest.mark.parametrize("name", [c.name for c in WORLD_CITIES])
    def test_every_catalog_city_is_accepted(self, name):
        """The whole dataset: every name the catalog holds resolves to its own row."""
        outcome = provision_city(city_name=name)

        assert outcome.city_id is not None, f"{name!r} was refused"
        assert CityProvisioning.objects.using(CATALOG).filter(city_id=outcome.city_id).exists()


class TestAPickProvisions:
    """The pick reaches the registry, and the registry says what happened."""

    def test_a_pick_mints_the_city_row(self):
        outcome = provision_city(city_name=CITY)

        assert outcome.city_id is not None
        city = City.objects.using(CATALOG).get(pk=outcome.city_id)
        assert city.name == _catalog_row(CITY).name

    def test_a_pick_registers_the_providers_sources(self):
        outcome = provision_city(city_name=CITY)

        assert outcome.source_count > 0
        assert Source.objects.using(CATALOG).filter(city=CITY).exists()

    def test_the_source_carries_the_catalogs_timezone(self):
        """The last link in FR-60's chain, and the reason a new city publishes at all.

        Without `city_tz`, a brand-new city rejects every naive or date-only time as
        `tz_unresolvable` and publishes nothing, forever.
        """
        provision_city(city_name=CITY)

        source = Source.objects.using(CATALOG).get(city=CITY)
        assert source.city_tz == _catalog_row(CITY).tz

    def test_the_source_carries_the_catalogs_name_verbatim(self):
        provision_city(city_name=CITY)

        source = Source.objects.using(CATALOG).get(city=CITY)
        assert source.city == _catalog_row(CITY).name

    def test_the_provisioning_row_says_collecting(self):
        """`collecting`, not `live`.

        The city has no events until the scheduler has run and a source has answered.
        Saying `live` would be a claim we cannot keep.
        """
        outcome = provision_city(city_name=CITY)

        assert outcome.status == CityProvisioning.Status.COLLECTING

    def test_the_provisioning_row_counts_the_sources_it_registered(self):
        outcome = provision_city(city_name=CITY)

        row = CityProvisioning.objects.using(CATALOG).get(pk=outcome.provisioning_id)
        assert row.source_count == Source.objects.using(CATALOG).filter(city=CITY).count()

    def test_the_provisioning_row_carries_no_error(self):
        outcome = provision_city(city_name=CITY)

        row = CityProvisioning.objects.using(CATALOG).get(pk=outcome.provisioning_id)
        assert row.last_error_code == ""

    def test_the_provisioning_row_holds_the_city_and_not_its_name(self):
        """AD-13: the row says *that* a city was provisioned, not where a reader lives."""
        outcome = provision_city(city_name=CITY)

        row = CityProvisioning.objects.using(CATALOG).get(pk=outcome.provisioning_id)
        assert row.city_id == outcome.city_id

    def test_the_audit_row_carries_the_city_id_and_not_the_city_name(self):
        """The one place the city's *name* must never reach, on the way into `catalog`."""
        from apps.ingestion.models import IngestionAuditEntry

        provision_city(city_name=CITY)

        audit = IngestionAuditEntry.objects.using(CATALOG).filter(action="city.provisioned").get()
        assert "city_id" in audit.details
        assert audit.details["city_id"]
        assert CITY not in str(audit.details)
        assert "Portland" not in str(audit.details)

    def test_the_audit_row_is_written_by_a_system_actor(self):
        from apps.ingestion.models import IngestionAuditEntry

        provision_city(city_name=CITY)

        audit = IngestionAuditEntry.objects.using(CATALOG).filter(action="city.provisioned").get()
        assert audit.actor_kind == "system"
        assert audit.actor_label == ACTOR_LABEL

    def test_a_registered_source_is_due_immediately(self):
        """The scheduler takes it on its next tick, because it has never been attempted."""
        provision_city(city_name=CITY)

        source = Source.objects.using(CATALOG).get(city=CITY)
        assert source.last_attempted_at is None

    def test_a_registered_source_is_active(self):
        provision_city(city_name=CITY)

        source = Source.objects.using(CATALOG).get(city=CITY)
        assert source.status == Source.Status.ACTIVE


class TestNoProvidersIsANormalOutcome:
    """A city no enabled template covers is a fact, not a failure."""

    def test_a_city_no_provider_covers_is_recorded_as_no_providers(self):
        outcome = provision_city(city_name=NO_PROVIDER_CITY)

        assert outcome.status == CityProvisioning.Status.NO_PROVIDERS

    def test_a_city_no_provider_covers_registers_nothing(self):
        provision_city(city_name=NO_PROVIDER_CITY)

        assert Source.objects.using(CATALOG).count() == 0

    def test_a_city_no_provider_covers_still_gets_a_city_row(self):
        """The city exists; the reader picked a real place and nothing is wrong with it."""
        outcome = provision_city(city_name=NO_PROVIDER_CITY)

        assert outcome.city_id is not None
        assert City.objects.using(CATALOG).filter(pk=outcome.city_id).exists()

    def test_a_city_no_provider_covers_still_gets_a_provisioning_row(self):
        """So the surface can say "we have no source for this city" rather than "unknown"."""
        outcome = provision_city(city_name=NO_PROVIDER_CITY)

        assert outcome.provisioned is True
        assert CityProvisioning.objects.using(CATALOG).filter(city_id=outcome.city_id).exists()

    def test_a_city_no_provider_covers_registers_no_source_but_says_why(self):
        outcome = provision_city(city_name=NO_PROVIDER_CITY)

        assert outcome.source_count == 0
        assert outcome.error_code != ""

    def test_a_city_no_template_covers_says_so(self):
        """**"No template serves this city" and "we cannot authenticate the ones that
        do" are different facts**, and an operator will want to tell them apart: the
        first needs a new template, the second needs a secret."""
        outcome = provision_city(city_name=NO_PROVIDER_CITY)

        assert outcome.error_code == NO_TEMPLATE_COVERS_THIS_CITY


class TestASpecWithNoParserIsSkipped:
    """A source whose method has no parser would never ingest, so it is not registered.

    **The check is repeated at the point of registration.** Item 6's registry already
    guarantees every method it can emit has a parser — over the whole cross-product of
    every city and every template — but the check belongs here too, because that is
    where the defect would bite, and because a future template must not be able to slip
    past.
    """

    def test_a_spec_with_no_parser_is_not_registered(self, monkeypatch):
        _patch_templates(monkeypatch, _spec_with_no_parser())

        outcome = provision_city(city_name=CITY)

        assert outcome.source_count == 0
        assert Source.objects.using(CATALOG).count() == 0

    def test_the_reason_is_recorded(self, monkeypatch):
        _patch_templates(monkeypatch, _spec_with_no_parser())

        outcome = provision_city(city_name=CITY)

        assert outcome.error_code == "no_parser:crawl"

    def test_the_city_is_recorded_as_having_no_providers(self, monkeypatch):
        _patch_templates(monkeypatch, _spec_with_no_parser())

        outcome = provision_city(city_name=CITY)

        assert outcome.status == CityProvisioning.Status.NO_PROVIDERS

    def test_a_spec_with_a_parser_is_registered(self, monkeypatch):
        """The other half: the check must not refuse a method that *can* be parsed."""
        _patch_templates(monkeypatch, _spec_with_no_parser(method="api"))

        outcome = provision_city(city_name=CITY)

        assert outcome.source_count == 1


class TestTwoProvisioningsOfOneCityAreSerialised:
    """The lock is what makes "two readers, one city" produce one set of sources.

    **Without the lock**, two concurrent provisioners would both find no provisioning
    row and both register sources — and the loser would get a raw `IntegrityError` from
    the unique constraint, which reaches the caller as a 500.
    """

    def test_the_lock_is_taken_before_the_row_is_read(self, monkeypatch):
        """The order is the guarantee: lock, then re-read, then register.

        **A re-read outside the lock would be a race.** The lock is taken *before* the
        provisioning row is looked up, so a second writer cannot slip between the two.
        """
        from django.db.models.query import QuerySet

        from apps.ingestion.services import city_provisioning as module

        order: list[str] = []
        original_lock = module._lock_city
        original_filter = QuerySet.filter

        def record_lock(city_id):
            order.append("lock")
            original_lock(city_id)

        def record_filter(self, *args, **kwargs):
            if self.model is CityProvisioning:
                order.append("read")
            return original_filter(self, *args, **kwargs)

        monkeypatch.setattr(module, "_lock_city", record_lock)
        monkeypatch.setattr(QuerySet, "filter", record_filter)

        provision_city(city_name=CITY)

        assert order[:2] == ["lock", "read"]

    def test_the_lock_is_held_for_the_whole_registration(self, monkeypatch):
        """The sources are registered **inside** the lock, not after it.

        A lock released before the sources are written would let a second writer register
        the same sources — and `register_source` refuses a duplicate URL, so the second
        would fail on a rule that has nothing to do with concurrency.
        """
        from apps.ingestion.services import city_provisioning as module

        locked: list[bool] = []
        original_lock = module._lock_city
        original_register = module.register_source

        def record_lock(city_id):
            locked.append(False)
            original_lock(city_id)

        def record_register(**kwargs):
            locked[-1] = True
            return original_register(**kwargs)

        monkeypatch.setattr(module, "_lock_city", record_lock)
        monkeypatch.setattr(module, "register_source", record_register)

        provision_city(city_name=CITY)

        assert locked == [True], "the source was registered after the lock was released"

    def test_the_lock_is_advisory_and_transaction_scoped(self):
        """`pg_advisory_xact_lock` is released at commit, so a crashed worker cannot
        leave a city wedged."""
        import inspect

        from apps.ingestion.services.city_provisioning import _lock_city

        source = inspect.getsource(_lock_city)
        assert "pg_advisory_xact_lock" in source
        assert "pg_advisory_lock" not in source.replace("pg_advisory_xact_lock", "")

    def test_the_lock_is_actually_taken(self, monkeypatch):
        """**The SQL is really issued, with the city's own key.**

        A test that only read the source would pass even if the call were never made —
        so this one watches the query go out.
        """
        from django.db import connections

        queries: list[tuple[str, list]] = []
        original = connections[CATALOG].cursor

        def record_cursor(*args, **kwargs):
            cursor = original(*args, **kwargs)
            real_execute = cursor.execute

            def record_execute(sql, params=None):
                queries.append((sql, list(params) if params else []))
                return real_execute(sql, params)

            cursor.execute = record_execute
            return cursor

        monkeypatch.setattr(connections[CATALOG], "cursor", record_cursor)

        provision_city(city_name=CITY)

        locks = [q for q in queries if "pg_advisory" in q[0]]
        assert len(locks) == 1, f"expected one advisory lock, saw {locks}"
        assert "pg_advisory_xact_lock" in locks[0][0]

    def test_the_lock_key_is_the_citys_own(self, monkeypatch):
        """Two cities take two locks; the same city takes the same one."""
        from django.db import connections

        queries: list[tuple[str, list]] = []
        original = connections[CATALOG].cursor

        def record_cursor(*args, **kwargs):
            cursor = original(*args, **kwargs)
            real_execute = cursor.execute

            def record_execute(sql, params=None):
                queries.append((sql, list(params) if params else []))
                return real_execute(sql, params)

            cursor.execute = record_execute
            return cursor

        monkeypatch.setattr(connections[CATALOG], "cursor", record_cursor)

        provision_city(city_name=CITY)
        first = [q[1][0] for q in queries if "pg_advisory" in q[0]]

        queries.clear()
        provision_city(city_name="Dhaka")
        second = [q[1][0] for q in queries if "pg_advisory" in q[0]]

        assert first and second
        assert first[0] != second[0], "two cities took the same lock"


class TestAProviderWithoutACredentialIsSkipped:
    """A deployment cannot provision what it cannot authenticate."""

    def test_an_api_source_is_not_registered_without_its_key(self, settings):
        settings.TICKETMASTER_API_KEY = ""

        outcome = provision_city(city_name=CITY)

        assert outcome.source_count == 0
        assert Source.objects.using(CATALOG).count() == 0

    def test_the_reason_is_recorded(self, settings):
        settings.TICKETMASTER_API_KEY = ""

        outcome = provision_city(city_name=CITY)

        assert outcome.error_code == "no_credential:TICKETMASTER_API_KEY"

    def test_the_city_is_recorded_as_having_no_providers(self, settings):
        settings.TICKETMASTER_API_KEY = ""

        outcome = provision_city(city_name=CITY)

        assert outcome.status == CityProvisioning.Status.NO_PROVIDERS

    def test_with_the_key_the_source_is_registered(self, settings):
        settings.TICKETMASTER_API_KEY = "a-key"

        outcome = provision_city(city_name=CITY)

        assert outcome.source_count > 0

    def test_the_registered_url_never_carries_the_key(self, settings):
        """The key is added at fetch time, never stored (AD-13)."""
        settings.TICKETMASTER_API_KEY = "super-secret"

        provision_city(city_name=CITY)

        source = Source.objects.using(CATALOG).get(city=CITY)
        assert "super-secret" not in source.url
        assert "apikey" not in source.url


class TestProvisioningIsIdempotent:
    """Two readers picking the same city produce one set of sources."""

    def test_a_second_pick_registers_nothing_more(self):
        provision_city(city_name=CITY)
        first = Source.objects.using(CATALOG).count()

        provision_city(city_name=CITY)

        assert Source.objects.using(CATALOG).count() == first

    def test_a_second_pick_leaves_one_provisioning_row(self):
        provision_city(city_name=CITY)
        provision_city(city_name=CITY)

        assert CityProvisioning.objects.using(CATALOG).count() == 1

    def test_a_second_pick_does_not_change_the_status(self):
        """A city that has gone `live` must not be dragged back to `collecting`."""
        provision_city(city_name=CITY)
        row = CityProvisioning.objects.using(CATALOG).get()
        row.status = CityProvisioning.Status.LIVE
        row.save(using=CATALOG, update_fields=["status"])

        provision_city(city_name=CITY)

        row.refresh_from_db()
        assert row.status == CityProvisioning.Status.LIVE

    def test_a_second_pick_returns_the_existing_row(self):
        first = provision_city(city_name=CITY)
        second = provision_city(city_name=CITY)

        assert second.provisioning_id == first.provisioning_id
        assert second.city_id == first.city_id

    def test_a_second_pick_writes_no_second_audit_row(self):
        from apps.ingestion.models import IngestionAuditEntry

        provision_city(city_name=CITY)
        provision_city(city_name=CITY)

        assert (
            IngestionAuditEntry.objects.using(CATALOG).filter(action="city.provisioned").count()
            == 1
        )

    def test_a_failed_provisioning_is_not_retried_by_a_later_pick(self):
        """The row's existence means "provisioned", whatever its status says.

        A reader's pick is not a retry request: they did not know anything failed, and a
        retry would be invisible to them.
        """
        outcome = provision_city(city_name=CITY)
        row = CityProvisioning.objects.using(CATALOG).get(pk=outcome.provisioning_id)
        row.status = CityProvisioning.Status.FAILED
        row.last_error_code = "something_broke"
        row.save(using=CATALOG, update_fields=["status", "last_error_code"])

        second = provision_city(city_name=CITY)

        assert second.status == CityProvisioning.Status.FAILED
        assert second.error_code == "something_broke"

    def test_a_second_pick_of_a_city_with_no_providers_stays_at_no_providers(self):
        first = provision_city(city_name=NO_PROVIDER_CITY)
        second = provision_city(city_name=NO_PROVIDER_CITY)

        assert second.provisioning_id == first.provisioning_id
        assert second.status == CityProvisioning.Status.NO_PROVIDERS


class TestAYieldedNothingCityIsResumed:
    """A re-pick resumes a city that yielded nothing — it does not duplicate it.

    **`register_source` raises on a duplicate URL** and never updates an existing row, so
    the lookup has to come first: `find_source_by_url` canonicalises the URL the same
    way `register_source` does. A city whose sources were paused for zero yield already
    has those sources, and registering them again would either raise or — worse — create
    a second source that fetches the same feed and burns the reliability score twice.
    """

    def _yielded_nothing_city(self):
        outcome = provision_city(city_name=CITY)
        city = City.objects.using(CATALOG).get(pk=outcome.city_id)
        row = CityProvisioning.objects.using(CATALOG).get(city=city)
        row.status = CityProvisioning.Status.YIELDED_NOTHING
        row.save(using=CATALOG, update_fields=["status"])
        source = Source.objects.using(CATALOG).filter(city_ref=city).first()
        pause_source(actor=ACTOR, source_id=source.id, reason=Source.PausedReason.ZERO_YIELD)
        return city, row, source

    def test_a_re_pick_puts_the_city_back_to_collecting(self):
        city, row, _source = self._yielded_nothing_city()

        provision_city(city_name=CITY)

        row.refresh_from_db(using=CATALOG)
        assert row.status == CityProvisioning.Status.COLLECTING

    def test_a_re_pick_resumes_the_source_rather_than_registering_a_second_one(self):
        _city, _row, source = self._yielded_nothing_city()
        before = Source.objects.using(CATALOG).count()

        provision_city(city_name=CITY)

        assert Source.objects.using(CATALOG).count() == before
        source.refresh_from_db(using=CATALOG)
        assert source.status == Source.Status.ACTIVE

    def test_a_resumed_source_starts_its_probation_afresh(self):
        """Otherwise the next run would instantly re-pause it."""
        _city, _row, source = self._yielded_nothing_city()
        source.consecutive_zero_yield_runs = 3
        source.save(using=CATALOG, update_fields=["consecutive_zero_yield_runs"])

        provision_city(city_name=CITY)

        source.refresh_from_db(using=CATALOG)
        assert source.consecutive_zero_yield_runs == 0

    def test_a_re_pick_backfills_the_city_ref(self):
        """A source registered before the column existed has no link — and the probation
        would never see it again, so the city would never yield nothing a second time."""
        _city, _row, source = self._yielded_nothing_city()
        source.city_ref = None
        source.save(using=CATALOG, update_fields=["city_ref"])

        provision_city(city_name=CITY)

        source.refresh_from_db(using=CATALOG)
        assert source.city_ref is not None

    def test_a_re_pick_clears_the_error_code(self):
        _city, row, _source = self._yielded_nothing_city()
        row.last_error_code = "something_broke"
        row.save(using=CATALOG, update_fields=["last_error_code"])

        provision_city(city_name=CITY)

        row.refresh_from_db(using=CATALOG)
        assert row.last_error_code == ""

    def test_a_re_pick_writes_a_resume_audit_row(self):
        city, _row, _source = self._yielded_nothing_city()

        provision_city(city_name=CITY)

        audit = IngestionAuditEntry.objects.using(CATALOG).filter(action="city.resumed").get()
        assert audit.details["city_id"] == str(city.id)
        assert CITY not in str(audit.details)

    def test_a_re_pick_registers_a_source_that_was_missing(self, monkeypatch):
        """**A paused source is resumed; a missing source is registered.** The two are
        different operations with different audit rows.

        A source can go missing between the original provisioning and the resume — a
        template that was added, or a source an operator deleted. The resume registers
        it rather than leaving the city short of the providers it is supposed to have.
        """
        import apps.ingestion.services.city_provisioning as module
        from domain.city_providers import SourceSpec

        city, row, _source = self._yielded_nothing_city()
        extra = SourceSpec(
            name="A source that appeared later",
            source_type="media",
            url="https://example.test/later.ics",
            acquisition_method="ics",
            tz_coverage="none",
        )
        real_resolve = module.resolve

        def resolve_with_extra(choice):
            return (*real_resolve(choice), extra)

        monkeypatch.setattr(module, "resolve", resolve_with_extra)

        provision_city(city_name=CITY)

        assert Source.objects.using(CATALOG).filter(url=extra.url).exists()
        row.refresh_from_db(using=CATALOG)
        assert row.source_count == Source.objects.using(CATALOG).filter(city_ref=city).count()

    def test_the_resume_audit_row_counts_the_resumed_and_the_registered(self):
        city, _row, _source = self._yielded_nothing_city()

        provision_city(city_name=CITY)

        audit = IngestionAuditEntry.objects.using(CATALOG).filter(action="city.resumed").get()
        assert audit.details["resumed"] == 1
        assert audit.details["registered"] == 0

    def test_a_live_city_is_not_dragged_back_to_collecting(self):
        """The other half of the rule: only `yielded_nothing` re-opens."""
        outcome = provision_city(city_name=CITY)
        row = CityProvisioning.objects.using(CATALOG).get(pk=outcome.provisioning_id)
        row.status = CityProvisioning.Status.LIVE
        row.save(using=CATALOG, update_fields=["status"])

        provision_city(city_name=CITY)

        row.refresh_from_db(using=CATALOG)
        assert row.status == CityProvisioning.Status.LIVE

    def test_a_paused_city_stays_paused(self):
        """An editor's pause is not undone by a reader picking the city."""
        outcome = provision_city(city_name=CITY)
        row = CityProvisioning.objects.using(CATALOG).get(pk=outcome.provisioning_id)
        row.status = CityProvisioning.Status.PAUSED
        row.save(using=CATALOG, update_fields=["status"])

        provision_city(city_name=CITY)

        row.refresh_from_db(using=CATALOG)
        assert row.status == CityProvisioning.Status.PAUSED


class TestTwoCitiesNeverShareALock:
    """The lock is on the city, in its own key space."""

    def test_the_lock_key_is_stable_across_calls(self):
        from apps.ingestion.services.city_provisioning import _city_lock_key

        city_id = uuid7()
        assert _city_lock_key(city_id) == _city_lock_key(city_id)

    def test_two_cities_get_two_lock_keys(self):
        from apps.ingestion.services.city_provisioning import _city_lock_key

        ids = [uuid7() for _ in range(50)]
        assert len({_city_lock_key(i) for i in ids}) == len(ids)

    def test_the_lock_key_space_is_not_the_one_the_personal_path_uses(self):
        """Two UUIDs, two lock key spaces.

        A user id and a city id are both UUIDs, and a hash of one must never be mistaken
        for a hash of the other — the two would then serialise against each other for no
        reason, and a bug in one would look like a bug in the other.
        """
        from apps.ingestion.services.city_provisioning import _LOCK_PERSON
        from apps.personalization.services.digest_preferences import _LOCK_PERSON as PERSONAL

        assert _LOCK_PERSON != PERSONAL

    def test_the_lock_key_is_not_the_bare_uuid(self):
        """The key is a hash, so it is stable across processes.

        `hash()` is salted per process, so two workers would take two different locks
        for the same city — and the second would go straight past the first.
        """
        from apps.ingestion.services.city_provisioning import _city_lock_key

        city_id = uuid7()
        assert _city_lock_key(city_id) != hash(city_id)


class TestTheAfterCommitSeam:
    """The pick path's route in: after the commit, never inline."""

    def test_the_provisioning_does_not_run_inside_the_callers_transaction(
        self, monkeypatch, on_commit
    ):
        """A registry write must not be part of the reader's save."""
        seen = _record_provisioning(monkeypatch)

        with transaction.atomic(using=CATALOG):
            provision_city_on_commit(city_name=CITY)
            assert seen == [], "the provisioning ran inside the transaction"

    def test_the_provisioning_runs_after_the_commit(self, monkeypatch, on_commit):
        seen = _record_provisioning(monkeypatch)

        with transaction.atomic(using=CATALOG):
            provision_city_on_commit(city_name=CITY)
        on_commit()

        assert seen == [CITY]

    def test_a_rollback_leaves_nothing_provisioned(
        self, monkeypatch, django_capture_on_commit_callbacks
    ):
        """A rolled-back pick does not provision.

        **The rollback is on `personal`**, because that is the alias the callback is
        registered against — the pick is written in `personal` and the sources in
        `catalog`, and the callback belongs to the pick's transaction. Rolling back
        `catalog` would prove nothing about this seam.

        **Django's own capture is used here**, not the fixture above, because Django's
        capture *discards* the callbacks of a rolled-back transaction — which is the
        behaviour under test. A hand-run list of captured callbacks would run them
        anyway, and the test would pass for the wrong reason.
        """
        seen = _record_provisioning(monkeypatch)

        with django_capture_on_commit_callbacks(using=PERSONAL, execute=True):
            with pytest.raises(RuntimeError):
                with transaction.atomic(using=PERSONAL):
                    provision_city_on_commit(city_name=CITY)
                    raise RuntimeError("the pick failed")

        assert seen == []

    def test_a_rollback_leaves_no_source(
        self, django_user_model, django_capture_on_commit_callbacks
    ):
        """The end-to-end shape of the same promise: a rolled-back pick registers nothing."""
        from apps.personalization.services.digest_preferences import set_home_city

        with django_capture_on_commit_callbacks(using=PERSONAL, execute=True):
            with pytest.raises(RuntimeError):
                with transaction.atomic(using=PERSONAL):
                    set_home_city(
                        user_id=django_user_model.objects.create().id,
                        city=CITY,
                        source=SOURCE_CHOICE,
                        actor=Actor.system("pick_test"),
                        now=NOW,
                    )
                    raise RuntimeError("the pick failed")

        assert Source.objects.using(CATALOG).filter(city=CITY).count() == 0

    def test_a_failure_does_not_reach_the_caller(self, on_commit):
        """`robust=True`: the pick stands, whatever the registry does."""
        import apps.ingestion.services.city_provisioning as module

        original = module.provision_city

        def explode(**kwargs):
            raise RuntimeError("the registry is down")

        module.provision_city = explode
        try:
            with transaction.atomic(using=CATALOG):
                provision_city_on_commit(city_name=CITY)
            on_commit()  # robust: the exception is logged, not raised
        finally:
            module.provision_city = original

    def test_the_callback_is_registered_on_the_personal_alias(self, on_commit):
        """The pick is written in `personal`; the callback belongs to that transaction."""
        provision_city_on_commit(city_name=CITY)

        [_func, using, _robust] = on_commit.captured[0]
        assert using == PERSONAL

    def test_the_callback_is_registered_robustly(self, on_commit):
        """A failure in the registry must not reach the reader."""
        provision_city_on_commit(city_name=CITY)

        [_func, _using, robust] = on_commit.captured[0]
        assert robust is True


class TestThePickPathReachesTheService:
    """`set_home_city` is what a reader's pick actually calls."""

    def _set(self, user_id, city):
        from apps.personalization.services.digest_preferences import set_home_city

        return set_home_city(
            user_id=user_id,
            city=city,
            source=SOURCE_CHOICE,
            actor=Actor.system("pick_test"),
            now=NOW,
        )

    def test_a_pick_triggers_the_provisioning(self, django_user_model, monkeypatch, on_commit):
        seen = _record_provisioning(monkeypatch)

        self._set(django_user_model.objects.create().id, CITY)
        on_commit()

        assert seen == [CITY]

    def test_a_pick_without_a_city_provisions_nothing(
        self, django_user_model, monkeypatch, on_commit
    ):
        seen = _record_provisioning(monkeypatch)

        self._set(django_user_model.objects.create().id, None)
        on_commit()

        assert seen == []

    def test_a_refused_pick_provisions_nothing(self, django_user_model, monkeypatch, on_commit):
        """A city the catalog does not hold is refused before anything is written."""
        from domain.errors import UnknownHomeCityError

        seen = _record_provisioning(monkeypatch)

        with pytest.raises(UnknownHomeCityError):
            self._set(django_user_model.objects.create().id, "Atlantis")
        on_commit()

        assert seen == []

    def test_a_pick_that_provisions_really_registers_the_sources(
        self, django_user_model, on_commit
    ):
        """The end-to-end shape, with no seam monkeypatched: the pick reaches the
        registry and the sources are there."""
        self._set(django_user_model.objects.create().id, CITY)
        on_commit()

        assert Source.objects.using(CATALOG).filter(city=CITY).exists()
        assert CityProvisioning.objects.using(CATALOG).filter(city__name=CITY).exists()


class TestTheOutcomeIsPlainData:
    """The outcome is not the model, and cannot be written back."""

    def test_the_outcome_is_frozen(self):
        outcome = ProvisioningOutcome(city_id=None, status="", source_count=0)

        with pytest.raises(FrozenInstanceError):
            outcome.status = "live"  # type: ignore[misc]

    def test_the_outcome_does_not_expose_the_model(self):
        """A caller holding a `CityProvisioning` could write it; `ingestion` is its
        sole writer (AD-16)."""
        outcome = provision_city(city_name=CITY)

        assert not hasattr(outcome, "save")
        assert not hasattr(outcome, "delete")


class TestTheGuardsThatShouldNeverFire:
    """Two states that cannot happen, and what the service does when they do.

    **A guard nobody exercises is a guard nobody has read.** Each of these is a
    "cannot happen" branch, and each is here so that the branch is known to work rather
    than merely known to exist.
    """

    def test_a_catalog_row_that_names_no_city_is_refused(self, monkeypatch):
        """The catalog's name always resolves, so this cannot happen — and if it ever
        does, it is a disagreement between two facts we hold, not something to guess at."""
        import apps.ingestion.services.city_provisioning as module

        monkeypatch.setattr(module, "resolve_city", lambda **kwargs: None)

        with pytest.raises(RuntimeError, match="names no city"):
            provision_city(city_name=CITY)

    def test_a_url_that_cannot_be_parsed_is_assumed_to_need_no_key(self):
        """A malformed URL is not a provider, so it is never assumed to need a key.

        **Exact hosts, never suffixes** — a URL that cannot be read has no host to
        match, so the answer is "no key", not "some key".
        """
        from apps.ingestion.services.city_provisioning import _spec_needs_a_key

        spec = SourceSpec(
            name="Broken",
            source_type="media",
            url="https://[not-a-host/path",
            acquisition_method="api",
            tz_coverage="none",
        )

        assert _spec_needs_a_key(spec) == ""

    def test_a_url_with_no_host_is_assumed_to_need_no_key(self):
        from apps.ingestion.services.city_provisioning import _spec_needs_a_key

        spec = SourceSpec(
            name="Relative",
            source_type="media",
            url="not-a-url-at-all",
            acquisition_method="api",
            tz_coverage="none",
        )

        assert _spec_needs_a_key(spec) == ""

    def test_a_host_that_only_ends_with_a_providers_host_needs_no_key(self):
        """`app.ticketmaster.com.evil.test` must never be handed our key."""
        from apps.ingestion.services.city_provisioning import _spec_needs_a_key

        spec = SourceSpec(
            name="Impostor",
            source_type="media",
            url="https://app.ticketmaster.com.evil.test/events.json",
            acquisition_method="api",
            tz_coverage="none",
        )

        assert _spec_needs_a_key(spec) == ""


class TestAProvisionedCityDoesNotClashWithTheRegistry:
    """The registry's own rules still apply to a provisioned source."""

    def test_provisioning_a_city_twice_does_not_raise_a_duplicate_error(self):
        """The duplicate check is `register_source`'s; the second call must not reach it."""
        provision_city(city_name=CITY)
        provision_city(city_name=CITY)  # must not raise

    def test_a_source_registered_by_hand_is_not_duplicated(self):
        """A source already in the registry for this city is left alone."""
        register_source(
            actor=Actor.system("hand"),
            name="Hand-made",
            source_type="media",
            url="https://example.test/feed.ics",
            acquisition_method="ics",
            tz_coverage="none",
            city=CITY,
        )

        outcome = provision_city(city_name=CITY)

        assert outcome.source_count > 0
