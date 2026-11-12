"""The collections endpoints (FR-49): CRUD, reorder, membership, and the Pro gate.

**Three things these tests exist to hold.**

1. **The gate covers the two operations that add, and nothing else.** A lapsed Pro user
   keeps reading, renaming, reordering, unassigning and deleting — what they lose is the
   ability to grow the set. That split is a decision, not an accident, so each half has its
   own test.
2. **Another user's collection is 404, never 403**, on *every* endpoint. The scoping test is
   parametrized across the whole surface rather than written once, because "this one
   endpoint forgot the user id" is exactly the bug that hides in a surface this size.
3. **The events read touches no `catalog` table** (AD-3). Asserted by running it in a test
   that is not granted the catalog database at all — so a stray join raises rather than
   quietly working in an environment that happens to have both.
"""

import json
from uuid import uuid4

import pytest

from apps.identity.models import SubscriptionStatus
from shared.db import PERSONAL
from tests.csrf import CsrfClient
from tests.identity.factories import SubscriptionFactory, UserFactory
from tests.personalization.factories import SavedEventFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

COLLECTIONS = "/api/personal/collections"


def client_for(user) -> CsrfClient:
    """A client carrying a real session for `user`, and the CSRF token its writes need."""
    client = CsrfClient()
    client.force_login(user)
    return client


def pro_user():
    """A user with a live subscription."""
    user = UserFactory()
    SubscriptionFactory(user_id=user.pk, status=SubscriptionStatus.ACTIVE)
    return user


def lapsed_user():
    """A user whose subscription ended. Their collections survive; their tier does not."""
    user = UserFactory()
    SubscriptionFactory(user_id=user.pk, status=SubscriptionStatus.CANCELED)
    return user


def create(client, name="Weekend"):
    return client.post(COLLECTIONS, {"name": name}, content_type="application/json")


def created(client, name="Weekend") -> dict:
    response = create(client, name)
    assert response.status_code == 201, response.content
    return json.loads(response.content)


def body_of(response) -> dict:
    return json.loads(response.content)


# ── The ordinary surface, for somebody who may use it ──────────────────────────────


def test_a_pro_user_creates_a_collection_at_the_end_of_their_list():
    client = client_for(pro_user())

    first = created(client, "Weekend")
    second = created(client, "Gigs")

    assert first["position"] == 0
    assert second["position"] == 1
    assert second["item_count"] == 0


def test_the_list_comes_back_in_the_users_own_order():
    client = client_for(pro_user())
    for name in ("One", "Two", "Three"):
        created(client, name)

    listed = body_of(client.get(COLLECTIONS))

    assert [row["name"] for row in listed] == ["One", "Two", "Three"]


def test_a_name_this_user_already_has_is_refused_with_a_sentence():
    client = client_for(pro_user())
    created(client, "Weekend")

    response = create(client, "WEEKEND")

    assert response.status_code == 409
    assert body_of(response)["code"] == "collection_name_taken"


def test_a_blank_name_is_refused_by_the_parser():
    client = client_for(pro_user())

    response = create(client, "")

    assert response.status_code == 422


def test_renaming_a_collection():
    client = client_for(pro_user())
    collection = created(client, "Weekend")

    response = client.patch(
        f"{COLLECTIONS}/{collection['id']}",
        {"name": "Weekends"},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert body_of(response)["name"] == "Weekends"


def test_deleting_a_collection_keeps_its_saves():
    client = client_for(pro_user())
    user_id = client.session["_auth_user_id"]
    collection = created(client)
    saved = SavedEventFactory(user_id=user_id)
    assert client.put(f"{COLLECTIONS}/{collection['id']}/events/{saved.id}").status_code == 204

    assert client.delete(f"{COLLECTIONS}/{collection['id']}").status_code == 204

    # The grouping is gone; the save is not.
    from apps.personalization.models import SavedEvent

    assert SavedEvent.objects.using(PERSONAL).filter(id=saved.id).exists()
    assert body_of(client.get(COLLECTIONS)) == []


# ── Reorder ────────────────────────────────────────────────────────────────────────


def test_reorder_takes_the_whole_list_in_one_request():
    """**One request, so the server never observes a partially reordered list.**"""
    client = client_for(pro_user())
    rows = [created(client, name) for name in ("One", "Two", "Three")]

    response = client.put(
        f"{COLLECTIONS}/order",
        {"collection_ids": [rows[2]["id"], rows[0]["id"], rows[1]["id"]]},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert [row["name"] for row in body_of(response)] == ["Three", "One", "Two"]
    assert [row["position"] for row in body_of(response)] == [0, 1, 2]


def test_a_reorder_that_does_not_name_every_collection_is_refused():
    """The unnamed ones would otherwise land somewhere nobody asked for."""
    client = client_for(pro_user())
    rows = [created(client, name) for name in ("One", "Two", "Three")]

    response = client.put(
        f"{COLLECTIONS}/order",
        {"collection_ids": [rows[0]["id"], rows[1]["id"]]},
        content_type="application/json",
    )

    assert response.status_code == 422
    assert [row["name"] for row in body_of(client.get(COLLECTIONS))] == [
        "One",
        "Two",
        "Three",
    ]


def test_a_reorder_naming_another_users_collection_is_not_found():
    client = client_for(pro_user())
    mine = created(client, "Mine")
    theirs = created(client_for(pro_user()), "Theirs")

    response = client.put(
        f"{COLLECTIONS}/order",
        {"collection_ids": [mine["id"], theirs["id"]]},
        content_type="application/json",
    )

    assert response.status_code == 404


# ── Membership, and the snapshot it returns ────────────────────────────────────────


def test_a_save_can_be_put_into_two_collections_and_read_back():
    client = client_for(pro_user())
    user_id = client.session["_auth_user_id"]
    weekend = created(client, "Weekend")
    gigs = created(client, "Gigs")
    saved = SavedEventFactory(user_id=user_id)

    for collection in (weekend, gigs):
        assert client.put(f"{COLLECTIONS}/{collection['id']}/events/{saved.id}").status_code == 204

    for collection in (weekend, gigs):
        events = body_of(client.get(f"{COLLECTIONS}/{collection['id']}/events"))
        assert [row["id"] for row in events] == [str(saved.id)]


def test_the_events_read_returns_the_snapshot_and_no_catalog_fields():
    """**AD-3**: the times are the user's own rows, kept correct by AD-17 propagation. A
    title or venue here would mean a `catalog` query behind a `personal` endpoint.

    This test is granted only the `personal` database, so a stray join raises rather than
    quietly working.
    """
    client = client_for(pro_user())
    user_id = client.session["_auth_user_id"]
    collection = created(client)
    saved = SavedEventFactory(user_id=user_id)
    client.put(f"{COLLECTIONS}/{collection['id']}/events/{saved.id}")

    events = body_of(client.get(f"{COLLECTIONS}/{collection['id']}/events"))

    assert set(events[0]) == {
        "id",
        "event_id",
        "start_time_utc",
        "end_time_utc",
        "event_version",
    }
    assert events[0]["event_version"] == saved.event_version


def test_assigning_the_same_save_twice_is_a_no_op():
    client = client_for(pro_user())
    user_id = client.session["_auth_user_id"]
    collection = created(client)
    saved = SavedEventFactory(user_id=user_id)

    for _ in range(2):
        assert client.put(f"{COLLECTIONS}/{collection['id']}/events/{saved.id}").status_code == 204

    events = body_of(client.get(f"{COLLECTIONS}/{collection['id']}/events"))
    assert len(events) == 1


def test_unassigning_removes_the_membership_and_not_the_save():
    client = client_for(pro_user())
    user_id = client.session["_auth_user_id"]
    collection = created(client)
    saved = SavedEventFactory(user_id=user_id)
    client.put(f"{COLLECTIONS}/{collection['id']}/events/{saved.id}")

    assert client.delete(f"{COLLECTIONS}/{collection['id']}/events/{saved.id}").status_code == 204

    assert body_of(client.get(f"{COLLECTIONS}/{collection['id']}/events")) == []
    from apps.personalization.models import SavedEvent

    assert SavedEvent.objects.using(PERSONAL).filter(id=saved.id).exists()


def test_another_users_save_cannot_be_assigned():
    client = client_for(pro_user())
    collection = created(client)
    someone_elses = SavedEventFactory(user_id=UserFactory().pk)

    response = client.put(f"{COLLECTIONS}/{collection['id']}/events/{someone_elses.id}")

    assert response.status_code == 404


# ── The gate ───────────────────────────────────────────────────────────────────────


def test_a_free_user_creating_a_collection_is_refused_with_an_upgrade_hint():
    client = client_for(UserFactory())

    response = create(client)

    assert response.status_code == 409
    body = body_of(response)
    assert body["code"] == "collections_pro_required"
    assert body["details"]["cap"] == 0
    assert body["details"]["upgrade_hint"]


def test_the_refusal_carries_no_modal_shaped_field():
    """A cap that interrupts is a cap that trains people to dismiss prompts."""
    client = client_for(UserFactory())

    details = body_of(create(client))["details"]

    assert set(details) == {"cap", "upgrade_hint"}
    for modal_shaped in ("modal", "title", "actions", "dismissable"):
        assert modal_shaped not in details


def test_a_refused_create_writes_nothing():
    client = client_for(UserFactory())

    create(client)

    assert body_of(client.get(COLLECTIONS)) == []


def test_a_free_user_may_still_list_their_collections():
    """Reads are never gated — a list that hid them would be the deletion the brief
    forbids, as far as the user could tell."""
    client = client_for(UserFactory())

    assert client.get(COLLECTIONS).status_code == 200


# ── The lapse: what survives, and what does not ────────────────────────────────────


@pytest.fixture
def lapsed_with_a_collection():
    """A user who was Pro, made a collection with a save in it, and then lapsed."""
    user = UserFactory()
    live = SubscriptionFactory(user_id=user.pk, status=SubscriptionStatus.ACTIVE)
    client = client_for(user)
    collection = created(client, "Weekend")
    saved = SavedEventFactory(user_id=user.pk)
    client.put(f"{COLLECTIONS}/{collection['id']}/events/{saved.id}")

    # The subscription ends. Nothing of theirs is deleted.
    from apps.identity.models import Subscription

    Subscription.objects.using(PERSONAL).filter(id=live.id).update(
        status=SubscriptionStatus.CANCELED
    )
    return client, collection, saved


def test_a_lapsed_user_still_sees_their_collections(lapsed_with_a_collection):
    client, collection, _saved = lapsed_with_a_collection

    listed = body_of(client.get(COLLECTIONS))

    assert [row["name"] for row in listed] == ["Weekend"]
    assert listed[0]["item_count"] == 1


def test_a_lapsed_user_still_reads_what_is_inside(lapsed_with_a_collection):
    client, collection, saved = lapsed_with_a_collection

    events = body_of(client.get(f"{COLLECTIONS}/{collection['id']}/events"))

    assert [row["id"] for row in events] == [str(saved.id)]


def test_a_lapsed_user_may_still_unassign(lapsed_with_a_collection):
    """**Named by the acceptance criterion.** This is how they tidy up, and refusing it
    would trap them with an arrangement they cannot change."""
    client, collection, saved = lapsed_with_a_collection

    response = client.delete(f"{COLLECTIONS}/{collection['id']}/events/{saved.id}")

    assert response.status_code == 204


def test_a_lapsed_user_may_still_rename(lapsed_with_a_collection):
    """Gating this would mean they cannot fix a typo in a name they wrote themselves."""
    client, collection, _saved = lapsed_with_a_collection

    response = client.patch(
        f"{COLLECTIONS}/{collection['id']}",
        {"name": "Weekends"},
        content_type="application/json",
    )

    assert response.status_code == 200


def test_a_lapsed_user_may_still_reorder(lapsed_with_a_collection):
    client, collection, _saved = lapsed_with_a_collection

    response = client.put(
        f"{COLLECTIONS}/order",
        {"collection_ids": [collection["id"]]},
        content_type="application/json",
    )

    assert response.status_code == 200


def test_a_lapsed_user_may_still_delete(lapsed_with_a_collection):
    """Gating this would trap them with data they want gone — the inverse of what the
    never-delete constraint is for."""
    client, collection, _saved = lapsed_with_a_collection

    assert client.delete(f"{COLLECTIONS}/{collection['id']}").status_code == 204


def test_a_lapsed_user_cannot_create_another(lapsed_with_a_collection):
    client, _collection, _saved = lapsed_with_a_collection

    response = create(client, "Gigs")

    assert response.status_code == 409
    assert body_of(response)["code"] == "collections_pro_required"


def test_a_lapsed_user_cannot_add_another_save(lapsed_with_a_collection):
    """Without this, the cap would limit how many collections exist and not how much they
    are used."""
    client, collection, _saved = lapsed_with_a_collection
    user_id = client.session["_auth_user_id"]
    another = SavedEventFactory(user_id=user_id)

    response = client.put(f"{COLLECTIONS}/{collection['id']}/events/{another.id}")

    assert response.status_code == 409
    assert body_of(response)["code"] == "collections_pro_required"


# ── Scoping, across the whole surface ──────────────────────────────────────────────


def another_users_collection() -> dict:
    return created(client_for(pro_user()), "Theirs")


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("patch", "{id}", {"name": "Mine now"}),
        ("delete", "{id}", None),
        ("get", "{id}/events", None),
        ("put", "{id}/events/{save}", None),
        ("delete", "{id}/events/{save}", None),
    ],
    ids=["rename", "delete", "read-events", "assign", "unassign"],
)
def test_another_users_collection_is_not_found_on_every_endpoint(method, path, payload):
    """**404, never 403.** A "forbidden" answer confirms the row exists, and a collection's
    name is content somebody wrote.

    Parametrized across the surface rather than written once: "this one endpoint forgot the
    user id" is the bug that hides in eight endpoints.
    """
    theirs = another_users_collection()
    client = client_for(pro_user())
    saved = SavedEventFactory(user_id=client.session["_auth_user_id"])
    url = f"{COLLECTIONS}/{path.format(id=theirs['id'], save=saved.id)}"

    if payload is None:
        response = getattr(client, method)(url)
    else:
        response = getattr(client, method)(url, payload, content_type="application/json")

    assert response.status_code == 404, f"{method.upper()} {url} answered {response.status_code}"


def test_a_collection_that_does_not_exist_is_not_found():
    client = client_for(pro_user())

    assert client.get(f"{COLLECTIONS}/{uuid4()}/events").status_code == 404


@pytest.mark.parametrize(
    "method,path",
    [("get", ""), ("post", ""), ("put", "/order")],
    ids=["list", "create", "reorder"],
)
def test_an_anonymous_caller_is_refused_everywhere(method, path):
    """The user comes from the session and never from a payload (AD-12)."""
    from django.test import Client

    response = getattr(Client(), method)(
        f"{COLLECTIONS}{path}", {}, content_type="application/json"
    )

    assert response.status_code in (401, 403)
