"""The coverage request: a reader asks us to cover a city we have not covered.

**What this file holds.** The command behind `POST /api/catalog/coverage-requests`: it
records that a reader wants a city covered, it does it **once per city**, it counts how
many readers have asked, and it writes an audit row that says which city and how many —
and nothing else.

**The three promises this file defends.**

1. **One row per city, and the database says so.** The constraint is the guarantee, not a
   promise the service makes — so the file asserts the *database* refuses the duplicate,
   by the constraint's name.
2. **A request never mints a city.** A request is for a city we have already tried to cover
   and failed to; a city we have never heard of is a *pick*, and a pick provisions. A
   request that minted would put a place into the registry that nobody chose.
3. **Nothing about the reader reaches the row.** No user id on the row, no city name in the
   audit `details`, no user id in the `details`. The count is a number; the city is an id.
"""

import logging
import uuid
from contextlib import contextmanager

import pytest
from django.db import IntegrityError, transaction

from apps.ingestion.models import City, CityCoverageRequest, IngestionAuditEntry
from apps.ingestion.services import coverage_requests as service
from apps.ingestion.services.coverage_requests import (
    COVERAGE_REQUEST_ACTION,
    read_coverage_request,
    request_coverage,
    throttle_key,
)
from domain.errors import ThrottledError, UnknownHomeCityError
from shared.actor import Actor
from shared.db import CATALOG

pytestmark = pytest.mark.django_db(databases=[CATALOG])

#: A city in the curated catalog.
CITY = "Portland, OR"

#: A reader who asks.
ACTOR = Actor.user(uuid.UUID("33333333-3333-3333-3333-333333333333"))


@pytest.fixture(autouse=True)
def throttle(monkeypatch):
    """A fresh in-memory throttle per test, with an injected clock.

    The adapter is swapped at the module that calls it, the way
    `tests/personalization/test_event_reports.py` does, so the limit is deterministic:
    no sleeping, no Redis, no shared counters between tests.
    """
    from adapters.throttle.memory import InMemoryThrottleAdapter

    clock = {"now": 1_000_000.0}
    adapter = InMemoryThrottleAdapter(now=lambda: clock["now"])
    monkeypatch.setattr(service, "get_throttle_port", lambda: adapter)
    return adapter


# --- helpers ---------------------------------------------------------------------------------


def _city(name: str = CITY, *, key: str = "", region: str = "", country: str = "US") -> City:
    """A `City` row, written directly.

    **The provisioning service is not used here** because this file is about the *request*,
    and the request must work for a city whose collection failed for any reason.
    """
    return City.objects.using(CATALOG).create(
        name=name,
        country_code=country,
        normalized_key=key or name.lower(),
        slug=f"slug-{name.lower().replace(' ', '-').replace(',', '')}",
        region=region,
    )


@contextmanager
def violates(constraint: str):
    """Expect the block to fail on exactly this named constraint (rolled back to a savepoint)."""
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic(using=CATALOG):
        yield
    assert excinfo.value.__cause__.diag.constraint_name == constraint


def _requests() -> list[CityCoverageRequest]:
    return list(CityCoverageRequest.objects.using(CATALOG).order_by("pk"))


def _audits() -> list[IngestionAuditEntry]:
    return list(IngestionAuditEntry.objects.using(CATALOG).order_by("pk"))


# --- the constraint ----------------------------------------------------------------------------


class TestTheDatabaseRefusesADuplicate:
    """The guarantee is in the schema, not in the service's good manners."""

    def test_a_second_row_for_the_same_city_is_refused(self):
        """**The AC's headline test.**

        The constraint is what makes "one request per city" a fact rather than a
        intention — a second writer that did not know about the first is stopped by
        PostgreSQL rather than by a code path somebody has to remember to write.
        """
        city = _city()
        CityCoverageRequest.objects.using(CATALOG).create(city=city, request_count=1)

        with violates("city_coverage_request_city_uq"):
            CityCoverageRequest.objects.using(CATALOG).create(city=city, request_count=1)

    def test_the_constraint_is_named(self):
        """The constraint's name is stable, so a test can assert *that* constraint refused.

        **An auto-named unique index could not be asserted by name** — and the AC asks
        for a test that the constraint actually rejects a duplicate, not merely that
        *something* rejected it.
        """
        names = {constraint.name for constraint in CityCoverageRequest._meta.constraints}
        assert "city_coverage_request_city_uq" in names

    def test_the_constraint_covers_the_city_alone(self):
        """**The constraint is on the city and on nothing else.**

        A unique constraint on `(city, request_count)` would also forbid a second row
        for the same city — but only when the count matched, so it would permit a
        second row for the same city at a different count. **That is not "one row per
        city"**, and the difference between the two is invisible to the test above:
        the constraint's *name* would still be there.

        **So the fields are asserted, not just the name.** A declared constraint and
        the database's are two different things — the migration is what built the
        database's — so this test pins the *declaration*, and the test above pins the
        *database*.
        """
        constraint = next(
            c
            for c in CityCoverageRequest._meta.constraints
            if c.name == "city_coverage_request_city_uq"
        )

        assert list(constraint.fields) == ["city"]

    def test_two_cities_may_each_have_a_request(self):
        """The constraint is one-per-*city*, not one-per-table."""
        first = _city(name="Portland, OR", key="portland", region="or")
        second = _city(name="Portland, ME", key="portland", region="me")

        CityCoverageRequest.objects.using(CATALOG).create(city=first, request_count=1)
        CityCoverageRequest.objects.using(CATALOG).create(city=second, request_count=1)

        assert len(_requests()) == 2


# --- the command -------------------------------------------------------------------------------


class TestTheRequestIsRecorded:
    """One row per city, and a count of how many readers asked."""

    def test_a_request_creates_one_row(self):
        """The first ask makes the row."""
        city = _city()

        outcome = request_coverage(city=city.name, actor=ACTOR)

        assert outcome.created is True
        assert outcome.city == city.name
        assert outcome.request_count == 1
        assert len(_requests()) == 1

    def test_a_second_request_does_not_create_a_second_row(self):
        """**The AC's idempotence, and the row is what it is about.**

        Two readers asking for Chittagong is two people wanting it covered — and it is
        still *one* request. The count is where the second reader lands.
        """
        city = _city()
        request_coverage(city=city.name, actor=ACTOR)

        outcome = request_coverage(city=city.name, actor=ACTOR)

        assert len(_requests()) == 1
        assert outcome.created is False
        assert outcome.request_count == 2

    def test_the_count_moves_up_with_every_reader(self):
        """The count is the number editorial prioritises on."""
        city = _city()
        request_coverage(city=city.name, actor=ACTOR)
        request_coverage(city=city.name, actor=ACTOR)
        request_coverage(city=city.name, actor=ACTOR)

        assert _requests()[0].request_count == 3

    def test_the_request_is_found_by_the_catalogs_own_name(self):
        """The lookup is on the canonical name — the form the picker stores."""
        city = _city(name="Portland, OR", key="portland", region="or")

        request_coverage(city="Portland, OR", actor=ACTOR)

        assert len(_requests()) == 1
        assert _requests()[0].city_id == city.id

    def test_the_request_is_found_by_the_identity_key_too(self):
        """A city minted by a *venue* carries the venue's spelling, not the catalog's.

        **The reader's stored city is the catalog's canonical form** — but the `City` row
        a venue minted carries whatever that venue wrote. So the lookup falls back to the
        identity key `domain.cities` computes, and the two spellings of one place are one
        city.
        """
        city = _city(name="Portland, Oregon", key="portland", region="or")

        request_coverage(city="Portland, OR", actor=ACTOR)

        assert len(_requests()) == 1
        assert _requests()[0].city_id == city.id

    def test_the_first_raised_time_does_not_move(self):
        """`created_at` answers "when did somebody first tell us about this city".

        **It must not move on a later request** — a timestamp that moved would answer
        "when did somebody last ask", which is a different question, and the editorial
        queue sorts on the first one.
        """
        city = _city()
        request_coverage(city=city.name, actor=ACTOR)
        first_raised = _requests()[0].created_at

        request_coverage(city=city.name, actor=ACTOR)

        row = _requests()[0]
        assert row.created_at == first_raised
        assert row.request_count == 2

    def test_the_read_finds_the_request(self):
        """The read is a read, and it answers the same question the command wrote."""
        city = _city()
        request_coverage(city=city.name, actor=ACTOR)

        found = read_coverage_request(city=city.name)

        assert found is not None
        assert found.city == city.name
        assert found.request_count == 1

    def test_the_read_finds_nothing_for_a_city_that_was_never_asked_for(self):
        """No request is an answer, not a failure."""
        _city()

        assert read_coverage_request(city=CITY) is None

    def test_the_read_finds_nothing_for_an_empty_city(self):
        """An empty name names no city, and the read does not go looking for one."""
        assert read_coverage_request(city="") is None

    def test_the_read_finds_nothing_for_a_name_that_normalises_to_nothing(self):
        """**Punctuation alone is not a place.**

        A lookup with an empty key would match *every* city whose `normalized_key` is
        empty — a different question from the one being asked.
        """
        assert read_coverage_request(city="!!!") is None


# --- a request never mints ---------------------------------------------------------------------


class TestTheRequestNeverMints:
    """A request that minted would put a place into the registry that nobody chose."""

    def test_a_request_for_an_unknown_city_is_refused(self):
        """**A city we have never heard of is a *pick*, not a request.**

        Picking it provisions it immediately, which is a better answer than queueing it.
        So the request is refused, and the reader is sent to the picker.
        """
        before = City.objects.using(CATALOG).count()

        with pytest.raises(UnknownHomeCityError):
            request_coverage(city="Nowhere, ZZ", actor=ACTOR)

        assert City.objects.using(CATALOG).count() == before

    def test_a_refused_request_writes_nothing(self):
        """No row, no count, no audit row — the refusal leaves nothing behind."""
        with pytest.raises(UnknownHomeCityError):
            request_coverage(city="Nowhere, ZZ", actor=ACTOR)

        assert _requests() == []
        assert _audits() == []

    def test_an_empty_city_is_refused(self):
        """An empty name names no city, and the request does not guess one."""
        with pytest.raises(UnknownHomeCityError):
            request_coverage(city="", actor=ACTOR)

    def test_a_name_that_normalises_to_nothing_is_refused(self):
        """Punctuation alone is not a place, and the lookup must not go looking for one.

        **`normalize_city` folds case, whitespace, punctuation and accents**, so a name
        made only of punctuation has no identity key at all. There is no city it could
        name, and a lookup with an empty key would match *every* city whose
        `normalized_key` is empty — a different question from the one being asked.
        """
        with pytest.raises(UnknownHomeCityError):
            request_coverage(city="!!!", actor=ACTOR)


# --- AD-13 ------------------------------------------------------------------------------------


class TestNothingAboutTheReaderReachesTheRow:
    """The row is about a place. The reader's id is not on it."""

    def test_the_row_carries_no_user_field(self):
        """**The model's own fields are the check** — not a runtime assertion.

        A `user_id` column would be a user id beside a city, which is the pairing AD-13
        is careful about. There is no such column, and there is no way to add one without
        this test noticing.
        """
        names = {field.name for field in CityCoverageRequest._meta.get_fields()}
        assert "user" not in names
        assert "user_id" not in names
        assert "requesting_user" not in names

    def test_the_audit_details_carry_the_city_id_and_the_count(self):
        """**The city *id*, never the city name.**

        The name is a location — a reader's city is weak location data about a real
        person — and the id is not. The count is the number editorial reads.
        """
        city = _city()
        request_coverage(city=city.name, actor=ACTOR)

        details = _audits()[0].details
        assert details == {"city_id": str(city.id), "request_count": 1}

    def test_the_audit_details_carry_no_city_name(self):
        """The name is not in the log, under any key."""
        city = _city()
        request_coverage(city=city.name, actor=ACTOR)

        details = _audits()[0].details
        assert city.name not in str(details)

    def test_the_audit_details_carry_no_user_id(self):
        """**The reader's id is on the audit row's `actor_id`, and nowhere else.**

        The `actor_id` is the codebase's own mechanism for recording who did a thing
        without pairing them with a place in the payload — every command and every admin
        action writes it. It is not a `details` field, and it is not a log line.
        """
        city = _city()
        request_coverage(city=city.name, actor=ACTOR)

        details = _audits()[0].details
        assert str(ACTOR.id) not in str(details)

    def test_the_command_writes_no_log_line(self, caplog):
        """There is nothing to leak, because there is no log line at all.

        A city name in a log line would be a location in a sink that crosses into the
        catalog. **The command does not log**, so the question does not arise — and this
        is the assertion that would notice the day somebody added a `logger.info`.
        """
        city = _city()
        with caplog.at_level(logging.DEBUG):
            request_coverage(city=city.name, actor=ACTOR)

        assert caplog.records == []


# --- the audit ---------------------------------------------------------------------------------


class TestTheAuditRow:
    """One audit row per request, in the same transaction as the row."""

    def test_a_request_writes_one_audit_row(self):
        city = _city()

        request_coverage(city=city.name, actor=ACTOR)

        audits = _audits()
        assert len(audits) == 1
        assert audits[0].action == COVERAGE_REQUEST_ACTION
        assert audits[0].target_type == "CityCoverageRequest"

    def test_a_repeat_writes_another_audit_row(self):
        """**Every ask is audited, not only the first.**

        The row did not change shape — but somebody asked again, and the audit trail is
        how editorial would see that a city is being asked for more and more.
        """
        city = _city()
        request_coverage(city=city.name, actor=ACTOR)

        request_coverage(city=city.name, actor=ACTOR)

        assert len(_audits()) == 2

    def test_the_audit_row_and_the_request_roll_back_together(self):
        """AD-5: the audit row is written in the mutation's transaction.

        **A command that failed must leave no audit row**, or the log would claim
        something that did not happen.
        """
        city = _city()

        with pytest.raises(RuntimeError):
            with transaction.atomic(using=CATALOG):
                request_coverage(city=city.name, actor=ACTOR)
                raise RuntimeError("boom")

        assert _requests() == []
        assert _audits() == []


# --- the throttle ------------------------------------------------------------------------------


class TestTheThrottle:
    """A limit that a repeat could slip past is not a limit."""

    def test_the_limit_is_five_per_reader(self):
        """**Five, and the sixth is refused.** The same number as a report's daily limit,
        for the same reason: the abuse is the same shape.
        """
        city = _city()
        for _ in range(5):
            request_coverage(city=city.name, actor=ACTOR)

        with pytest.raises(ThrottledError):
            request_coverage(city=city.name, actor=ACTOR)

    def test_a_refused_request_writes_nothing(self):
        """The refusal happens before the write, so it leaves nothing behind."""
        city = _city()
        for _ in range(5):
            request_coverage(city=city.name, actor=ACTOR)

        with pytest.raises(ThrottledError):
            request_coverage(city=city.name, actor=ACTOR)

        assert len(_requests()) == 1
        assert _requests()[0].request_count == 5

    def test_the_throttle_is_checked_before_the_idempotence_shortcut(self):
        """**A repeat still spends an attempt.**

        This is the `event_reports.py` rule: the throttle runs *first*, so a client
        hammering the same request is still spending attempts. A limit the idempotence
        shortcut could slip past would not be a limit at all.

        **The first request spent attempt one**, so four more fit inside the limit and
        the *fifth* repeat is the one refused. If the throttle ran *after* the
        idempotence shortcut, every one of these repeats would have been free and the
        reader would never have been refused at all.
        """
        city = _city()
        request_coverage(city=city.name, actor=ACTOR)

        for _ in range(4):
            request_coverage(city=city.name, actor=ACTOR)

        with pytest.raises(ThrottledError):
            request_coverage(city=city.name, actor=ACTOR)

    def test_the_throttle_key_is_the_readers_own(self):
        """One reader's spending is another's not, and the key is opaque."""
        assert throttle_key(ACTOR.id) == f"coverage_request:{ACTOR.id}"
        assert throttle_key(uuid.UUID("44444444-4444-4444-4444-444444444444")) != throttle_key(
            ACTOR.id
        )
