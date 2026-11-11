"""End to end: seed by command -> tick -> ingest -> catalog API -> tick again, unchanged.

The whole chain runs through the real seams — the management command, the registry services,
the 60 s tick, the scheduling claim, the ingest pipeline, the catalog read service and the
HTTP API. Only two things are substituted, both deliberately:

1. the fetch, served by `FakeFetchAdapter` from recorded fixtures, so CI never opens a socket;
2. the broker, recorded by `tests/e2e/conftest.py`, with the jobs run inline.
"""

from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from apps.ingestion.models import Event, EventStateChange, ExtractedRecord, Source
from shared.db import CATALOG, PERSONAL
from worker import tasks

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

FIXTURE_CITY = "Fixtureville"

#: The instant this module pretends it is.
#:
#: **The recorded fixtures carry fixed dates, and the catalog listing is bounded by the
#: clock.** `list_public_events` answers "what has not started yet", so the JSON-LD
#: fixture's `2026-11-03` event was listed while that date was in the future and is
#: filtered out the day after. A test that reads the real clock therefore fails on a
#: calendar boundary rather than on a fault in the code — and the fixture is a
#: *recorded* feed, so its dates cannot follow the wall clock.
#:
#: **The clock is pinned rather than the fixture rewritten.** Rewriting the fixture
#: would move the dates the assertions quote (`"2026-11-03T14:30:00"`) and the dates
#: other packages' tests quote, so the fixture is the shared, fixed thing and the
#: *reading* of it is what moves.
PINNED_NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)

EXPECTED_PERMISSIONS = {
    "ingestion.source": {"add", "change", "view"},
    "ingestion.venue": {"add", "change", "view"},
    "ingestion.tosreview": {"add", "change", "view"},
    "ingestion.event": {"view"},
    "ingestion.eventstatechange": {"view"},
    "ingestion.ingestionauditentry": {"view"},
    # FR-57's queue (review-queue-model D9): worked, never created or deleted by hand.
    "ingestion.reviewitem": {"change", "view"},
}

# The codenames are `<action>_<model>` with the model in lower case, so `TosReview` becomes
# `add_tosreview` and `EventStateChange` becomes `view_eventstatechange`.
EXPECTED_CODENAMES = {
    f"{action}_{model.split('.', 1)[1]}"
    for model, actions in EXPECTED_PERMISSIONS.items()
    for action in actions
}


@pytest.fixture(autouse=True)
def fake_fetch(settings):
    """The fake adapter, whatever SOURCE_FETCH says in the environment."""
    settings.ADAPTERS = {**settings.ADAPTERS, "fetch": "adapters.crawl.fake.FakeFetchAdapter"}


@pytest.fixture(autouse=True)
def pinned_clock(monkeypatch):
    """The clock, pinned to `PINNED_NOW` for the whole module.

    **Every reader of the wall clock in this chain is patched.** The listing reads
    `django.utils.timezone.now` in `apps/catalog/api.py`, the tick reads it in
    `worker.tasks._now`, and the ingest reads it in
    `apps.ingestion.services.ingest_source`. Patching the one function on the module
    they all share — `django.utils.timezone.now` — is the only patch that reaches all
    three without touching production code.

    **`django.utils.timezone.now` is patched, not `datetime.now`.** The readers ask
    Django for the time, and Django is what the patch replaces; a module that had
    reached for `datetime.now` directly would be a different question, and this suite
    does not have one.
    """
    monkeypatch.setattr(timezone, "now", lambda *args, **kwargs: PINNED_NOW)


@pytest.fixture
def seeded():
    call_command("seed_local_stack", stdout=None)
    return Source.objects.using(CATALOG).all()


def _run_tick_inline(enqueued) -> None:
    """Run the tick, then run every job it would publish, inline."""
    tasks.tick()
    tasks.schedule_sources()
    for name, args in list(enqueued):
        if name == "worker.tasks.ingest_source":
            tasks.ingest_source(*args)
    enqueued.clear()


def _force_due(source_ids) -> None:
    """Make the sources due again, so the second tick really re-ingests them.

    Due-ness is keyed on the last attempt, so without this the second tick would claim
    nothing and the "nothing changed" assertion would pass vacuously.
    """
    Source.objects.using(CATALOG).filter(pk__in=list(source_ids)).update(
        last_attempted_at=timezone.now() - timedelta(hours=5)
    )


def _snapshot(source_ids):
    """Everything the catalog must not change on a second ingest."""
    events = list(
        Event.objects.using(CATALOG)
        .filter(source_id__in=list(source_ids))
        .order_by("id")
        .values(
            "id",
            "source_event_id",
            "title",
            "slug",
            "event_version",
            "start_time_utc",
            "start_time_tz",
            "start_time_local",
            "status",
        )
    )
    changes = list(
        EventStateChange.objects.using(CATALOG).order_by("id").values("id", "event_id", "kind")
    )
    records = list(
        ExtractedRecord.objects.using(CATALOG)
        .filter(source_id__in=list(source_ids))
        .order_by("id")
        .values("id", "source_event_id", "resolution", "content_hash")
    )
    return events, changes, records


def _listed_events():
    body = Client().get("/api/catalog/events", {"city": FIXTURE_CITY}).json()
    assert body["total"] == len(body["items"])
    return body["items"]


# --- 1. the seed command ----------------------------------------------------------------------


def test_the_seed_command_registers_the_three_methods_and_is_idempotent(seeded):
    call_command("seed_local_stack", stdout=None)

    assert sorted(source.acquisition_method for source in seeded) == ["ics", "jsonld", "rss"]
    assert all(source.tos_status == "approved" for source in seeded)
    assert all(source.status == "active" for source in seeded)


def test_each_seeded_source_carries_its_own_tos_review(seeded):
    from apps.ingestion.models import TosReview

    for source in seeded:
        reviews = list(TosReview.objects.using(CATALOG).filter(source=source))
        assert len(reviews) == 1, f"{source.name} should carry exactly one review"
        assert reviews[0].decision == "approved"
        assert reviews[0].evidence_url.startswith("https://")
        assert reviews[0].notes


def test_re_running_the_command_does_not_stack_duplicate_reviews(seeded):
    call_command("seed_local_stack", stdout=None)

    from apps.ingestion.models import TosReview

    assert TosReview.objects.using(CATALOG).count() == len(seeded)


def test_the_seed_command_registers_the_venues_with_their_timezones():
    call_command("seed_local_stack", stdout=None)

    from apps.ingestion.models import Venue

    venues = Venue.objects.using(CATALOG).all()
    assert {venue.name for venue in venues} == {
        "Proof Fixture Venue",
        "Park Slope Library",
        "St. Mary's Hall",
        "Central Library",
    }
    assert all(venue.city == FIXTURE_CITY for venue in venues)
    assert all(venue.country_code == "US" for venue in venues)
    assert all(venue.tz == "America/New_York" for venue in venues)


# --- 2. the editorial group (AD-14) ------------------------------------------------------------


def test_the_editorial_group_holds_exactly_the_granted_permissions():
    call_command("seed_local_stack", stdout=None)

    group = Group.objects.using(PERSONAL).get(name="editorial")
    granted = set(group.permissions.values_list("codename", flat=True))
    assert granted == EXPECTED_CODENAMES
    assert len(granted) == 14


def test_the_operator_is_staff_and_not_a_superuser_and_uses_the_group():
    call_command("seed_local_stack", stdout=None)

    from django.contrib.auth import get_user_model

    operator = get_user_model().objects.db_manager(PERSONAL).get(email="operator@example.test")
    assert operator.is_staff is True
    assert operator.is_superuser is False
    assert operator.groups.filter(name="editorial").exists()
    assert operator.has_perm("ingestion.change_source") is True
    # Sources are paused, never deleted, so the group must not grant delete.
    assert operator.has_perm("ingestion.delete_source") is False
    # The review queue is worked through commands: no hand-made items, no deleted ones.
    assert operator.has_perm("ingestion.change_reviewitem") is True
    assert operator.has_perm("ingestion.add_reviewitem") is False
    assert operator.has_perm("ingestion.delete_reviewitem") is False


def test_an_operator_who_became_a_superuser_is_demoted_on_the_next_run():
    """The operator never keeps superuser rights, even if something else granted them."""
    from django.contrib.auth import get_user_model

    call_command("seed_local_stack", stdout=None)
    manager = get_user_model().objects.db_manager(PERSONAL)
    operator = manager.get(email="operator@example.test")
    operator.is_superuser = True
    operator.save(using=PERSONAL, update_fields=["is_superuser"])

    call_command("seed_local_stack", stdout=None)

    assert manager.get(email="operator@example.test").is_superuser is False


def test_a_stale_grant_is_removed_from_the_editorial_group():
    """The permission set is assigned, not appended: a stale grant does not survive."""
    from django.contrib.auth.models import Group, Permission

    call_command("seed_local_stack", stdout=None)
    group = Group.objects.using(PERSONAL).get(name="editorial")
    stale = Permission.objects.using(PERSONAL).get(codename="delete_source")
    group.permissions.add(stale)

    call_command("seed_local_stack", stdout=None)

    group.refresh_from_db()
    assert "delete_source" not in set(group.permissions.values_list("codename", flat=True))


# --- 3. the end-to-end run ----------------------------------------------------------------------


def test_the_whole_chain_lands_events_in_the_public_catalog(seeded, enqueued):
    _run_tick_inline(enqueued)

    items = _listed_events()
    titles = {item["title"] for item in items}
    # One title from each acquisition method: JSON-LD, RSS and ICS.
    assert "Mini Makers: Art + Gratitude" in titles
    assert "Gallery After Hours" in titles
    assert "Board Game Meetup" in titles
    assert "Library Book Club" in titles

    # The JSON-LD events carry the zone the fixture wrote, with the local wall clock beside it.
    mini = next(item for item in items if item["title"] == "Mini Makers: Art + Gratitude")
    assert mini["start_time_utc"].startswith("2026-11-03T14:30:00")
    assert mini["start_time_tz"] == "America/New_York"
    assert mini["venue_city"] == FIXTURE_CITY
    assert mini["tz_review_pending"] is False


def test_the_series_instances_are_distinct_events_sharing_one_series_id(seeded, enqueued):
    _run_tick_inline(enqueued)

    workshops = list(
        Event.objects.using(CATALOG)
        .filter(title="Studio Workshop")
        .values("id", "source_event_id", "series_id", "event_version")
    )
    assert len(workshops) == 2
    assert len({workshop["id"] for workshop in workshops}) == 2
    assert len({workshop["series_id"] for workshop in workshops}) == 1
    assert workshops[0]["series_id"] is not None


def test_one_event_per_source_item_with_no_duplicates(seeded, enqueued):
    _run_tick_inline(enqueued)

    per_source = {}
    for source_id, source_event_id in ExtractedRecord.objects.using(CATALOG).values_list(
        "source_id", "source_event_id"
    ):
        per_source.setdefault(source_id, []).append(source_event_id)
    assert all(len(ids) == len(set(ids)) for ids in per_source.values())

    live = Event.objects.using(CATALOG).exclude(status=Event.Status.SUPERSEDED)
    keys = list(live.values_list("source_id", "source_event_id"))
    assert len(keys) == len(set(keys))


def test_re_running_the_tick_changes_nothing(seeded, enqueued):
    _run_tick_inline(enqueued)
    before = _snapshot([source.id for source in seeded])

    _force_due([source.id for source in seeded])
    _run_tick_inline(enqueued)
    after = _snapshot([source.id for source in seeded])

    before_events, before_changes, before_records = before
    after_events, after_changes, after_records = after
    assert after_events == before_events
    assert after_changes == before_changes
    assert after_records == before_records
    assert after_events, "the first run should have produced events"
    assert all(event["event_version"] == 1 for event in after_events)


def test_the_second_ingest_finds_every_item_unchanged(seeded, enqueued):
    """A re-read of the same fixture is a silent update: no version bump, no state change."""
    _run_tick_inline(enqueued)
    events_before = Event.objects.using(CATALOG).count()
    versions_before = sorted(Event.objects.using(CATALOG).values_list("id", "event_version"))

    _force_due([source.id for source in seeded])
    _run_tick_inline(enqueued)

    assert Event.objects.using(CATALOG).count() == events_before
    assert (
        sorted(Event.objects.using(CATALOG).values_list("id", "event_version")) == versions_before
    )
    assert not EventStateChange.objects.using(CATALOG).exists()


def test_each_ingest_records_the_attempt_on_its_source(seeded, enqueued):
    _run_tick_inline(enqueued)

    for source in seeded:
        source.refresh_from_db(using=CATALOG)
        assert source.last_attempted_at is not None
        assert source.last_ingested_at is not None


def test_a_corrected_venue_timezone_re_resolves_its_events(seeded, enqueued):
    """A venue's timezone is a resolution input: correcting it moves the events that name it.

    This is the one legitimate reason for a re-ingest to change an Event, so it is also the
    proof that the re-ingest really re-resolves when it has to.
    """
    from django.contrib.auth import get_user_model

    from apps.ingestion.models import Venue
    from apps.ingestion.services.venue_registry import set_venue_timezone
    from shared.actor import Actor

    _run_tick_inline(enqueued)
    before = {
        event.id: event.start_time_utc
        for event in Event.objects.using(CATALOG).filter(venue__name="Proof Fixture Venue")
    }
    assert before, "the JSON-LD events should name the proof venue"

    operator = get_user_model().objects.db_manager(PERSONAL).get(email="operator@example.test")
    venue = Venue.objects.using(CATALOG).get(name="Proof Fixture Venue")
    set_venue_timezone(actor=Actor.user(operator.id), venue_id=venue.id, tz="America/Chicago")

    _force_due([source.id for source in seeded])
    _run_tick_inline(enqueued)

    after = {
        event.id: event.start_time_utc
        for event in Event.objects.using(CATALOG).filter(venue__name="Proof Fixture Venue")
    }
    assert set(after) == set(before)
    # New York to Chicago is one hour earlier, so every start moved.
    assert all(after[event_id] != before[event_id] for event_id in before)
    assert all(
        event.start_time_tz == "America/Chicago"
        for event in Event.objects.using(CATALOG).filter(venue__name="Proof Fixture Venue")
    )


def test_the_catalog_api_serves_the_events_to_an_anonymous_client(seeded, enqueued):
    _run_tick_inline(enqueued)

    response = Client().get("/api/catalog/events", {"city": FIXTURE_CITY})

    assert response.status_code == 200
    assert "Set-Cookie" not in response.headers
    assert response.json()["items"]
