"""The Detail Screen's conflict: the caller's active pair for one saved event.

**What these tests pin**, grouped by the rule each one protects:

- **the payload names the pair** — its id, the side the save clashes with, and the
  three choices the server allows;
- **only an active pair is reported** — a resolved pair is history and a cleared one is
  nobody's decision, so neither produces an indicator;
- **the choices are the saved side's** — `keep_both`, `edit_new` and `skip_public`, and
  **never** `delete_new`: the Detail Screen acts on the save, and deleting the user's
  personal event is not a choice this surface should present;
- **an anonymous caller gets nothing** — `personal` is `None`, and the `personal` schema
  is never queried;
- **the pair names the save row, not the catalog event** — the read resolves the user's
  own save row first, and finds the pair by that row's id.

The pair's sides are stored sorted, so "the other side" is computed from the **kinds**,
never from `left`/`right`.
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone as django_timezone

from apps.personalization.models import ConflictPair, PersonalEvent, SavedEvent
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory, VenueFactory
from tests.personalization.factories import (
    ConflictPairFactory,
    PersonalEventFactory,
    SavedEventFactory,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()

#: The endpoint resolves "now" itself, so the event it looks for is one that has not
#: started yet. Pinned at import time so every instant in the file is measured from one
#: "now".
NOW = django_timezone.now()
START = NOW + timedelta(days=1)


def make_user(email=None):
    return User.objects.create_user(
        email=email or f"sam-{uuid4().hex}@example.test", password="pw"
    )


def signed_in(user=None):
    client = Client()
    client.force_login(user or make_user())
    return client


def make_event(**overrides):
    """A published, upcoming public event."""
    fields = {
        "title": "Brooklyn Tech Meetup",
        "venue": VenueFactory(city="Los Angeles"),
        "start_time_utc": START,
        "last_seen_at": NOW,
    }
    fields.update(overrides)
    return EventFactory(**fields)


def detail_url(event):
    return f"/api/events/{event.id}"


def make_saved(user, event):
    """The user's save row for this catalog event."""
    return SavedEventFactory(
        user_id=user.pk,
        event_id=event.id,
        start_utc=event.start_time_utc,
        end_utc=event.start_time_utc + timedelta(hours=2),
    )


def make_pair(user, saved, personal, **overrides):
    """An active pair naming the save and the personal event.

    **The sides are stored sorted** on `(kind, id)` — so the pair row does not say which
    side is "the new one". The factory's defaults put the personal event on the left,
    which is what the sort produces for a personal id that sorts before a saved one; the
    test that pins the sort's independence sets them the other way round on purpose.
    """
    fields = {
        "user_id": user.pk,
        "kind": ConflictPair.Kind.TIME,
        "left_kind": ConflictPair.SideKind.PERSONAL_EVENT,
        "left_id": personal.id,
        "right_kind": ConflictPair.SideKind.SAVED_EVENT,
        "right_id": saved.id,
        "status": ConflictPair.Status.ACTIVE,
    }
    fields.update(overrides)
    return ConflictPairFactory(**fields)


def test_the_payload_names_the_pair_and_the_other_side():
    """The signed-in caller receives the pair, the other side and the choices."""
    user = make_user()
    event = make_event()
    saved = make_saved(user, event)
    personal = PersonalEventFactory(user_id=user.pk, name="Dentist")
    pair = make_pair(user, saved, personal)

    body = signed_in(user).get(detail_url(event)).json()

    conflict = body["personal"]["conflict"]
    assert conflict is not None
    assert conflict["pair_id"] == str(pair.id)
    assert conflict["kind"] == "time"
    assert conflict["other_side"]["id"] == str(personal.id)
    assert conflict["other_side"]["kind"] == "personal_event"
    assert conflict["other_side"]["name"] == "Dentist"


def test_the_payload_names_the_save_row_s_own_id():
    """The saved side's id is the **save row's**, not the catalog event's.

    A resolution names a side by `(kind, id)`, and the server checks it against the
    pair's own two sides. The pair stores a `SavedEvent` by **that row's id** — so a
    `skip_public` has to name the save row, and the client cannot derive it from the
    catalog event id the Detail Screen is keyed by. So the payload carries it.
    """
    user = make_user()
    event = make_event()
    saved = make_saved(user, event)
    personal = PersonalEventFactory(user_id=user.pk, name="Dentist")
    make_pair(user, saved, personal)

    body = signed_in(user).get(detail_url(event)).json()

    conflict = body["personal"]["conflict"]
    assert conflict["saved_side_id"] == str(saved.id)
    # **Not** the catalog event's id. The two are different records and confusing them
    # would make the resolution name a side the pair does not have.
    assert conflict["saved_side_id"] != str(event.id)


def test_the_choices_are_the_saved_side_s_three():
    """`keep_both`, `edit_new` and `skip_public` — and never `delete_new`.

    The Detail Screen acts on the **save**. The pair's union would also offer
    `delete_new`, and deleting the user's personal event is not a choice this surface
    should present.
    """
    user = make_user()
    event = make_event()
    saved = make_saved(user, event)
    personal = PersonalEventFactory(user_id=user.pk)
    make_pair(user, saved, personal)

    body = signed_in(user).get(detail_url(event)).json()

    actions = body["personal"]["conflict"]["actions"]
    assert set(actions) == {"keep_both", "edit_new", "skip_public"}
    assert "delete_new" not in actions


def test_an_event_with_no_pair_has_no_conflict():
    """`None` means "there is nothing to decide" — not "the screen failed to look"."""
    user = make_user()
    event = make_event()
    make_saved(user, event)

    body = signed_in(user).get(detail_url(event)).json()

    assert body["personal"]["conflict"] is None


def test_an_event_that_was_never_saved_has_no_conflict():
    """Without a save row there is nothing for a pair to name."""
    user = make_user()
    event = make_event()

    body = signed_in(user).get(detail_url(event)).json()

    assert body["personal"]["conflict"] is None
    assert body["personal"]["saved"] is False


def test_a_resolved_pair_is_not_reported():
    """A resolved pair is history. There is no choice left to make."""
    user = make_user()
    event = make_event()
    saved = make_saved(user, event)
    personal = PersonalEventFactory(user_id=user.pk)
    make_pair(
        user,
        saved,
        personal,
        status=ConflictPair.Status.RESOLVED,
        resolution=ConflictPair.Resolution.KEEP_BOTH,
        resolved_at=NOW,
    )

    body = signed_in(user).get(detail_url(event)).json()

    assert body["personal"]["conflict"] is None


def test_a_cleared_pair_is_not_reported():
    """A cleared pair ended because a side went away — nobody chose it."""
    user = make_user()
    event = make_event()
    saved = make_saved(user, event)
    personal = PersonalEventFactory(user_id=user.pk)
    make_pair(
        user,
        saved,
        personal,
        status=ConflictPair.Status.CLEARED_BY_STATE_CHANGE,
        resolved_at=NOW,
    )

    body = signed_in(user).get(detail_url(event)).json()

    assert body["personal"]["conflict"] is None


def test_the_other_side_is_found_whatever_order_the_pair_stores_its_sides_in():
    """The pair row sorts its sides by id, so `left` is not "the saved one".

    The read finds the save by its **kind**, and the other side is the one that is not
    the save. A pair stored the other way round must read the same.
    """
    user = make_user()
    event = make_event()
    saved = make_saved(user, event)
    personal = PersonalEventFactory(user_id=user.pk, name="Dentist")
    make_pair(
        user,
        saved,
        personal,
        left_kind=ConflictPair.SideKind.SAVED_EVENT,
        left_id=saved.id,
        right_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        right_id=personal.id,
    )

    body = signed_in(user).get(detail_url(event)).json()

    conflict = body["personal"]["conflict"]
    assert conflict["other_side"]["id"] == str(personal.id)
    assert conflict["other_side"]["name"] == "Dentist"


def test_another_users_pair_is_not_reported():
    """The pair is scoped to the caller, so another user's clash is not this one's."""
    owner = make_user()
    other = make_user()
    event = make_event()
    owner_saved = make_saved(owner, event)
    owner_personal = PersonalEventFactory(user_id=owner.pk)
    make_pair(owner, owner_saved, owner_personal)

    body = signed_in(other).get(detail_url(event)).json()

    assert body["personal"]["conflict"] is None


def test_an_anonymous_caller_gets_nothing_personal():
    """`personal` is `None` — the public facts and nothing else."""
    event = make_event()

    body = Client().get(detail_url(event)).json()

    assert body["personal"] is None


def test_the_anonymous_path_never_queries_the_personal_schema():
    """**The strongest statement about a leak is that the query never happened.**"""
    event = make_event()

    with CaptureQueriesContext(connections[PERSONAL]) as captured:
        Client().get(detail_url(event))

    assert captured.captured_queries == []


def test_the_signed_in_path_does_query_the_personal_schema():
    """The control for the test above — a signed-in caller *does* read `personal`.

    Without this, "the anonymous path queried nothing" could be true because the
    endpoint queries nothing for anyone.
    """
    user = make_user()
    event = make_event()

    with CaptureQueriesContext(connections[PERSONAL]) as captured:
        signed_in(user).get(detail_url(event))

    assert captured.captured_queries != []


def test_a_pair_naming_a_deleted_personal_event_reads_as_unavailable():
    """The pair is real, but its other side is gone — so the name is absent, not blank.

    The client renders "event no longer available" rather than showing nothing.
    """
    user = make_user()
    event = make_event()
    saved = make_saved(user, event)
    personal = PersonalEventFactory(user_id=user.pk)
    make_pair(user, saved, personal)
    PersonalEvent.objects.using(PERSONAL).filter(pk=personal.id).delete()

    body = signed_in(user).get(detail_url(event)).json()

    conflict = body["personal"]["conflict"]
    assert conflict is not None
    assert conflict["other_side"]["id"] == str(personal.id)
    assert conflict["other_side"]["name"] is None


def test_the_saved_events_own_row_is_what_the_pair_is_found_by():
    """The pair names the **save row**, and the save row is the user's own.

    Two saves of the same catalog event by the same user cannot exist — the unique
    constraint on `(user_id, event_id)` says so — so the read finds one row and looks
    the pair up by that row's id. A pair naming a *different* save row is not this
    event's pair.
    """
    user = make_user()
    event = make_event()
    saved = make_saved(user, event)
    other_save = SavedEventFactory(user_id=user.pk)
    personal = PersonalEventFactory(user_id=user.pk)
    make_pair(user, other_save, personal, right_id=other_save.id)

    body = signed_in(user).get(detail_url(event)).json()

    assert body["personal"]["conflict"] is None
    # The save itself is still found — the row lookup works.
    assert body["personal"]["saved"] is True
    assert saved.id != other_save.id


def test_the_pair_is_not_found_for_a_save_the_user_does_not_own():
    """The save row is scoped to the caller, so another user's save is not found."""
    owner = make_user()
    other = make_user()
    event = make_event()
    owner_save = make_saved(owner, event)
    personal = PersonalEventFactory(user_id=owner.pk)
    make_pair(owner, owner_save, personal)

    # The other user has their own save of the same catalog event.
    make_saved(other, event)

    body = signed_in(other).get(detail_url(event)).json()

    assert body["personal"]["conflict"] is None


def test_a_duplicate_pair_offers_update_rather_than_edit():
    """The **kind** decides the middle action's name.

    A duplicate pair offers `update_existing`, not `edit_new` — the same map the
    resolve endpoint enforces, read from one source rather than a second list.
    """
    user = make_user()
    event = make_event()
    saved = make_saved(user, event)
    personal = PersonalEventFactory(user_id=user.pk)
    make_pair(user, saved, personal, kind=ConflictPair.Kind.DUPLICATE)

    body = signed_in(user).get(detail_url(event)).json()

    actions = body["personal"]["conflict"]["actions"]
    assert set(actions) == {"keep_both", "update_existing", "skip_public"}


def test_the_openapi_schema_carries_the_new_field():
    """The regenerated client has to know about `conflict` — the contract is the gate."""
    import json

    from django.test import Client as DjangoClient

    spec = json.loads(DjangoClient().get("/api/openapi.json").content)
    personal = spec["components"]["schemas"]["DetailPersonalOut"]
    assert "conflict" in personal["properties"]
    # **And the save row's id is in the contract too.** The client has to be able to
    # name the saved side, and an untyped field is a field the client cannot read.
    conflict = spec["components"]["schemas"]["DetailConflictOut"]
    assert "saved_side_id" in conflict["properties"]
    assert "saved_side_id" in conflict["required"]
