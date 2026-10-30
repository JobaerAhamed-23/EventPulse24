"""The Pulse Preview's endpoints: the cards for a city, and the supported cities (FR-2).

`GET /api/public/preview` and `GET /api/public/preview/cities` are the backend of the
Pulse Preview — the first value a visitor gets, before they have an account.

**This router has no `auth=` and no session.** django-ninja's `auth=` is the session
dependency; the preview router has none, and the endpoints never touch `request.user`,
never read `personal`, and set no cookie. That is AD-12: "Public event pages render fully
without a session." It is also what makes the response cacheable, and the two are the
same fact rather than two properties.

**The resolution order lives in one place.** There is one table of what happens when:

| Situation | Resolved city | `city_source` | Cards |
|---|---|---|---|
| `use_geo=false` (the opt-out) | the fallback city | `fallback` | the fallback city's |
| `city` given, supported | that city | `query` | that city's |
| `city` given, **not** supported | that city (unchanged) | `query` | **none** |
| no `city`, geo resolves to a supported city | that city | `geo` | that city's |
| no `city`, geo resolves to an unsupported city | the fallback city | `fallback` | its own |
| no `city`, geo resolves to nothing | the fallback city | `fallback` | the fallback city's |

**An explicit city is never silently replaced.** If the visitor picked a city the catalog
does not cover, the answer is an empty preview carrying **that** city's name — not the
fallback's events under the requested name, which would be a heading that lies. The
frontend shows "No preview available in {city} yet."

**The opt-out is honoured by not consulting the geo port at all.** "Don't use my
location" is a real choice, and a choice the server ignores is not a choice. When
`use_geo=false` the geo port is **not called** — a stronger claim than "called and the
answer ignored", and the stronger claim is the one a test can check.

**The resolved city is never stored and never logged** (PRD §10.2, FR-2's consent
banner). It is a response field and nothing else: no table, no cache entry, no session
key. It is computed, returned, and forgotten. Nothing on this path writes the city to a
log, and nothing pairs a city with an IP — the IP is used only as part of a throttle
key, which is the same treatment the auth endpoints give it.
"""

import ipaddress

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from ninja import Router, Status

from apps.catalog.preview_schemas import (
    CITY_SOURCE_FALLBACK,
    CITY_SOURCE_GEO,
    CITY_SOURCE_QUERY,
    PreviewCardOut,
    PreviewCitiesOut,
    PreviewOut,
)
from apps.ingestion.services.preview_read import (
    list_preview_cards,
    list_supported_cities,
)
from ports.registry import get_geo_port, get_throttle_port
from shared.constants import (
    GEO_CITY_MAX_LENGTH,
    PREVIEW_CACHE_CONTROL,
    PREVIEW_FALLBACK_CITY,
    PREVIEW_THROTTLE_IP,
    PREVIEW_THROTTLE_WINDOW_SECONDS,
    PREVIEW_VARY,
)
from shared.errors import ErrorOut

router = Router(tags=["preview"])

#: The number of cards the preview returns. Three is what FR-2 and the UX spec show.
PREVIEW_SIZE = 3


def _client_ip(request) -> str | None:
    """The caller's IP, for the throttle key and nothing else.

    **The same rule the auth endpoints use**, and for the same reason. It comes from
    `X-Forwarded-For` only when a trusted edge is known to overwrite that header
    (`settings.TRUST_FORWARDED_FOR`, off by default). The header is otherwise
    attacker-controlled: Next's rewrite forwards the browser's headers as they arrived,
    so a browser that sets `X-Forwarded-For` has that value reach Django unchanged.
    Trusting it unconditionally let any caller mint a fresh throttle bucket per request.

    The value must also parse as an IP address, so a caller cannot pad the key with
    arbitrary text. It is **never logged and never stored** (AD-13); it only ever becomes
    part of a throttle key.
    """
    if settings.TRUST_FORWARDED_FOR:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            candidate = forwarded.split(",")[0].strip()
            try:
                ipaddress.ip_address(candidate)
            except ValueError:
                pass
            else:
                return candidate
    return request.META.get("REMOTE_ADDR")


def _throttle_key(ip_address: str | None, scope: str = "preview") -> str:
    """The per-IP counter key for one of the preview's routes.

    The IP is the **only** part of the key. The preview has no user, and a per-user
    limit would mean reading the session — which would mean the endpoint is not
    anonymous (AD-12).

    **Each route has its own scope**, so the two counters are separate and neither
    route can spend the other's budget. The scope is a fixed literal at every call
    site, never anything a caller controls — the caller's contribution to the key is
    the address and nothing else.
    """
    return f"{scope}:ip:{ip_address or 'unknown'}"


def _cacheable(response: HttpResponse) -> HttpResponse:
    """Mark a response as a public, cacheable, per-city response.

    **`Vary` carries nothing session-related.** A response that varies on the cookie is
    not cacheable, and — worse — a shared cache that stores one variant under a key that
    ignores the cookie would serve one visitor's response to another. The preview sets no
    cookie and reads no session, so the response is identical for everyone and the cache
    key is the URL.

    The response object is the one django-ninja injects into a view parameter annotated
    as `HttpResponse` — it is the *same* object ninja fills with the body afterwards, so
    the headers set here survive.
    """
    response["Cache-Control"] = PREVIEW_CACHE_CONTROL
    response["Vary"] = PREVIEW_VARY
    return response


@router.get(
    "/preview",
    response={200: PreviewOut, 429: ErrorOut},
    summary="The Pulse Preview for a city",
    description=(
        "Up to three Pulse Cards for a city, each with its Event Fit score and Why-this "
        "tags and its Source Badge. With no `city` parameter the city is inferred from "
        "the edge's geo header; an explicit `city` overrides it; `use_geo=false` is the "
        "visitor's 'Don't use my location' choice and the location is then not consulted "
        "at all. The response says which city was resolved and how it was resolved. "
        "No session is used and none is set."
    ),
)
def preview(
    request,
    response: HttpResponse,
    city: str | None = None,
    use_geo: bool = True,
):
    """The Pulse Preview. See the module docstring for the resolution order."""
    # The throttle runs first: a refused request must not do the work of serving one.
    decision = get_throttle_port().check(
        _throttle_key(_client_ip(request)),
        limit=PREVIEW_THROTTLE_IP,
        window_seconds=PREVIEW_THROTTLE_WINDOW_SECONDS,
    )
    if not decision.allowed:
        response["Retry-After"] = str(decision.retry_after_seconds)
        # A 429 is not content. Caching it as if it were would keep serving the refusal
        # after the window has passed.
        response["Cache-Control"] = "no-store"
        # `Status` carries the status code as well as the body, so ninja validates the
        # body against the 429 schema rather than the 200 one. Setting
        # `response.status_code` alone would not do it — ninja overwrites it from the
        # return value.
        return Status(429, ErrorOut(code="rate_limited", message="Too many requests."))

    now = timezone.now()
    supported = list_supported_cities(now=now)

    resolved, source = _resolve_city(request, city=city, use_geo=use_geo, supported=supported)

    cards = list_preview_cards(city=resolved, now=now, limit=PREVIEW_SIZE)

    _cacheable(response)
    return PreviewOut(
        city=resolved,
        city_source=source,
        items=[PreviewCardOut.from_preview_card(card) for card in cards],
    )


def _resolve_city(request, *, city: str | None, use_geo: bool, supported):
    """The resolved city, and how it was resolved.

    One function, so there is one rule and not three. The order is:

    1. **An explicit city wins.** It is what the visitor asked for, and it is never
       replaced by a *different* city. If the catalog does not cover it, the caller
       gets an empty preview carrying that name.
    2. **The opt-out skips geo entirely.** The geo port is not called.
    3. **Geo, if it names a city the catalog covers.**
    4. **The fallback** — the named constant — when geo says nothing, or names a city
       the catalog does not cover.

    The fallback is used for a *geo* city that is not supported, because the visitor did
    not choose it: the edge guessed, and a guess the catalog cannot serve should not
    produce an empty page. It is **not** used for an explicit unsupported city, because
    there the visitor did choose it and deserves to be told the truth about it.

    **Both paths answer with the catalog's spelling of the city.** The spelling a
    visitor types is not the spelling the events are filed under, and a preview headed
    `"BROOKLYN"` listing the events filed under `"Brooklyn"` is a heading nobody can
    search for. `_canonical` replaces the name only when the catalog holds that city;
    when it does not, the name the visitor gave is returned unchanged — so an
    unsupported city is never silently renamed.

    **The explicit city is bounded, because it is caller-supplied too.** The geo header
    is length-bounded in the adapter, for the same reason this is: a `?city=` value is
    written by the caller, and a city name is short. The bound is the *same* constant,
    because a city name is a city name whichever way it arrived. An over-long city is
    treated as no city at all — the request falls through to geo, and then to the
    fallback — rather than being echoed back in the response.
    """
    if city is not None and city.strip():
        wanted = city.strip()
        if len(wanted) <= GEO_CITY_MAX_LENGTH:
            return _canonical(supported, wanted), CITY_SOURCE_QUERY

    if use_geo:
        geo_city = get_geo_port().resolve_city(request.headers)
        if geo_city and supported.supports(geo_city):
            # The catalog's spelling of the city, not the header's. "brooklyn" and
            # "Brooklyn" are the same city, and the catalog's is the one the events are
            # filed under.
            return _canonical(supported, geo_city), CITY_SOURCE_GEO

    return PREVIEW_FALLBACK_CITY, CITY_SOURCE_FALLBACK


def _canonical(supported, city: str) -> str:
    """The catalog's spelling of `city`.

    The comparison is case-insensitive because the city came from a header, and the
    result is the catalog's own spelling — so the heading the visitor sees is the
    spelling the events are filed under.
    """
    wanted = city.strip().casefold()
    for name in supported.cities:
        if name.casefold() == wanted:
            return name
    return city.strip()


@router.get(
    "/preview/cities",
    response={200: PreviewCitiesOut, 429: ErrorOut},
    summary="The cities the Pulse Preview can serve",
    description=(
        "The supported cities, alphabetically, for the one-tap city picker. A city is "
        "supported when the catalog has at least one upcoming public event with an "
        "Event Fit for it. No session is used and none is set."
    ),
)
def preview_cities(request, response: HttpResponse):
    """The supported cities."""
    # The cities list is cheap and public, and the throttle protects the endpoint family
    # rather than one route. This route is checked by the same port, with its own key,
    # so a caller cannot use it to burn the preview's budget.
    decision = get_throttle_port().check(
        _throttle_key(_client_ip(request), scope="preview:cities"),
        limit=PREVIEW_THROTTLE_IP,
        window_seconds=PREVIEW_THROTTLE_WINDOW_SECONDS,
    )
    if not decision.allowed:
        response["Retry-After"] = str(decision.retry_after_seconds)
        response["Cache-Control"] = "no-store"
        return Status(429, ErrorOut(code="rate_limited", message="Too many requests."))

    supported = list_supported_cities(now=timezone.now())

    _cacheable(response)
    return PreviewCitiesOut(cities=list(supported.cities))


__all__ = ["PREVIEW_SIZE", "preview", "preview_cities", "router"]
