"""The AD-21 save race, proven deterministically.

AD-21: "A save re-reads the Event's version after commit and requests re-propagation for
that user if it moved meanwhile, so a save racing a postponement cannot keep a stale
snapshot."

**The race is forced, not hoped for.** A probabilistic race test is a flaky test, and a
flaky test in CI is worse than no test. So the interleaving is made reproducible by
patching the *catalog read* the save service makes: the first read — inside the
transaction, the one that stamps the snapshot — returns version N, and the second read —
after the commit, the one that checks — returns version N+1. That is precisely the
postponement-lands-mid-save interleaving, reproduced every time.

The patch is at the **service's** namespace, not the catalog module's: `save_event` does
`from apps.ingestion.services.catalog_read import get_public_event`, so the name it
calls is bound in `apps.personalization.services.saved_events`. Patching the catalog
module instead would not be seen by the service — and a test that silently patches
nothing is a test that proves nothing.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import UUID

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from apps.ingestion.models import Event, Source
from apps.personalization.models import SavedEvent
from apps.personalization.services import saved_events as saved_events_service
from shared.db import CATALOG, PERSONAL
from tests.csrf import CsrfClient
from worker import tasks

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()

#: A fixed instant far enough ahead that the scenario does not race the clock.
START = datetime(2026, 11, 6, 3, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fake_fetch(settings):
    """The fake adapter, whatever SOURCE_FETCH says in the environment."""
    settings.ADAPTERS = {**settings.ADAPTERS, "fetch": "adapters.crawl.fake.FakeFetchAdapter"}


@pytest.fixture
def seeded(enqueued):
    """The catalog has data: the seed command registers the sources, the tick ingests them."""
    call_command("seed_local_stack", stdout=None)
    tasks.tick()
    tasks.schedule_sources()
    for name, args in list(enqueued):
        if name == "worker.tasks.ingest_source":
            tasks.ingest_source(*args)
    enqueued.clear()
    return Source.objects.using(CATALOG).all()


def _signed_in():
    """A client whose session identifies a real user.

    It is a `CsrfClient`: the personal endpoints resolve their user through `identity`'s
    resolver, and the resolver checks CSRF on every unsafe method (D13). The token is
    fetched on the first unsafe request and travels in the `X-CSRFToken` header.
    """
    client = CsrfClient()
    client.force_login(User.objects.create_user(email="sam@example.test", password="pw"))
    return client


def _published_event():
    """A published, not-superseded, upcoming catalog event."""
    return (
        Event.objects.using(CATALOG)
        .filter(publication_status=Event.PublicationStatus.PUBLISHED)
        .exclude(status=Event.Status.SUPERSEDED)
        .filter(start_time_utc__gte=START)
        .order_by("start_time_utc")
        .first()
    )


def test_a_save_that_races_a_postponement_reports_itself_stale(seeded):
    """The save's second read sees a newer version, so the snapshot is reported stale.

    The catalog read is patched so that:
      - the **first** read (inside the transaction, stamping the snapshot) sees version N;
      - the **second** read (after the commit, the check) sees version N+1.

    That is the postponement landing between the save's version read and its commit —
    forced, so the test is deterministic rather than lucky.
    """
    catalog_event = _published_event()
    assert catalog_event is not None

    client = _signed_in()
    user = UUID(client.session["_auth_user_id"])

    calls: list[datetime | None] = []
    real_read = saved_events_service.get_public_event

    def racing_read(*, event_id, now=None):
        """The first read is the old version; every read after it is the new one."""
        calls.append(now)
        public = real_read(event_id=event_id, now=now)
        if len(calls) == 1:
            return replace(public, event_version=public.event_version)
        return replace(public, event_version=public.event_version + 1)

    with patch.object(saved_events_service, "get_public_event", racing_read):
        response = client.post(f"/api/personal/saved-events/{catalog_event.id}")

    assert response.status_code in (200, 201), response.content
    body = response.json()
    assert body["stale"] is True
    assert body["current_version"] == body["event_version"] + 1

    # The snapshot itself keeps the version it was stamped with — it is *reported* stale,
    # not silently rewritten. Repairing it is AD-17's job, which is a later intent.
    save_row = SavedEvent.objects.using(PERSONAL).get(user_id=user, event_id=catalog_event.id)
    assert save_row.event_version == body["event_version"]
    assert save_row.event_version == catalog_event.event_version

    # The catalog read happened twice: once to stamp, once to check.
    assert len(calls) == 2


def test_a_save_that_does_not_race_is_not_stale(seeded):
    """The control case: with the version steady, the save reports itself fresh.

    Without this, "stale is True" would only prove that the endpoint has a `stale` field.
    """
    catalog_event = _published_event()
    assert catalog_event is not None

    client = _signed_in()

    response = client.post(f"/api/personal/saved-events/{catalog_event.id}")
    assert response.status_code in (200, 201), response.content
    body = response.json()
    assert body["stale"] is False
    assert body["current_version"] is None


def test_a_snapshot_survives_a_catalog_postponement_unchanged(seeded):
    """A postponed event's snapshot is **not** repaired by a later read (AD-21, pre-AD-17).

    The snapshot is a record of what the user saved and saw. Until AD-17's propagation
    runs, it stays behind the catalog — and the test says so explicitly, so the pre-
    propagation state cannot be mistaken for a bug.
    """
    catalog_event = _published_event()
    assert catalog_event is not None

    client = _signed_in()
    user = UUID(client.session["_auth_user_id"])

    saved = client.post(f"/api/personal/saved-events/{catalog_event.id}")
    assert saved.status_code in (200, 201), saved.content

    # The catalog moves: a postponement pushes the event an hour later and bumps its
    # version. The snapshot is not touched — nothing here propagates.
    Event.objects.using(CATALOG).filter(pk=catalog_event.id).update(
        start_time_utc=catalog_event.start_time_utc + timedelta(hours=1),
        event_version=catalog_event.event_version + 1,
    )

    save_row = SavedEvent.objects.using(PERSONAL).get(user_id=user, event_id=catalog_event.id)
    assert save_row.start_utc == catalog_event.start_time_utc
    assert save_row.event_version == catalog_event.event_version

    # The catalog is now ahead of the snapshot. That is the correct pre-propagation state.
    moved = Event.objects.using(CATALOG).get(pk=catalog_event.id)
    assert moved.event_version > save_row.event_version
    assert moved.start_time_utc > save_row.start_utc

    # And a re-read of the user's own calendar shows the snapshot's times, not the
    # catalog's current ones — the snapshot is what the user's calendar holds.
    listed = client.get("/api/personal/saved-events")
    assert listed.status_code == 200
    item = listed.json()["items"][0]
    assert item["start_time_utc"] == catalog_event.start_time_utc.isoformat().replace("+00:00", "Z")
    assert item["event_version"] == catalog_event.event_version
    # The display fields *do* come from the catalog, so an editorial correction shows up
    # immediately — only the times are the snapshot's.
    assert item["title"] == moved.title


def test_a_save_is_idempotent_and_one_row(seeded):
    """Saving the same event twice is one row, returned again."""
    catalog_event = _published_event()
    assert catalog_event is not None

    client = _signed_in()
    user = UUID(client.session["_auth_user_id"])

    first = client.post(f"/api/personal/saved-events/{catalog_event.id}")
    second = client.post(f"/api/personal/saved-events/{catalog_event.id}")

    assert first.status_code == 201, first.content
    assert second.status_code == 200, second.content
    assert first.json()["id"] == second.json()["id"]
    assert (
        SavedEvent.objects.using(PERSONAL).filter(user_id=user, event_id=catalog_event.id).count()
        == 1
    )


def test_a_save_of_an_unpublished_event_is_not_found(seeded):
    """A hidden event cannot be saved — the public catalog is one truth."""
    catalog_event = _published_event()
    assert catalog_event is not None

    Event.objects.using(CATALOG).filter(pk=catalog_event.id).update(
        publication_status=Event.PublicationStatus.IN_REVIEW
    )

    client = _signed_in()
    response = client.post(f"/api/personal/saved-events/{catalog_event.id}")
    assert response.status_code == 404, response.content
    assert response.json()["code"] == "not_found"
