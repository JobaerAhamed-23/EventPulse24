"""The coverage request's endpoint: `POST /api/catalog/coverage-requests`.

**The write behind the no-sources state.** A reader whose city has no sources is offered
one way out — ask us to go and cover it — and this is where that ask goes.

**It lives on the `/catalog` prefix because the row is a catalog row.** The request is
about a *place* — editorial reads a queue of cities nobody covers us — so it belongs beside
the Source Registry, on the catalog side of the AD-3 wall (AD-16). `apps.ingestion` may
import its own models (the one exception the `models-ingestion` contract makes), and the
row's writer is this app.

**AD-12's session-free rule applies to the *public* catalog, and this is not it.** The
public catalog's answers are identical for every caller, which is what makes them
cacheable. **This is a write, and every write on this surface is a signed-in act** — so the
router carries `auth=current_user`, the same resolver every other authed endpoint uses.
The auth lives on the **router**, not on the operation, so the reader's id comes from the
session and never from a payload.

**The body carries a city and nothing else.** No user id — that is the rule
`apps.identity.api_auth` states, and the reason every endpoint in this project refuses one:
a user-supplied id in a payload is the classic way scoping goes wrong, because the client
asserts *who it is* and the server believes it.

**The layer is thin.** It parses the body, calls the published command, and projects the
command's plain data back onto the wire shape. It never touches the ORM (AD-5).
"""

from ninja import Router, Status

from apps.identity.api_auth import current_user
from apps.ingestion.schemas import CoverageRequestIn, CoverageRequestOut
from apps.ingestion.services.coverage_requests import request_coverage
from shared.actor import Actor
from shared.errors import ErrorOut

router = Router(tags=["catalog"], auth=current_user)


@router.post(
    "/coverage-requests",
    response={201: CoverageRequestOut, 422: ErrorOut, 429: ErrorOut},
    summary="Ask us to cover a city we have no sources for",
    description=(
        "Records that a reader wants us to cover a city we have not covered\n\n"
        "**One row per city, always.** A second request for the same city does not "
        "create a second row — the database refuses it — and the count of how many "
        "readers have asked goes up instead. The request is recorded whether it is the "
        "first or the hundredth, and the answer is the same either way.\n\n"
        "**The city must be one we know about.** A request is for a city we have already "
        "tried to cover and failed to. A city we have never heard of is a *pick*, and "
        "picking it provisions it immediately — which is a better answer than queueing "
        "it. So an unknown city answers 422, and nothing is written.\n\n"
        "Five requests per reader per day; the sixth answers 429 with the wait. The "
        "limit is checked before the one-row rule, so a repeated request still spends an "
        "attempt."
    ),
    operation_id="request_city_coverage",
)
def request_city_coverage(request, body: CoverageRequestIn):
    """Record one coverage request. 422 for a city we do not have; 429 past the limit."""
    outcome = request_coverage(
        city=body.city,
        # **The reader comes from the session, never from the body.**
        actor=Actor.user(request.user.pk),
    )
    return Status(
        201,
        CoverageRequestOut(
            city=outcome.city,
            recorded=True,
            request_count=outcome.request_count,
            created=outcome.created,
        ),
    )


__all__ = ["request_city_coverage", "router"]
