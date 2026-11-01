"""The signed tokens behind the unsubscribe and the click tracker (FR-11, AD-20, SM-2).

**Two tokens, two purposes, two salts.** An unsubscribe token says *"stop sending this
thing to this user"*. A click token says *"this link points at this destination"*. They carry
different facts and must not be interchangeable — a click token that could unsubscribe would
let a tracked link turn into an opt-out, and an unsubscribe token that could be replayed as a
click would make the click count meaningless. The separate salts make them different
signatures over different payloads, so neither can be replayed as the other.

---

## Why Django's `signing`, and not a scheme of our own

The work item says to reuse the project's existing signing helper rather than adding a
scheme. **The project has no signing helper of its own** — the identity app's password-reset
token is a salted SHA-256 digest *stored in a row*, which is a different mechanism entirely: it
needs a database round trip on every use, and an unsubscribe link is clicked from a mail
client that carries no session and may be weeks old.

What the project does have is **Django's own signing module** — `django.core.signing`, the
framework's HMAC-signed serializer, the same primitive Django uses for its own password-reset
tokens. It is vendored into the framework rather than added by us, it is HMAC-SHA256 over a
keyed digest, and its failure mode is a typed exception (`signing.BadSignature`). Using it is
the closest available reading of "do not add a scheme": the scheme is Django's, not ours.

---

## What the token names, and why

The payload is three fields:

| field | what it is |
|---|---|
| `user` | whose subscription is being changed |
| `scope` | **which** subscription — `event_reminders` or `pulse_ping` |
| `target` | for the event scope, which event; empty for the Ping |

**The scope is inside the signed payload, not in the URL path.** A URL that said
`/unsub/pulse_ping/<token>` would have the scope *outside* the signature, and the two could
disagree — a token for the event scope sitting under a `pulse_ping` path. Inside the payload,
the scope is covered by the signature, so editing it invalidates the token.

**The target is inside it for the same reason.** "Stop this event's reminders" is only
meaningful for one event. A token without a target would stop the user's reminders for
*every* event, which is the Pulse Ping's scope and not this one's.

---

## Why the token does not expire

Django's `TimestampSigner` would expire the token. **The work item forbids that**: a token
must not *"expire into uselessness"*. An unsubscribe link sits in an inbox for weeks — a
holiday reminder, a digest from the previous month — and the moment a user finally clicks it
must be the moment it works. An expired link is a dead link, and a dead link is the user
unable to stop what they asked to stop.

So this is a plain `Signer`: the signature is valid forever. What governs the token's effect
is not its age but its **scope** — and a scope is read at the moment the token is used, so
turning the Ping off twice is idempotent and turning it back on is always possible.

**The trade-off, stated plainly.** A never-expiring unsubscribe token is a bearer credential:
anyone who obtains the link can act on it. That is acceptable *because* the only thing it can
do is unsubscribe — it cannot read data, cannot act as the user, and cannot be edited into
another user's unsubscribe because the user id is inside the signed payload. The blast radius
of a leaked link is "this user stops getting this one kind of mail", which is exactly what
the link was for.

---

## The refusal is uniform

A token that is malformed, tampered with, or carries a scope outside the closed set raises
`InvalidTokenError`. **The error says nothing about the user.** A refusal must not become an
oracle: "that user does not exist" would let anyone probe for accounts by minting tokens
against candidate ids and watching what the endpoint said. Every failure is the same
refusal with the same message.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from django.core import signing

from domain.errors import ValidationError
from shared.constants import (
    CLICK_SIGNING_SALT,
    UNSUBSCRIBE_SCOPE_EVENT_REMINDERS,
    UNSUBSCRIBE_SCOPE_PING,
    UNSUBSCRIBE_SCOPES,
    UNSUBSCRIBE_SIGNING_SALT,
)


class InvalidTokenError(ValidationError):
    """The token is malformed, tampered with, or carries a scope we do not act on.

    **One error for every failure**, so the refusal never says which half was wrong. A
    token that was forged, a token that was edited and a token naming a scope we do not
    act on are the same refusal with the same message — otherwise the response becomes an
    oracle and the endpoint can be used to probe for accounts.
    """

    default_message = "That link isn't valid any more. You can change this in your settings."


@dataclass(frozen=True)
class UnsubscribeToken:
    """A verified unsubscribe token: whose, which, and which event."""

    user_id: UUID
    scope: str
    target_id: UUID | None

    @property
    def is_event_scope(self) -> bool:
        """Whether this token stops one event's reminders rather than the Ping."""
        return self.scope == UNSUBSCRIBE_SCOPE_EVENT_REMINDERS


@dataclass(frozen=True)
class ClickToken:
    """A verified click token: who clicked, and where they were going."""

    user_id: UUID
    destination: str


def _signer(salt: str) -> signing.Signer:
    """A signer for one purpose.

    The salt is what makes two signers over the same secret produce different
    signatures, so a payload signed for one purpose cannot verify under the other.
    """
    return signing.Signer(salt=salt)


def _dumps(payload: dict[str, Any], *, salt: str) -> str:
    """Sign a payload and return the signed token."""
    return _signer(salt).sign_object(payload, compress=True)


def _loads(token: str, *, salt: str) -> dict[str, Any]:
    """Verify a signed token and return its payload.

    Raises:
        InvalidTokenError: the token is malformed, the signature does not match, or the
            payload is not the shape we signed.
    """
    try:
        payload = _signer(salt).unsign_object(token)
    except signing.BadSignature:
        # Every failure — a forged signature, a truncated token, a token signed under the
        # other salt — arrives here, and all of them are the same refusal.
        raise InvalidTokenError() from None
    if not isinstance(payload, dict):
        raise InvalidTokenError()
    return payload


def mint_unsubscribe_token(
    *,
    user_id: UUID,
    scope: str,
    target_id: UUID | None = None,
) -> str:
    """Mint the unsubscribe token for one user and one scope.

    Args:
        user_id: whose subscription the token changes.
        scope: which subscription. Must be one of `UNSUBSCRIBE_SCOPES`.
        target_id: the event, for the event scope. `None` for the Pulse Ping.

    Raises:
        InvalidTokenError: the scope is not one we act on, or the event scope has no
            target. A token that names a scope we do not act on would be a signed
            instruction to do nothing — or, worse, something we would have to interpret
            later — so it is refused at the point it is minted.
    """
    if scope not in UNSUBSCRIBE_SCOPES:
        raise InvalidTokenError()
    if scope == UNSUBSCRIBE_SCOPE_EVENT_REMINDERS and target_id is None:
        # An event-scope token with no event is "stop all reminders", which is the Ping's
        # scope and not this one's. Minting it would produce a link that stops the wrong
        # thing.
        raise InvalidTokenError()
    return _dumps(
        {"user": str(user_id), "scope": scope, "target": str(target_id) if target_id else ""},
        salt=UNSUBSCRIBE_SIGNING_SALT,
    )


def read_unsubscribe_token(token: str) -> UnsubscribeToken:
    """Verify an unsubscribe token and return what it names.

    Raises:
        InvalidTokenError: the token is not valid, or it names a scope we do not act on.
    """
    payload = _loads(token, salt=UNSUBSCRIBE_SIGNING_SALT)

    scope = payload.get("scope")
    if scope not in UNSUBSCRIBE_SCOPES:
        raise InvalidTokenError()

    raw_user = payload.get("user")
    raw_target = payload.get("target") or ""
    try:
        user_id = UUID(str(raw_user))
        target_id = UUID(str(raw_target)) if raw_target else None
    except (TypeError, ValueError):
        raise InvalidTokenError() from None

    if scope == UNSUBSCRIBE_SCOPE_EVENT_REMINDERS and target_id is None:
        raise InvalidTokenError()

    return UnsubscribeToken(user_id=user_id, scope=scope, target_id=target_id)


def mint_click_token(*, user_id: UUID, destination: str) -> str:
    """Mint a click-tracker's token for one destination.

    **A click token is not an unsubscribe token and cannot become one.** They are signed
    under different salts over different payloads, so a click token fails verification
    under the unsubscribe salt — and vice versa. That is what stops a tracked link from
    being an opt-out.
    """
    return _dumps(
        {"user": str(user_id), "destination": destination},
        salt=CLICK_SIGNING_SALT,
    )


def read_click_token(token: str) -> ClickToken:
    """Verify a click token and return what it names.

    Raises:
        InvalidTokenError: the token is not valid.
    """
    payload = _loads(token, salt=CLICK_SIGNING_SALT)

    raw_user = payload.get("user")
    destination = payload.get("destination")
    if not isinstance(destination, str) or not destination:
        raise InvalidTokenError()
    try:
        user_id = UUID(str(raw_user))
    except (TypeError, ValueError):
        raise InvalidTokenError() from None

    return ClickToken(user_id=user_id, destination=destination)


__all__ = [
    "ClickToken",
    "InvalidTokenError",
    "UNSUBSCRIBE_SCOPE_EVENT_REMINDERS",
    "UNSUBSCRIBE_SCOPE_PING",
    "UnsubscribeToken",
    "mint_click_token",
    "mint_unsubscribe_token",
    "read_click_token",
    "read_unsubscribe_token",
]
