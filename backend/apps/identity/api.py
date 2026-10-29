"""The auth endpoints (FR-4, AD-18, AD-19).

Six endpoints, plus one that issues the CSRF token:

- `GET  /api/auth/csrf` — the CSRF token the frontend sends back on unsafe requests.
- `POST /api/auth/signup` — create an account.
- `POST /api/auth/signin` — authenticate and establish the session.
- `POST /api/auth/signout` — end the session.
- `GET  /api/auth/me` — the signed-in user.
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

**Sign-up establishes a session, and it does so without leaking.** The service
deliberately does not say whether it created the account, so the endpoint cannot ask.
Instead it answers a different question: *does the password the caller just supplied
verify against the account now in front of us?* If it does, the caller knows the
password, so signing them in is legitimate — a new account (the password they just set)
and an existing account they own (the password they supplied) both verify, and a caller
who does not know the password gets no session and no session cookie. The response body
is the same in all three cases.

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

from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from ninja import Router, Status

from apps.identity.api_auth import (
    current_user,
    issue_csrf_token,
    require_csrf,
    unauthenticated_user,
)
from apps.identity.schemas import (
    CsrfTokenOut,
    CurrentUserOut,
    PasswordResetConfirmIn,
    PasswordResetConfirmOut,
    PasswordResetRequestIn,
    PasswordResetRequestOut,
    SignInIn,
    SignInOut,
    SignOutOut,
    SignUpIn,
    SignUpOut,
)
from apps.identity.services.authenticate import authenticate
from apps.identity.services.password_reset import request_password_reset, reset_password
from apps.identity.services.session import sign_out
from apps.identity.services.sign_up import sign_up
from domain.errors import AuthenticationFailedError
from shared.errors import ErrorOut

router = Router(tags=["auth"])

#: The status a password-reset request answers with. It is 202 rather than 200 because
#: the work may not have happened yet: a known address gets an email, and an unknown one
#: gets nothing. Both answer the same, so the status cannot say which happened.
RESET_REQUESTED = 202


def _client_ip(request) -> str | None:
    """The caller's IP, for the throttle key and nothing else.

    It comes from `X-Forwarded-For` when the request came through the proxy, because the
    proxy is the one talking to this runtime. The value is never logged and never stored
    (AD-13); it only ever becomes part of a throttle key.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
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
    response={201: SignUpOut},
    summary="Create an account",
    description=(
        "Creates an account and signs the user in. The answer is the same whether the "
        "address was new or already taken: an existing account holder is told by email "
        "instead. A caller who signs up with an address that is already taken, and who "
        "does not know that account's password, is not signed in."
    ),
)
def signup(request, body: SignUpIn):
    """Create an account. The answer never says whether the address was taken."""
    require_csrf(request)

    sign_up(email=body.email, password=body.password, ip_address=_client_ip(request))

    # The service will not say whether it created the account, and asking it to would
    # undo its enumeration safety. So the endpoint answers a different question: does the
    # password the caller just supplied verify against the account in front of us?
    #
    # A new account verifies (the password they just set). An existing account verifies
    # only for its real owner. Anyone else gets no session and no session cookie — and
    # the response body is the same either way, so the refusal is invisible in the body.
    #
    # A failed verification is not an error here: the address may simply have been taken
    # by someone else, and the caller is no worse off than before they signed up.
    try:
        user = authenticate(
            email=body.email, password=body.password, ip_address=_client_ip(request)
        )
    except AuthenticationFailedError:
        user = None

    if user is not None:
        django_login(request, user)

    return Status(201, SignUpOut())


@router.post(
    "/signin",
    response={200: SignInOut, 401: ErrorOut},
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
    response={200: SignOutOut},
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
        "The signed-in user's id and email. An anonymous request is refused with 401. "
        "Nothing internal is returned: there is no password hash, no permission list and "
        "no catch-all field."
    ),
)
def me(request):
    """The signed-in user."""
    user = current_user(request)
    return CurrentUserOut(id=user.pk, email=user.email)


@router.post(
    "/password-reset",
    response={202: PasswordResetRequestOut},
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
    response={200: PasswordResetConfirmOut, 422: ErrorOut},
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
    reset_password(
        token=body.token,
        new_password=body.new_password,
        # The session this request carries is kept: the person who just reset their
        # password is not signed out of the browser they did it in. Every other session
        # of the account ends.
        keep_session_key=session.session_key if session is not None else None,
    )
    return PasswordResetConfirmOut()


__all__ = ["router"]
