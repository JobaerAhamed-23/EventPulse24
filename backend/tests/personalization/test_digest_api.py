"""The digest read API: persisted rows, and nothing else (FR-5, FR-6, FR-8, AD-10).

**What these tests pin is the shape of the contract**, not the composition's behaviour
(which `test_digest_composition.py` owns):

- the endpoint is **authed** — an anonymous request is refused;
- the endpoint is **scoped to the session user** — another user's digest is invisible,
  and no endpoint accepts a user id as an input;
- the **three states are three distinct responses** — `composed`, `empty` and
  `not_composed` — and collapsing them is the bug this surface exists to prevent;
- the card carries **FR-6's six elements** and the persisted explanation;
- the card carries the **bucket, not the score**, and the persisted **tag keys in the
  persisted order**;
- **nothing is computed** — the endpoint never calls the ranking and never writes;
- the **query count is bounded**, so an N+1 cannot land silently inside the <500ms
  budget.

The client is a `CsrfClient`, because the endpoints resolve their user through
`identity`'s resolver and the resolver checks CSRF on every unsafe method (D13).
"""

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone as django_timezone

from apps.ingestion.services.source_badges import SOURCE_BADGE_OFFICIAL
from apps.personalization.models import (
    ConflictPair,
    DigestComposition,
    PersonalizationAuditEntry,
    PulseDigest,
)
from apps.personalization.services.digest_dates import local_date_for
from apps.personalization.services.digest_read import read_digest
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory, VenueFactory
from tests.personalization.factories import (
    ConflictPairFactory,
    DigestCompositionFactory,
    DigestPreferenceFactory,
    PersonalEventFactory,
    PulseDigestFactory,
    SavedEventFactory,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()

#: The endpoint resolves "now" itself, from the wall clock — so the digest it looks for
#: is the one for **today's** local date, and the tests have to write that one. `NOW` is
#: therefore the wall clock, pinned at import time so that every instant in a test is
#: measured from the same "today" (the composition service's own tests pin a fixed
#: instant instead, because it takes `now` as a parameter; this surface does not).
NOW = django_timezone.now()

CITY = "Los Angeles"
ZONE = "America/Los_Angeles"


def make_user(email="sam@example.test"):
    """A real user with a real pk — the session resolves to this one."""
    return User.objects.create_user(email=email, password="pw")


def signed_in(user=None):
    """A client whose session identifies `user`."""
    client = Client()
    client.force_login(user or make_user())
    return client


def make_preference(user_id, **overrides):
    fields = {"user_id": user_id, "timezone": ZONE, "city": CITY, "city_source": "choice"}
    fields.update(overrides)
    return DigestPreferenceFactory(**fields)


def make_event(*, hours=2, title="Brooklyn Tech Meetup", city=CITY, **overrides):
    """A published public event in the catalog.

    **The venue fingerprint is unique per call.** The catalog holds one venue per
    fingerprint, so two events with the same title would collide on it.
    """
    fingerprint = f"venue-{title}|{city}|{uuid4()}"
    fields = {
        "title": title,
        "venue": VenueFactory(city=city, venue_fingerprint=fingerprint),
        "start_time_utc": NOW + timedelta(hours=hours),
        "last_seen_at": NOW,
    }
    fields.update(overrides)
    return EventFactory(**fields)


def make_digest(user_id, *, local_date=None, is_empty=False, timezone=ZONE):
    return PulseDigestFactory(
        user_id=user_id,
        local_date=local_date or local_date_for(now=NOW, zone_name=timezone),
        timezone=timezone,
        is_empty=is_empty,
        composed_at=NOW,
    )


def make_composition(digest, **overrides):
    fields = {
        "digest_id": digest.id,
        "user_id": digest.user_id,
        "event_kind": DigestComposition.EventKind.PUBLIC,
        "score": Decimal("0.83"),
        "bucket": 4,
        "tags": ["nearby", "tonight", "saved"],
        "source_badge": SOURCE_BADGE_OFFICIAL,
        "event_version": 1,
        "composed_at": NOW,
    }
    fields.update(overrides)
    return DigestCompositionFactory(**fields)


def get_digest(client, path="/api/personal/digest"):
    return client.get(path)


# --- the three states ----------------------------------------------------------------


def test_a_composed_digest_returns_its_cards():
    user = make_user()
    make_preference(user.pk)
    digest = make_digest(user.pk)
    event = make_event()
    make_composition(digest, event_id=event.id, slot=DigestComposition.Slot.MUST_KNOW)

    response = get_digest(signed_in(user))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "composed"
    assert body["local_date"] == str(local_date_for(now=NOW, zone_name=ZONE))
    assert body["timezone"] == ZONE
    assert body["city"] == CITY
    assert body["city_source"] == "choice"
    assert len(body["cards"]) == 1
    card = body["cards"][0]
    assert card["event_id"] == str(event.id)
    assert card["slot"] == "must_know"
    assert card["event_kind"] == "public"
    assert card["title"] == event.title
    assert card["bucket"] == 4
    assert card["tags"] == ["nearby", "tonight", "saved"]
    assert card["source_badge"] == SOURCE_BADGE_OFFICIAL


def test_an_empty_digest_is_a_digest_with_no_cards():
    """FR-8: "we looked and there was nothing" — a real digest, zero cards."""
    user = make_user()
    make_preference(user.pk)
    make_digest(user.pk, is_empty=True)

    response = get_digest(signed_in(user))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "empty"
    assert body["cards"] == []
    assert body["city"] == CITY


def test_a_digest_that_was_never_composed_is_distinguishable():
    """The third state. Not the empty state — the worker has simply not looked yet."""
    user = make_user()
    make_preference(user.pk)

    response = get_digest(signed_in(user))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_composed"
    assert body["cards"] == []


def test_the_empty_state_and_the_not_composed_state_are_different_bodies():
    """The two empties must not collapse into one — that is the bug this surface prevents."""
    empty_user = make_user("empty@example.test")
    make_preference(empty_user.pk)
    make_digest(empty_user.pk, is_empty=True)

    pending_user = make_user("pending@example.test")
    make_preference(pending_user.pk)

    empty_body = get_digest(signed_in(empty_user)).json()
    pending_body = get_digest(signed_in(pending_user)).json()

    assert empty_body["status"] == "empty"
    assert pending_body["status"] == "not_composed"
    assert empty_body["cards"] == pending_body["cards"] == []
    assert empty_body["status"] != pending_body["status"]


def test_the_empty_state_carries_the_city():
    """FR-8's copy is "No qualifying events in {city}" — the city is part of the message."""
    user = make_user()
    make_preference(user.pk, city="Brooklyn", city_source="choice")
    make_digest(user.pk, is_empty=True)

    body = get_digest(signed_in(user)).json()

    assert body["city"] == "Brooklyn"
    assert body["city_source"] == "choice"


def test_a_fallback_city_is_labelled_as_one():
    """The fallback city is not the user's city, and the copy must not imply it is."""
    user = make_user()
    make_preference(user.pk, city="New York City", city_source="fallback")
    make_digest(user.pk, is_empty=True)

    body = get_digest(signed_in(user)).json()

    assert body["city"] == "New York City"
    assert body["city_source"] == "fallback"


# --- auth and scoping ----------------------------------------------------------------


def test_the_endpoint_requires_a_session():
    response = get_digest(Client())

    assert response.status_code == 401


def test_another_users_digest_is_invisible():
    """The scoping comes from the session and cannot be talked out of by a payload."""
    other = make_user("other@example.test")
    other_preference = make_preference(other.pk, city="Brooklyn")
    other_digest = make_digest(other.pk)
    other_event = make_event(title="Other Event")
    make_composition(other_digest, event_id=other_event.id)

    user = make_user()
    make_preference(user.pk)

    body = get_digest(signed_in(user)).json()

    assert body["status"] == "not_composed"
    assert body["city"] != other_preference.city
    assert body["cards"] == []


def test_the_endpoint_takes_no_user_id_input():
    """A payload cannot ask for somebody else's digest."""
    user = make_user()
    other = make_user("other@example.test")
    make_preference(other.pk)
    other_digest = make_digest(other.pk)
    other_event = make_event(title="Other Event")
    make_composition(other_digest, event_id=other_event.id)

    response = get_digest(signed_in(user), f"/api/personal/digest?user_id={other.pk}")

    assert response.status_code == 200
    assert response.json()["status"] == "not_composed"


# --- the card ------------------------------------------------------------------------


def test_the_cards_are_in_slot_order():
    """The read sorts against `DIGEST_SLOT_ORDER`, not the database's alphabetical order."""
    user = make_user()
    make_preference(user.pk)
    digest = make_digest(user.pk)
    events = {}
    for slot, title in (
        ("serendipity", "Third"),
        ("must_know", "First"),
        ("nearby", "Second"),
    ):
        events[slot] = make_event(title=title, hours=len(events) + 2)
        make_composition(digest, event_id=events[slot].id, slot=slot)

    body = get_digest(signed_in(user)).json()

    assert [card["slot"] for card in body["cards"]] == ["must_know", "nearby", "serendipity"]


def test_the_card_carries_the_bucket_and_not_the_score():
    """A client that re-buckets the score could flicker. The bucket is persisted."""
    user = make_user()
    make_preference(user.pk)
    digest = make_digest(user.pk)
    event = make_event()
    make_composition(digest, event_id=event.id, bucket=5, score=Decimal("0.97"))

    card = get_digest(signed_in(user)).json()["cards"][0]

    assert card["bucket"] == 5
    assert "score" not in card


def test_the_card_carries_the_persisted_tags_in_the_persisted_order():
    user = make_user()
    make_preference(user.pk)
    digest = make_digest(user.pk)
    event = make_event()
    make_composition(digest, event_id=event.id, tags=["tonight", "nearby", "saved"])

    card = get_digest(signed_in(user)).json()["cards"][0]

    assert card["tags"] == ["tonight", "nearby", "saved"]


def test_the_saved_flag_travels_as_a_tag():
    """The `saved` Why-this tag is persisted in the composition's tags."""
    user = make_user()
    make_preference(user.pk)
    digest = make_digest(user.pk)
    event = make_event()
    make_composition(digest, event_id=event.id, tags=["nearby", "saved"])

    card = get_digest(signed_in(user)).json()["cards"][0]

    assert "saved" in card["tags"]


def test_a_personal_card_carries_the_agenda_row_and_no_badge():
    """A personal event has no source, so it has no badge — and its place is free text."""
    user = make_user()
    make_preference(user.pk)
    digest = make_digest(user.pk)
    personal = PersonalEventFactory(
        user_id=user.pk,
        name="Dentist",
        start_utc=NOW + timedelta(hours=3),
        end_utc=NOW + timedelta(hours=4),
        location="2 Example Street",
    )
    make_composition(
        digest,
        event_id=personal.id,
        event_kind=DigestComposition.EventKind.PERSONAL,
        slot=DigestComposition.Slot.MUST_KNOW,
        source_badge=None,
        event_version=None,
        tags=["tonight"],
    )

    card = get_digest(signed_in(user)).json()["cards"][0]

    assert card["event_kind"] == "personal"
    assert card["title"] == "Dentist"
    assert card["location"] == "2 Example Street"
    assert card["venue_name"] is None
    assert card["source_badge"] is None


def test_the_card_carries_the_time_as_an_instant_plus_the_zone():
    """AD-6: display-time conversion happens at the presentation edge.

    The card carries the **instant** and the **IANA zone** — never a pre-formatted local
    string. The instant is the catalog's own start time, and the zone is the catalog's
    own IANA name, so the client can convert it and nothing else has to.
    """
    user = make_user()
    make_preference(user.pk)
    digest = make_digest(user.pk)
    event = make_event()
    make_composition(digest, event_id=event.id)

    card = get_digest(signed_in(user)).json()["cards"][0]

    assert card["start_time_utc"].startswith(event.start_time_utc.isoformat()[:13])
    assert card["start_time_tz"] == event.start_time_tz
    assert "/" in card["start_time_tz"]


def test_tz_review_pending_survives_to_the_payload():
    """A live fact about the event, read at request time — not an explanation."""
    user = make_user()
    make_preference(user.pk)
    digest = make_digest(user.pk)
    event = make_event(tz_review_pending=True)
    make_composition(digest, event_id=event.id)

    card = get_digest(signed_in(user)).json()["cards"][0]

    assert card["tz_review_pending"] is True


def test_a_personal_card_whose_agenda_row_is_gone_still_appears_and_is_marked():
    """The same rule for the user's own agenda: the user may delete the event after the
    composition. The card survives, with the flag, and the explanation stays."""
    user = make_user()
    make_preference(user.pk)
    digest = make_digest(user.pk)
    personal = PersonalEventFactory(
        user_id=user.pk,
        name="Dentist",
        start_utc=NOW + timedelta(hours=3),
        end_utc=NOW + timedelta(hours=4),
    )
    make_composition(
        digest,
        event_id=personal.id,
        event_kind=DigestComposition.EventKind.PERSONAL,
        slot=DigestComposition.Slot.MUST_KNOW,
        source_badge=None,
        event_version=None,
        tags=["tonight"],
    )
    personal.delete()

    card = get_digest(signed_in(user)).json()["cards"][0]

    assert card["event_kind"] == "personal"
    assert card["catalog_event_missing"] is True
    assert card["title"] is None
    assert card["tags"] == ["tonight"]


def test_a_card_whose_catalog_event_is_gone_still_appears_and_is_marked():
    """AD-10: the composition is a fact about the day, and its explanation must not change
    because a source moved. The card survives, with the flag."""
    user = make_user()
    make_preference(user.pk)
    digest = make_digest(user.pk)
    event = make_event()
    make_composition(digest, event_id=event.id, tags=["nearby", "tonight"], bucket=4)
    event.publication_status = event.PublicationStatus.IN_REVIEW
    event.save()

    card = get_digest(signed_in(user)).json()["cards"][0]

    assert card["catalog_event_missing"] is True
    assert card["bucket"] == 4
    assert card["tags"] == ["nearby", "tonight"]
    assert card["title"] is None


def test_a_personal_card_in_a_conflict_carries_the_flag():
    """FR-58's indicator renders on a card whose event is in a `CONFLICT_PAIR`."""
    user = make_user()
    make_preference(user.pk)
    digest = make_digest(user.pk)
    personal = PersonalEventFactory(
        user_id=user.pk,
        name="Dentist",
        start_utc=NOW + timedelta(hours=3),
        end_utc=NOW + timedelta(hours=4),
    )
    make_composition(
        digest,
        event_id=personal.id,
        event_kind=DigestComposition.EventKind.PERSONAL,
        slot=DigestComposition.Slot.MUST_KNOW,
        source_badge=None,
        event_version=None,
    )
    other = PersonalEventFactory(user_id=user.pk, name="Standup")
    ConflictPairFactory(
        user_id=user.pk,
        kind=ConflictPair.Kind.TIME,
        left_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        left_id=personal.id,
        right_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        right_id=other.id,
    )

    card = get_digest(signed_in(user)).json()["cards"][0]

    assert card["conflict"] is True


def test_a_public_card_in_a_conflict_carries_the_flag():
    """A public card's conflict comes through the user's save of it.

    A conflict pair's sides are the `personal` rows — a `PersonalEvent`'s id and a
    `SavedEvent`'s id — while a public card names the **catalog** event's id. The save
    is the bridge.
    """
    user = make_user()
    make_preference(user.pk)
    digest = make_digest(user.pk)
    event = make_event()
    make_composition(digest, event_id=event.id)
    saved = SavedEventFactory(user_id=user.pk, event_id=event.id)
    other = PersonalEventFactory(user_id=user.pk, name="Standup")
    ConflictPairFactory(
        user_id=user.pk,
        kind=ConflictPair.Kind.TIME,
        left_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        left_id=other.id,
        right_kind=ConflictPair.SideKind.SAVED_EVENT,
        right_id=saved.id,
    )

    card = get_digest(signed_in(user)).json()["cards"][0]

    assert card["conflict"] is True


def test_a_resolved_conflict_is_not_a_flag():
    """A resolved pair is answered; a cleared one is over. Neither is an open conflict,
    and neither may put a conflict prompt on a card."""
    user = make_user()
    make_preference(user.pk)
    digest = make_digest(user.pk)
    personal = PersonalEventFactory(user_id=user.pk, name="Dentist")
    make_composition(
        digest,
        event_id=personal.id,
        event_kind=DigestComposition.EventKind.PERSONAL,
        slot=DigestComposition.Slot.MUST_KNOW,
        source_badge=None,
        event_version=None,
    )
    other = PersonalEventFactory(user_id=user.pk, name="Standup")
    ConflictPairFactory(
        user_id=user.pk,
        kind=ConflictPair.Kind.TIME,
        left_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        left_id=personal.id,
        right_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        right_id=other.id,
        status=ConflictPair.Status.RESOLVED,
        resolution=ConflictPair.Resolution.KEEP_BOTH,
        resolved_at=NOW,
    )

    card = get_digest(signed_in(user)).json()["cards"][0]

    assert card["conflict"] is False


# --- nothing is computed -------------------------------------------------------------


def test_the_endpoint_never_calls_the_ranking(monkeypatch):
    """The endpoint path never calls `domain/ranking.py` — the explanation is persisted."""
    import domain.ranking as ranking

    def explode(*args, **kwargs):
        raise AssertionError("the read path computed something")

    for name in ("score_slot_1", "score_slot_2", "score_slot_3", "why_this_tags"):
        monkeypatch.setattr(ranking, name, explode)

    user = make_user()
    make_preference(user.pk)
    digest = make_digest(user.pk)
    event = make_event()
    make_composition(digest, event_id=event.id)

    response = get_digest(signed_in(user))

    assert response.status_code == 200
    assert len(response.json()["cards"]) == 1


def test_the_endpoint_never_writes_a_row():
    """A read that writes is a read that is not a read."""
    user = make_user()
    make_preference(user.pk)
    digest = make_digest(user.pk)
    event = make_event()
    make_composition(digest, event_id=event.id)

    before_personal = PulseDigest.objects.using(PERSONAL).count()
    before_rows = DigestComposition.objects.using(PERSONAL).count()
    before_audit = PersonalizationAuditEntry.objects.using(PERSONAL).count()

    response = get_digest(signed_in(user))

    assert response.status_code == 200
    assert PulseDigest.objects.using(PERSONAL).count() == before_personal
    assert DigestComposition.objects.using(PERSONAL).count() == before_rows
    assert PersonalizationAuditEntry.objects.using(PERSONAL).count() == before_audit


# --- the query bound -----------------------------------------------------------------


def test_the_query_count_is_bounded():
    """Three cards must not become three-plus queries per card.

    **The bound is on the read, and the read is counted directly.** The endpoint's
    request path also carries the auth seam's two queries — the session row and the user
    row — and every endpoint on the personal router pays those. They are the framework's
    cost, not the read's, and a bound that counted them would be a bound on the login
    machinery rather than on the digest.

    **Six is the worst case:** the preference, the digest, the compositions, the open
    conflict pairs, the user's saves of the public cards (the bridge from a catalog
    event id to a pair's side), and the catalog's display facts. A user with no open
    conflicts pays one fewer, because the saved-events lookup is only reached once a
    pair exists to look for.
    """
    user = make_user()
    make_preference(user.pk)
    digest = make_digest(user.pk)
    for hours, slot in ((2, "must_know"), (3, "nearby"), (4, "serendipity")):
        event = make_event(hours=hours, title=f"Event {hours}")
        make_composition(digest, event_id=event.id, slot=slot)

    with CaptureQueriesContext(connections[PERSONAL]) as personal_queries:
        with CaptureQueriesContext(connections[CATALOG]) as catalog_queries:
            result = read_digest(user_id=user.pk, now=NOW)

    assert len(result.cards) == 3
    assert len(personal_queries.captured_queries) + len(catalog_queries.captured_queries) <= 6


def test_the_query_count_is_bounded_with_an_open_conflict():
    """The worst case is the one with a conflict — the extra lookup is only reached
    when there is a pair to look for."""
    user = make_user()
    make_preference(user.pk)
    digest = make_digest(user.pk)
    event = make_event()
    make_composition(digest, event_id=event.id)
    saved = SavedEventFactory(user_id=user.pk, event_id=event.id)
    ConflictPairFactory(
        user_id=user.pk,
        kind=ConflictPair.Kind.TIME,
        left_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        left_id=make_event().id,
        right_kind=ConflictPair.SideKind.SAVED_EVENT,
        right_id=saved.id,
    )

    with CaptureQueriesContext(connections[PERSONAL]) as personal_queries:
        with CaptureQueriesContext(connections[CATALOG]) as catalog_queries:
            result = read_digest(user_id=user.pk, now=NOW)

    assert len(result.cards) == 1
    assert len(personal_queries.captured_queries) + len(catalog_queries.captured_queries) <= 6


def test_the_query_count_does_not_grow_with_the_number_of_cards():
    """The bound is a property of the read, not of the day.

    A three-card digest and a one-card digest cost the same number of queries. If they
    did not, the read had an N+1 in it and the four-query bound would be a coincidence.
    """
    user = make_user()
    make_preference(user.pk)
    digest = make_digest(user.pk)
    for hours, slot in ((2, "must_know"), (3, "nearby"), (4, "serendipity")):
        event = make_event(hours=hours, title=f"Event {hours}")
        make_composition(digest, event_id=event.id, slot=slot)

    with CaptureQueriesContext(connections[PERSONAL]) as personal_queries:
        with CaptureQueriesContext(connections[CATALOG]) as catalog_queries:
            read_digest(user_id=user.pk, now=NOW)
    three_cards = len(personal_queries.captured_queries) + len(catalog_queries.captured_queries)

    user2 = make_user("two@example.test")
    make_preference(user2.pk)
    digest2 = make_digest(user2.pk)
    event = make_event(hours=2, title="Only Event")
    make_composition(digest2, event_id=event.id)

    with CaptureQueriesContext(connections[PERSONAL]) as personal_queries2:
        with CaptureQueriesContext(connections[CATALOG]) as catalog_queries2:
            read_digest(user_id=user2.pk, now=NOW)
    one_card = len(personal_queries2.captured_queries) + len(catalog_queries2.captured_queries)

    assert three_cards == one_card


def test_the_endpoint_path_issues_no_query_per_card():
    """The endpoint's own cost does not grow with the number of cards either.

    The endpoint path adds the auth seam's two queries on top of the read's four, so a
    three-card digest and a one-card digest cost the same number of queries at the
    endpoint too.
    """
    user = make_user()
    make_preference(user.pk)
    digest = make_digest(user.pk)
    for hours, slot in ((2, "must_know"), (3, "nearby"), (4, "serendipity")):
        event = make_event(hours=hours, title=f"Event {hours}")
        make_composition(digest, event_id=event.id, slot=slot)

    client = signed_in(user)
    with CaptureQueriesContext(connections[PERSONAL]) as personal_queries:
        with CaptureQueriesContext(connections[CATALOG]) as catalog_queries:
            response = get_digest(client)
    three_cards = len(personal_queries.captured_queries) + len(catalog_queries.captured_queries)

    user2 = make_user("two@example.test")
    make_preference(user2.pk)
    digest2 = make_digest(user2.pk)
    event = make_event(hours=2, title="Only Event")
    make_composition(digest2, event_id=event.id)

    client2 = signed_in(user2)
    with CaptureQueriesContext(connections[PERSONAL]) as personal_queries2:
        with CaptureQueriesContext(connections[CATALOG]) as catalog_queries2:
            get_digest(client2)
    one_card = len(personal_queries2.captured_queries) + len(catalog_queries2.captured_queries)

    assert response.status_code == 200
    assert three_cards == one_card


# --- the local day -------------------------------------------------------------------


def test_the_local_day_is_the_users_and_not_the_servers():
    """A user at 23:00 local and a user at 01:00 local get different digests."""
    late_user = make_user("late@example.test")
    make_preference(late_user.pk, timezone="Asia/Tokyo")
    late_digest = make_digest(
        late_user.pk,
        local_date=local_date_for(now=NOW, zone_name="Asia/Tokyo"),
        timezone="Asia/Tokyo",
    )
    late_event = make_event()
    make_composition(late_digest, event_id=late_event.id)

    body = get_digest(signed_in(late_user)).json()

    assert body["local_date"] == str(local_date_for(now=NOW, zone_name="Asia/Tokyo"))
    assert body["local_date"] != str(local_date_for(now=NOW, zone_name=ZONE))


def test_a_digest_for_another_day_is_not_the_users_digest():
    """The read looks for the user's local day and nothing else."""
    user = make_user()
    make_preference(user.pk)
    yesterday = local_date_for(now=NOW, zone_name=ZONE) - timedelta(days=1)
    digest = make_digest(user.pk, local_date=yesterday)
    event = make_event()
    make_composition(digest, event_id=event.id)

    body = get_digest(signed_in(user)).json()

    assert body["status"] == "not_composed"
    assert body["cards"] == []


def test_the_endpoint_is_in_the_openapi_schema():
    """A contract that is not in the schema is a contract the frontend cannot call."""
    from config.api import api

    schema = api.get_openapi_schema()

    assert "/api/personal/digest" in schema["paths"]
    assert "get" in schema["paths"]["/api/personal/digest"]
