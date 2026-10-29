"""The calendar-connection commands (AD-18, FR-50): connect, disconnect, purge, reveal.

These are the only way a `CalendarConnection` changes (AD-16). Each command takes an
explicit `Actor` and an explicit `now`, opens one `transaction.atomic(using=PERSONAL)`, and
writes its audit row inside it (AD-5).

The credential is a secret throughout. It is encrypted on the way in, it is never logged,
it is never in an audit row, and the only function that hands it back wraps it in
`ports.calendar.Credential`, which redacts its own `repr` and `str`.

Design: .specs-fire/intents/onboarding-and-account/work-items/
calendar-connection-model-design.md (decisions D6, D7, D13).
"""

from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.personalization.credentials import fingerprint
from apps.personalization.models import CalendarConnection, PersonalEvent
from apps.personalization.services.audit import write_audit
from domain.errors import (
    CalendarProviderCapReached,
    CredentialDecryptionError,
    InvalidCalendarCredentialError,
)
from ports.calendar import Credential
from shared.actor import Actor
from shared.constants import FREE_TIER_CALENDAR_PROVIDER_CAP
from shared.credential_key import InvalidCredentialKey, parse_key
from shared.db import PERSONAL

#: The schemes a calendar address may use. `webcal://` and `webcals://` are the iCloud
#: spelling; the adapter normalises them to `https://` at fetch time (D13). This is a
#: *shape* check, not the SSRF policy — that belongs to the adapter.
ALLOWED_SCHEMES = frozenset({"http", "https", "webcal", "webcals"})

#: A status that still occupies one of the user's provider slots. A disconnected
#: connection does not: the user gave it up (D7).
OCCUPYING_STATUSES = (
    CalendarConnection.Status.ACTIVE,
    CalendarConnection.Status.NEEDS_RECONNECT,
)


def _validated_url(url: str) -> str:
    """The address as it will be stored, or a refusal.

    The address is stored **as the user typed it** (trimmed). The adapter normalises
    `webcal://` to `https://` at fetch time, so the stored form and the fetched form can
    differ — which is right, because the stored form is what the user recognises.

    Two refusals:

    - **No usable scheme.** The address must have one of the four schemes above. This is a
      shape check, not a normalisation: the address is never rewritten on the way in.
    - **Credentials in the userinfo component.** `https://user:pass@host/...` carries a
      second secret inside a URL we are about to encrypt and store, and the redaction
      patterns are tuned for the path/query form. Refusing it is simpler and safer than
      trying to redact it everywhere.

    The address is never echoed back in the error: it is a secret, and this error can reach
    an HTTP response (AD-13).
    """
    text = (url or "").strip()
    if not text:
        raise InvalidCalendarCredentialError(details={"field": "url"})

    parts = urlsplit(text)
    if not parts.scheme or parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise InvalidCalendarCredentialError(details={"field": "url"})
    if not parts.netloc:
        raise InvalidCalendarCredentialError(details={"field": "url"})
    if parts.username or parts.password or "@" in parts.netloc:
        raise InvalidCalendarCredentialError(details={"field": "url"})
    return text


def _key():
    """The application-level key, parsed.

    A malformed key raises `CredentialDecryptionError`: at this point the row's fate is
    the caller's business, and the settings load already refused a malformed key at
    startup (D5), so this only fires when a key was rotated wrongly under a running
    process.
    """
    try:
        return parse_key(settings.CALENDAR_CREDENTIAL_KEY)
    except InvalidCredentialKey as exc:
        raise CredentialDecryptionError(
            "The configured calendar credential key is malformed."
        ) from exc


def _slot_count(user_id) -> int:
    """How many of the user's provider slots are taken.

    A `needs_reconnect` connection still occupies a slot: the user has not given it up,
    and letting it go free would let them connect past the cap by waiting for a failure.
    """
    return (
        CalendarConnection.objects.using(PERSONAL)
        .filter(user_id=user_id, status__in=OCCUPYING_STATUSES)
        .count()
    )


def connect_calendar(
    *,
    user_id,
    provider: str,
    url: str,
    display_label: str = "",
    actor: Actor,
    now=None,
) -> CalendarConnection:
    """Connect a calendar: encrypt its credential and store the connection (AD-18, FR-50).

    The Free-tier cap is enforced **here**, at the connect step, rather than in the API
    layer: the API is one caller, and a cap that only one caller enforces is a cap another
    caller walks past.

    The three refusals are ordered by specificity, so the user is told the most precise
    truth: "already connected" beats "plan limit", because the cap counts *distinct*
    calendars and a calendar the user already has is already counted.

    Reconnecting a `needs_reconnect` connection updates that row in place — the credential,
    the fingerprint, the status and the poll schedule — rather than creating a second row
    for the same calendar. The row is matched by **status**, not by fingerprint: the
    provider revoked the old secret, so the address the user pastes now is a *new* one,
    and the row waiting for it is the one to reuse.

    The address itself is never written to an audit row, and never appears in the returned
    object's `repr`.
    """
    moment = now or timezone.now()
    address = _validated_url(url)
    key = _key()
    digest = fingerprint(address, key)

    with transaction.atomic(using=PERSONAL):
        # The checks are ordered by **specificity**: the most precise truth wins, so the
        # user is never told "plan limit" when the real answer is "already connected".
        #
        # 1. Is this exact calendar already connected and healthy? Then the answer is
        #    "already connected", not "plan limit" — the cap is about *distinct*
        #    calendars, and this one is already counted.
        already_active = (
            CalendarConnection.objects.using(PERSONAL)
            .filter(
                user_id=user_id,
                credential_fingerprint=digest,
                status=CalendarConnection.Status.ACTIVE,
            )
            .first()
        )
        if already_active is not None:
            # The unique constraint would refuse this anyway; refusing here says so plainly
            # instead of raising a database error at the boundary.
            raise InvalidCalendarCredentialError(details={"field": "url"})

        # 2. Is the user waiting to reconnect a calendar? Then this connect **is** the
        #    reconnect: the row is reused rather than a second row being created, and it
        #    does not take another slot. The address may be a new one — the provider
        #    revoked the old secret — which is exactly why the row is matched by status
        #    and not by fingerprint.
        #
        #    The Free tier is one calendar, so a user has at most one such row.
        existing = (
            CalendarConnection.objects.using(PERSONAL)
            .filter(user_id=user_id, status=CalendarConnection.Status.NEEDS_RECONNECT)
            .first()
        )

        # 3. Only now does the cap apply: a *new* calendar for a user who is already at
        #    the cap. A `needs_reconnect` connection still occupies its slot (the user has
        #    not given it up), so the count is taken over the occupying statuses.
        if existing is None and _slot_count(user_id) >= FREE_TIER_CALENDAR_PROVIDER_CAP:
            raise CalendarProviderCapReached(details={"cap": FREE_TIER_CALENDAR_PROVIDER_CAP})

        if existing is not None:
            connection = existing
            connection.provider = provider
            connection.credential = address
            connection.credential_fingerprint = digest
            connection.status = CalendarConnection.Status.ACTIVE
            connection.display_label = display_label
            connection.last_error_kind = None
            connection.last_error_at = None
            connection.last_polled_at = None
            connection.next_poll_at = None
            connection.save(
                using=PERSONAL,
                update_fields=[
                    "provider",
                    "credential",
                    "credential_fingerprint",
                    "status",
                    "display_label",
                    "last_error_kind",
                    "last_error_at",
                    "last_polled_at",
                    "next_poll_at",
                    "updated_at",
                ],
            )
            action = "calendar.reconnected"
        else:
            connection = CalendarConnection.objects.using(PERSONAL).create(
                user_id=user_id,
                provider=provider,
                credential=address,
                credential_fingerprint=digest,
                status=CalendarConnection.Status.ACTIVE,
                display_label=display_label,
            )
            action = "calendar.connected"

        write_audit(
            actor=actor,
            action=action,
            target_type="calendar_connection",
            target_id=connection.pk,
            # The provider and the moment. Never the address, never the fingerprint
            # (AD-13).
            details={"provider": provider, "at": moment.isoformat()},
        )

    return connection


def disconnect_calendar(*, connection: CalendarConnection, actor: Actor, now=None) -> None:
    """Disconnect a calendar: destroy its credential, then purge its events (D7).

    The order matters, and it is the safe one. The credential is destroyed **first**, in
    this transaction, so the user's revocation never depends on a purge job succeeding: if
    the purge fails, the secret is already gone.

    The row is **not** deleted here. It becomes `disconnected` with a `NULL` credential, and
    the retention sweep removes it later (AD-15). A row that lingered with a live
    credential would keep a secret alive after the user asked for it to be revoked.

    The audit row is written in the same transaction, so "the user disconnected this" and
    "the credential is gone" commit together (AD-5).
    """
    moment = now or timezone.now()

    with transaction.atomic(using=PERSONAL):
        CalendarConnection.objects.using(PERSONAL).filter(pk=connection.pk).update(
            status=CalendarConnection.Status.DISCONNECTED,
            credential=None,
            last_error_kind=None,
            last_error_at=None,
            next_poll_at=None,
        )
        write_audit(
            actor=actor,
            action="calendar.disconnected",
            target_type="calendar_connection",
            target_id=connection.pk,
            details={"provider": connection.provider, "at": moment.isoformat()},
        )


def purge_connection_events(*, connection: CalendarConnection) -> int:
    """Delete exactly the events this connection imported, and return how many.

    The connection is held by value, so the purge is one equality filter — exact by
    construction, and the same query for one connection or for all of them (AD-18: "a
    disconnect purges exactly that connection's events").
    """
    deleted, _ = (
        PersonalEvent.objects.using(PERSONAL).filter(calendar_connection_id=connection.pk).delete()
    )
    return deleted


def reveal_credential(*, connection: CalendarConnection) -> Credential:
    """The connection's credential, wrapped so it cannot be printed by accident.

    This is the **only** function in the codebase that returns the plaintext, and it
    returns it wrapped in `ports.calendar.Credential`, whose `repr` and `str` are
    `Credential('[redacted]')`. The caller that needs the real value calls `reveal()`,
    and that caller is the fetch path (AD-18).

    A cleared credential (a disconnected connection) is refused, and so is a credential
    that cannot be decrypted — a wrong key is a fault, not an absence, and the two must
    not look alike (D7).
    """
    if connection.credential is None:
        raise CredentialDecryptionError("This calendar connection has no credential.")
    return Credential(connection.credential)


__all__ = [
    "ALLOWED_SCHEMES",
    "connect_calendar",
    "disconnect_calendar",
    "purge_connection_events",
    "reveal_credential",
]
