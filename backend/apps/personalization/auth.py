"""The session seam: how a request says which user it is (AD-5, AD-12).

The project has **no auth implementation yet** — `apps/identity/api.py` is an empty router,
and FR-1–FR-4 (onboarding and account) are a later intent. But Django's
`AuthenticationMiddleware` and `SessionMiddleware` are already installed, and `User` extends
`AbstractUser`, so a session already identifies a user.

This module is that seam, and it is deliberately **one function**, so the onboarding intent
replaces it in one place rather than in every endpoint.

Two properties matter, and they are what the tests prove:

- **The user id comes from the session, never from the request body.** A user-supplied user
  id in a payload is the classic way scoping goes wrong: the client asserts *who it is*, and
  the server believes it. Here there is nowhere for one to come from — no endpoint in this
  app accepts a user id as input.
- **An anonymous request is refused.** The endpoints are personal data; AD-12's session-free
  rule applies to the *public* catalog only. An anonymous request gets a 401 through the
  shared handler in `config/errors.py`, so the message and the shape are the project's, not
  this module's.

The 401's message is the project's calm voice: "Please sign in to continue."
"""

from ninja.errors import HttpError

#: The status an anonymous request gets. `config/errors.py` maps it to
#: `{"code": "not_authenticated", "message": "Please sign in to continue."}`.
UNAUTHENTICATED = 401

UNAUTHENTICATED_MESSAGE = "Please sign in to continue."


def current_user(request):
    """The signed-in user, or a 401.

    Returns Django's `User` — the project has no auth model of its own yet, and the
    onboarding intent will decide what replaces this. The endpoints use only `request.user.pk`
    and `request.user.is_authenticated`, so nothing here depends on the model's fields.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        raise HttpError(UNAUTHENTICATED, UNAUTHENTICATED_MESSAGE)
    return user


__all__ = ["UNAUTHENTICATED", "UNAUTHENTICATED_MESSAGE", "current_user"]
