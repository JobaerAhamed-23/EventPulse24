"""Sessions: sign-out, and ending a user's other sessions (AD-12, D12).

Two commands, and the difference between them matters:

- **`sign_out(*, user, request)`** ends *this* session. It flushes the session and deletes
  its row, so the browser's cookie no longer identifies anybody, and it audits the sign-out
  (D14).

- **`end_other_sessions(user, *, keep_session_key=None)`** ends *all of that user's other*
  sessions. This is what a password reset does: a stolen session must not survive a password
  change. The session the user reset *from* is kept — it is rotated (a new session key) by
  the caller, not deleted — so the person who just reset their password is not signed out
  of the browser they did it in.

Why the rows are deleted rather than flagged: Django's session store is keyed by a random
session key, and the row is the whole session. Deleting the row is what makes the session
unusable; there is nothing else to invalidate. `django.contrib.sessions` is in the personal
schema (AD-3), so the delete runs on the personal alias.

The session lifetime itself is Django's (`SESSION_COOKIE_AGE`), configured from the named
constant `AUTH_SESSION_LIFETIME` in `config/settings.py`. This module never reads that
constant: the store enforces the expiry, and the settings are asserted by
`tests/identity/test_session_settings.py`.
"""

from django.contrib.sessions.models import Session
from django.db import transaction

from apps.identity.services import audit as audit_service
from shared.actor import Actor
from shared.db import PERSONAL


def sign_out(*, user, request) -> None:
    """End the session this request carries, and audit the sign-out (D14).

    The session is flushed, so its data is cleared and the row is deleted, and the session
    key is cycled so the next request gets a fresh one.

    Args:
        user: The account signing out. It is the actor of the audit row, and it is passed
            explicitly (D20) rather than read off the request.
        request: The request whose session is ended. The session is the thing being ended,
            and it is reachable only through the request; the *authentication decisions*
            take explicit arguments (the spine: "Auth resolved at the API edge").
    """
    session = getattr(request, "session", None)
    if session is None:
        return None

    session.flush()

    # The audit row is written in its own transaction. It records that the account signed
    # out; the actor is the UUID, never the address (AD-13).
    with transaction.atomic(using=PERSONAL):
        audit_service.write_audit(
            actor=Actor.user(user.pk),
            action="sign_out",
            target_type="User",
            target_id=user.pk,
            details={"method": "session"},
        )

    return None


def end_other_sessions(user, *, keep_session_key: str | None = None) -> int:
    """End every session of `user` except the one identified by `keep_session_key`.

    Args:
        user: The account whose sessions are ended.
        keep_session_key: The session key to keep — the session the user is acting from.
            It is rotated by the caller, not deleted here. `None` ends all of them.

    Returns:
        How many session rows were deleted.
    """
    ended = 0
    for session in _user_sessions(user):
        if keep_session_key is not None and session.session_key == keep_session_key:
            continue
        session.delete(using=PERSONAL)
        ended += 1
    return ended


def _user_sessions(user):
    """The stored sessions that belong to `user`.

    Django's session model keeps the user id inside an encoded payload, not in a column,
    so there is no database-level lookup for "this user's sessions". The rows are read and
    filtered in Python. An account has only a handful of sessions, and the payload is
    decoded with Django's own decoder, so nothing here interprets the format itself.
    """
    for session in Session.objects.using(PERSONAL).all():
        payload = session.get_decoded()
        if str(payload.get("_auth_user_id")) == str(user.pk):
            yield session
