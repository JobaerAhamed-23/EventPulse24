"""The Detail Screen's endpoints (FR-24, AD-12, AD-19).

`GET /api/events/{id}` is the Detail Screen's read, and `POST /api/events/{id}/opened`
records that the screen was opened.

**This surface serves two audiences with different rights.** The IA marks `/events/:id`
as "Authed + Anon (read-only)": a signed-in user may see their own explanation, and an
anonymous visitor may see the event and nothing personal at all (AD-12).

**So the router has no `auth=`, and the handler resolves the user itself.** A router's
`auth=` is all-or-nothing, and this route needs both answers — so the two rules live in
the two handlers. The read calls `unauthenticated_user(request)` and branches; the write
calls `current_user(request)`, which raises a 401 for an anonymous caller and runs the
CSRF check, which an unsafe method needs.

**Why the write is a `POST` and not a side effect of the `GET`.** The detail-open signal
feeds the neighbor count, and a signal anyone can forge inflates a number that is
supposed to mean "other people are interested in this". A `GET` that writes is exactly
the shape CSRF exists to stop — a third-party page can make a browser issue a `GET` —
and Django's own rule is that only **unsafe** methods carry the CSRF token, so
`require_csrf` returns early on a `GET` and checks nothing. A signal recorded from an
unprotected `GET` is forgeable.

So the read writes **nothing at all**, and the signal is a separate request the frontend
fires when the screen is actually shown. The cost is a second round trip, and the trade
is stated rather than hidden.

**The anonymous path never touches the `personal` schema.** Not "does not return personal
data" — does not query it. A test asserts the personal alias was never queried on an
anonymous request. The strongest statement about a leak is that the query never happened.

**The Event Fit is not reached from here (AD-10).** This is the surface where the
substitution would be most tempting: an anonymous visitor sees an event with no personal
explanation, and the Event Fit is the one explanation an anonymous visitor is allowed to
see. Reaching for it would be the substitution AD-10 calls "company-ending".

**This is not the public catalog's endpoint.** `GET /api/catalog/events/{id}` is the
catalog listing: session-free, cacheable, and never touching `personal` (AD-12). This
one is the Detail Screen, which is a personal surface that happens to degrade.
"""

from uuid import UUID

from django.utils import timezone
from ninja import Router, Status

from apps.identity.api_auth import current_user, unauthenticated_user
from apps.personalization.schemas import (
    DetailPersonalOut,
    EventDetailFactsOut,
    EventDetailOut,
    WhyThisOut,
)
from apps.personalization.services.detail_opens import record_detail_open
from apps.personalization.services.detail_read import read_event_detail
from shared.actor import Actor
from shared.errors import ErrorOut

# **No `auth=`.** This route serves anonymous callers, and `current_user` would answer
# them with a 401 — which is right for `/api/personal/*` and wrong here. The two
# handlers below apply their own rules.
router = Router(tags=["events"])


def _facts(event) -> EventDetailFactsOut:
    """The event's public facts, projected onto the wire shape."""
    return EventDetailFactsOut(
        id=event.id,
        slug=event.slug,
        title=event.title,
        description=event.description,
        canonical_url=event.canonical_url,
        start_time_utc=event.start_time_utc,
        start_time_tz=event.start_time_tz,
        end_time_utc=event.end_time_utc,
        venue_name=event.venue_name,
        venue_city=event.venue_city,
        venue_country_code=event.venue_country_code,
        status=event.status,
        event_version=event.event_version,
        source_name=event.source_name,
        tz_review_pending=event.tz_review_pending,
        is_sold_out=event.is_sold_out,
    )


@router.get(
    "/{event_id}",
    response={200: EventDetailOut, 404: ErrorOut},
    summary="Get one event's Detail Screen",
    description=(
        "The Detail Screen's data. A signed-in caller also receives their own why-this "
        "breakdown, their saved state, and the k-anonymous neighbor count; an anonymous "
        "caller receives the public facts and nothing personal. "
        "An event that is not public — or that has already started — reads as not found, "
        "the same set the public catalog shows."
    ),
)
def get_event_detail(request, event_id: UUID):
    """One event's Detail Screen. Raises `EventNotFoundError` (a 404) when there isn't one."""
    user = unauthenticated_user(request)
    detail = read_event_detail(
        event_id=event_id,
        user_id=user.pk if user is not None else None,
        now=timezone.now(),
    )

    personal = None
    if detail.personal is not None:
        personal = DetailPersonalOut(
            why_this=(
                WhyThisOut(
                    tags=list(detail.personal.why_this.tags),
                    bucket=detail.personal.why_this.bucket,
                    source_badge=detail.personal.why_this.source_badge,
                    composed_at=detail.personal.why_this.composed_at,
                    slot=detail.personal.why_this.slot,
                )
                if detail.personal.why_this is not None
                else None
            ),
            saved=detail.personal.saved,
            neighbor_bucket=detail.personal.neighbors.bucket,
        )

    return EventDetailOut(event=_facts(detail.event), personal=personal)


@router.post(
    "/{event_id}/opened",
    response={204: None},
    summary="Record that the Detail Screen was opened",
    description=(
        "Records that the signed-in user opened this event's Detail Screen, which is one "
        "of the two signals that make a user count as a neighbor (FR-24). "
        "The signal is recorded once per `(user, event)`: opening the screen again "
        "refreshes the timestamp rather than adding a row. "
        "Anonymous callers are refused."
    ),
)
def post_event_opened(request, event_id: UUID):
    """Record the detail-open signal. 204 on success; 401 for an anonymous caller."""
    user = current_user(request)
    record_detail_open(
        user_id=user.pk,
        event_id=event_id,
        actor=Actor.user(user.pk),
        now=timezone.now(),
    )
    return Status(204, None)
