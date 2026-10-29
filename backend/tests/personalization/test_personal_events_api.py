"""The personal-events endpoints (FR-18, FR-58, AD-12, AD-19).

These are the tests for the surface itself: the wire shapes, the status codes, the session
scoping, and the conflict round trip.

**Every request is a signed-in one, except where it is specifically not.** The surface is
session-based by design (AD-12 applies to the *public* catalog only), so the bulk of these
tests drive a client with a session, and a handful prove that an anonymous request is
refused with a 401 and a calm message.

**The user id comes from the session, never from the payload.** No endpoint takes one, and
several tests prove it: the cross-user attempt reads as **404, not 403**, so the endpoint
cannot be used to probe for another user's ids.

**The conflict round trip is the centre of this file.** A create that clashes does not
complete — it answers 409 with the conflicting event and the three actions — and the client
then posts one of them to the resolve endpoint. There is no dismiss, and the schema cannot
offer one either.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.personalization.models import ConflictPair, PersonalEvent
from shared.constants import DEFAULT_REMINDER_PLAN
from shared.db import PERSONAL
from tests.personalization.factories import PersonalEventFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

#: A fixed instant far enough ahead that the tests do not race the clock.
START = datetime(2026, 11, 6, 3, 30, tzinfo=UTC)
END = START + timedelta(hours=2)
#: The same instant, expressed in the zone the body names.
START_LOCAL = "2026-11-05T19:30:00"
TZ = "America/Los_Angeles"

User = get_user_model()


def make_user(username="sam"):
    """A real user with a real pk — the session resolves to this one."""
    return User.objects.create_user(username=username, password="pw")


def make_event(user, *, name="Coffee with Sam", start=START, hours=2, **extra):
    """An event on the user's calendar.

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


def signed_in(user=None):
    """A client whose session identifies `user`."""
    client = Client()
    client.force_login(user or make_user())
    return client


def body(name="Coffee with Sam", start=START, end=None, tz=TZ, hours=2, **extra):
    """A create body.

    The end is derived from the start unless one is named, so moving the start cannot leave
    the end behind it — the model's check constraint refuses an end before its start.
    """
    payload = {
        "name": name,
        "start_time_utc": start.isoformat(),
        "start_time_tz": tz,
    }
    if end is None and hours is not None:
        end = start + timedelta(hours=hours)
    if end is not None:
        payload["end_time_utc"] = end.isoformat()
    payload.update(extra)
    return payload


# --- Creating (FR-18) ------------------------------------------------------------------------


def test_creating_an_event_answers_201_with_the_event():
    client = signed_in()

    response = client.post("/api/personal/events", body(), content_type="application/json")

    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == "Coffee with Sam"
    assert payload["start_time_tz"] == TZ
    assert payload["version"] == 1
    assert payload["id"]


def test_the_created_event_belongs_to_the_signed_in_user():
    user = make_user()
    client = signed_in(user)

    client.post("/api/personal/events", body(), content_type="application/json")

    event = PersonalEvent.objects.get(name="Coffee with Sam")
    assert event.user_id == user.pk


def test_the_response_carries_only_the_contracted_fields():
    client = signed_in()

    payload = client.post("/api/personal/events", body(), content_type="application/json").json()

    assert set(payload) == {
        "id",
        "name",
        "start_time_utc",
        "end_time_utc",
        "start_time_tz",
        "location",
        "notes",
        "version",
    }


def test_creating_an_event_without_a_timezone_is_refused():
    client = signed_in()

    response = client.post(
        "/api/personal/events",
        {"name": "Coffee", "start_time_utc": START.isoformat()},
        content_type="application/json",
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"


def test_creating_an_event_with_an_unknown_timezone_is_refused():
    client = signed_in()

    response = client.post(
        "/api/personal/events", body(tz="Mars/Olympus"), content_type="application/json"
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_timezone"
    assert not PersonalEvent.objects.exists()


def test_creating_an_event_with_an_end_before_its_start_is_refused():
    client = signed_in()

    response = client.post(
        "/api/personal/events",
        body(start=END, end=START),
        content_type="application/json",
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_interval"
    assert not PersonalEvent.objects.exists()


def test_creating_an_event_with_no_end_stores_a_null_end():
    client = signed_in()

    response = client.post(
        "/api/personal/events", body(hours=None), content_type="application/json"
    )

    assert response.status_code == 201
    assert response.json()["end_time_utc"] is None


def test_a_created_event_gets_the_default_reminder_plan():
    """FR-20: a new personal event has a plan of 1d + 1hr."""
    client = signed_in()

    client.post("/api/personal/events", body(), content_type="application/json")

    from apps.delivery.models import ReminderPlan

    plan = ReminderPlan.objects.get()
    assert plan.slots == [slot.value for slot in DEFAULT_REMINDER_PLAN]


# --- The conflict round trip (FR-58) --------------------------------------------------------


def test_a_conflicting_create_answers_409_with_the_conflict_and_the_three_actions():
    user = make_user()
    make_event(user, name="Coffee with Sam")
    client = signed_in(user)

    response = client.post("/api/personal/events", body(), content_type="application/json")

    assert response.status_code == 409
    payload = response.json()
    assert payload["code"] == "scheduling_conflict"
    details = payload["details"]
    assert details["event_id"]
    conflict = details["conflicts"][0]
    assert conflict["kind"] == "time"
    assert conflict["other"]["name"] == "Coffee with Sam"
    assert conflict["other"]["id"]
    assert conflict["actions"] == ["delete_new", "edit_new", "keep_both"]


def test_the_conflict_payload_offers_no_dismiss():
    """FR-58: exactly three buttons, and no dismiss."""
    user = make_user()
    make_event(user, name="Coffee with Sam")
    client = signed_in(user)

    response = client.post("/api/personal/events", body(), content_type="application/json")

    actions = response.json()["details"]["conflicts"][0]["actions"]
    assert len(actions) == 3
    assert "dismiss" not in actions


def test_the_openapi_schema_cannot_express_a_dismiss():
    """The action set is a closed literal, so a generated client cannot offer one."""
    schema = Client().get("/api/openapi.json").json()

    resolution = schema["components"]["schemas"]["ConflictResolutionIn"]
    assert set(resolution["properties"]["resolution"]["enum"]) == {
        "keep_both",
        "edit_new",
        "update_existing",
        "delete_new",
    }


def test_a_conflicting_create_still_writes_the_event():
    """The pair names the new event by id, so the row has to exist."""
    user = make_user()
    make_event(user, name="Coffee with Sam")
    client = signed_in(user)

    client.post("/api/personal/events", body(), content_type="application/json")

    assert PersonalEvent.objects.filter(user_id=user.pk).count() == 2


def test_a_conflicting_create_leaves_the_pair_active():
    user = make_user()
    make_event(user, name="Coffee with Sam")
    client = signed_in(user)

    client.post("/api/personal/events", body(), content_type="application/json")

    pair = ConflictPair.objects.get()
    assert pair.status == ConflictPair.Status.ACTIVE
    assert pair.resolution is None


def test_a_non_conflicting_create_answers_201():
    user = make_user()
    make_event(user, name="Dentist")
    client = signed_in(user)

    response = client.post(
        "/api/personal/events",
        body(name="Coffee with Sam", start=START + timedelta(days=3)),
        content_type="application/json",
    )

    assert response.status_code == 201


# --- Resolving a conflict (FR-58) ------------------------------------------------------------


def resolve(client, pair, resolution, new_side_id):
    return client.post(
        f"/api/personal/events/conflicts/{pair}/resolve",
        {"resolution": resolution, "new_side_id": str(new_side_id)},
        content_type="application/json",
    )


def conflicted_pair(user):
    """An existing event and a second one that clashes with it, plus the pair."""
    existing = make_event(user, name="Coffee with Sam")
    client = signed_in(user)
    response = client.post("/api/personal/events", body(), content_type="application/json")
    assert response.status_code == 409
    new_side_id = response.json()["details"]["event_id"]
    pair = ConflictPair.objects.get()
    return existing, new_side_id, pair


def test_keeping_both_records_the_resolution_and_closes_the_pair():
    user = make_user()
    _, new_side_id, pair = conflicted_pair(user)

    response = resolve(signed_in(user), pair.id, "keep_both", new_side_id)

    assert response.status_code == 200
    payload = response.json()
    assert payload["resolution"] == "keep_both"
    assert payload["status"] == "resolved"
    assert payload["new_side_id"] == new_side_id
    pair.refresh_from_db()
    assert pair.status == ConflictPair.Status.RESOLVED
    assert pair.resolution == "keep_both"
    assert PersonalEvent.objects.filter(pk=new_side_id).exists()


def test_deleting_the_new_one_removes_the_new_event():
    user = make_user()
    existing, new_side_id, pair = conflicted_pair(user)

    response = resolve(signed_in(user), pair.id, "delete_new", new_side_id)

    assert response.status_code == 200
    assert not PersonalEvent.objects.filter(pk=new_side_id).exists()
    assert PersonalEvent.objects.filter(pk=existing.pk).exists()


def test_editing_the_new_one_records_the_resolution_and_keeps_the_event():
    user = make_user()
    _, new_side_id, pair = conflicted_pair(user)

    response = resolve(signed_in(user), pair.id, "edit_new", new_side_id)

    assert response.status_code == 200
    assert response.json()["resolution"] == "edit_new"
    assert PersonalEvent.objects.filter(pk=new_side_id).exists()


def test_a_resolution_that_is_illegal_for_the_conflicts_kind_is_refused():
    """`update_existing` is a duplicate's button, not a time conflict's."""
    user = make_user()
    _, new_side_id, pair = conflicted_pair(user)

    response = resolve(signed_in(user), pair.id, "update_existing", new_side_id)

    assert response.status_code == 422
    assert response.json()["code"] == "illegal_resolution"
    pair.refresh_from_db()
    assert pair.status == ConflictPair.Status.ACTIVE
    assert pair.resolution is None


def test_answering_a_conflict_twice_is_refused():
    """A closed pair is immutable and never re-prompted (AD-21)."""
    user = make_user()
    _, new_side_id, pair = conflicted_pair(user)
    client = signed_in(user)
    assert resolve(client, pair.id, "keep_both", new_side_id).status_code == 200

    response = resolve(client, pair.id, "keep_both", new_side_id)

    assert response.status_code == 422
    assert response.json()["code"] == "conflict_already_resolved"


def test_answering_a_conflict_that_does_not_exist_is_a_404():
    user = make_user()

    response = resolve(signed_in(user), uuid4(), "keep_both", uuid4())

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_answering_another_users_conflict_is_a_404():
    other = make_user("other")
    _, new_side_id, pair = conflicted_pair(other)

    response = resolve(signed_in(make_user("stranger")), pair.id, "keep_both", new_side_id)

    assert response.status_code == 404
    pair.refresh_from_db()
    assert pair.status == ConflictPair.Status.ACTIVE


# --- Reading ---------------------------------------------------------------------------------


def test_listing_returns_only_the_signed_in_users_events():
    user = make_user()
    mine = make_event(user, name="Mine")
    make_event(make_user("other"), name="Theirs")
    client = signed_in(user)

    payload = client.get("/api/personal/events").json()

    names = [item["name"] for item in payload["items"]]
    assert names == ["Mine"]
    assert str(mine.id) in [item["id"] for item in payload["items"]]


def test_listing_orders_by_start_time():
    user = make_user()
    make_event(user, name="Later", start=START + timedelta(days=2))
    make_event(user, name="Sooner")
    client = signed_in(user)

    payload = client.get("/api/personal/events").json()

    assert [item["name"] for item in payload["items"]] == ["Sooner", "Later"]


def test_listing_honours_the_start_time_bounds():
    user = make_user()
    make_event(user, name="Early")
    make_event(user, name="Late", start=START + timedelta(days=5))
    client = signed_in(user)

    payload = client.get(
        "/api/personal/events",
        {"starts_after": (START + timedelta(days=1)).isoformat()},
    ).json()

    assert [item["name"] for item in payload["items"]] == ["Late"]


def test_listing_honours_the_upper_start_time_bound():
    user = make_user()
    make_event(user, name="Early")
    make_event(user, name="Late", start=START + timedelta(days=5))
    client = signed_in(user)

    payload = client.get(
        "/api/personal/events",
        {"starts_before": (START + timedelta(days=1)).isoformat()},
    ).json()

    assert [item["name"] for item in payload["items"]] == ["Early"]


def test_listing_with_both_bounds_returns_the_events_between_them():
    user = make_user()
    make_event(user, name="Before")
    make_event(user, name="Between", start=START + timedelta(days=2))
    make_event(user, name="After", start=START + timedelta(days=5))
    client = signed_in(user)

    payload = client.get(
        "/api/personal/events",
        {
            "starts_after": (START + timedelta(days=1)).isoformat(),
            "starts_before": (START + timedelta(days=3)).isoformat(),
        },
    ).json()

    assert [item["name"] for item in payload["items"]] == ["Between"]


def test_getting_one_event_returns_it():
    user = make_user()
    event = make_event(user, name="Coffee with Sam")
    client = signed_in(user)

    response = client.get(f"/api/personal/events/{event.id}")

    assert response.status_code == 200
    assert response.json()["name"] == "Coffee with Sam"
    assert response.json()["id"] == str(event.id)


def test_getting_an_event_that_does_not_exist_is_a_404():
    response = signed_in().get(f"/api/personal/events/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_getting_another_users_event_is_a_404_not_a_403():
    """A 404 does not confirm the record exists, so the endpoint cannot be used to probe."""
    event = make_event(make_user("other"))

    response = signed_in().get(f"/api/personal/events/{event.id}")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


# --- Editing and deleting (FR-18) ------------------------------------------------------------


def test_editing_changes_only_the_named_fields():
    user = make_user()
    event = make_event(user, name="Coffee with Sam", location="Cafe", notes="Notes.")
    client = signed_in(user)

    response = client.patch(
        f"/api/personal/events/{event.id}",
        {"name": "Coffee with Sam and Alex"},
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Coffee with Sam and Alex"
    assert payload["location"] == "Cafe"
    assert payload["notes"] == "Notes."
    assert payload["version"] == event.version + 1


def test_editing_reruns_conflict_detection():
    user = make_user()
    make_event(user, name="Dentist")
    event = make_event(user, name="Coffee with Sam", start=START + timedelta(days=3))
    client = signed_in(user)

    response = client.patch(
        f"/api/personal/events/{event.id}",
        {"start_time_utc": START.isoformat(), "end_time_utc": END.isoformat()},
        content_type="application/json",
    )

    assert response.status_code == 409
    assert response.json()["code"] == "scheduling_conflict"
    assert response.json()["details"]["conflicts"][0]["kind"] == "time"


def test_editing_another_users_event_is_a_404():
    event = make_event(make_user("other"))

    response = signed_in().patch(
        f"/api/personal/events/{event.id}",
        {"name": "Mine now"},
        content_type="application/json",
    )

    assert response.status_code == 404


def test_deleting_removes_the_event():
    user = make_user()
    event = make_event(user)
    client = signed_in(user)

    response = client.delete(f"/api/personal/events/{event.id}")

    assert response.status_code == 204
    assert not PersonalEvent.objects.filter(pk=event.pk).exists()


def test_deleting_another_users_event_is_a_404():
    event = make_event(make_user("other"))

    response = signed_in().delete(f"/api/personal/events/{event.id}")

    assert response.status_code == 404
    assert PersonalEvent.objects.filter(pk=event.pk).exists()


def test_deleting_closes_the_pairs_it_took_part_in():
    user = make_user()
    _, new_side_id, pair = conflicted_pair(user)
    client = signed_in(user)

    response = client.delete(f"/api/personal/events/{new_side_id}")

    assert response.status_code == 204
    pair.refresh_from_db()
    assert pair.status == ConflictPair.Status.CLEARED_BY_STATE_CHANGE
    assert pair.resolution is None


# --- The session seam (AD-12) ----------------------------------------------------------------


UNAUTHENTICATED_REQUESTS = [
    ("get", "/api/personal/events", None),
    ("post", "/api/personal/events", body()),
    ("get", "/api/personal/events/{event_id}", None),
    ("patch", "/api/personal/events/{event_id}", {"name": "x"}),
    ("delete", "/api/personal/events/{event_id}", None),
    ("post", "/api/personal/events/conflicts/{pair_id}/resolve", {"resolution": "keep_both"}),
]


@pytest.mark.parametrize(("method", "path", "payload"), UNAUTHENTICATED_REQUESTS)
def test_an_anonymous_request_is_refused_with_a_401(method, path, payload):
    client = Client()
    url = path.format(event_id=uuid4(), pair_id=uuid4())

    response = getattr(client, method)(url, payload, content_type="application/json")

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"
    assert response.json()["message"] == "Please sign in to continue."


def test_no_endpoint_accepts_a_user_id():
    """The scoping cannot be talked out of by a payload."""
    user = make_user()
    client = signed_in(user)

    response = client.post(
        "/api/personal/events",
        body(user_id=str(make_user("other").pk)),
        content_type="application/json",
    )

    assert response.status_code == 201
    event = PersonalEvent.objects.get(name="Coffee with Sam")
    assert event.user_id == user.pk


# --- The contract (AD-19) --------------------------------------------------------------------


def test_the_endpoints_are_in_the_openapi_schema():
    schema = Client().get("/api/openapi.json").json()

    assert "/api/personal/events" in schema["paths"]
    assert "/api/personal/events/{event_id}" in schema["paths"]
    assert "/api/personal/events/conflicts/{pair_id}/resolve" in schema["paths"]


def test_the_409_carries_a_typed_conflict_payload():
    """The client has to render the three actions, so the shape is in the contract."""
    schema = Client().get("/api/openapi.json").json()

    response = schema["paths"]["/api/personal/events"]["post"]["responses"]["409"]
    assert response["content"]["application/json"]["schema"]["$ref"].endswith(
        "SchedulingConflictOut"
    )
    details = schema["components"]["schemas"]["SchedulingConflictDetails"]
    assert details["properties"]["conflicts"]["items"]["$ref"].endswith("ConflictOut")


def test_the_list_query_parameters_are_in_the_openapi_schema():
    schema = Client().get("/api/openapi.json").json()

    parameters = schema["paths"]["/api/personal/events"]["get"]["parameters"]
    assert {parameter["name"] for parameter in parameters} == {
        "starts_after",
        "starts_before",
    }
    assert all(parameter["in"] == "query" for parameter in parameters)


def test_the_api_layer_does_not_import_the_models():
    """The surface reads the app's published interface, not its tables."""
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

    assert "apps.personalization.models" not in imported
