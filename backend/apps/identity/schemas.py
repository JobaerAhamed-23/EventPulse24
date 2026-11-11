"""The auth endpoints' wire shapes (AD-19).

Request and response shapes are Pydantic schemas, never ad-hoc dicts. These live in the
`identity` app because the surface owns the contract; the data comes from
`apps.identity.services`, which owns the commands.

**Two of these shapes are deliberately informationless.** The sign-up and the
password-reset-request responses carry the same fields whether the address was known or
not, because an answer that differs between the two cases is an account-existence oracle
(AD-18). The fields below are the *whole* answer — there is no second shape to fall back
to, so the two cases cannot drift apart.

**`CurrentUserOut` carries no password field.** There is no field for the hash, no field
for the last-login stamp, and no `**kwargs` catch-all: the response is spelled out, so a
new column on `User` cannot leak by accident.
"""

from uuid import UUID

from ninja import Schema

from apps.personalization.schemas import OnboardingStatusOut
from ports.billing import ProPlan


class SignUpIn(Schema):
    """The sign-up request: an address, a password, and optionally a home city.

    The password is a plain string here and is never echoed back. It goes to
    `apps.identity.services.sign_up`, which validates it against Django's configured
    password validators and hashes it.

    **`city` is optional, and it is the visitor's preview choice carried across
    sign-up.** The preview choice lives in a **session cookie** read in the browser
    only — deliberately, because a server-side choice would make `/preview` vary per
    visitor and break AD-12's cacheability. So the carry is a **request field**: the
    frontend reads the cookie and sends the city here.

    A city the catalog does not cover is stored as the fallback with `city_source`
    `fallback`, so the digest can say "we don't have your city yet" rather than passing
    the fallback off as the user's city. The sign-up **response** says nothing about
    it either way — a city is not an account-existence oracle, but the response shape
    carries nothing beyond `status` in any case.
    """

    email: str
    password: str
    city: str | None = None


class SignUpOut(Schema):
    """The sign-up answer. The same for a new address and an existing one.

    There is no `created` flag, and no account id: either would say whether the address
    was taken. The account holder of an existing address is told by email instead.
    """

    status: str = "accepted"


class SignInIn(Schema):
    """The sign-in request: an address and a password."""

    email: str
    password: str


class SignInOut(Schema):
    """The sign-in answer. The same for a wrong password and an unknown address.

    The status is the only field. A body that named the account, or said which half of
    the pair was wrong, would be the enumeration leak the services are careful to avoid.
    """

    status: str = "signed_in"


class SignOutOut(Schema):
    """The sign-out answer. The session is over; nothing else is said."""

    status: str = "signed_out"


class CurrentUserOut(Schema):
    """The signed-in user.

    The id and the email are what the frontend needs. There is no password field, no
    permission field and no catch-all, so nothing internal can ride along.

    The **onboarding status** is here, and it is here because the frontend needs it to
    decide between the onboarding flow and the home. It says only whether the onboarding
    is finished and which step the user is on — it carries no interests and no digest
    preference, because `me` is about *who* the user is and a settings blob there would
    grow without bound. The full state lives at `/api/personal/onboarding`.

    It is read through `personalization`'s **published interface** — the service, never
    the model — because `identity` may not reach into another app's tables (AD-2). The
    import contract `models-personalization` proves it.
    """

    id: UUID
    email: str
    onboarding: OnboardingStatusOut


class PasswordResetRequestIn(Schema):
    """The reset request: the address to reset."""

    email: str


class PasswordResetRequestOut(Schema):
    """The reset-request answer. The same for a known address and an unknown one.

    It says the request was received, and nothing about whether there is an account.
    """

    status: str = "accepted"


class PasswordResetConfirmIn(Schema):
    """The reset confirmation: the token from the reset link, and the new password."""

    token: str
    new_password: str


class PasswordResetConfirmOut(Schema):
    """The reset-confirmation answer.

    The password has been changed and the account's other sessions have ended.
    """

    status: str = "password_reset"


class CsrfTokenOut(Schema):
    """The CSRF token the frontend sends back on every unsafe request.

    The token is also set as the `csrftoken` cookie on the same response; the frontend
    reads the cookie and echoes the value in the `X-CSRFToken` header. Sending both is
    Django's own convention, and it is the one `CsrfViewMiddleware` checks.
    """

    csrf_token: str


class CheckoutIn(Schema):
    """The checkout request: which plan to buy.

    **The plan is the only field.** There is deliberately no `success_url`, no
    `cancel_url` and no `return_url`, and that absence is the security property rather
    than an oversight: the URLs handed to the provider are built from configuration, so a
    client cannot name one. Taking the redirect target from the request is the classic
    open-redirect in a checkout flow — a crafted target sends a paying user (and the
    session id in the query string) to somebody else's site.

    The plan is an enum, so an unknown one is a 422 at the edge rather than a provider
    error later.
    """

    plan: ProPlan


class CheckoutOut(Schema):
    """The checkout answer: the URL to send the user to.

    **It carries no entitlement, and asking for one here would be a lie.** The user is not
    Pro when this response is written; they are Pro when the provider's webhook lands,
    which may be later or never. So there is no `is_pro` field, no status and no plan
    echo: the answer is a URL and nothing else.
    """

    url: str


class PortalOut(Schema):
    """The portal answer: the URL to send the user to.

    Same shape as the checkout answer and for the same reason — the URL is the whole
    answer, and nothing about the subscription rides along with it.
    """

    url: str


class SubscriptionOut(Schema):
    """The caller's entitlement: one bool and nothing else.

    **The minimum, on purpose.** This answers exactly one question — *may this person buy
    a plan?* — and the answer is a bool. There is no plan name, no renewal date and no
    status here, because the fuller subscription record belongs to the account-and-billing
    surface, which needs a wider read and builds it there. A field here would be a field
    two callers could disagree about.

    **It is a read of the caller's own entitlement.** There is no user id in the request
    and none in the response: the user comes from the session, so a caller cannot ask
    about somebody else.
    """

    is_pro: bool
