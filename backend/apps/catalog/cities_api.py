"""The city picker's choices (FR-2): `GET /api/public/cities`.

**This is not the preview's city list, and the difference is the whole point.**

`GET /api/public/preview/cities` answers *"which cities can the Pulse Preview serve right
now?"* — a live question, computed from `EventFit` rows, true only while those events are
upcoming. `list_supported_cities` is still the right answer to it and is unchanged.

This endpoint answers *"which cities may a reader pick?"* — a static question about the
curated catalog in `domain.city_catalog`, and it answers the same whether that city has a
thousand ingested events or none. A reader in Chittagong can pick Chittagong before
anything has ever been collected there; finding the events is `city-provisioning-service`'s
job, and saying so honestly while it tries is `browse-collecting-states`'.

Conflating the two is what made the picker a mirror of the catalog instead of a map of the
world. That is why this lives in its own module on its own route, rather than as a second
view in `preview_api.py` under the `/preview/` prefix.

**It runs no query.** The answer is a projection of a frozen module-level tuple, the way
`ranking_transparency_api` projects `shared.constants`. `tests/api/test_cities_api.py`
asserts zero queries, so a database read cannot be added later for symmetry with the
preview endpoint.

**No `auth=`, no session, no `request.user`, no `personal` read** (AD-12). The response is
byte-identical for every caller, which is what makes it cacheable — those are one fact, not
two. `tests/architecture/test_preview_anonymity.py` checks it structurally, in the source,
not only in the bytes.
"""

from django.http import HttpResponse
from ninja import Router, Status

from apps.catalog.preview_schemas import CityChoiceOut, CityChoicesOut
from apps.catalog.public_surface import cacheable, client_ip, throttle_key
from domain.city_catalog import choices
from ports.registry import get_throttle_port
from shared.constants import (
    CITY_CHOICES_CACHE_CONTROL,
    PREVIEW_THROTTLE_IP,
    PREVIEW_THROTTLE_WINDOW_SECONDS,
)
from shared.errors import ErrorOut

router = Router(tags=["preview"])


@router.get(
    "/cities",
    response={200: CityChoicesOut, 429: ErrorOut},
    summary="The cities a reader may pick",
    description=(
        "Every city in the curated catalog, alphabetically by label, as `value`/`label` "
        "pairs. `value` is the string to store; `label` is the disambiguating form to "
        "show. This is the picker's source and is independent of which cities have "
        "events — for that, see `/preview/cities`. No session is used and none is set."
    ),
)
def city_choices(request, response: HttpResponse):
    """Every pickable city, alphabetical by label."""
    # Its own scope, so this route and the preview's cannot spend each other's budget.
    # Serving this response is cheaper than checking the throttle — the limit is here so
    # that "every anonymous route on this surface is throttled" stays a rule rather than a
    # judgement made afresh each time a route is added.
    decision = get_throttle_port().check(
        throttle_key(client_ip(request), scope="cities"),
        limit=PREVIEW_THROTTLE_IP,
        window_seconds=PREVIEW_THROTTLE_WINDOW_SECONDS,
    )
    if not decision.allowed:
        response["Retry-After"] = str(decision.retry_after_seconds)
        response["Cache-Control"] = "no-store"
        return Status(429, ErrorOut(code="rate_limited", message="Too many requests."))

    cacheable(response)
    # Longer than the preview's: these choices change when code ships, not when events
    # are ingested.
    response["Cache-Control"] = CITY_CHOICES_CACHE_CONTROL
    return CityChoicesOut(
        cities=[CityChoiceOut(value=row.name, label=row.label) for row in choices()]
    )


__all__ = ["city_choices", "router"]
