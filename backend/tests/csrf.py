"""CSRF helpers for the API tests (D13).

**Every state-changing request in this project needs a CSRF token.** Django Ninja
exempts every view it builds from Django's `CsrfViewMiddleware`, and Ninja's own
cookie-CSRF check only runs for routers whose `auth=` is a cookie-based handler — so
`identity`'s resolver checks CSRF explicitly, and the personal endpoints get the check
through that same resolver.

The consequence for the tests: a `POST`, `PATCH` or `DELETE` without a token is refused
with a 403 and the code `csrf_failed`. That is the behaviour, and `CsrfClient` is how a
test sends the token.

**The token is obtained the way a browser obtains it**: `GET /api/auth/csrf` returns it
and sets the `csrftoken` cookie, and the request then sends the value in the
`X-CSRFToken` header. Django's own convention, and the one `CsrfViewMiddleware` reads.

The `Origin` header matters too. Django's origin check compares it against the
request's own host and against `CSRF_TRUSTED_ORIGINS`. The tests send the origin the
frontend would send — `http://testserver` is Django's test host — so the check has
something to compare, exactly as a browser's `Origin` header does.

`CsrfClient` attaches the header to the unsafe methods only. A `GET` needs no token, and
adding one would hide a bug where a safe request is checked.
"""

from django.test import Client
from django.test.client import MULTIPART_CONTENT

#: The origin a browser would send. Django's test client uses `testserver` as the host,
#: so this is the same origin the request appears to come from.
ORIGIN = "http://testserver"


def csrf_token(client: Client | None = None) -> str:
    """The CSRF token for `client`, obtained the way a browser obtains it.

    `GET /api/auth/csrf` returns the token in the body and sets the `csrftoken` cookie.
    The cookie is left on the client, because Django's check compares the header against
    the cookie.
    """
    http = client if client is not None else Client()
    response = http.get("/api/auth/csrf", headers={"origin": ORIGIN})
    return response.json()["csrf_token"]


class CsrfClient(Client):
    """A test client that sends the CSRF token on every state-changing request.

    The token is fetched lazily, on the first unsafe request, so a test that only reads
    never fetches one. `GET /api/auth/csrf` sets the `csrftoken` cookie on the client,
    and the token travels in the `X-CSRFToken` header — the same pair Django's check
    compares.

    **The token is refreshed when the server rotates it.** Django's `login()` calls
    `rotate_token`, so a sign-in or a sign-up replaces the `csrftoken` cookie. A browser
    does this automatically: it always sends the *current* cookie value, and Django's
    masked-token comparison accepts the new mask of the same secret. This client has to do
    it explicitly — it compares the cookie's value with the one the token was taken from,
    and fetches a fresh token when they differ. Without that, every request after a
    sign-in would be refused, and the refusal would be an artefact of the test client
    rather than a property of the endpoint.

    A test that wants to send a *wrong* token, or none at all, uses a plain `Client`.
    That is the point of the split: the refusal is provable because the ordinary client
    still refuses.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._csrf_token: str | None = None
        self._csrf_cookie: str | None = None

    def _csrf_headers(self) -> dict[str, str]:
        """The headers an unsafe request needs.

        The token is fetched when there is none, or when the cookie has been rotated
        since it was taken.
        """
        cookie = self.cookies.get("csrftoken")
        cookie_value = cookie.value if cookie is not None else None

        if self._csrf_token is None or cookie_value != self._csrf_cookie:
            self._csrf_token = csrf_token(self)
            refreshed = self.cookies.get("csrftoken")
            self._csrf_cookie = refreshed.value if refreshed is not None else None

        return {"origin": ORIGIN, "x-csrftoken": self._csrf_token}

    def post(
        self,
        path,
        data=None,
        content_type=MULTIPART_CONTENT,
        secure=False,
        *,
        headers=None,
        **extra,
    ):
        return super().post(
            path,
            data,
            content_type,
            secure,
            headers={**self._csrf_headers(), **(headers or {})},
            **extra,
        )

    def put(
        self,
        path,
        data="",
        content_type="application/octet-stream",
        secure=False,
        *,
        headers=None,
        **extra,
    ):
        return super().put(
            path,
            data,
            content_type,
            secure,
            headers={**self._csrf_headers(), **(headers or {})},
            **extra,
        )

    def patch(
        self,
        path,
        data="",
        content_type="application/octet-stream",
        secure=False,
        *,
        headers=None,
        **extra,
    ):
        return super().patch(
            path,
            data,
            content_type,
            secure,
            headers={**self._csrf_headers(), **(headers or {})},
            **extra,
        )

    def delete(
        self,
        path,
        data="",
        content_type="application/octet-stream",
        secure=False,
        *,
        headers=None,
        **extra,
    ):
        return super().delete(
            path,
            data,
            content_type,
            secure,
            headers={**self._csrf_headers(), **(headers or {})},
            **extra,
        )
