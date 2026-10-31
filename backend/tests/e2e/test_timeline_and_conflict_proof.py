"""The Unified Timeline and the Conflict Review, end to end.

**Why one scenario and not fifteen.** The point of a proof is that the steps
*compose*. Seven work items of this intent were built and each was tested in isolation;
the failures that matter live in the seams between them. A chain of independent tests
proves each step and not the whole — a pair created in one test and resolved in another
is not the same pair, and a Timeline read in a third test sees a week that no longer
has the clash in it.

So the scenario is one test, one user, one database, and one transaction's worth of
shared state.

**Why this scenario drives the HTTP stack, and not the services.** The digest proof
called the services directly, and that was right for its claim: "the card and the
breakdown are the same persisted row". This intent's claim is a **round trip**: the
pair id in the 409 is the pair id in the list is the pair id in the resolve response, and
the Timeline's `conflict` flag follows FR-58 for that same pair. A service-level call
cannot observe a 409 at all — the 409 *is* the seam. So the scenario posts to the real
endpoints through Django, as a browser would, with the session cookie and the CSRF
token a browser would send.

**What is proved here is the half a browser cannot see: the seams.** The rendered half
was proved by the three frontend items — the Timeline screen's own tests assert the
rendered week, the conflicts page's assert the rendered pair, and the Detail Screen's
assert the rendered prompt. What those tests cannot see is whether the **pair** the
screen renders is the pair the server created, and whether the **flag** the screen
draws is the flag the server decided.

**The claims, one by one.**

1. **The week.** A personal event and an overlapping saved public event: the Timeline
   read for that week returns **both**, on the right local day, both flagged
   `conflict`.
2. **The review.** The conflicts list returns the pair **active**, with the actions the
   pair offers — and the actions are the ones the resolve endpoint enforces, read from
   the same map.
3. **The resolution.** Each action moves the pair to `resolved` with its own wording,
   and the Timeline's flag follows FR-58: `keep_both` **keeps** it, every other
   resolution **clears** it.
4. **The detail path.** A clashing save answers **409** with a pair the resolve
   endpoint can close — the same pair id, and the sides named with their kinds.
5. **Isolation.** A second user sees **none** of the first user's pairs or blocks.

**The last claim is separate for a reason.** Isolation is not a seam — it is a
property of every query, and it holds or fails independently of whether the chain
composes. A test that proved it inside the main scenario would have to run its
assertions *after* the first user's pair was resolved, by which time the pair is
`resolved` and the scoping claim is about a different state than the one that matters.
So isolation is its own test, with its own user, at the point where the first user's
pair is **active** — which is the state a scoping bug would leak.

**The 409's `event_id` is the *save row's* id, not the catalog event's.** That is not
an accident of the implementation: the pair stores the save by the personal row's id,
so the pair can name a side that exists. A client that resolved the pair using the
catalog event's id would be asking the server to act on a record that is not one of the
pair's two — and the server refuses it with `side_not_in_pair`. The scenario asserts
the 409's ids and then resolves with **those** ids, so the round trip is proven to be
possible rather than merely to look possible.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from django.contrib.auth import get_user_model

from apps.ingestion.models import Event
from apps.personalization.models import ConflictPair, SavedEvent
from shared.db import CATALOG, PERSONAL
from tests.csrf import CsrfClient
from tests.ingestion.factories import EventFactory, VenueFactory
from tests.personalization.factories import DigestPreferenceFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()

#: The instant the scenario is "now". 2026-11-04 16:00 UTC is 09:00 in Los Angeles (PST).
NOW = datetime(2026, 11, 4, 16, 0, tzinfo=UTC)

#: The zone the user's days are cut in.
ZONE = "America/Los_Angeles"

#: The week under test. 2026-11-04 is a **Wednesday**, so the week's Monday is the
#: 2nd and its Sunday the 8th. Asking for a Wednesday rather than the Monday is
#: deliberate: `week=` accepts *any* date in the wanted week, and that is the property
#: the frontend's link relies on — the link names the day the event starts on, not the
#: Monday.
WEDNESDAY = "2026-11-04"

#: The instant the personal event starts: 2026-11-04 19:00 in Los Angeles.
#: That is 2026-11-05 03:00 UTC — still the Wednesday in the user's own zone.
START_UTC = datetime(2026, 11, 5, 3, 0, tzinfo=UTC)
END_UTC = START_UTC + timedelta(hours=2)

#: The instant the catalog event starts, overlapping the personal event by an hour.
CATALOG_START_UTC = START_UTC + timedelta(hours=1)
CATALOG_END_UTC = CATALOG_START_UTC + timedelta(hours=2)


# ── The fixtures ─────────────────────────────────────────────────────────────────────


def _signed_in(email: str = "sam@example.test") -> CsrfClient:
    """A client whose session identifies a real user.

    It is a `CsrfClient`: the personal endpoints resolve their user through `identity`'s
    resolver, and the resolver checks CSRF on every unsafe method (D13). The token is
    fetched on the first unsafe request and travels in the `X-CSRFToken` header.
    """
    client = CsrfClient()
    client.force_login(User.objects.create_user(email=email, password="pw"))
    return client


def _user_id(client: CsrfClient) -> UUID:
    """The user's id, as the session holds it."""
    return UUID(client.session["_auth_user_id"])


def _preference(user_id: UUID) -> None:
    """The user's zone.

    **The Timeline cuts its days in this zone**, so without it the week would be cut in
    UTC and the local-day assertions would be about the wrong days.
    """
    DigestPreferenceFactory(
        user_id=user_id,
        timezone=ZONE,
        city="Los Angeles",
        city_source="choice",
    )


def _catalog_event(*, start_utc: datetime, end_utc: datetime, title: str = "Brooklyn Tech Meetup"):
    """A published, upcoming catalog event.

    **`last_seen_at` is pinned to `NOW`.** FR-14's staleness bound is measured from it
    against the test's clock, and the column's default is the wall clock — so an event
    built with the default would be days stale against a `NOW` in the future, and the
    catalog read would drop it before the save ever saw it.

    The event is **published** and **not superseded**, because `get_public_event` — the
    catalog's published interface — omits anything else, and a save of an unpublished
    event is a 404.
    """
    return EventFactory(
        title=title,
        venue=VenueFactory(city="Los Angeles", venue_fingerprint=f"venue-{title}"),
        start_time_utc=start_utc,
        end_time_utc=end_utc,
        last_seen_at=NOW,
    )


def _create_personal_event(client: CsrfClient, *, name: str = "Dentist") -> dict:
    """A personal event on the user's calendar.

    **The zone is the user's own.** The event is 19:00 local, and the local day it
    lands on is the thing the Timeline's placement is about.
    """
    response = client.post(
        "/api/personal/events",
        data={
            "name": name,
            "start_time_utc": START_UTC.isoformat().replace("+00:00", "Z"),
            "start_time_tz": ZONE,
            "end_time_utc": END_UTC.isoformat().replace("+00:00", "Z"),
        },
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    return response.json()


def _save_public_event(client: CsrfClient, event: Event):
    """Save a public event onto the user's calendar.

    **No body.** The endpoint takes the catalog event's id in the path and nothing else,
    so the request is a bare POST — the shape the frontend's generated client sends.
    """
    return client.post(f"/api/personal/saved-events/{event.id}")


def _week(client: CsrfClient, *, week: str = WEDNESDAY) -> dict:
    """The Timeline read for one week."""
    response = client.get(f"/api/personal/timeline?week={week}")
    assert response.status_code == 200, response.content
    return response.json()


def _conflicts(client: CsrfClient) -> dict:
    """The conflicts list."""
    response = client.get("/api/personal/conflicts")
    assert response.status_code == 200, response.content
    return response.json()


def _blocks(week: dict) -> list[dict]:
    """Every block in the week, flattened out of its seven days."""
    return [block for day in week["days"] for block in day["blocks"]]


def _block_on(week: dict, local_date: str) -> list[dict]:
    """The blocks on one local day."""
    return next(day["blocks"] for day in week["days"] if day["date"] == local_date)


# ── The scenario ─────────────────────────────────────────────────────────────────────


def test_the_week_the_review_and_the_resolution_are_one_pair():
    """**The whole intent, in one path.**

    The chain: a user with a zone, a personal event, an overlapping public event saved
    onto their calendar, the 409, the conflicts list, the Timeline read, the resolution
    — and the claim that the **same pair** is what every one of them names, and that
    the Timeline's flag follows FR-58 for that pair.

    **The resolution is `keep_both`**, because it is the one action that changes
    *nothing* about the events — so the pair's two sides are still on the calendar
    afterwards, and the flag's fate can be observed without a second scenario. FR-58
    says "Keep both" leaves a **permanent, calm reminder** on both events; every other
    resolution removes it. The other actions are proved separately, below, because each
    one changes the calendar.
    """
    client = _signed_in()
    user_id = _user_id(client)
    _preference(user_id)

    personal = _create_personal_event(client)
    catalog_event = _catalog_event(start_utc=CATALOG_START_UTC, end_utc=CATALOG_END_UTC)

    # ── The clash ────────────────────────────────────────────────────────────────────
    # The save overlaps the personal event by an hour, so it answers **409** with the
    # pair the user must answer.
    saved_response = _save_public_event(client, catalog_event)
    assert saved_response.status_code == 409, saved_response.content
    clash = saved_response.json()
    assert clash["code"] == "scheduling_conflict", clash
    assert len(clash["details"]["conflicts"]) == 1, "one clash, not two"

    conflict = clash["details"]["conflicts"][0]
    pair_id = conflict["pair_id"]

    # **The 409 names both sides, with their kinds.** The client has to render the
    # three actions and post one of them back, and a resolution names a side — so the
    # kind is part of the answer, not a detail the client could guess.
    assert conflict["new_side"]["kind"] == "saved_event"
    assert conflict["other_side"]["kind"] == "personal_event"
    assert conflict["other_side"]["id"] == personal["id"], (
        "the clash is against the personal event the scenario created"
    )
    assert conflict["actions"] == ["edit_new", "keep_both", "skip_public"], (
        "a saved side's actions are the personal side's edit and the saved side's skip"
    )

    # **The 409's `event_id` is the save row's id, not the catalog event's.** The pair
    # stores the save by the personal row's id — that is the id a resolution names —
    # and this is the point at which a client could plausibly get it wrong.
    save_row_id = clash["details"]["event_id"]
    assert save_row_id != str(catalog_event.id), (
        "the 409 names the save row, not the catalog event; the pair names a row that "
        "exists on the personal side"
    )
    assert SavedEvent.objects.using(PERSONAL).filter(user_id=user_id, pk=save_row_id).exists()

    # ── The week ────────────────────────────────────────────────────────────────────
    week = _week(client)

    # **Seven days, always.** The screen draws seven columns and should not have to
    # know whether the week has anything in it.
    assert len(week["days"]) == 7
    assert week["timezone"] == ZONE, "the days are cut in the user's own zone"

    # The week is named by its Monday and Sunday, even though the request asked for a
    # Wednesday. The frontend's link names the *day* the event starts on, and the
    # server resolves the Monday — that is the property this asserts.
    assert week["week_start"] == "2026-11-02", "the Monday of the week asked for"
    assert week["week_end"] == "2026-11-08", "the Sunday of the week asked for"

    blocks = _blocks(week)
    assert len(blocks) == 2, "the personal event and the saved public event"

    # **Both on the right local day.** The personal event starts at 19:00 Los Angeles
    # on the Wednesday; the public event an hour later, so it starts at 20:00 — still
    # the Wednesday. Neither is on the Thursday, even though both are on the 5th in UTC.
    wednesday = _block_on(week, "2026-11-04")
    assert len(wednesday) == 2, (
        f"both events are on the Wednesday; the week's blocks are "
        f"{[(day['date'], len(day['blocks'])) for day in week['days']]}"
    )
    assert _block_on(week, "2026-11-05") == [], "the Thursday is empty"

    # **The kinds are the two vocabularies, kept apart.** A personal block carries the
    # personal event's id; a public block carries the **catalog** event's id, because
    # that is the id the screen routes to.
    personal_block = next(block for block in wednesday if block["kind"] == "personal")
    public_block = next(block for block in wednesday if block["kind"] == "public")
    assert personal_block["id"] == personal["id"]
    assert public_block["id"] == str(catalog_event.id), (
        "a public block carries the catalog event's id, so the screen routes to it"
    )
    assert public_block["name"] == "Brooklyn Tech Meetup", (
        "the public block is named by the catalog's title"
    )

    # **Both flagged.** The pair is active, and an active pair flags both sides.
    assert personal_block["conflict"] is True
    assert public_block["conflict"] is True

    # ── The review ──────────────────────────────────────────────────────────────────
    listing = _conflicts(client)
    assert len(listing["active"]) == 1, "one pair needs a decision"
    assert listing["resolved"] == [], "nothing has been answered yet"

    pair = listing["active"][0]
    assert pair["pair_id"] == pair_id, "the list names the pair the 409 named"
    assert pair["status"] == "active"
    assert pair["kind"] == "time"

    # **The list offers the union across the pair's two sides.** A pair with a saved
    # side can be answered on either side, so it offers the personal side's
    # `delete_new` *and* the saved side's `skip_public` — both are real choices.
    assert pair["actions"] == ["delete_new", "edit_new", "keep_both", "skip_public"], (
        "the list offers every action legal against either side"
    )

    # **Both sides are named, so the pair can be shown without a second request.**
    assert pair["left"]["kind"] == "personal_event"
    assert pair["right"]["kind"] == "saved_event"
    assert pair["right"]["id"] == save_row_id, "the saved side is the save row"
    assert pair["left"]["available"] is True
    assert pair["right"]["available"] is True

    # ── The resolution ──────────────────────────────────────────────────────────────
    resolved = client.post(
        f"/api/personal/events/conflicts/{pair_id}/resolve",
        data={"resolution": "keep_both", "side": {"kind": "saved_event", "id": save_row_id}},
        content_type="application/json",
    )
    assert resolved.status_code == 200, resolved.content
    body = resolved.json()
    assert body["pair_id"] == pair_id
    assert body["resolution"] == "keep_both"
    assert body["status"] == "resolved", "the pair is closed, whatever the choice was"

    # **The pair is now history.** It is in the resolved list, with its answer, and it
    # is no longer active.
    after = _conflicts(client)
    assert after["active"] == [], "nothing needs a decision any more"
    assert len(after["resolved"]) == 1
    assert after["resolved"][0]["pair_id"] == pair_id
    assert after["resolved"][0]["resolution"] == "keep_both"
    assert after["resolved"][0]["actions"] == [], "a resolved pair offers nothing"

    # ── The flag follows FR-58 ──────────────────────────────────────────────────────
    # "Keep both" leaves a **permanent, calm reminder** on both events. Every other
    # resolution removes it — the conflict the user was reminded about is gone.
    after_week = _week(client)
    after_wednesday = _block_on(after_week, "2026-11-04")
    assert len(after_wednesday) == 2, "keep both leaves both events on the calendar"
    assert all(block["conflict"] for block in after_wednesday), (
        "FR-58: keep both keeps the indicator on both events, permanently"
    )


# ── The other resolutions ───────────────────────────────────────────────────────────


def test_skip_public_releases_the_save_and_clears_the_indicator():
    """**`skip_public` — the action that removes something.**

    The save is released, the pair is answered, and the Timeline's flag goes.

    **The order matters and the server gets it right.** The resolution is recorded on the
    pair *before* the save is released, and the release is told to leave that one pair
    alone. Without that, the unsave would close the pair as `cleared_by_state_change` —
    NULLing the answer the user just gave and turning their choice into "nobody
    answered", which would drop it out of the Resolved list entirely.
    """
    client = _signed_in()
    user_id = _user_id(client)
    _preference(user_id)

    _create_personal_event(client)
    catalog_event = _catalog_event(start_utc=CATALOG_START_UTC, end_utc=CATALOG_END_UTC)

    saved_response = _save_public_event(client, catalog_event)
    assert saved_response.status_code == 409, saved_response.content
    conflict = saved_response.json()["details"]["conflicts"][0]
    pair_id = conflict["pair_id"]
    save_row_id = saved_response.json()["details"]["event_id"]

    resolved = client.post(
        f"/api/personal/events/conflicts/{pair_id}/resolve",
        data={"resolution": "skip_public", "side": {"kind": "saved_event", "id": save_row_id}},
        content_type="application/json",
    )
    assert resolved.status_code == 200, resolved.content
    assert resolved.json()["resolution"] == "skip_public"

    # **The save is gone**, and only the save — the personal event is untouched, because
    # `skip_public` acts on the saved side and on nothing else.
    assert not SavedEvent.objects.using(PERSONAL).filter(user_id=user_id).exists()
    assert ConflictPair.objects.using(PERSONAL).get(pk=pair_id).status == "resolved"

    # **The pair is history, and it carries the answer.** A pair closed as
    # `cleared_by_state_change` would carry a NULL resolution and would not be listed
    # at all — so "in the resolved list, with the resolution" is the sharp assertion.
    listing = _conflicts(client)
    assert listing["active"] == []
    assert len(listing["resolved"]) == 1
    assert listing["resolved"][0]["resolution"] == "skip_public"

    # **The indicator is gone.** The conflict is dealt with; the reminder goes.
    week = _week(client)
    blocks = _blocks(week)
    assert len(blocks) == 1, "the saved event is released, so only the personal event is left"
    assert blocks[0]["kind"] == "personal"
    assert blocks[0]["conflict"] is False, "every resolution but keep both removes the indicator"


def test_delete_new_removes_the_personal_event_and_clears_the_indicator():
    """**`delete_new` — the other action that removes something.**

    The personal event is deleted, through the one path to delete an event, and the
    pair is answered.
    """
    client = _signed_in()
    user_id = _user_id(client)
    _preference(user_id)

    personal = _create_personal_event(client)
    catalog_event = _catalog_event(start_utc=CATALOG_START_UTC, end_utc=CATALOG_END_UTC)

    saved_response = _save_public_event(client, catalog_event)
    assert saved_response.status_code == 409, saved_response.content
    conflict = saved_response.json()["details"]["conflicts"][0]
    pair_id = conflict["pair_id"]

    resolved = client.post(
        f"/api/personal/events/conflicts/{pair_id}/resolve",
        data={
            "resolution": "delete_new",
            "side": {"kind": "personal_event", "id": personal["id"]},
        },
        content_type="application/json",
    )
    assert resolved.status_code == 200, resolved.content
    assert resolved.json()["resolution"] == "delete_new"

    # **The personal event is gone; the save is not.** `delete_new` acts on the personal
    # side and on nothing else.
    from apps.personalization.models import PersonalEvent

    assert not PersonalEvent.objects.using(PERSONAL).filter(user_id=user_id).exists()
    assert SavedEvent.objects.using(PERSONAL).filter(user_id=user_id).exists()

    listing = _conflicts(client)
    assert listing["active"] == []
    assert len(listing["resolved"]) == 1
    assert listing["resolved"][0]["resolution"] == "delete_new"

    # **The indicator is gone.**
    week = _week(client)
    blocks = _blocks(week)
    assert len(blocks) == 1
    assert blocks[0]["kind"] == "public"
    assert blocks[0]["conflict"] is False


def test_edit_new_keeps_both_events_and_clears_the_indicator():
    """**`edit_new` — the action that changes nothing, and is not "keep both".

    `edit_new` opens the personal side in the edit sheet; the edit happens after the
    answer. So immediately after the resolution both events are still there, and the
    indicator is **gone** — which is the difference from `keep_both`, and the sharpest
    contrast the two actions offer.

    **This is why the two are separate tests.** A single test that resolved both ways
    would have to rebuild the clash between the resolutions, and a scenario that
    rebuilds its own subject is a scenario that can pass for the wrong reason.
    """
    client = _signed_in()
    user_id = _user_id(client)
    _preference(user_id)

    personal = _create_personal_event(client)
    catalog_event = _catalog_event(start_utc=CATALOG_START_UTC, end_utc=CATALOG_END_UTC)

    saved_response = _save_public_event(client, catalog_event)
    assert saved_response.status_code == 409, saved_response.content
    conflict = saved_response.json()["details"]["conflicts"][0]
    pair_id = conflict["pair_id"]

    resolved = client.post(
        f"/api/personal/events/conflicts/{pair_id}/resolve",
        data={"resolution": "edit_new", "side": {"kind": "personal_event", "id": personal["id"]}},
        content_type="application/json",
    )
    assert resolved.status_code == 200, resolved.content
    assert resolved.json()["resolution"] == "edit_new"

    # **Both events are still on the calendar** — the edit has not happened yet.
    week = _week(client)
    assert len(_blocks(week)) == 2

    # **But the indicator is gone.** "Edit the new one" means the conflict is dealt
    # with; only "Keep both" leaves the reminder.
    assert all(block["conflict"] is False for block in _blocks(week)), (
        "edit_new clears the indicator even though both events remain"
    )

    listing = _conflicts(client)
    assert len(listing["resolved"]) == 1
    assert listing["resolved"][0]["resolution"] == "edit_new"


# ── The detail path ─────────────────────────────────────────────────────────────────


def test_a_clashing_save_answers_409_with_a_pair_the_resolve_endpoint_can_close():
    """**The round trip is possible, not merely well-shaped.**

    The 409's sides are named with their kinds and their ids, and a resolution posted
    with **those** ids closes the pair. A 409 that named the wrong id — the catalog
    event's rather than the save row's — would be a well-shaped response the client
    could not act on, and the error would only surface when a user tried to answer.

    **The pair is the same pair throughout.** The 409's `pair_id`, the list's
    `pair_id`, the resolve response's `pair_id` and the row's id are one id.
    """
    client = _signed_in()
    user_id = _user_id(client)
    _preference(user_id)

    personal = _create_personal_event(client)
    catalog_event = _catalog_event(start_utc=CATALOG_START_UTC, end_utc=CATALOG_END_UTC)

    response = _save_public_event(client, catalog_event)
    assert response.status_code == 409, response.content
    details = response.json()["details"]
    conflict = details["conflicts"][0]

    pair_id = conflict["pair_id"]
    save_row_id = details["event_id"]

    # **The pair is a real row**, owned by the user who made it.
    row = ConflictPair.objects.using(PERSONAL).get(pk=pair_id)
    assert row.user_id == user_id
    assert row.status == "active"
    assert row.kind == "time"

    # **And the resolve endpoint closes it with the ids the 409 named.**
    resolved = client.post(
        f"/api/personal/events/conflicts/{pair_id}/resolve",
        data={"resolution": "keep_both", "side": {"kind": "saved_event", "id": save_row_id}},
        content_type="application/json",
    )
    assert resolved.status_code == 200, resolved.content
    assert resolved.json()["pair_id"] == pair_id
    assert ConflictPair.objects.using(PERSONAL).get(pk=pair_id).status == "resolved"

    # **The pair the 409 named is the pair the row holds.** The personal side is the
    # event the scenario created, and the saved side is the save row. The row's ids
    # are UUIDs and the wire's are strings, so they are compared as UUIDs — a string
    # comparison against a UUID is always false, and a test that compares them that
    # way would fail for a reason that has nothing to do with the rule.
    assert row.left_id == UUID(personal["id"]) or row.right_id == UUID(personal["id"])
    assert row.left_id == UUID(save_row_id) or row.right_id == UUID(save_row_id)


def test_a_resolution_naming_a_side_outside_the_pair_is_refused():
    """**The safety property, observed.**

    `delete_new` demands a personal side and `skip_public` demands a saved one. A
    request naming the wrong kind is refused — and the refusal **leaves the pair
    answerable**, because the pair's status is only written after the check passes.
    """
    client = _signed_in()
    user_id = _user_id(client)
    _preference(user_id)

    personal = _create_personal_event(client)
    catalog_event = _catalog_event(start_utc=CATALOG_START_UTC, end_utc=CATALOG_END_UTC)

    saved_response = _save_public_event(client, catalog_event)
    assert saved_response.status_code == 409, saved_response.content
    details = saved_response.json()["details"]
    pair_id = details["conflicts"][0]["pair_id"]
    save_row_id = details["event_id"]

    # `skip_public` against the **personal** side: the action names a saved side, and
    # this request names the other one.
    refused = client.post(
        f"/api/personal/events/conflicts/{pair_id}/resolve",
        data={
            "resolution": "skip_public",
            "side": {"kind": "personal_event", "id": personal["id"]},
        },
        content_type="application/json",
    )
    assert refused.status_code == 422, refused.content
    assert refused.json()["code"] == "illegal_resolution"

    # **The pair is still answerable.** A refusal must not close the prompt.
    assert ConflictPair.objects.using(PERSONAL).get(pk=pair_id).status == "active"
    listing = _conflicts(client)
    assert len(listing["active"]) == 1

    # **And the right request closes it.**
    resolved = client.post(
        f"/api/personal/events/conflicts/{pair_id}/resolve",
        data={"resolution": "skip_public", "side": {"kind": "saved_event", "id": save_row_id}},
        content_type="application/json",
    )
    assert resolved.status_code == 200, resolved.content


def test_a_closed_pair_is_never_re_prompted():
    """**AD-21: a closed pair is immutable and never re-prompted.**

    The second answer is refused, and the first answer stands. Without this, a client
    that double-posted would either overwrite the user's choice or trip the database's
    guard trigger — and the first is the worse failure, because it is silent.
    """
    client = _signed_in()
    user_id = _user_id(client)
    _preference(user_id)

    _create_personal_event(client)
    catalog_event = _catalog_event(start_utc=CATALOG_START_UTC, end_utc=CATALOG_END_UTC)

    saved_response = _save_public_event(client, catalog_event)
    details = saved_response.json()["details"]
    pair_id = details["conflicts"][0]["pair_id"]
    save_row_id = details["event_id"]

    first = client.post(
        f"/api/personal/events/conflicts/{pair_id}/resolve",
        data={"resolution": "keep_both", "side": {"kind": "saved_event", "id": save_row_id}},
        content_type="application/json",
    )
    assert first.status_code == 200, first.content

    second = client.post(
        f"/api/personal/events/conflicts/{pair_id}/resolve",
        data={"resolution": "skip_public", "side": {"kind": "saved_event", "id": save_row_id}},
        content_type="application/json",
    )
    assert second.status_code == 422, second.content
    assert second.json()["code"] == "conflict_already_resolved"

    # **The first answer stands.**
    row = ConflictPair.objects.using(PERSONAL).get(pk=pair_id)
    assert row.resolution == "keep_both"
    assert row.status == "resolved"


# ── Isolation ───────────────────────────────────────────────────────────────────────


def test_a_second_user_sees_none_of_the_first_users_pairs_or_blocks():
    """**AD-12 and the scoping of every read.**

    The second user reads the same week and the same conflicts list, and sees **none**
    of the first user's events, saves or pairs. The first user's pair is **active** at
    this moment — which is the state a scoping bug would leak, and the reason this
    assertion is made before anything is resolved.

    **The second user has their own preference**, so their week is cut in a zone and
    the read is a real read rather than a refusal.
    """
    first = _signed_in("first@example.test")
    first_id = _user_id(first)
    _preference(first_id)

    _create_personal_event(first)
    catalog_event = _catalog_event(start_utc=CATALOG_START_UTC, end_utc=CATALOG_END_UTC)
    saved_response = _save_public_event(first, catalog_event)
    assert saved_response.status_code == 409, saved_response.content
    pair_id = saved_response.json()["details"]["conflicts"][0]["pair_id"]

    # The first user's pair is active, and their week has two flagged blocks.
    assert len(_conflicts(first)["active"]) == 1
    assert len(_blocks(_week(first))) == 2

    # ── The second user ────────────────────────────────────────────────────────────
    second = _signed_in("second@example.test")
    second_id = _user_id(second)
    _preference(second_id)

    listing = _conflicts(second)
    assert listing["active"] == [], "another user's pairs are not readable"
    assert listing["resolved"] == []

    week = _week(second)
    assert _blocks(week) == [], "another user's events are not on another user's week"

    # **And the second user cannot close the first user's pair.** The resolve endpoint
    # scopes by the session's user, so the pair is not theirs to answer — and the
    # refusal is a 404, not a 422, because from the second user's side the pair does
    # not exist at all.
    save_row_id = saved_response.json()["details"]["event_id"]
    refused = second.post(
        f"/api/personal/events/conflicts/{pair_id}/resolve",
        data={"resolution": "keep_both", "side": {"kind": "saved_event", "id": save_row_id}},
        content_type="application/json",
    )
    assert refused.status_code == 404, refused.content

    # **The first user's pair is untouched by the attempt.**
    assert ConflictPair.objects.using(PERSONAL).get(pk=pair_id).status == "active"


def test_the_anonymous_visitor_gets_no_timeline_and_no_conflicts():
    """**No session, no personal data.**

    The personal endpoints resolve their user from the session, so an unauthenticated
    request has no user and the endpoints refuse it. This is AD-12's session-free rule
    applied to the personal surfaces: the public catalog is the only thing an anonymous
    visitor can read.
    """
    anonymous = CsrfClient()

    week = anonymous.get(f"/api/personal/timeline?week={WEDNESDAY}")
    assert week.status_code == 401, week.content

    listing = anonymous.get("/api/personal/conflicts")
    assert listing.status_code == 401, listing.content


# ── The week is asked for by any date ────────────────────────────────────────────────


def test_the_week_is_named_by_any_date_in_it():
    """**`week=` takes any date in the wanted week.**

    The frontend's link names the *day* the event starts on, not the Monday — so the
    endpoint has to accept a Wednesday and answer with the Monday and the Sunday. A
    server that only accepted Mondays would make the link land on the wrong week.

    **Every day of the week names the same week.** That is the whole claim, and
    asserting only one day would prove only that one day works.
    """
    client = _signed_in()
    user_id = _user_id(client)
    _preference(user_id)

    _create_personal_event(client)

    for day in range(2, 9):
        week = _week(client, week=f"2026-11-{day:02d}")
        assert week["week_start"] == "2026-11-02", f"2026-11-{day:02d} named the week"
        assert week["week_end"] == "2026-11-08", f"2026-11-{day:02d} named the week"
        assert len(week["days"]) == 7


def test_a_malformed_week_is_refused():
    """**A bad parameter is a 422**, on the same path every other malformed query takes.

    The parameter is typed as a date, so Django Ninja's own validation answers it. A
    server that guessed — and picked *this* week — would be answering a question the
    client did not ask.
    """
    client = _signed_in()

    response = client.get("/api/personal/timeline?week=not-a-date")
    assert response.status_code == 422, response.content


# ── The cross-midnight indicator ─────────────────────────────────────────────────────


def test_the_indicator_follows_the_overlap_and_not_the_events_own_span():
    """**The indicator fires on the day-cell that contains the *overlap*.**

    A personal event running from Friday 22:00 to Saturday 02:00 that clashes with
    something on **Friday** lights Friday's cell only — even though the event itself
    spans Saturday. The clash is what the reminder is about, and the clash is on
    Friday.

    **This is the rule that is easy to get wrong and impossible to notice.** A flag
    carried on the block rather than on the day-cell would light both days, and the
    difference is one extra amber dot on a screen the user reads every morning.
    """
    client = _signed_in()
    user_id = _user_id(client)
    _preference(user_id)

    # A personal event from Friday 22:00 to Saturday 02:00, in the user's own zone.
    # 2026-11-06 22:00 Los Angeles is 2026-11-07 06:00 UTC.
    friday_start = datetime(2026, 11, 7, 6, 0, tzinfo=UTC)
    friday_end = datetime(2026, 11, 7, 10, 0, tzinfo=UTC)

    response = client.post(
        "/api/personal/events",
        data={
            "name": "Late shift",
            "start_time_utc": friday_start.isoformat().replace("+00:00", "Z"),
            "start_time_tz": ZONE,
            "end_time_utc": friday_end.isoformat().replace("+00:00", "Z"),
        },
        content_type="application/json",
    )
    assert response.status_code == 201, response.content

    # A public event that clashes on **Friday only**: 21:00–23:00 Los Angeles.
    catalog_event = _catalog_event(
        start_utc=datetime(2026, 11, 7, 5, 0, tzinfo=UTC),
        end_utc=datetime(2026, 11, 7, 7, 0, tzinfo=UTC),
        title="Friday Night Market",
    )

    saved_response = _save_public_event(client, catalog_event)
    assert saved_response.status_code == 409, saved_response.content

    week = _week(client)

    # **The personal event spans Friday and Saturday; the public event is on Friday
    # only.** So the Friday carries both blocks and the Saturday carries one.
    friday = _block_on(week, "2026-11-06")
    saturday = _block_on(week, "2026-11-07")
    assert len(friday) == 2, "the Friday carries the personal event and the public one"
    assert len(saturday) == 1, "the Saturday carries only the personal event"

    # **But only the Friday's cell carries the flag.**
    assert all(block["conflict"] for block in friday), (
        "the clash is on the Friday, so the Friday's cells are flagged"
    )
    assert saturday[0]["conflict"] is False, (
        "the clash is not on the Saturday, so the Saturday's cell is not flagged"
    )
