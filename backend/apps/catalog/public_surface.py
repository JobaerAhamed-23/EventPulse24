"""What every anonymous route on the public surface does the same way (AD-12, AD-13).

Two routers answer on `/api/public`: the Pulse Preview (`preview_api`) and the city
picker's choices (`cities_api`). They serve different things, but three rules are
identical for both and must stay identical — who the caller is for throttling purposes,
how that becomes a counter key, and what makes a response cacheable.

**Shared rather than copied, because these are the rules that must not drift.** The IP
rule in particular is security-critical: a third hand-maintained copy is a third place for
`TRUST_FORWARDED_FOR` to be forgotten. `apps.identity.api` keeps its own `_client_ip` —
that is a different app and a different surface — but within this one public surface there
is one rule, in one place.
"""

import ipaddress

from django.conf import settings
from django.http import HttpResponse

from shared.constants import PREVIEW_CACHE_CONTROL, PREVIEW_VARY

__all__ = ["cacheable", "client_ip", "throttle_key"]


def client_ip(request) -> str | None:
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


def throttle_key(ip_address: str | None, scope: str = "preview") -> str:
    """The per-IP counter key for one route of the public surface.

    The IP is the **only** part of the key. These routes have no user, and a per-user
    limit would mean reading the session — which would mean the endpoint is not
    anonymous (AD-12).

    **Each route has its own scope**, so the counters are separate and no route can spend
    another's budget. The scope is a fixed literal at every call site, never anything a
    caller controls — the caller's contribution to the key is the address and nothing else.
    """
    return f"{scope}:ip:{ip_address or 'unknown'}"


def cacheable(response: HttpResponse) -> HttpResponse:
    """Mark a response as public and cacheable.

    **`Vary` carries nothing session-related.** A response that varies on the cookie is
    not cacheable, and — worse — a shared cache that stores one variant under a key that
    ignores the cookie would serve one visitor's response to another. These routes set no
    cookie and read no session, so the response is identical for everyone and the cache
    key is the URL.

    The response object is the one django-ninja injects into a view parameter annotated
    as `HttpResponse` — it is the *same* object ninja fills with the body afterwards, so
    the headers set here survive.

    The default `Cache-Control` is the preview's. A route whose resource is more static
    overwrites it afterwards — `cities_api` does, because its answer changes only when
    code ships.
    """
    response["Cache-Control"] = PREVIEW_CACHE_CONTROL
    response["Vary"] = PREVIEW_VARY
    return response
