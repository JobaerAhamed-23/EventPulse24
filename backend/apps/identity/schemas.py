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


class SignUpIn(Schema):
    """The sign-up request: an address and a password.

    The password is a plain string here and is never echoed back. It goes to
    `apps.identity.services.sign_up`, which validates it against Django's configured
    password validators and hashes it.
    """

    email: str
    password: str


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

    The onboarding status is **not** here yet: `personalization` owns onboarding progress,
    and it does not exist yet. It is added when it does, through `personalization`'s
    published interface — this item does not depend on that one.
    """

    id: UUID
    email: str


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
