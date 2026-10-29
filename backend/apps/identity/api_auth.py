"""The authenticated-actor resolver (AD-5, AD-18).

**This is the published interface other apps use to find out who is making a request.**
`identity` owns `USER` and the auth flows (AD-16), so it owns the answer to "who is this
request?" — and every other app asks through here.

Two properties make it safe to point every authed endpoint at one function:

- **The user id comes from the session, never from the request body.** A user-supplied
  user id in a payload is the classic way scoping goes wrong: the client asserts *who it
  is*, and the server believes it. There is nowhere for one to come from — no endpoint in
  this project accepts a user id as input.

- **An anonymous request is refused.** The endpoints are personal data; AD-12's
  session-free rule applies to the *public* catalog only. An anonymous request gets a 401
  through the shared handler in `config/errors.py`, so the message and the shape are the
  project's, not this module's.

This module is deliberately **not** `apps/identity/models.py`. The import contract
`models-identity` keeps `apps.identity.models` private to `apps.identity`; other apps
reach `identity` through a published interface instead. Putting the resolver here is what
makes that true for auth.

It also replaces `apps/personalization/auth.py`'s one-function seam. That module used to
be *the* seam, with a docstring saying the onboarding intent would replace it in one
place. It now delegates here — so there is still one place, and it is the one that owns
the auth rules.

**CSRF is checked here, for every authed endpoint (D13).** This is not decoration; it is
the only protection the authed endpoints have:

- Django Ninja sets `csrf_exempt = True` on **every** view it builds
  (`ninja/operation.py`), so Django's `CsrfViewMiddleware` — which is in `MIDDLEWARE` —
  does not protect a Ninja endpoint.
- Ninja's own cookie-CSRF check lives in `APIKeyCookie`, and it only runs for routers
  whose `auth=` is a cookie-based `AuthBase` subclass. The resolver is a plain function,
  so that check never runs for it.

So the check is made explicitly, here, using Django's own rules. The frontend holds the
`csrftoken` cookie on its **own** origin (the browser only ever calls `/api/*` on the
site's own origin, through `frontend/proxy.ts`) and sends the token back in the
`X-CSRFToken` header, which is Django's own convention. The proxy forwards both the
`Cookie` and the `X-CSRFToken` headers. Because the request arrives with the frontend's
`Origin`, the frontend's origin must be in `CSRF_TRUSTED_ORIGINS` — that is D13's
mechanism, and `USE_X_FORWARDED_HOST` stays `False`.

Only unsafe methods are checked. A `GET` cannot change anything, and the CSRF endpoint
that *issues* the token is a `GET`.
"""

from django.http import HttpResponseForbidden
from django.middleware.csrf import CsrfViewMiddleware, RejectRequest, get_token
from ninja.errors import HttpError

from domain.errors import CsrfError

#: The status an anonymous request gets. `config/errors.py` maps it to
#: `{"code": "not_authenticated", "message": "Please sign in to continue."}`.
UNAUTHENTICATED = 401

UNAUTHENTICATED_MESSAGE = "Please sign in to continue."

#: The methods that change something, and so need a CSRF token. Django's own set, spelled
#: out here so the rule is readable at the call site.
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _is_unsafe(request) -> bool:
    """Whether this request could change something, and so needs a CSRF token."""
    return request.method.upper() in UNSAFE_METHODS


def require_csrf(request) -> None:
    """Check the CSRF token on an unsafe request. Refuse the request if it is missing or wrong.

    The check is Django's own, so the rules are Django's: the token in the
    `X-CSRFToken` header must match the `csrftoken` cookie, and the request's `Origin`
    must be the request's own host or one of `CSRF_TRUSTED_ORIGINS`.

    A safe request is not checked: a `GET` changes nothing, and the endpoint that issues
    the token is itself a `GET`.

    Raises:
        CsrfError: The check failed. `config/errors.py` maps it to a 403 with the code
            `csrf_failed`.
    """
    if not _is_unsafe(request):
        return None

    _check_csrf_token(request)
    return None


def _check_csrf_token(request) -> None:
    """Run Django's CSRF rules over this request, and refuse it if they fail.

    **Django's own rules, and Django's own implementation.** The origin allowlist
    (`CSRF_TRUSTED_ORIGINS`), the masked-token comparison and the "a POST needs a CSRF
    cookie at all" rule are all Django's, so they behave exactly as they do for an
    ordinary Django view. Nothing here re-implements any of them.

    **Why not `ninja.utils.check_csrf`.** That helper runs `CsrfViewMiddleware` over the
    request, which is Django's own code — but Django's `process_view` honours
    `request._dont_enforce_csrf_checks`, and Django's **test client** sets that flag on
    every request unless it was built with `enforce_csrf_checks=True`. Using it would
    mean the protection silently vanished under the default test client: the tests would
    pass without the CSRF check ever running, and the endpoint would look protected in
    the test suite while the code path that protects it was never taken.

    So the rules are applied here, directly, and the test-only escape hatch is not
    consulted. `CsrfViewMiddleware` is still the thing that applies them: this calls its
    own `_origin_verified` and `_check_token`, with its `RejectRequest` turned into the
    project's error.

    Raises:
        CsrfError: The origin is not trusted, or the token is missing or does not match.
    """
    middleware = CsrfViewMiddleware(_reject_with_forbidden)

    # `process_request` sets up the request's CSRF secret from the cookie. It is the
    # same first step Django's own middleware takes.
    middleware.process_request(request)

    # The origin check. Django refuses a request whose `Origin` is not the request's own
    # host and is not in `CSRF_TRUSTED_ORIGINS`. A request with no `Origin` header at
    # all skips this step — Django only falls back to the referer for HTTPS requests,
    # and the token check below is what stops a token-less request either way.
    origin = request.META.get("HTTP_ORIGIN")
    if origin is not None and not middleware._origin_verified(request):
        raise CsrfError()

    # The token check. This raises `RejectRequest` for a missing cookie, a missing
    # token, a malformed token and a token that does not match — all of them a refusal.
    try:
        middleware._check_token(request)
    except RejectRequest:
        raise CsrfError() from None

    return None


def _reject_with_forbidden(request):
    """The view Django's middleware would call. It is never reached: the checks above
    raise before `process_view` would call it."""
    return HttpResponseForbidden()


def unauthenticated_user(request):
    """The signed-in user, or `None` when the request is anonymous.

    This is for the endpoints where anonymous is a normal answer rather than a mistake —
    `GET /api/auth/me` answers 401 on its own, with its own shape. It never raises for an
    anonymous request.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    return user


def current_user(request):
    """The signed-in user, or a 401.

    **The user is resolved before the CSRF check.** An anonymous request is refused with
    a 401 whatever token it carries — there is no session to protect, so the CSRF
    question does not arise. The order also keeps the two refusals apart: a 401 says
    "you are not signed in", and a 403 `csrf_failed` says "you are signed in, but this
    request could not be shown to come from this site". An anonymous caller learns
    nothing either way, and the frontend can branch on the code: a 401 sends the user to
    sign in, a `csrf_failed` sends it to fetch a fresh token and retry.

    Returns:
        The account. The endpoints use only `request.user.pk` and
        `request.user.is_authenticated`, so nothing here depends on the model's fields.

    Raises:
        HttpError: 401, when the request is anonymous.
        CsrfError: The CSRF check failed.
    """
    user = unauthenticated_user(request)
    if user is None:
        raise HttpError(UNAUTHENTICATED, UNAUTHENTICATED_MESSAGE)

    require_csrf(request)
    return user


def issue_csrf_token(request) -> str:
    """The CSRF token for this request, and set the `csrftoken` cookie.

    Django's `get_token` returns the token and marks the request so the cookie is set on
    the response. It is the same token `CsrfViewMiddleware` checks against, so there is
    one token and one algorithm.
    """
    return get_token(request)


__all__ = [
    "UNAUTHENTICATED",
    "UNAUTHENTICATED_MESSAGE",
    "UNSAFE_METHODS",
    "current_user",
    "issue_csrf_token",
    "require_csrf",
    "unauthenticated_user",
]
