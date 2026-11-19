"""The auth endpoints (FR-4, AD-18, AD-19).

Eight endpoints, plus one that issues the CSRF token:

- `GET  /api/auth/csrf` — the CSRF token the frontend sends back on unsafe requests.
- `POST /api/auth/signup` — create an account.
- `POST /api/auth/signin` — authenticate and establish the session.
- `POST /api/auth/signout` — end the session.
- `GET  /api/auth/me` — the signed-in user.
- `PUT  /api/auth/profile` — set the signed-in user's name.
- `POST /api/auth/password-reset` — ask for a reset link.
- `POST /api/auth/password-reset/confirm` — consume the link and set a new password.

**This router has no `auth=`.** Sign-up and sign-in are how a session is *created*, so
requiring a session to get one would be circular. The authed endpoints resolve the user
explicitly, through `identity`'s published resolver (`apps.identity.api_auth`), which is
the same resolver every other app uses — so there is one rule for "who is this request?",
not two.

**Enumeration safety is enforced here, at the HTTP edge (AD-18).** The services already
avoid revealing whether an account exists, but the *response* has to avoid it too, and
that is a property of this layer, not of the services. Three of these endpoints answer
identically for a known address and an unknown one:

| Endpoint | Known address | Unknown address |
|---|---|---|
| `signup` | `201 {"status": "accepted"}` | `201 {"status": "accepted"}` |
| `signin` (wrong password) | `401 `invalid_credentials`` | `401 `invalid_credentials`` |
| `password-reset` | `202 {"status": "accepted"}` | `202 {"status": "accepted"}` |

The bodies are byte-identical, not merely equal in shape. The tests compare
`response.content`.

**The responses are header-identical too, and that took a second pass.** A byte-identical
body is not enough: a `Set-Cookie: sessionid` header on some responses and not on others
is an oracle of exactly the same strength, and a stronger one — it confirms a *password*,
not just an account. Sign-up therefore establishes **no** session at all. The frontend
signs in afterwards, through `signin`, and that is the one place a session is created.
The alternative — signing the caller in when the password they just supplied verifies —
was tried and rejected: it leaked existence through the headers and it spent two
throttle buckets per sign-up.

**Sign-up only creates the account.** It does not sign anybody in. The service
deliberately does not say whether it created the account, and the endpoint does not ask,
so the answer is the same either way and the caller learns nothing from it. An existing
account holder is told by email instead.

**CSRF is checked on every unsafe request (D13).** Django Ninja exempts every view it
builds from Django's `CsrfViewMiddleware`, and Ninja's own cookie-CSRF check only runs
for routers whose `auth=` is a cookie-based handler — which this router has none of. So
the check is made explicitly, through Django's own middleware, in
`apps.identity.api_auth.require_csrf`. It is the same check the personal endpoints get,
because they resolve their user through the same resolver.

The layer is thin: it checks CSRF, parses the body, calls the published service, and
projects the result onto the wire shape. It never imports `apps.identity.models` (import
contract `models-identity`) and never writes directly — every write is a named command in
`apps.identity.services` (AD-5).
"""

import ipaddress

from django.conf import settings
from django.contrib.auth import HASH_SESSION_KEY
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.utils import timezone
from ninja import Router, Status

from apps.identity.api_auth import (
    current_user,
    issue_csrf_token,
    require_csrf,
    unauthenticated_user,
)
from apps.identity.models import PendingEmailChange
from apps.identity.schemas import (
    CsrfTokenOut,
    CurrentUserOut,
    EmailChangeConfirmIn,
    EmailChangeConfirmOut,
    EmailChangeRequestIn,
    EmailChangeRequestOut,
    PasswordResetConfirmIn,
    PasswordResetConfirmOut,
    PasswordResetRequestIn,
    PasswordResetRequestOut,
    ProfileIn,
    ProfileOut,
    SignInIn,
    SignInOut,
    SignOutOut,
    SignUpIn,
    SignUpOut,
)
from apps.identity.services.authenticate import authenticate
from apps.identity.services.email_change import confirm_email_change, request_email_change
from apps.identity.services.emails import (
    email_change_stream,
    render_confirm_email_change_email,
    render_email_change_requested_email,
)
from apps.identity.services.password_reset import request_password_reset, reset_password
from apps.identity.services.profile import set_user_name
from apps.identity.services.session import sign_out
from apps.identity.services.sign_up import sign_up
from apps.personalization.schemas import OnboardingStatusOut
from apps.personalization.services.onboarding import get_onboarding_state
from ports.registry import get_email_port
from shared.constants import SEND_KEY_SEPARATOR
from shared.db import PERSONAL
from shared.errors import ErrorOut

router = Router(tags=["auth"])

#: The status a password-reset request answers with. It is 202 rather than 200 because
#: the work may not have happened yet: a known address gets an email, and an unknown one
#: gets nothing. Both answer the same, so the status cannot say which happened.
RESET_REQUESTED = 202

#: The email-change request is accepted, not finished: the link has yet to be opened.
EMAIL_CHANGE_REQUESTED = 202


def _client_ip(request) -> str | None:
    """The caller's IP, for the throttle key and nothing else.

    It comes from `X-Forwarded-For` **only when a trusted edge is known to overwrite
    that header** (`settings.TRUST_FORWARDED_FOR`, off by default). The header is
    otherwise attacker-controlled: Next's rewrite forwards the browser's headers as they
    arrived, so a browser that sets `X-Forwarded-For` has that value reach Django
    unchanged. Trusting it unconditionally let any caller mint a fresh throttle bucket per
    request, which defeated the per-IP limit completely.

    The value must also parse as an IP address, so a caller cannot pad the key with
    arbitrary text. It is never logged and never stored (AD-13); it only ever becomes
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


@router.get(
    "/csrf",
    response={200: CsrfTokenOut},
    summary="Get a CSRF token",
    description=(
        "The CSRF token the frontend sends back on every state-changing request, in the "
        "`X-CSRFToken` header. The token is also set as the `csrftoken` cookie on this "
        "response, so the frontend can read it from there. This is a safe request, so it "
        "is not itself checked for a token."
    ),
)
def get_csrf(request):
    """The CSRF token, and the cookie that goes with it."""
    return CsrfTokenOut(csrf_token=issue_csrf_token(request))


@router.post(
    "/signup",
    # The statuses this endpoint can actually answer with. A 403 is the CSRF refusal
    # (`require_csrf`), a 422 is a password Django's validators rejected or an address
    # that is not one, and a 429 is the throttle. Declaring them is what puts `ErrorOut`
    # in the generated client, so the frontend can read the message it has to show.
    response={201: SignUpOut, 403: ErrorOut, 422: ErrorOut, 429: ErrorOut},
    summary="Create an account",
    description=(
        "Creates an account. The answer is the same whether the address was new or "
        "already taken: an existing account holder is told by email instead. This "
        "endpoint does not sign anyone in — call `/api/auth/signin` for that — so the "
        "response is byte-identical and header-identical whichever case it was.\n\n"
        "`city` is optional: the visitor's home city, carried across from the preview "
        "choice. A city the catalog does not cover is stored as the fallback, and the "
        "response says nothing about it either way."
    ),
)
def signup(request, body: SignUpIn):
    """Create an account. The answer never says whether the address was taken."""
    require_csrf(request)

    sign_up(
        email=body.email,
        password=body.password,
        ip_address=_client_ip(request),
        city=body.city,
    )

    # **No session is established here, and that is deliberate.**
    #
    # The obvious design — sign the caller in when the password they just supplied
    # verifies — leaks the account's existence through the *response headers*, even
    # though the body is byte-identical. A new address gets a `sessionid` cookie and a
    # `Vary: Cookie` header; a taken address with the wrong password gets neither. The
    # cookie's presence is therefore a confirmed-password oracle: it says "this address
    # exists and you have just proven you know its password".
    #
    # It also burned two throttle buckets per sign-up. `sign_up` consumes the sign-up
    # bucket, and the authentication attempt that followed consumed the **sign-in**
    # bucket, so an attacker naming a victim's address could spend the victim's own
    # sign-in allowance and lock the real owner out of their account.
    #
    # Sign-up therefore only creates the account. The frontend signs in afterwards, and
    # `/api/auth/signin` is where the session is established — one place, one rule, and
    # every sign-up response is identical in body *and* in headers.
    return Status(201, SignUpOut())


@router.post(
    "/signin",
    # 401 is the one enumeration-safe credential refusal; 403 is the CSRF refusal and
    # 429 the throttle. `authenticate` raises nothing else.
    response={200: SignInOut, 401: ErrorOut, 403: ErrorOut, 429: ErrorOut},
    summary="Sign in",
    description=(
        "Authenticates an email and a password and establishes the session. A wrong "
        "password and an unknown address are answered identically — the same status and "
        "the same body — so neither can be used to find out who has an account."
    ),
)
def signin(request, body: SignInIn):
    """Authenticate and establish the session."""
    require_csrf(request)

    # `AuthenticationFailedError` is a `NotAuthenticatedError`, so `config/errors.py`
    # maps it to a 401 with the code `invalid_credentials`. One error for a wrong
    # password and for an unknown address, so the body never says which half was wrong.
    user = authenticate(email=body.email, password=body.password, ip_address=_client_ip(request))

    django_login(request, user)
    return SignInOut()


@router.post(
    "/signout",
    # Signing out cannot fail on its merits — an anonymous caller is answered 200 — so
    # the CSRF refusal is the only error it can produce.
    response={200: SignOutOut, 403: ErrorOut},
    summary="Sign out",
    description=(
        "Ends the session the request carries. The session cookie is cleared, so the "
        "next request is anonymous."
    ),
)
def signout(request):
    """End this session."""
    require_csrf(request)

    user = unauthenticated_user(request)
    if user is not None:
        sign_out(user=user, request=request)
    else:
        # Signing out when nobody is signed in is not an error: the caller's intent —
        # "have no session" — is satisfied either way. The session is flushed regardless,
        # so a stale cookie cannot survive.
        django_logout(request)

    return SignOutOut()


@router.get(
    "/me",
    response={200: CurrentUserOut, 401: ErrorOut},
    summary="The signed-in user",
    description=(
        "The signed-in user's id, email, name and onboarding status. An anonymous request "
        "is refused with 401. Nothing internal is returned: there is no password hash, no "
        "permission list and no catch-all field. The name is empty when no name is set; "
        "the frontend renders its own fallback in that case. The onboarding status says "
        "only whether the onboarding is finished and which step the user is on; the full "
        "state is at `/api/personal/onboarding`.\n\n"
        "`pending_email` is the address an outstanding email change is *to*, or empty "
        "when there is none. It is the caller's own pending change, and only the caller "
        "can read it."
    ),
)
def me(request):
    """The signed-in user."""
    user = current_user(request)

    # The onboarding status is read through `personalization`'s **published interface** —
    # the service, never the model. `identity` may not reach into another app's tables
    # (AD-2), and the `models-personalization` import contract proves it. The arrow is
    # one-way: `personalization`'s onboarding service imports nothing from `identity`.
    #
    # The read is **read-only**: an expired onboarding is *reported* as step 1, and the
    # row is left for the next command to restart. That matters here because `me` is a
    # `GET`, and a `GET` is never CSRF-checked — so a write behind one would be a
    # cross-site write.
    state = get_onboarding_state(user_id=user.pk, now=timezone.now())

    # **The outstanding email change, if there is one.** Read here rather than from a
    # second endpoint for the reason `name` is here: the shell is rendered on every page
    # and a second round trip for one row of the caller's own account would be a second
    # answer to a question this response already has in hand.
    #
    # Read-only, like the onboarding read above and for the same reason: `me` is a `GET`,
    # and a `GET` is never CSRF-checked, so a write behind one would be a cross-site
    # write. An expired request is simply not reported — it is left for the next command
    # to revoke.
    pending = (
        PendingEmailChange.objects.using(PERSONAL)
        .filter(
            user_id=user.pk,
            used_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .order_by("-created_at")
        .values_list("new_email", flat=True)
        .first()
    )

    return CurrentUserOut(
        id=user.pk,
        email=user.email,
        name=user.name,
        pending_email=pending or "",
        onboarding=OnboardingStatusOut(
            completed=state.completed,
            current_step=state.current_step,
        ),
    )


@router.put(
    "/profile",
    # The statuses this endpoint can actually answer with. A 403 is the CSRF refusal
    # (`require_csrf`), a 422 is a name the command refused — a control character or a
    # line break — and a 401 is an anonymous caller. Declaring them is what puts
    # `ErrorOut` in the generated client, so the frontend can read the message it has to
    # show.
    response={200: ProfileOut, 401: ErrorOut, 403: ErrorOut, 422: ErrorOut},
    summary="Set the signed-in user's name",
    description=(
        "Sets the name the product addresses this account by. An empty name is legal and "
        'means "no name set" — the frontend falls back to a name derived from the '
        "email address in that case. A name carrying a line break or a control character "
        "is refused with 422 and nothing is written.\n\n"
        "This is a `PUT`, not a `PATCH`: it is the one verb this product's settings "
        "writes use, and a second verb for the same write would put two shapes for one "
        "operation into the contract."
    ),
)
def put_profile(request, body: ProfileIn):
    """Set the caller's name."""
    # **The CSRF check is first.** This router has no router-level `auth=`, so the check
    # is explicit, exactly as it is in `signup`, `signin` and `signout`. It comes before
    # the resolver, so an unsafe request without a token is refused as a cross-site
    # write rather than as an authentication problem.
    #
    # **The one thing that happens before this is the body's own validation.** Ninja
    # parses and validates the request body before the handler is called, so a body that
    # is not a `ProfileIn` is refused with a 422 `invalid_request` before the token is
    # ever looked at. That is not a hole: the write still cannot happen. But it does
    # mean the claim is "the CSRF check comes before the *write*", not "before anything
    # at all" — and a request with a bad token *and* a bad body is answered 422.
    require_csrf(request)

    # The resolver raises the 401 for an anonymous caller. It is `identity`'s published
    # resolver — the same one every other app uses — so there is one rule for "who is
    # this request?", not two.
    #
    # **`current_user` checks CSRF too, and it does it after the resolver.** That is the
    # right order for it — a 401 says "you are not signed in" and a 403 says "you are
    # signed in, but this request could not be shown to come from this site" — and the
    # call above is what puts this endpoint's check *first*. The check inside the
    # resolver is then a second, idempotent pass over the same token.
    user = current_user(request)

    # **The write goes through the named command** (AD-5), never through the ORM: this
    # module is a surface file, and `tests/architecture/test_no_direct_writes.py` scans
    # it for exactly that. The command trims and collapses the name, truncates it to the
    # column's limit, refuses a control character, and writes the audit row in the same
    # transaction.
    #
    # It returns the name as it was **stored**, which is not the string that came in: the
    # command collapsed the whitespace and capped the length. The answer below therefore
    # reports what the account now holds rather than what was asked for.
    saved = set_user_name(user_id=user.pk, name=body.name)

    # The answer is the caller's whole profile — the id, the email and the name that was
    # just saved — so the client can update what it knows without a second `me` call.
    return ProfileOut(id=user.pk, email=user.email, name=saved)


@router.post(
    "/profile/email",
    # 202 is the accepted request; 401 an anonymous caller; 403 the CSRF refusal; 422 the
    # two plain refusals (no address, your own address); 429 the throttle. Declaring them
    # is what puts `ErrorOut` in the generated client.
    response={
        EMAIL_CHANGE_REQUESTED: EmailChangeRequestOut,
        401: ErrorOut,
        403: ErrorOut,
        422: ErrorOut,
        429: ErrorOut,
    },
    summary="Ask to change the account's email address",
    description=(
        "Asks to move the login to a new address. A confirmation link is sent to that "
        "address, and a warning that the change was asked for is sent to the current "
        "one. **Nothing changes until the link is opened.**\n\n"
        "The answer is the same whether the address is free or already belongs to "
        "another account, so this endpoint cannot be used to find out who has an "
        "account. Asking for the address you already have is refused with 422, because "
        "that is a mistake about your own account rather than a probe of someone "
        "else's."
    ),
)
def request_email_change_endpoint(request, body: EmailChangeRequestIn):
    """Ask to move the login. The answer never says whether the address was taken."""
    require_csrf(request)

    user = current_user(request)

    pending = request_email_change(
        user_id=user.pk,
        new_email=body.new_email,
        ip_address=_client_ip(request),
    )

    # **`None` means "nothing to send", and the response does not change because of it.**
    # It is the already-taken case, and a caller who could tell it apart from a free
    # address would have an account-existence oracle.
    if pending is not None:
        email_port = get_email_port()
        stream = email_change_stream()

        # The confirmation, to the address being proven.
        email_port.send(
            render_confirm_email_change_email(to=pending.new_email, token=pending.token),
            stream=stream,
            idempotency_key=f"email_change_confirm{SEND_KEY_SEPARATOR}{pending.row_id}",
        )
        # The warning, to the address still on the account. **This is the security
        # control**, not a courtesy: it is the one message that reaches the real account
        # holder when somebody else asked.
        email_port.send(
            render_email_change_requested_email(to=pending.old_email, new_email=pending.new_email),
            stream=stream,
            idempotency_key=f"email_change_warn{SEND_KEY_SEPARATOR}{pending.row_id}",
        )

    return Status(EMAIL_CHANGE_REQUESTED, EmailChangeRequestOut())


@router.post(
    "/profile/email/confirm",
    # 422 covers every way a token can fail — unknown, used, revoked, expired, or beaten
    # to the address — and says which it was in none of them. 403 is the CSRF refusal.
    response={200: EmailChangeConfirmOut, 403: ErrorOut, 422: ErrorOut},
    summary="Confirm a new email address",
    description=(
        "Consumes a confirmation token and moves the login to the address it proves. "
        "The token is single-use and short-lived.\n\n"
        "**The caller does not need a session**: the link is opened from a mailbox, "
        "possibly in a browser that never signed in, and requiring a session would make "
        "the link work only where it was requested. It is still CSRF-checked — fetch "
        "`GET /api/auth/csrf` first — exactly as the password-reset confirmation is.\n\n"
        "A token that was already used, revoked or expired is refused, and so is one "
        "whose address another account claimed in the meantime. The refusal does not say "
        "which of those it was."
    ),
)
def confirm_email_change_endpoint(request, body: EmailChangeConfirmIn):
    """Consume a confirmation token and move the login."""
    require_csrf(request)

    # **No `current_user` here.** The person opening this link is reading mail, and the
    # browser they read it in may never have signed in. `password_reset_confirm` is
    # anonymous for the same reason.
    user = confirm_email_change(token=body.token)

    return EmailChangeConfirmOut(email=user.email)


@router.post(
    "/password-reset",
    # The address is never validated here (an unknown one is answered identically), so
    # there is no 422: only the CSRF refusal and the throttle.
    response={202: PasswordResetRequestOut, 403: ErrorOut, 429: ErrorOut},
    summary="Ask for a password reset",
    description=(
        "Asks for a reset link. A known address gets one, by transactional email; an "
        "unknown address gets nothing. The answer is the same either way, so the "
        "endpoint cannot be used to find out who has an account."
    ),
)
def password_reset_request(request, body: PasswordResetRequestIn):
    """Ask for a reset link. The answer never says whether there is an account."""
    require_csrf(request)

    request_password_reset(email=body.email, ip_address=_client_ip(request))
    return Status(RESET_REQUESTED, PasswordResetRequestOut())


@router.post(
    "/password-reset/confirm",
    # 422 covers both a spent or expired token and a password the validators rejected;
    # 403 is the CSRF refusal. This endpoint has no throttle of its own.
    response={200: PasswordResetConfirmOut, 403: ErrorOut, 422: ErrorOut},
    summary="Set a new password",
    description=(
        "Consumes a reset token and sets a new password. The token is single-use and "
        "short-lived: a token that was already used, revoked or expired is refused, and "
        "the refusal does not say which of the three it was. The account's other "
        "sessions end, so a stolen session does not survive the password change."
    ),
)
def password_reset_confirm(request, body: PasswordResetConfirmIn):
    """Consume a reset token and set the new password."""
    require_csrf(request)

    session = getattr(request, "session", None)
    user = reset_password(
        token=body.token,
        new_password=body.new_password,
        # The session this request carries is kept: the person who just reset their
        # password is not signed out of the browser they did it in. Every other session
        # of the account ends.
        keep_session_key=session.session_key if session is not None else None,
    )

    # Re-stamp the kept session with the new password hash.
    #
    # Changing the password changes `get_session_auth_hash()`, and Django compares that
    # hash against the one stored in the session on every request. A mismatch makes
    # Django flush the session and treat the request as anonymous — so keeping the
    # session row was not enough on its own, and without this the session the reset was
    # made *from* died with every other one, despite the code saying it was kept.
    #
    # The hash is written directly rather than through Django's `update_session_auth_hash`,
    # because that function only stamps when `request.user == user` — and by the time
    # this endpoint runs, Django's `AuthenticationMiddleware` has *already* compared the
    # stale hash, flushed the session and left `request.user` anonymous. The helper's
    # guard therefore never passes, and it silently stamps nothing. The value written
    # here is the same one the helper would have written: `user.get_session_auth_hash()`.
    #
    # The session key is cycled as well, so a session key that was on the wire before the
    # reset cannot be reused afterwards.
    if session is not None:
        session[HASH_SESSION_KEY] = user.get_session_auth_hash()
        session.cycle_key()

    return PasswordResetConfirmOut()


__all__ = ["router"]
