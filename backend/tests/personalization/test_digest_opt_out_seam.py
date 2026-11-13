"""The seam: what a user opts out of, through the settings screen, reaches the digest.

**FR-19's opt-out is a promise made in two places, and this is the test that holds
both of them to it.**

The promise is made in the *settings screen* — the user presses a button, and the
browser sends `include_personal_events` to the API. The promise is kept in the
*composition service* — the digest reads the preference and leaves the personal event
out. **Those are two different paths that meet at a database column**, and until this
file existed, no test walked both of them.

**Why the two existing suites were not enough.** `test_onboarding_api.py` proves the
endpoint stores what it was sent. `test_digest_composition.py` proves the composition
honours the flag — but every one of its four opt-out tests writes the flag with a
**direct ORM factory write**, never through the API. So a regression in the *write*
path — a field dropped from the body, a key renamed, a field the endpoint silently
ignores because it was omitted — would leave every backend test green and the product
broken. **The two sides were tested; the seam was not.**

**So this file writes the way the settings screen writes** — over HTTP, through the
real endpoint — and then composes a digest for that same user.

**The write is over HTTP, not through the service function.** `set_digest_preference`
is the *second* half of the write path; the endpoint is the *first*. A test that
called the service function would still miss a broken schema binding or a serializer
that dropped the field. **This calls the thing the browser calls.**

**The user's id is the seam's hinge.** `request.user.pk` is a UUID and
`DigestPreference.user_id` is a UUIDField — the same id space — so a real signed-in
user *is* the `user_id` the composition reads by.
"""

from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model

from apps.personalization.services.digest_composition import compose_digest
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from tests.csrf import CsrfClient
from tests.ingestion.factories import EventFactory, VenueFactory
from tests.personalization.factories import PersonalEventFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()

#: A Wednesday. 2026-11-04 16:00 UTC is 09:00 in Los Angeles (PST), and 08:00 in New
#: York (EST).
NOW = datetime(2026, 11, 4, 16, 0, tzinfo=UTC)

ACTOR = Actor.system("digest_composition")

CITY = "Los Angeles"
ZONE = "America/Los_Angeles"

#: The delivery time the settings screen round-trips alongside the flag. The endpoint
#: requires it — `DigestPreferenceIn.delivery_time` is not nullable — so it is in
#: every body here, exactly as the toggle sends it.
DELIVERY_TIME = "09:00:00"


# --- the fixture ----------------------------------------------------------------------


def make_user(email="sam@example.test"):
    """A real user with a real pk — the session resolves to this one."""
    return User.objects.create_user(email=email, password="pw")


def signed_in(user=None):
    """A client whose session identifies `user`."""
    client = CsrfClient()
    client.force_login(user or make_user())
    return client


def make_event(*, hours=2, title="Brooklyn Tech Meetup", city=CITY, **overrides):
    """A published, eligible public event.

    **`last_seen_at` is pinned to `NOW`.** FR-14's staleness bound is measured from it
    against the *test's* clock, and the column's default is the wall clock — so an
    event built with the default would be days stale against a `NOW` in the future, and
    the candidate read would drop it before the composition ever saw it. Pinning it
    makes "seen by the catalog right now" the default, which is what a fresh event is.
    """
    fields = {
        "title": title,
        "venue": VenueFactory(city=city, venue_fingerprint=f"venue-{title}|{city}"),
        "start_time_utc": NOW + timedelta(hours=hours),
        "last_seen_at": NOW,
    }
    fields.update(overrides)
    return EventFactory(**fields)


def make_personal(user_id, *, hours=3, **overrides):
    """A personal event on the user's own agenda.

    **Three hours out — inside FR-5's 48-hour window, and not on its edge.** The
    candidate read is `start_utc >= now` and `start_utc <= now + 48h`, both ends
    inclusive, so an event on the boundary would be a test that depends on an
    inclusive edge. This one does not.

    **`end_utc` is derived from `start_utc`.** The factory's default end is a fixed
    instant from the factory module's own clock, so overriding only `start_utc` would
    leave the end *before* the start and trip the model's `end_after_start_ck`.
    """
    start = NOW + timedelta(hours=hours)
    fields = {"user_id": user_id, "start_utc": start, "end_utc": start + timedelta(hours=2)}
    fields.update(overrides)
    return PersonalEventFactory(**fields)


def opt_out(client, *, include):
    """Set the preference the way the settings screen sets it.

    **The body is exactly what the toggle sends** — the flag, plus the delivery time
    and the zone it round-trips, because the endpoint requires both.

    **No `city`.** The endpoint resolves a city against the catalog's covered cities,
    which is a different code path and a different assertion. The seam under test is
    the opt-out.
    """
    response = client.put(
        "/api/personal/onboarding/digest-preference",
        {
            "include_personal_events": include,
            "delivery_time": DELIVERY_TIME,
            "timezone": ZONE,
        },
        content_type="application/json",
    )
    assert response.status_code == 200
    return response


def compose(user_id, *, now=NOW, actor=ACTOR):
    return compose_digest(user_id=user_id, actor=actor, now=now)


def rows_of(result):
    return {row.slot: row for row in result.compositions}


# --- the seam ------------------------------------------------------------------------


def test_a_user_who_opted_out_gets_a_digest_with_no_personal_event():
    """**The proof.** The value the settings screen wrote is the value the composition
    read, and the personal event is not in the digest."""
    user = make_user()
    client = signed_in(user)
    opt_out(client, include=False)

    personal = make_personal(user.pk, hours=3)
    public = make_event(hours=2, title="Public Event")

    result = compose(user.pk)
    rows = rows_of(result)

    # **The personal event is not in the digest.**
    assert all(row.event_kind == "public" for row in result.compositions)
    assert personal.id not in {row.event_id for row in result.compositions}

    # **And the public fallback took Slot 1.** Without this, "no personal event" would
    # be satisfied by a digest that fell through for the wrong reason — a broken
    # candidate read, an event outside the window, a fixture mistake. **This is the
    # assertion that separates "the opt-out removed it" from "there was never one".**
    assert rows["must_know"].event_id == public.id

    # **And the product does not know about it.** The count is suppressed, so an
    # opted-out event is not the reason the user keeps receiving a Ping — a quieter
    # leak of the same bug that would survive the visible one being fixed.
    assert result.personal_qualifying_count == 0


def test_a_user_who_did_not_opt_out_still_gets_their_personal_event():
    """**The proof is not vacuous.** A digest that never contained personal events
    would satisfy the opt-out assertion too — so the same path, with the flag on, must
    put the personal event in Slot 1."""
    user = make_user()
    client = signed_in(user)
    opt_out(client, include=True)

    personal = make_personal(user.pk, hours=3)
    make_event(hours=2, title="Public Event")

    result = compose(user.pk)
    rows = rows_of(result)

    assert rows["must_know"].event_id == personal.id
    assert rows["must_know"].event_kind == "personal"
    # **And the count is live** — the same reason the opt-out suppresses it.
    assert result.personal_qualifying_count == 1


def test_a_user_who_opts_back_in_gets_their_personal_event_back():
    """**The control is not write-once.** Opting out and then opting back in restores
    the event.

    **This also exercises the other half of the write path.** The first `PUT` creates
    the preference row; the second finds it and updates it — a different branch of
    `_write_digest` from the first, and the one that could leave a stale flag behind.

    **The digest is composed once, after the opt-back-in.** The composition is
    idempotent per local date — a digest already persisted for the user's day is
    returned as it was (`digest_composition.py:699-712`) — so composing while opted
    out and then composing again would read back the *first* digest and prove nothing
    about the flag. **The opt-out side of this pair is the first test's job; this one
    is about the flag coming back.**
    """
    user = make_user()
    client = signed_in(user)

    opt_out(client, include=False)
    personal = make_personal(user.pk, hours=3)
    make_event(hours=2, title="Public Event")

    # **And opting back in brings it.**
    opt_out(client, include=True)

    result = compose(user.pk)
    rows = rows_of(result)

    assert rows["must_know"].event_id == personal.id
    assert rows["must_know"].event_kind == "personal"
    assert result.personal_qualifying_count == 1
