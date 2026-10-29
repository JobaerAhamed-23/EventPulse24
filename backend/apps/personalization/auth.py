"""The personal-events surface's view of the session.

**This module used to be the seam.** It held a one-function `current_user` whose
docstring said the onboarding intent would replace it in one place. That has happened:
`identity` now owns the auth rules and publishes the resolver, and this module delegates
to it.

Why it still exists at all: the import is what keeps the diff to the existing routers at
one line. `apps/personalization/api.py` says `Router(auth=current_user)` and
`request.user.pk`, and those keep working because the names are the same and the
behaviour is the same. A reader of that file does not have to know where the session is
resolved from.

What changed underneath:

- **The CSRF check.** Django Ninja exempts every view it builds from Django's
  `CsrfViewMiddleware`, and Ninja's own cookie-CSRF check only runs for routers whose
  `auth=` is a cookie-based `AuthBase` — a plain function never reaches it. The
  resolver in `identity` therefore checks CSRF explicitly, through Django's own
  middleware, on every unsafe request. That is why the personal endpoints now need a
  CSRF token: they are state-changing, they are borne by a session cookie, and without
  the check a cross-site POST would carry the user's session (D13).

- **The 401.** It is still 401, with the same calm message — "Please sign in to
  continue." — and still in the project's `{code, message}` shape, because
  `config/errors.py` is the one place that maps errors to HTTP.

The import contract matters here: `personalization` reaches `identity` through
`identity`'s published interface (`apps.identity.api_auth`), never through
`apps.identity.models`. The `models-identity` contract in `backend/pyproject.toml`
enforces it.
"""

from apps.identity.api_auth import (
    UNAUTHENTICATED,
    UNAUTHENTICATED_MESSAGE,
    current_user,
)

__all__ = ["UNAUTHENTICATED", "UNAUTHENTICATED_MESSAGE", "current_user"]
