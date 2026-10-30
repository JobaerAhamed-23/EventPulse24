"""The intent's end-to-end proof: personal events, conflicts, saves, and the resolved pair.

This is the proof item for `personal-events-and-saved-catalog`. It drives the **real HTTP
surface** — the same endpoints the browser drives — through one recorded scenario:

    ingest a real event → create a personal event → clash with it → answer the prompt →
    clash again with the *same* pair (no second prompt) → save a public event → clash with
    the save → answer with "delete the new one"

Everything here goes through the real services, the real models, the real database
schemas and the real conflict rules. Only two things are substituted, both deliberately and
both named below: the catalog fetch is served by the fake adapter from recorded fixtures,
and the worker is run inline.

**The scenario is one test.** It is not a sequence of independent assertions that each
rebuild their own world — the point of a proof is that the *steps compose*: the second
event clashes because of the first, the re-clash is not re-prompted *because* the first pair
was resolved, and the delete resolves because the pair was answered. Splitting it would test
the parts and lose the proof.
"""

import json
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from apps.ingestion.models import Event, Source
from apps.personalization.models import ConflictPair, PersonalEvent, SavedEvent
from shared.constants import TITLE_TOKEN_OVERLAP_MIN
from shared.db import CATALOG, PERSONAL
from tests.csrf import CsrfClient
from worker import tasks

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()

#: A fixed instant far enough ahead that the scenario does not race the clock.
START = datetime(2026, 11, 6, 3, 30, tzinfo=UTC)
END = START + timedelta(hours=2)
#: The same instant, expressed in the zone the body names.
START_LOCAL = "2026-11-05T19:30:00"
TZ = "America/Los_Angeles"


@pytest.fixture(autouse=True)
def fake_fetch(settings):
    """The fake adapter, whatever SOURCE_FETCH says in the environment."""
    settings.ADAPTERS = {**settings.ADAPTERS, "fetch": "adapters.crawl.fake.FakeFetchAdapter"}


@pytest.fixture
def seeded():
    """The catalog has data: the seed command registers the sources, the tick ingests them."""
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


def _signed_in(user=None):
    """A client whose session identifies `user`.

    It is a `CsrfClient`: the personal endpoints resolve their user through `identity`'s
    resolver, and the resolver checks CSRF on every unsafe method (D13). The token is
    fetched on the first unsafe request and travels in the `X-CSRFToken` header.
    """
    client = CsrfClient()
    client.force_login(user or User.objects.create_user(email="sam@example.test", password="pw"))
    return client


def _create_body(name, start=START, end=None, tz=TZ):
    """A create body. The end is derived from the start unless one is named."""
    payload = {
        "name": name,
        "start_time_utc": start.isoformat(),
        "start_time_tz": tz,
        "end_time_utc": (end if end is not None else start + timedelta(hours=2)).isoformat(),
    }
    return payload


def _post(client, url, payload):
    """POST a JSON body.

    The bodies go out as JSON, not as form data: Django Ninja parses the request body
    against the endpoint's schema, and a form-encoded body is not JSON — the endpoint
    answers 400 "That request couldn't be read." This is the same shape the browser sends.
    """
    return client.post(url, data=json.dumps(payload), content_type="application/json")


def _patch(client, url, payload):
    """PATCH a JSON body."""
    return client.patch(url, data=json.dumps(payload), content_type="application/json")


# --- the scenario ----------------------------------------------------------------------------


def test_the_whole_personal_event_and_save_flow_holds_together(seeded, enqueued):
    """The recorded scenario, end to end, through the real HTTP surface."""
    _run_tick_inline(enqueued)
    # The catalog has a *published*, not-superseded, upcoming event. `publication_status`
    # is the public flag; `status` is the lifecycle (scheduled/postponed/cancelled).
    catalog_event = (
        Event.objects.using(CATALOG)
        .filter(publication_status=Event.PublicationStatus.PUBLISHED)
        .exclude(status=Event.Status.SUPERSEDED)
        .filter(start_time_utc__gte=START)
        .order_by("start_time_utc")
        .first()
    )
    assert catalog_event is not None, "the ingest should have published an event"

    client = _signed_in()
    user = UUID(client.session["_auth_user_id"])

    # --- 1. a personal event persists in `personal` and comes back from the list ---------
    created = _post(client, "/api/personal/events", _create_body("Coffee with Sam"))
    assert created.status_code == 201, created.content
    first_event_id = created.json()["id"]

    stored = PersonalEvent.objects.using(PERSONAL).get(pk=first_event_id)
    assert stored.start_time_tz == TZ
    assert stored.start_utc == START
    # AD-6: the stored instant and the named zone agree — 19:30 on 5 November in Los
    # Angeles is 03:30 UTC on 6 November. The backend never reinterprets the wall clock;
    # it stores the instant the browser computed and keeps the zone beside it.
    assert stored.start_utc.astimezone(ZoneInfo(TZ)).replace(tzinfo=None).isoformat() == (
        START_LOCAL
    )

    listed = client.get("/api/personal/events")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [first_event_id]

    # --- 2. a second, overlapping event answers 409 with exactly three actions ----------
    clash_start = START + timedelta(minutes=30)
    clashing = _post(
        client,
        "/api/personal/events",
        _create_body("Coffee with Alex", start=clash_start),
    )
    assert clashing.status_code == 409, clashing.content
    details = clashing.json()["details"]
    assert details["event_id"] != first_event_id
    assert len(details["conflicts"]) == 1
    conflict = details["conflicts"][0]
    assert conflict["kind"] == "time"
    assert len(conflict["actions"]) == 3
    assert set(conflict["actions"]) == {"keep_both", "edit_new", "delete_new"}
    assert conflict["other"]["id"] == first_event_id
    # The event was **written** — a 409 is not a failed write, it is a pending prompt.
    assert PersonalEvent.objects.using(PERSONAL).filter(pk=details["event_id"]).exists()
    pair_id = conflict["pair_id"]
    second_event_id = details["event_id"]

    # --- 3. "Keep both — I'll manage" is recorded on the pair ---------------------------
    answered = _post(
        client,
        f"/api/personal/events/conflicts/{pair_id}/resolve",
        {"resolution": "keep_both", "new_side_id": second_event_id},
    )
    assert answered.status_code == 200, answered.content
    assert answered.json()["resolution"] == "keep_both"

    pair = ConflictPair.objects.using(PERSONAL).get(pk=pair_id)
    assert pair.status == ConflictPair.Status.RESOLVED
    assert pair.resolution == ConflictPair.Resolution.KEEP_BOTH
    assert pair.resolved_at is not None

    # --- 4. the same pair is never re-prompted -----------------------------------------
    # The *same two events* are made to clash again: the second event is edited back into
    # the first one's time. Because the pair is keyed on the two sides, this is the very
    # same pair — and it is resolved, so the prompt must not come back (AD-21).
    #
    # An edit, not a delete-and-recreate: a re-created event has a new id, so it would be a
    # *new* pair and the proof would prove nothing.
    re_clash = _patch(
        client,
        f"/api/personal/events/{second_event_id}",
        {
            "start_time_utc": (START + timedelta(minutes=30)).isoformat(),
            "end_time_utc": (START + timedelta(minutes=30) + timedelta(hours=2)).isoformat(),
        },
    )
    assert re_clash.status_code == 200, re_clash.content

    pair.refresh_from_db()
    assert pair.status == ConflictPair.Status.RESOLVED
    assert pair.resolution == ConflictPair.Resolution.KEEP_BOTH
    # And no second pair was written for the same two sides — the pair count did not move.
    assert (
        ConflictPair.objects.using(PERSONAL)
        .filter(user_id=user, left_id=first_event_id, right_id=second_event_id)
        .count()
        == 1
    )

    # Answering the same pair twice is refused — a resolved pair is immutable (AD-21).
    replay = _post(
        client,
        f"/api/personal/events/conflicts/{pair_id}/resolve",
        {"resolution": "delete_new", "new_side_id": second_event_id},
    )
    assert replay.status_code == 422, replay.content
    assert replay.json()["code"] == "conflict_already_resolved"

    pair.refresh_from_db()
    assert pair.status == ConflictPair.Status.RESOLVED
    assert pair.resolution == ConflictPair.Resolution.KEEP_BOTH

    # --- 5. a save carries a snapshot of the catalog event's time and version ----------
    saved = client.post(f"/api/personal/saved-events/{catalog_event.id}")
    assert saved.status_code in (200, 201), saved.content
    save_row = SavedEvent.objects.using(PERSONAL).get(user_id=user, event_id=catalog_event.id)
    assert save_row.start_utc == catalog_event.start_time_utc
    assert save_row.end_utc == catalog_event.end_time_utc
    assert save_row.event_version == catalog_event.event_version

    # --- 6. a personal event overlapping the save answers 409 with three actions --------
    save_start = catalog_event.start_time_utc + timedelta(minutes=30)
    over_save = _post(
        client,
        "/api/personal/events",
        _create_body("Dinner near the meetup", start=save_start),
    )
    assert over_save.status_code == 409, over_save.content
    save_conflict = over_save.json()["details"]["conflicts"][0]
    assert len(save_conflict["actions"]) == 3
    assert save_conflict["other"]["id"] == str(save_row.id)
    save_pair_id = save_conflict["pair_id"]
    over_save_id = over_save.json()["details"]["event_id"]

    # --- 7. "Delete the new one" removes the event and still records the resolution ---
    deleted = _post(
        client,
        f"/api/personal/events/conflicts/{save_pair_id}/resolve",
        {"resolution": "delete_new", "new_side_id": over_save_id},
    )
    assert deleted.status_code == 200, deleted.content
    assert deleted.json()["resolution"] == "delete_new"

    assert not PersonalEvent.objects.using(PERSONAL).filter(pk=over_save_id).exists()

    save_pair = ConflictPair.objects.using(PERSONAL).get(pk=save_pair_id)
    # The resolution is **recorded**, and the pair is resolved-not-cleared: the user
    # answered it, so it is not the NULL-resolution `cleared_by_state_change` shape.
    assert save_pair.status == ConflictPair.Status.RESOLVED
    assert save_pair.resolution == ConflictPair.Resolution.DELETE_NEW
    assert save_pair.resolved_at is not None

    # --- 8. and the state the user sees is the state that persisted -------------------
    final_events = client.get("/api/personal/events").json()["items"]
    assert first_event_id in [item["id"] for item in final_events]
    assert over_save_id not in [item["id"] for item in final_events]
    final_saved = client.get("/api/personal/saved-events").json()["items"]
    assert [item["id"] for item in final_saved] == [str(save_row.id)]


# --- the boundary the work item names ---------------------------------------------------------


def test_exactly_fifteen_minutes_is_not_a_conflict_but_one_second_more_is():
    """The 15-minute rule, at its boundary, through the real endpoint.

    AD-21 says the overlap must be **strictly more than** 15 minutes, so exactly 15 is
    not a conflict and 15 minutes and one second is.
    """
    client = _signed_in()
    first = _post(client, "/api/personal/events", _create_body("Coffee"))
    assert first.status_code == 201

    # The second event starts 15 minutes before the first ends, and lasts two hours, so
    # the overlap is exactly 15 minutes.
    exact = _post(
        client,
        "/api/personal/events",
        _create_body("Tea", start=END - timedelta(minutes=15)),
    )
    assert exact.status_code == 201, exact.content

    # One second more overlap: the second event starts one second earlier.
    over = _post(
        client,
        "/api/personal/events",
        _create_body("Tea again", start=END - timedelta(minutes=15) - timedelta(seconds=1)),
    )
    assert over.status_code == 409, over.content
    assert over.json()["details"]["conflicts"][0]["kind"] == "time"


def test_a_duplicate_is_flagged_at_exactly_eighty_percent_token_overlap():
    """The 80% duplicate threshold, at its boundary.

    The threshold is `Fraction(4, 5)` — exactly 4/5, not a float 0.8 — so the boundary is
    testable without a float comparison anywhere.

    The tokenisation matters here, and it is worth spelling out. `domain.dedup`'s
    `title_fingerprint` splits a title into **content** tokens and **stop** tokens
    (`and`, `for`, `the`, …), and Jaccard compares the content sets. So a title of five
    words, one of which is a stop word, has *four* content tokens — and a title that adds
    one more content word gives a union of five over an intersection of four: exactly 4/5.
    """
    from domain.dedup import jaccard, title_fingerprint

    # Four content tokens against five, four in common: exactly 4/5.
    at_threshold = jaccard(
        title_fingerprint("Calm Curious Designing Kindness"),
        title_fingerprint("Calm Curious Designing Kindness Quiet"),
    )
    # Compared against the exact rational, not the float: `Fraction(4, 5) == 0.8` is
    # **False**, because 0.8 is not exactly 4/5 in binary floating point. The threshold in
    # `shared.constants` is `Fraction(4, 5)` precisely so that this boundary is decidable.
    assert at_threshold == Fraction(4, 5)
    assert at_threshold >= TITLE_TOKEN_OVERLAP_MIN
    assert TITLE_TOKEN_OVERLAP_MIN == Fraction(4, 5)

    # Three content tokens against four, three in common: 3/4, below the threshold.
    below = jaccard(
        title_fingerprint("Calm Designing Kindness"),
        title_fingerprint("Calm Designing Kindness Quiet"),
    )
    assert below == Fraction(3, 4)
    assert below < TITLE_TOKEN_OVERLAP_MIN

    # And through the real endpoint: the same names, 24 hours apart, are a duplicate.
    client = _signed_in()
    first = _post(
        client,
        "/api/personal/events",
        _create_body("Calm Curious Designing Kindness"),
    )
    assert first.status_code == 201

    duplicate = _post(
        client,
        "/api/personal/events",
        _create_body(
            "Calm Curious Designing Kindness Quiet",
            start=START + timedelta(hours=23),
        ),
    )
    assert duplicate.status_code == 409, duplicate.content
    conflict = duplicate.json()["details"]["conflicts"][0]
    assert conflict["kind"] == "duplicate"
    # A duplicate offers "update_existing", not "edit_new" (FR-58).
    assert set(conflict["actions"]) == {"keep_both", "update_existing", "delete_new"}


def test_the_duplicate_window_is_twenty_four_hours_and_no_more():
    """The duplicate window is absolute: 23 hours away is inside, 25 hours away is outside.

    Each case gets its **own** user, so the "outside" case is not caught by the "inside"
    event that is still on the calendar — the window is measured against one event at a
    time, and a second event within 24 hours of *that* one would be a conflict in its own
    right.
    """
    client = _signed_in()
    first = _post(client, "/api/personal/events", _create_body("Designing for Calm"))
    assert first.status_code == 201

    inside = _post(
        client,
        "/api/personal/events",
        _create_body("Designing for Calm", start=START - timedelta(hours=23)),
    )
    assert inside.status_code == 409, inside.content
    assert inside.json()["details"]["conflicts"][0]["kind"] == "duplicate"

    # A second user, a second calendar: the only event to compare against is the original.
    other = _signed_in(User.objects.create_user(email="sam2@example.test", password="pw"))
    base = _post(other, "/api/personal/events", _create_body("Designing for Calm"))
    assert base.status_code == 201

    outside = _post(
        other,
        "/api/personal/events",
        _create_body("Designing for Calm", start=START - timedelta(hours=25)),
    )
    assert outside.status_code == 201, outside.content
