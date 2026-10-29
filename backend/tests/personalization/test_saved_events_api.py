"""The saved-events endpoints (AD-21, AD-22, FR-33, FR-58).

Saving a public catalog event is the act of taking it into the user's own calendar. These
tests pin the surface: the idempotent save, the unsave, the list, the scoping, and the two
things that make this surface different from the personal-events one — **the save race**
and **the two sources of the response**.

**The response has two sources.** The times come from the snapshot on the personal row;
the title and venue come from the catalog, read at request time. A saved event is
therefore not a copy of a catalog event, and the tests keep the two apart.

**The save race is exposed, not papered over.** AD-21: "A save re-reads the Event's version
after commit and requests re-propagation for that user if it moved meanwhile, so a save
racing a postponement cannot keep a stale snapshot." The service detects the race; the API
must report it, because a stale snapshot presented as current is a wrong time on the
user's calendar.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from apps.ingestion.models import Event
from apps.personalization.models import ConflictPair, SavedEvent
from shared.db import CATALOG, PERSONAL
from tests.csrf import CsrfClient
from tests.ingestion.factories import EventFactory, make_superseded_pair
from tests.personalization.factories import PersonalEventFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()

#: A fixed instant far enough ahead that a test's events are always "upcoming".
START = datetime(2026, 11, 6, 3, 30, tzinfo=UTC)
HOUR = timedelta(hours=1)


def make_user(email="sam@example.test"):
    """A real user with a real pk — the session resolves to this one."""
    return User.objects.create_user(email=email, password="pw")


def signed_in(user=None):
    """A client whose session identifies `user`.

    It is a `CsrfClient`, because these endpoints resolve their user through `identity`'s
    resolver and the resolver checks CSRF on every unsafe method (D13). The token is
    fetched on the first unsafe request and travels in the `X-CSRFToken` header.
    """
    client = CsrfClient()
    client.force_login(user or make_user())
    return client


def make_event(user, *, name="Coffee with Sam", start=START, hours=2, **extra):
    """A personal event on the user's calendar.

    The end is derived from the start, because the model's check constraint refuses an end
    before its start — overriding only `start_utc` would leave the factory's default end
    behind it.
    """
    return PersonalEventFactory(
        user_id=user.pk,
        name=name,
        start_utc=start,
        end_utc=start + timedelta(hours=hours),
        **extra,
    )


def public_event(**overrides):
    """A published, upcoming catalog event — the only kind that is saveable."""
    return EventFactory(**overrides)


def save(client, catalog_event_id):
    return client.post(f"/api/personal/saved-events/{catalog_event_id}")


def unsave(client, catalog_event_id):
    return client.delete(f"/api/personal/saved-events/{catalog_event_id}")


# --- Saving ----------------------------------------------------------------------------------


def test_saving_a_public_event_returns_the_saved_record():
    event = public_event(start_time_utc=START)
    client = signed_in()

    response = save(client, event.id)

    assert response.status_code == 201
    payload = response.json()
    assert payload["event_id"] == str(event.id)
    assert payload["title"] == event.title
    assert payload["venue_name"] == event.venue.name
    assert payload["id"]


def test_the_saved_record_carries_the_snapshot_and_the_display_fields():
    """Two sources, kept apart: the times from the snapshot, the title from the catalog."""
    event = public_event(start_time_utc=START)
    client = signed_in()

    payload = save(client, event.id).json()

    assert payload["start_time_utc"] == START.isoformat().replace("+00:00", "Z")
    assert payload["event_version"] == event.event_version
    assert payload["title"] == event.title
    assert payload["canonical_url"] == event.canonical_url


def test_the_save_belongs_to_the_signed_in_user():
    user = make_user()
    event = public_event(start_time_utc=START)

    signed_in(user).post(f"/api/personal/saved-events/{event.id}")

    saved = SavedEvent.objects.get()
    assert saved.user_id == user.pk
    assert saved.event_id == event.id


def test_saving_the_same_event_twice_is_idempotent():
    """One row, not two; and the second answers 200, not a 409."""
    event = public_event(start_time_utc=START)
    client = signed_in()

    first = save(client, event.id)
    second = save(client, event.id)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert SavedEvent.objects.count() == 1


def test_saving_an_event_that_is_not_public_is_a_404():
    """Only published, non-superseded, upcoming events are saveable."""
    client = signed_in()

    response = save(client, uuid4())

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert not SavedEvent.objects.exists()


def test_saving_an_unpublished_event_is_a_404():
    event = public_event(start_time_utc=START, publication_status=Event.PublicationStatus.IN_REVIEW)
    client = signed_in()

    response = save(client, event.id)

    assert response.status_code == 404
    assert not SavedEvent.objects.exists()


def test_saving_a_superseded_event_is_a_404():
    old, _ = make_superseded_pair(start_time_utc=START)
    client = signed_in()

    response = save(client, old.id)

    assert response.status_code == 404
    assert not SavedEvent.objects.exists()


def test_saving_an_event_that_has_already_started_is_a_404():
    """Only an event that is still ahead of you is saveable."""
    event = public_event(start_time_utc=timezone.now() - HOUR)
    client = signed_in()

    response = save(client, event.id)

    assert response.status_code == 404
    assert not SavedEvent.objects.exists()


def test_a_save_of_an_event_that_has_since_started_is_still_listed():
    """The user's own calendar does not un-save an event because it began."""
    user = make_user()
    event = public_event(start_time_utc=START)
    client = signed_in(user)
    save(client, event.id)

    # The event begins. The catalog's write guard requires the version to move with it.
    Event.objects.using(CATALOG).filter(pk=event.pk).update(
        start_time_utc=timezone.now() - HOUR,
        event_version=event.event_version + 1,
    )

    payload = client.get("/api/personal/saved-events").json()

    assert [item["event_id"] for item in payload["items"]] == [str(event.id)]
    assert payload["omitted"] == 0


# --- The save race (AD-21) --------------------------------------------------------------------


def _racing_read(counter):
    """A stand-in for the catalog read that postpones the event after the first read.

    The service reads the catalog twice — once to stamp the snapshot, once to check whether
    the version moved. The postponement lands between them.
    """
    from apps.personalization.services import saved_events as service

    real_read = service.get_public_event

    def racing_read(*, event_id, now=None):
        counter["count"] += 1
        result = real_read(event_id=event_id, now=now)
        if counter["count"] == 1:
            Event.objects.using(CATALOG).filter(pk=event_id).update(
                event_version=result.event_version + 1
            )
        return result

    return real_read, racing_read


def test_a_save_that_races_a_postponement_reports_the_snapshot_as_stale():
    """The version moves between the service's first read and its check."""
    event = public_event(start_time_utc=START)
    client = signed_in()

    from apps.personalization.services import saved_events as service

    counter = {"count": 0}
    real_read, racing_read = _racing_read(counter)
    service.get_public_event = racing_read
    try:
        payload = save(client, event.id).json()
    finally:
        service.get_public_event = real_read

    assert payload["stale"] is True
    assert payload["current_version"] == event.event_version + 1
    assert payload["event_version"] == event.event_version


def test_a_save_with_no_race_is_not_stale():
    event = public_event(start_time_utc=START)
    client = signed_in()

    payload = save(client, event.id).json()

    assert payload["stale"] is False
    assert payload["current_version"] is None


def test_a_stale_save_records_that_repropagation_was_requested():
    """AD-21: the service asks for re-propagation rather than repairing the snapshot."""
    from apps.personalization.models import PersonalizationAuditEntry

    event = public_event(start_time_utc=START)
    client = signed_in()

    from apps.personalization.services import saved_events as service

    counter = {"count": 0}
    real_read, racing_read = _racing_read(counter)
    service.get_public_event = racing_read
    try:
        save(client, event.id)
    finally:
        service.get_public_event = real_read

    entry = PersonalizationAuditEntry.objects.get(action="saved_event.stale_detected")
    assert entry.details["repropagation_requested"] is True


# --- Conflicts (FR-58) -----------------------------------------------------------------------


def test_a_save_that_clashes_with_a_personal_event_answers_409_with_the_three_actions():
    user = make_user()
    make_event(user, name="Coffee with Sam")
    catalog = public_event(start_time_utc=START)
    client = signed_in(user)

    response = save(client, catalog.id)

    assert response.status_code == 409
    payload = response.json()
    assert payload["code"] == "scheduling_conflict"
    conflict = payload["details"]["conflicts"][0]
    assert conflict["kind"] == "time"
    assert len(conflict["actions"]) == 3
    assert "dismiss" not in conflict["actions"]


def test_a_conflicting_save_still_writes_the_save_and_leaves_the_pair_active():
    user = make_user()
    make_event(user, name="Coffee with Sam")
    catalog = public_event(start_time_utc=START)
    client = signed_in(user)

    save(client, catalog.id)

    assert SavedEvent.objects.count() == 1
    pair = ConflictPair.objects.get()
    assert pair.status == ConflictPair.Status.ACTIVE
    assert pair.resolution is None


# --- Un-saving -------------------------------------------------------------------------------


def test_unsaving_removes_the_save():
    event = public_event(start_time_utc=START)
    client = signed_in()
    save(client, event.id)

    response = unsave(client, event.id)

    assert response.status_code == 204
    assert not SavedEvent.objects.exists()


def test_unsaving_an_event_that_is_not_saved_is_a_404():
    event = public_event(start_time_utc=START)

    response = unsave(signed_in(), event.id)

    assert response.status_code == 404


def test_unsaving_closes_the_pairs_the_save_took_part_in():
    user = make_user()
    make_event(user, name="Coffee with Sam")
    catalog = public_event(start_time_utc=START)
    client = signed_in(user)
    save(client, catalog.id)

    response = unsave(client, catalog.id)

    assert response.status_code == 204
    pair = ConflictPair.objects.get()
    assert pair.status == ConflictPair.Status.CLEARED_BY_STATE_CHANGE
    assert pair.resolution is None


def test_unsaving_another_users_save_is_a_404_not_a_403():
    other = make_user("other")
    event = public_event(start_time_utc=START)
    signed_in(other).post(f"/api/personal/saved-events/{event.id}")

    response = unsave(signed_in(make_user("stranger")), event.id)

    assert response.status_code == 404
    assert SavedEvent.objects.count() == 1


# --- Listing ---------------------------------------------------------------------------------


def test_listing_returns_the_users_saved_events():
    user = make_user()
    event = public_event(start_time_utc=START)
    client = signed_in(user)
    save(client, event.id)

    payload = client.get("/api/personal/saved-events").json()

    assert [item["event_id"] for item in payload["items"]] == [str(event.id)]
    assert payload["omitted"] == 0


def test_listing_does_not_show_another_users_saves():
    event = public_event(start_time_utc=START)
    signed_in(make_user("other")).post(f"/api/personal/saved-events/{event.id}")

    payload = signed_in().get("/api/personal/saved-events").json()

    assert payload["items"] == []


def test_listing_orders_by_the_snapshot_start_time():
    user = make_user()
    later = public_event(start_time_utc=START + timedelta(days=2))
    sooner = public_event(start_time_utc=START)
    client = signed_in(user)
    save(client, later.id)
    save(client, sooner.id)

    payload = client.get("/api/personal/saved-events").json()

    assert [item["event_id"] for item in payload["items"]] == [str(sooner.id), str(later.id)]


def test_listing_bounds_filter_by_the_snapshot_start_time():
    """The bound applies to the snapshot the list returns, so the two never disagree."""
    user = make_user()
    earlier = public_event(start_time_utc=START)
    later = public_event(start_time_utc=START + timedelta(days=2))
    client = signed_in(user)
    save(client, earlier.id)
    save(client, later.id)

    payload = client.get(
        "/api/personal/saved-events",
        {"starts_after": START.isoformat(), "starts_before": START.isoformat()},
    ).json()

    assert [item["event_id"] for item in payload["items"]] == [str(earlier.id)]


def test_a_save_whose_catalog_event_has_gone_is_omitted_and_counted():
    """The catalog event was superseded: there is no title to show, but it is not hidden."""
    user = make_user()
    old, _ = make_superseded_pair(start_time_utc=START)
    client = signed_in(user)
    # The save is written directly, as if it had been made while the event was public.
    SavedEvent.objects.using(PERSONAL).create(
        user_id=user.pk,
        event_id=old.id,
        start_utc=START,
        end_utc=START + timedelta(hours=2),
        event_version=1,
    )

    payload = client.get("/api/personal/saved-events").json()

    assert payload["items"] == []
    assert payload["omitted"] == 1


# --- The session seam (AD-12) ----------------------------------------------------------------


UNAUTHENTICATED_REQUESTS = [
    ("get", "/api/personal/saved-events", None),
    ("post", "/api/personal/saved-events/{catalog_event_id}", None),
    ("delete", "/api/personal/saved-events/{catalog_event_id}", None),
]


@pytest.mark.parametrize(("method", "path", "payload"), UNAUTHENTICATED_REQUESTS)
def test_an_anonymous_request_is_refused_with_a_401(method, path, payload):
    client = Client()
    url = path.format(catalog_event_id=uuid4())

    response = getattr(client, method)(url, payload, content_type="application/json")

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"
    assert response.json()["message"] == "Please sign in to continue."


def test_no_endpoint_accepts_a_user_id():
    """The scoping cannot be talked out of by a payload."""
    user = make_user()
    event = public_event(start_time_utc=START)

    response = signed_in(user).post(
        f"/api/personal/saved-events/{event.id}",
        {"user_id": str(make_user("other").pk)},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert SavedEvent.objects.get().user_id == user.pk


# --- The contract (AD-19) --------------------------------------------------------------------


def test_the_endpoints_are_in_the_openapi_schema():
    schema = Client().get("/api/openapi.json").json()

    assert "/api/personal/saved-events" in schema["paths"]
    assert "/api/personal/saved-events/{catalog_event_id}" in schema["paths"]


def test_the_save_response_carries_the_staleness_fields():
    """The client has to know the snapshot may be behind the catalog."""
    schema = Client().get("/api/openapi.json").json()

    saved_event = schema["components"]["schemas"]["SavedEventOut"]
    assert "stale" in saved_event["properties"]
    assert "current_version" in saved_event["properties"]


def test_the_api_layer_does_not_import_the_ingestion_models():
    """The catalog is reached through ingestion's published read interface."""
    import ast
    from pathlib import Path

    source = Path("apps/personalization/api.py").read_text()
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)

    assert "apps.ingestion.models" not in imported
