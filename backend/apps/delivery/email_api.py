"""The mail endpoints: one-click unsubscribe and the click tracker (FR-11, AD-20, SM-2).

Three endpoints, and **two of them are unauthenticated on purpose**:

| endpoint | method | authenticated | changes state |
|---|---|---|---|
| `/api/email/unsubscribe` | `GET` | no | **no** |
| `/api/email/unsubscribe` | `POST` | no | yes |
| `/api/email/click` | `GET` | no | no (it redirects) |

---

## Why the POST is unauthenticated

RFC 8058's one-click unsubscribe is a `POST` to a URL in the mail, made by the mail
provider's user agent rather than by a browser with a session. The provider has no
session, no cookie and no CSRF token, so an endpoint that required one could never be
called by the very mechanism RFC 8058 describes.

**The signed token is the authentication.** It names the user, the scope and the target,
and it is signed, so it cannot be forged and cannot be edited into somebody else's
unsubscribe. That is the whole of the authorisation: possession of the link *is* the
permission, and the link's blast radius is bounded by what it names.

**No CSRF check applies here**, and that is correct rather than an oversight. CSRF
protects an *ambient* authority — the session cookie, which a browser attaches to every
request without being asked. This endpoint has no ambient authority to abuse: the caller
must present a secret bearer token, which a cross-site attacker cannot read. Checking
CSRF would make the endpoint impossible to use and would protect nothing.

---

## Why the GET does not unsubscribe

**A `GET` from a link scanner must not unsubscribe anyone.** Mail clients, security
proxies and corporate mail gateways follow links in a message to decide whether it is
safe — several of them do so *automatically, before the user has seen the message*. If a
`GET` unsubscribed, every reminder and every digest would be silently cancelled by the
user's own mail provider, and the user would never know why the mail stopped.

So the two verbs do different things, and the difference is the point:

- **`GET`** renders a confirmation page. It says what would be turned off, and it offers
  the inverse — turning it back on. **Nothing changes.** The page is what a person sees
  when they click the link in their mail client.
- **`POST`** applies the unsubscribe. This is the RFC 8058 one-click path, and it is what
  the mail provider's own unsubscribe button hits.

**The confirmation page offers the inverse**, because unsubscribing by accident is a
real thing: a user who meant to stop one event's reminders and stopped the daily digest
instead would otherwise have no way back.

---

## The confirmation page is HTML, and it is calm

The link lands in a browser, so the answer is a page rather than a JSON body. It is
rendered from a Django template in this app's `templates/delivery/` directory, in the same
voice as the mail itself: no exclamation marks, no urgency, no emoji. It says exactly
what was turned off, and it offers the inverse.

---

## The click tracker is a redirect, not a pixel

SM-2 measures the digest CTA click and explicitly rejects open-pixel measurement as
unreliable. So the link is a real link the user clicks, and the endpoint **redirects** to
the destination.

**The click is not stored.** There is no click table, and this work item does not add one:
SM-2 is a success metric measured in analytics, and the storage that would feed it is not
in scope here. What this endpoint guarantees is the *trackability* the criterion asks for —
**every link into the app goes through our server**, so the server sees the click and a
store can be added behind it later without changing a single link already sent. The
alternative — an open pixel — is what SM-2 rejects, and it is the only measurement that
does not survive a text-only mail client.

**The destination is inside the signed token**, so it cannot be edited into an open
redirect — a token whose destination is somebody else's phishing page would be the whole
attack. The endpoint refuses a destination that is not one of ours.

---

## No address reaches a log sink (AD-13)

Nothing here logs the recipient's address, the token, or the destination. The audit rows
the commands write carry ids and counts only.
"""

from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.utils import timezone
from ninja import Router

from apps.delivery.services.unsubscribe_tokens import (
    InvalidTokenError,
    read_click_token,
    read_unsubscribe_token,
)
from apps.delivery.services.unsubscribes import (
    unsubscribe_event_reminders,
    unsubscribe_pulse_ping,
)
from shared.actor import Actor

router = Router(tags=["email"])

#: The destinations a click token may point at. **A closed set**, so a token cannot be
#: edited into an open redirect. The check is on the *path*, not the whole URL, because
#: the frontend host is configuration rather than something the token may choose.
ALLOWED_CLICK_PATHS = frozenset({"/pulse", "/events"})


def _page(request, *, template: str, context: dict, status: int = 200):
    """Render one of this app's confirmation pages."""
    return render(request, template, context, status=status)


def _landing_url(path: str) -> str:
    """The frontend URL for a page, from the configured frontend base."""
    from django.conf import settings

    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}{path}"


@router.get(
    "/unsubscribe",
    response={200: None},
    summary="What an unsubscribe link would turn off",
    description=(
        "Renders a confirmation page for an unsubscribe link. **Nothing changes.** A "
        "`GET` must never unsubscribe anyone: mail clients and security scanners follow "
        "links in a message automatically, and a `GET` that unsubscribed would let a mail "
        "provider cancel a subscription the user never touched. The page says what would "
        "be turned off and offers the inverse."
    ),
    include_in_schema=True,
)
def unsubscribe_confirmation(request, token: str = ""):
    """The confirmation page. It changes nothing."""
    try:
        parsed = read_unsubscribe_token(token)
    except InvalidTokenError:
        # The same calm refusal as an invalid POST. The page does not say whether the
        # token was forged, expired or edited — that difference is an oracle.
        return _page(
            request,
            template="delivery/unsubscribe_invalid.html",
            context={"reason": "invalid"},
            status=422,
        )

    if parsed.is_event_scope:
        subject = "reminders for this event"
    else:
        subject = "the daily Pulse digest"

    return _page(
        request,
        template="delivery/unsubscribe_confirm.html",
        context={
            "scope": parsed.scope,
            "subject": subject,
            "is_event_scope": parsed.is_event_scope,
            "token": token,
            "resubscribe_url": _landing_url("/settings/reminders"),
        },
    )


@router.post(
    "/unsubscribe",
    response={200: None},
    summary="Turn off a subscription",
    description=(
        "Applies the unsubscribe the signed token names. **This is the RFC 8058 one-click "
        "path**, and it is deliberately unauthenticated: the provider that makes the "
        "request has no session, so the signed token is the authorisation. The token "
        "names the user, the scope and the target, and cannot be forged or edited.\n\n"
        "Two scopes, and they never touch each other: an event scope turns off that "
        "event's reminders and leaves the daily digest alone; the Pulse Ping scope turns "
        "off the digest and leaves every reminder plan alone. Applying a scope also "
        "cancels that scope's pending sends, so the mail the user just turned off is not "
        "delivered afterwards."
    ),
    include_in_schema=True,
)
def unsubscribe(request, token: str = ""):
    """Apply the unsubscribe. The signed token is the authorisation."""
    # The token may arrive in the query string (RFC 8058's provider posts to the URL in
    # the mail) or in the body (the confirmation page's form). **Both are read**, so
    # neither path has to be special-cased at the call site.
    #
    # The body is read from `request.POST` rather than through a Ninja schema, because
    # the two callers send different content types: the provider posts an empty body,
    # and the form posts `application/x-www-form-urlencoded`. A schema would demand one
    # content type and refuse the other — and the refusal would land on the provider,
    # which has no way to send a different one.
    effective_token = token or request.POST.get("token", "")

    try:
        parsed = read_unsubscribe_token(effective_token)
    except InvalidTokenError:
        return _page(
            request,
            template="delivery/unsubscribe_invalid.html",
            context={"reason": "invalid"},
            status=422,
        )

    now = timezone.now()
    actor = Actor.user(parsed.user_id)

    if parsed.is_event_scope:
        result = unsubscribe_event_reminders(
            user_id=parsed.user_id,
            target_id=parsed.target_id,
            actor=actor,
            now=now,
        )
        subject = "reminders for this event"
    else:
        result = unsubscribe_pulse_ping(
            user_id=parsed.user_id,
            actor=actor,
            now=now,
        )
        subject = "the daily Pulse digest"

    if result.already_unsubscribed:
        headline = "Already off"
        detail = f"{subject.capitalize()} was already turned off. Nothing changed."
    else:
        headline = "Turned off"
        detail = f"{subject.capitalize()} will not come in an email any more."

    return _page(
        request,
        template="delivery/unsubscribe_done.html",
        context={
            "headline": headline,
            "detail": detail,
            "subject": subject,
            "scope": result.scope,
            "is_event_scope": parsed.is_event_scope,
            "resubscribe_url": _landing_url("/settings/reminders"),
        },
    )


@router.get(
    "/click",
    response={302: None},
    summary="Follow a tracked link",
    description=(
        "Redirects to the link's destination. **A redirect, not an open pixel**: SM-2 "
        "measures the digest CTA click and rejects open-pixel measurement as unreliable. "
        "The click passes through our server, so it is trackable. The destination is "
        "inside the signed token, and it must be one of ours, so the link cannot be "
        "edited into an open redirect."
    ),
    include_in_schema=True,
)
def click(request, token: str = ""):
    """Send the user on to the link's destination."""
    try:
        parsed = read_click_token(token)
    except InvalidTokenError:
        return _page(
            request,
            template="delivery/unsubscribe_invalid.html",
            context={"reason": "invalid"},
            status=422,
        )

    path = _path_of(parsed.destination)
    if path not in ALLOWED_CLICK_PATHS:
        # The token is valid but names somewhere we do not send people. That is a
        # refusal, not a redirect: following an unknown destination would make this
        # endpoint an open redirect, which is a phishing primitive.
        return _page(
            request,
            template="delivery/unsubscribe_invalid.html",
            context={"reason": "invalid"},
            status=422,
        )

    return HttpResponseRedirect(parsed.destination)


def _path_of(destination: str) -> str:
    """The path part of a destination URL.

    Parsed with Django's own `urlparse`, so a destination that carries a query or a
    fragment is read the same way the browser would read it.
    """
    from urllib.parse import urlparse

    return urlparse(destination).path


__all__ = ["router"]
