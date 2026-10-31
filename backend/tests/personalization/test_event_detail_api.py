"""The Detail Screen API: the persisted breakdown, and the k-anonymous count (FR-24, AD-10).

**What these tests pin**, grouped by the rule each one protects:

- **the breakdown is persisted, never recomputed** — it comes from the most recent
  `DigestComposition` for `(user, event)`, whatever day it was composed, and when there
  is none the response carries an **explicit absence**;
- **the ranking is never called** — the single most important test in the intent, and
  it is a monkeypatch that makes `domain/ranking.py` raise;
- **the anonymous caller gets the public facts and nothing personal** — no breakdown, no
  bucket, no neighbor count, no saved state, and the `personal` schema is never queried;
- **the Event Fit is not reached** from either path (AD-10);
- **the neighbor count honours k-anonymity** — suppressed below 5, bucketed above it,
  and the exact count is nowhere in the payload;
- **the detail-open signal is recorded once per `(user, event)`**, by a `POST` that a
  `GET` cannot forge.

The client is a `CsrfClient` for the write, because the detail-open `POST` runs the
CSRF check (D13). The read is a plain `Client` — an anonymous caller has no token, and
the read must not need one.
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone as django_timezone

from apps.personalization.models import EventDetailOpen, PersonalizationAuditEntry
from apps.personalization.services.detail_read import read_event_detail
from apps.personalization.services.neighbor_count import (
    NEIGHBOR_BUCKET_A_LOT,
    NEIGHBOR_BUCKET_FEW,
    NEIGHBOR_BUCKET_MANY,
    NEIGHBOR_BUCKET_SOME,
    NEIGHBOR_COUNT_MIN,
    NEIGHBOR_QUALIFYING_WINDOW,
    bucket_for,
    count_neighbors,
)
from shared.db import CATALOG, PERSONAL
from tests.csrf import CsrfClient
from tests.ingestion.factories import EventFactory, VenueFactory
from tests.personalization.factories import (
    DigestCompositionFactory,
    EventDetailOpenFactory,
    SavedEventFactory,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()

#: The endpoint resolves "now" itself, from the wall clock — so the event it looks for
#: is one that has not started yet, and the instants in the tests are measured from the
#: same "today". Pinned at import time so every instant in a file is measured from one
#: "now".
NOW = django_timezone.now()

#: The event starts tomorrow, so it is inside the public catalog's "has not started yet"
#: bound for the whole test run.
START = NOW + timedelta(days=1)

CITY = "Los Angeles"


def make_user(email=None):
    """A real user with a real pk — the session resolves to this one.

    The email is unique by default: several tests create two users, and the identity
    schema's `user_email_uq` constraint is real.
    """
    return User.objects.create_user(email=email or f"sam-{uuid4().hex}@example.test", password="pw")


def signed_in(user=None):
    """A client whose session identifies `user`."""
    client = Client()
    client.force_login(user or make_user())
    return client


def make_event(**overrides):
    """A published, upcoming public event."""
    fields = {
        "title": "Brooklyn Tech Meetup",
        "description": "A night of talks about the things we build.",
        "venue": VenueFactory(city=CITY),
        "start_time_utc": START,
        "last_seen_at": NOW,
    }
    fields.update(overrides)
    return EventFactory(**fields)


def detail_url(event) -> str:
    return f"/api/events/{event.id}"


# ── The public facts ────────────────────────────────────────────────────────────


def test_the_detail_carries_the_events_public_facts():
    """The catalog's own fields, read through the published interface."""
    event = make_event()
    user = make_user()

    body = signed_in(user).get(detail_url(event)).json()

    assert body["event"]["id"] == str(event.id)
    assert body["event"]["title"] == event.title
    assert body["event"]["description"] == event.description
    assert body["event"]["slug"] == event.slug
    assert body["event"]["canonical_url"] == event.canonical_url
    assert body["event"]["venue_name"] == event.venue.name
    assert body["event"]["venue_city"] == CITY
    assert body["event"]["venue_country_code"] == event.venue.country_code
    assert body["event"]["status"] == event.status
    assert body["event"]["source_name"] == event.source.name


def test_the_detail_carries_the_time_as_an_instant_plus_the_zone():
    """AD-6: display conversion happens at the presentation edge, never in the API."""
    event = make_event()

    body = signed_in().get(detail_url(event)).json()

    # The instant and the zone travel separately: the API never renders a local time.
    # The wire form is an ISO instant in UTC ("...Z"), so compare the instants rather
    # than the strings — the serializer's precision is not the contract, the instant is.
    assert body["event"]["start_time_utc"].endswith("Z")
    parsed = django_timezone.datetime.fromisoformat(
        body["event"]["start_time_utc"].replace("Z", "+00:00")
    )
    assert abs((parsed - event.start_time_utc).total_seconds()) < 0.001
    assert body["event"]["start_time_tz"] == event.start_time_tz


def test_the_sold_out_state_flows_through():
    """A-15 / FR-53: `Event.is_sold_out` exists, so the screen shows it."""
    event = make_event(is_sold_out=True)

    body = signed_in().get(detail_url(event)).json()

    assert body["event"]["is_sold_out"] is True


def test_an_event_that_is_not_public_is_a_404():
    """The Detail Screen shows the same set the public catalog lists."""
    event = make_event(publication_status="in_review")

    response = signed_in().get(detail_url(event))

    assert response.status_code == 404


def test_an_event_that_has_already_started_is_a_404():
    """The public catalog's bound is "has not started yet", and this is the same set."""
    event = make_event(start_time_utc=NOW - timedelta(hours=1))

    response = signed_in().get(detail_url(event))

    assert response.status_code == 404


def test_an_unknown_event_is_a_404():
    response = signed_in().get(f"/api/events/{uuid4()}")

    assert response.status_code == 404


# ── The breakdown is persisted, never recomputed ─────────────────────────────────


def test_the_breakdown_comes_from_a_composition_made_today():
    """The persisted tags, bucket and badge — the row's own values."""
    event = make_event()
    user = make_user()
    DigestCompositionFactory(
        user_id=user.pk,
        event_id=event.id,
        tags=["nearby", "tonight", "saved"],
        bucket=4,
        source_badge="official_site",
        slot="must_know",
        composed_at=NOW - timedelta(hours=2),
    )

    body = signed_in(user).get(detail_url(event)).json()

    why = body["personal"]["why_this"]
    assert why is not None
    assert why["tags"] == ["nearby", "tonight", "saved"]
    assert why["bucket"] == 4
    assert why["source_badge"] == "official_site"
    assert why["slot"] == "must_know"


def test_the_breakdown_comes_from_a_composition_made_three_days_ago():
    """The most recent composition for the pair, **whatever day it was composed**.

    The Detail Screen is reachable for an event that is not in today's digest, and the
    explanation it shows is the one the user was given at the time.
    """
    event = make_event()
    user = make_user()
    DigestCompositionFactory(
        user_id=user.pk,
        event_id=event.id,
        tags=["nearby"],
        bucket=3,
        composed_at=NOW - timedelta(days=3),
    )

    body = signed_in(user).get(detail_url(event)).json()

    why = body["personal"]["why_this"]
    assert why is not None
    assert why["bucket"] == 3
    assert why["tags"] == ["nearby"]


def test_the_most_recent_composition_wins():
    """Two compositions for the pair: the newer one is the explanation."""
    event = make_event()
    user = make_user()
    DigestCompositionFactory(
        user_id=user.pk,
        event_id=event.id,
        tags=["nearby"],
        bucket=2,
        composed_at=NOW - timedelta(days=3),
    )
    DigestCompositionFactory(
        user_id=user.pk,
        event_id=event.id,
        tags=["tonight"],
        bucket=5,
        composed_at=NOW - timedelta(hours=1),
    )

    body = signed_in(user).get(detail_url(event)).json()

    why = body["personal"]["why_this"]
    assert why["bucket"] == 5
    assert why["tags"] == ["tonight"]


def test_no_composition_means_an_explicit_absence():
    """**The single most important test in the intent.**

    No composition means **no explanation**: not an empty breakdown, not a zero bucket,
    not a recomputed one. `why_this` is `None` — and `None` is a shape, not a magic
    value, so a client cannot mistake it for "we looked and the answer was nothing".
    """
    event = make_event()
    user = make_user()

    body = signed_in(user).get(detail_url(event)).json()

    assert body["personal"] is not None
    assert body["personal"]["why_this"] is None


def test_the_read_never_calls_the_ranking():
    """AD-10: "An explanation is never generated at view time."

    The ranking is monkeypatched to raise, so the test fails loudly if the read ever
    reaches it — whether to compute a score, a bucket or a tag.
    """
    import domain.ranking as ranking

    event = make_event()
    user = make_user()
    DigestCompositionFactory(user_id=user.pk, event_id=event.id)

    def explode(*args, **kwargs):
        raise AssertionError("the detail read called the ranking; AD-10 forbids it")

    for name in ("relevance_score", "score_bucket", "why_this_tags", "apply_hysteresis"):
        monkey = getattr(ranking, name)
        setattr(ranking, name, explode)
        try:
            body = signed_in(user).get(detail_url(event)).json()
        finally:
            setattr(ranking, name, monkey)
        assert body["personal"]["why_this"] is not None


def test_the_read_does_not_reach_the_event_fit():
    """AD-10: the two kinds of explanation never cross.

    This is the surface where the substitution would be most tempting — an anonymous
    visitor sees an event with no personal explanation, and the Event Fit is the one
    explanation an anonymous visitor may see. Reaching for it would be the substitution
    AD-10 calls "company-ending".
    """
    import apps.ingestion.event_fit.reads as event_fit_reads

    event = make_event()
    user = make_user()

    def explode(*args, **kwargs):
        raise AssertionError("the detail read reached the Event Fit; AD-10 forbids it")

    original = event_fit_reads.list_event_fit_for_city
    event_fit_reads.list_event_fit_for_city = explode
    try:
        signed_in(user).get(detail_url(event))
        Client().get(detail_url(event))
    finally:
        event_fit_reads.list_event_fit_for_city = original


# ── The anonymous caller ────────────────────────────────────────────────────────


def test_an_anonymous_caller_gets_the_public_facts():
    """The public facts are the same for everyone."""
    event = make_event()

    body = Client().get(detail_url(event)).json()

    assert body["event"]["id"] == str(event.id)
    assert body["event"]["title"] == event.title


def test_an_anonymous_caller_gets_nothing_personal():
    """No breakdown, no bucket, no neighbor count, no saved state.

    `personal` is `None` — not an empty object. "You are not signed in, so we looked up
    nothing" and "you are signed in and have nothing here" are different claims.
    """
    event = make_event()

    body = Client().get(detail_url(event)).json()

    assert body["personal"] is None


def test_the_anonymous_path_never_queries_the_personal_schema():
    """**The strongest statement about a leak is that the query never happened.**

    Not "does not return personal data" — does not *query* `personal`. The personal alias
    is wrapped, and the count of personal queries must be zero.
    """
    event = make_event()

    with CaptureQueriesContext(connections[PERSONAL]) as personal_queries:
        Client().get(detail_url(event))

    assert len(personal_queries) == 0, (
        "the anonymous detail path queried the personal schema: "
        + "; ".join(str(q["sql"]) for q in personal_queries)
    )


def test_the_anonymous_path_never_reads_another_users_explanation():
    """A composition exists for some other user; the anonymous caller sees nothing."""
    event = make_event()
    other = make_user()
    DigestCompositionFactory(user_id=other.pk, event_id=event.id, tags=["nearby"], bucket=4)

    body = Client().get(detail_url(event)).json()

    assert body["personal"] is None
    assert "why_this" not in body


def test_one_users_explanation_is_invisible_to_another():
    """The breakdown is scoped to the session user."""
    event = make_event()
    owner = make_user()
    other = make_user()
    DigestCompositionFactory(user_id=owner.pk, event_id=event.id, tags=["nearby"], bucket=4)

    body = signed_in(other).get(detail_url(event)).json()

    assert body["personal"]["why_this"] is None


def test_the_endpoint_takes_no_user_id_parameter():
    """No endpoint accepts a user id as an input — the scoping cannot be talked out of."""
    event = make_event()
    owner = make_user()
    DigestCompositionFactory(user_id=owner.pk, event_id=event.id, tags=["nearby"], bucket=4)

    body = signed_in().get(detail_url(event), {"user_id": str(owner.pk)}).json()

    assert body["personal"]["why_this"] is None


# ── The saved state ─────────────────────────────────────────────────────────────


def test_the_saved_flag_is_the_users_own():
    """The save button's state, read from the user's own save row."""
    event = make_event()
    user = make_user()
    SavedEventFactory(user_id=user.pk, event_id=event.id)

    body = signed_in(user).get(detail_url(event)).json()

    assert body["personal"]["saved"] is True


def test_an_unsaved_event_is_not_saved():
    event = make_event()

    body = signed_in().get(detail_url(event)).json()

    assert body["personal"]["saved"] is False


def test_another_users_save_is_not_yours():
    """The save is scoped to the session user."""
    event = make_event()
    other = make_user()
    SavedEventFactory(user_id=other.pk, event_id=event.id)

    body = signed_in().get(detail_url(event)).json()

    assert body["personal"]["saved"] is False


# ── The neighbor count, under k-anonymity ───────────────────────────────────────


def make_neighbors(event, count, *, now=NOW):
    """`count` distinct users who saved this event, all within the window."""
    for _ in range(count):
        SavedEventFactory(
            user_id=uuid4(),
            event_id=event.id,
            saved_at=now - timedelta(days=1),
        )


def test_four_neighbors_are_suppressed():
    """Below the threshold, the count says nothing at all."""
    event = make_event()
    make_neighbors(event, NEIGHBOR_COUNT_MIN - 1)

    body = signed_in().get(detail_url(event)).json()

    assert body["personal"]["neighbor_bucket"] is None


def test_five_neighbors_are_a_few():
    """Exactly at the threshold, the signal appears."""
    event = make_event()
    make_neighbors(event, NEIGHBOR_COUNT_MIN)

    body = signed_in().get(detail_url(event)).json()

    assert body["personal"]["neighbor_bucket"] == NEIGHBOR_BUCKET_FEW


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (5, NEIGHBOR_BUCKET_FEW),
        (9, NEIGHBOR_BUCKET_FEW),
        (10, NEIGHBOR_BUCKET_SOME),
        (24, NEIGHBOR_BUCKET_SOME),
        (25, NEIGHBOR_BUCKET_MANY),
        (99, NEIGHBOR_BUCKET_MANY),
        (100, NEIGHBOR_BUCKET_A_LOT),
        (101, NEIGHBOR_BUCKET_A_LOT),
    ],
)
def test_the_buckets_are_the_ones_fr_24_names(count, expected):
    """FR-24's four buckets: 5–9, 10–24, 25–99, 100+.

    The boundaries are inclusive upper bounds, so 9 is "few" and 10 is "some".
    """
    event = make_event()
    make_neighbors(event, count)

    body = signed_in().get(detail_url(event)).json()

    assert body["personal"]["neighbor_bucket"] == expected


def test_the_bucket_function_is_the_rule():
    """The pure function, at every boundary the buckets name."""
    assert bucket_for(0) is None
    assert bucket_for(4) is None
    assert bucket_for(5) == NEIGHBOR_BUCKET_FEW
    assert bucket_for(9) == NEIGHBOR_BUCKET_FEW
    assert bucket_for(10) == NEIGHBOR_BUCKET_SOME
    assert bucket_for(24) == NEIGHBOR_BUCKET_SOME
    assert bucket_for(25) == NEIGHBOR_BUCKET_MANY
    assert bucket_for(99) == NEIGHBOR_BUCKET_MANY
    assert bucket_for(100) == NEIGHBOR_BUCKET_A_LOT
    assert bucket_for(10_000) == NEIGHBOR_BUCKET_A_LOT


def test_the_payload_never_carries_an_exact_count():
    """FR-24: "Exact counts are never exposed."

    **There is no count field, anywhere.** The assertion is on the *shape* — the whole
    body is searched for a field that could hold a number — so a later change that adds
    `neighbor_count` fails here rather than shipping.
    """
    event = make_event()
    make_neighbors(event, 7)

    body = signed_in().get(detail_url(event)).json()

    assert "neighbor_count" not in body["personal"]
    assert "count" not in body["personal"]
    # The whole shape, so a later change that adds a field fails here rather than
    # shipping. `conflict` is the Detail Screen's active pair for this event (FR-33).
    assert set(body["personal"]) == {"why_this", "saved", "neighbor_bucket", "conflict"}


def test_a_save_outside_the_window_does_not_qualify():
    """FR-24: "in the last 30 days" — a save 31 days ago does not count."""
    event = make_event()
    SavedEventFactory(
        user_id=uuid4(),
        event_id=event.id,
        saved_at=NOW - NEIGHBOR_QUALIFYING_WINDOW - timedelta(seconds=1),
    )

    body = signed_in().get(detail_url(event)).json()

    assert body["personal"]["neighbor_bucket"] is None


def test_a_save_exactly_on_the_window_boundary_qualifies():
    """The window is inclusive: a save exactly 30 days old still counts.

    **This is pinned at the service, not at the endpoint.** The endpoint resolves "now"
    from the wall clock, so an exact instant cannot be stated against it — the request
    happens a few milliseconds after the test's reference. `count_neighbors` takes `now`
    as a parameter, so the boundary is exactly expressible there, and the endpoint-level
    tests above and below cover the same rule with a margin.
    """
    event = make_event()
    SavedEventFactory(
        user_id=uuid4(),
        event_id=event.id,
        saved_at=NOW - NEIGHBOR_QUALIFYING_WINDOW,
    )
    make_neighbors(event, NEIGHBOR_COUNT_MIN - 1)

    count = count_neighbors(event_id=event.id, now=NOW)

    assert count.bucket == NEIGHBOR_BUCKET_FEW


def test_a_save_one_second_inside_the_window_qualifies():
    """The same rule, one second inside the boundary."""
    event = make_event()
    SavedEventFactory(
        user_id=uuid4(),
        event_id=event.id,
        saved_at=NOW - NEIGHBOR_QUALIFYING_WINDOW + timedelta(seconds=1),
    )
    make_neighbors(event, NEIGHBOR_COUNT_MIN - 1)

    count = count_neighbors(event_id=event.id, now=NOW)

    assert count.bucket == NEIGHBOR_BUCKET_FEW


def test_an_open_outside_the_window_does_not_qualify():
    """The open half of the signal obeys the same window."""
    event = make_event()
    EventDetailOpenFactory(
        user_id=uuid4(),
        event_id=event.id,
        opened_at=NOW - NEIGHBOR_QUALIFYING_WINDOW - timedelta(seconds=1),
    )

    body = signed_in().get(detail_url(event)).json()

    assert body["personal"]["neighbor_bucket"] is None


def test_a_user_who_saved_and_opened_counts_once():
    """**Distinct users, not signals.** A join would multiply that user.

    The dual-signal user plus four others make **five distinct users**, which reaches
    the threshold. If the two signals were counted separately, the same five users would
    be six signals and the bucket would still read "few" — so this test also pins the
    count *at the threshold*, where a multiplication would show up as a different bucket.
    """
    event = make_event()
    user_id = uuid4()
    SavedEventFactory(user_id=user_id, event_id=event.id, saved_at=NOW - timedelta(days=1))
    EventDetailOpenFactory(user_id=user_id, event_id=event.id, opened_at=NOW - timedelta(days=1))
    make_neighbors(event, NEIGHBOR_COUNT_MIN - 1)

    body = signed_in().get(detail_url(event)).json()

    assert body["personal"]["neighbor_bucket"] == NEIGHBOR_BUCKET_FEW


def test_a_user_who_saved_and_opened_does_not_push_the_count_over_the_threshold():
    """The multiplication would be visible: four distinct users, five signals.

    Four users who qualify — one of whom has both signals — are **four users**, so the
    count stays below the threshold. If the two signals were counted separately, the
    count would be five and the bucket would appear.
    """
    event = make_event()
    user_id = uuid4()
    SavedEventFactory(user_id=user_id, event_id=event.id, saved_at=NOW - timedelta(days=1))
    EventDetailOpenFactory(user_id=user_id, event_id=event.id, opened_at=NOW - timedelta(days=1))
    make_neighbors(event, NEIGHBOR_COUNT_MIN - 2)

    body = signed_in().get(detail_url(event)).json()

    assert body["personal"]["neighbor_bucket"] is None


def _read_queries(queries):
    """The read's own queries — the session and identity reads are not the read's work.

    Django's session middleware reads the session row and the user row on every
    request. Those belong to the request, not to the Detail Screen's read, so they are
    excluded: what is left is the read's own work — the composition, the save, and the
    count's two signal reads.
    """
    return [
        str(query["sql"])
        for query in queries
        if "django_session" not in str(query["sql"]) and "identity_user" not in str(query["sql"])
    ]


def test_the_count_is_tier_agnostic():
    """FR-24's privacy floor: Pro and Free count identically.

    There is no subscription entity yet, so this holds trivially — but the assertion is
    on the **shape of the query**, not on the prose. A tier filter would have to filter
    on a tier column, and the two signal queries filter on nothing but the event and the
    window. That is a statement about the SQL that actually runs, so a later change
    that added a tier predicate would fail here.
    """
    event = make_event()
    make_neighbors(event, 6)

    client = signed_in()
    with CaptureQueriesContext(connections[PERSONAL]) as personal_queries:
        client.get(detail_url(event))

    signal_queries = [
        sql
        for sql in _read_queries(personal_queries)
        if "personalization_savedevent" in sql or "personalization_eventdetailopen" in sql
    ]

    # The save read (`_is_saved`) plus the count's two signal reads.
    assert len(signal_queries) == 3
    for sql in signal_queries:
        # The only predicates are the event and the window.
        assert "tier" not in sql.lower()
        assert "subscription" not in sql.lower()


def test_the_count_does_not_grow_with_the_number_of_neighbors():
    """One aggregate per signal, not one query per neighbour.

    The capture covers **only the read**: the client is logged in before the capture
    opens, so the login's own writes are not counted. What is counted is the read's
    work — the composition, the save, and the count's two signal reads — and that is a
    constant, whatever the neighbour count is.
    """
    event = make_event()
    make_neighbors(event, 40)

    client = signed_in()
    with CaptureQueriesContext(connections[PERSONAL]) as personal_queries:
        client.get(detail_url(event))

    # The composition, the save, the count's two signal reads — a constant.
    assert len(_read_queries(personal_queries)) <= 4, (
        "the detail read's personal query count grew: "
        + "; ".join(str(q["sql"]) for q in personal_queries)
    )


def test_the_count_does_not_grow_with_the_number_of_neighbors_either():
    """The same bound with far more neighbours, and the same queries.

    Forty neighbours and a hundred and fifty take the same number of queries: the count
    is two aggregates over the signal tables, not a loop over the neighbours.
    """
    event = make_event()
    make_neighbors(event, 150)

    client = signed_in()
    with CaptureQueriesContext(connections[PERSONAL]) as personal_queries:
        client.get(detail_url(event))

    assert len(_read_queries(personal_queries)) <= 4, (
        "the detail read's personal query count grew with the neighbour count: "
        + "; ".join(str(q["sql"]) for q in personal_queries)
    )


# ── The detail-open signal ──────────────────────────────────────────────────────


def test_the_open_signal_is_recorded():
    """The `POST` records the signal, with its audit row."""
    event = make_event()
    user = make_user()
    client = CsrfClient()
    client.force_login(user)

    response = client.post(f"/api/events/{event.id}/opened")

    assert response.status_code == 204
    opened = EventDetailOpen.objects.using(PERSONAL).get(user_id=user.pk, event_id=event.id)
    assert opened.opened_at is not None
    audit = PersonalizationAuditEntry.objects.using(PERSONAL).get(
        action="event_detail.opened", target_id=opened.id
    )
    assert audit.details["event_id"] == str(event.id)


def test_the_open_signal_is_recorded_once_per_pair():
    """Opening the screen again refreshes the timestamp; it does not add a row."""
    event = make_event()
    user = make_user()
    client = CsrfClient()
    client.force_login(user)

    client.post(f"/api/events/{event.id}/opened")
    first = EventDetailOpen.objects.using(PERSONAL).get(user_id=user.pk, event_id=event.id)
    client.post(f"/api/events/{event.id}/opened")
    second = EventDetailOpen.objects.using(PERSONAL).get(user_id=user.pk, event_id=event.id)

    assert EventDetailOpen.objects.using(PERSONAL).filter(user_id=user.pk).count() == 1
    assert second.opened_at >= first.opened_at


def test_an_anonymous_open_is_refused():
    """The signal is about a user, so an anonymous `POST` is a 401."""
    event = make_event()

    response = Client().post(f"/api/events/{event.id}/opened")

    assert response.status_code == 401
    assert not EventDetailOpen.objects.using(PERSONAL).exists()


def test_the_open_signal_makes_the_user_a_neighbor():
    """The signal and the count are joined: an open makes a qualifying user."""
    event = make_event()
    opener = make_user()
    make_neighbors(event, NEIGHBOR_COUNT_MIN - 1)
    EventDetailOpenFactory(
        user_id=opener.pk,
        event_id=event.id,
        opened_at=NOW - timedelta(days=1),
    )

    body = signed_in().get(detail_url(event)).json()

    assert body["personal"]["neighbor_bucket"] == NEIGHBOR_BUCKET_FEW


def test_the_read_writes_nothing():
    """**The `GET` writes nothing at all** — not even the signal.

    The signal is a separate `POST`, because a `GET` that writes is not protected by
    CSRF: Django checks the token only on unsafe methods.
    """
    event = make_event()
    user = make_user()

    signed_in(user).get(detail_url(event))

    assert not EventDetailOpen.objects.using(PERSONAL).exists()


def test_the_open_signal_stores_nothing_but_the_pair_and_the_time():
    """The row answers one question and holds the minimum (AD-13)."""
    event = make_event()
    user = make_user()
    client = CsrfClient()
    client.force_login(user)

    client.post(f"/api/events/{event.id}/opened")

    opened = EventDetailOpen.objects.using(PERSONAL).get()
    fields = {f.name for f in opened._meta.get_fields()}
    assert fields == {"id", "user_id", "event_id", "opened_at"}


# ── The contract ────────────────────────────────────────────────────────────────


def test_the_endpoint_is_in_the_openapi_schema():
    """AD-19: the contract is generated, not hand-written."""
    from config.api import api

    paths = {
        f"{prefix}{path}"
        for prefix, router in getattr(api, "_routers", [])
        for path in router.path_operations
    }

    assert "/events/{event_id}" in paths
    assert "/events/{event_id}/opened" in paths


def test_the_reviews_and_similar_events_are_absent():
    """FR-24's out-of-scope items are **absent**, not present and empty.

    Reviews are ASSUM-6, deferred to Phase 3+. Similar-events needs attendance data
    that does not exist. An empty `similar_events: []` would say "we looked and there
    are none", which is a lie for a user who *has* attended events the app does not
    know about.
    """
    event = make_event()

    body = signed_in().get(detail_url(event)).json()

    assert "reviews" not in body
    assert "similar_events" not in body
    assert "rating" not in body


# ── The read, at the service level ──────────────────────────────────────────────


def test_the_service_reads_the_breakdown_and_the_count_together():
    """The service is the surface the endpoint projects, and it is testable directly."""
    event = make_event()
    user = make_user()
    DigestCompositionFactory(user_id=user.pk, event_id=event.id, tags=["nearby"], bucket=4)

    detail = read_event_detail(event_id=event.id, user_id=user.pk, now=NOW)

    assert detail.personal is not None
    assert detail.personal.why_this is not None
    assert detail.personal.why_this.tags == ("nearby",)
    assert detail.personal.why_this.bucket == 4
    assert detail.personal.saved is False


def test_the_service_gives_an_anonymous_caller_no_personal_state():
    event = make_event()

    detail = read_event_detail(event_id=event.id, user_id=None, now=NOW)

    assert detail.personal is None
    assert detail.event.id == event.id
