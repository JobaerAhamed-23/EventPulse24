"""The calendar-connection commands and reads (AD-18, FR-50): connect, disconnect,
purge, reveal, list.

These are the only way a `CalendarConnection` changes (AD-16). Each command takes an
explicit `Actor` and an explicit `now`, opens one `transaction.atomic(using=PERSONAL)`, and
writes its audit row inside it (AD-5).

The credential is a secret throughout. It is encrypted on the way in, it is never logged,
it is never in an audit row, and the only function that hands it back wraps it in
`ports.calendar.Credential`, which redacts its own `repr` and `str`.

**The reads never return the credential either.** `list_calendar_connections` and
`get_calendar_connection` return a projection with no field for the address and no field
for the fingerprint — so the guarantee that no response body carries the secret is
structural rather than careful: there is nowhere for it to go.

**Two policies live here, not in the API layer.** The Free-tier cap and the address
pre-flight are both enforced in the service. A policy that only one caller enforces is a
policy another caller walks past, and the API is only one caller — the worker's dispatch
path and the settings surface are others.

Design: .specs-fire/intents/onboarding-and-account/work-items/
calendar-connection-model-design.md (decisions D6, D7, D13).
"""

from dataclasses import dataclass
from datetime import datetime
from hashlib import blake2b
from ipaddress import ip_address
from urllib.parse import urlsplit
from uuid import UUID

from django.conf import settings
from django.db import connections, transaction
from django.utils import timezone

from apps.delivery.services.reminder_plans import remove_plans_for_targets
from apps.personalization.credentials import fingerprint
from apps.personalization.models import CalendarConnection, ConflictPair, PersonalEvent
from apps.personalization.services.audit import write_audit
from apps.personalization.services.personal_events import delete_personal_event
from domain.errors import (
    CalendarConnectionNotFoundError,
    CalendarProviderCapReached,
    CredentialDecryptionError,
    InvalidCalendarCredentialError,
)
from ports.calendar import Credential
from ports.fetch_policy import fetch_deny_policy
from shared.actor import Actor
from shared.constants import CALENDAR_CLAIM_TTL, FREE_TIER_CALENDAR_PROVIDER_CAP
from shared.credential_key import InvalidCredentialKey, parse_key
from shared.db import PERSONAL

#: The schemes a calendar address may use. `webcal://` and `webcals://` are the iCloud
#: spelling; the adapter normalises them to `https://` at fetch time (D13). This is a
#: *shape* check, not the SSRF policy — that belongs to the adapter.
#:
#: `http://` is **not** allowed: the secret ICS URL *is* the credential, and fetching it
#: in cleartext would put it on the wire on every poll, forever. The adapter refuses it
#: too — but refusing it here means the user hears about it while they are still typing,
#: rather than at the first poll, with a stored connection they cannot use.
ALLOWED_SCHEMES = frozenset({"https", "webcal", "webcals"})

#: A status that still occupies one of the user's provider slots. A disconnected
#: connection does not: the user gave it up (D7).
OCCUPYING_STATUSES = (
    CalendarConnection.Status.ACTIVE,
    CalendarConnection.Status.NEEDS_RECONNECT,
)


def _validated_provider(provider: str) -> str:
    """The provider, if it is one we know; otherwise a refusal.

    **This is a membership test, not a branch.** Nothing downstream treats Google
    differently from Apple — the provider is a label on the connection, and the whole
    point of FR-3's parity rule is that the server's behaviour does not change with it
    (Amendment A-9: all three providers connect by pasting an address).

    The check lives here rather than in the API layer for two reasons: the API layer may
    not import the model, so the set of known providers lives with the model; and a check
    that only one caller performs is a check another caller walks past.
    """
    known = {choice.value for choice in CalendarConnection.Provider}
    if provider not in known:
        raise InvalidCalendarCredentialError(details={"field": "provider"})
    return provider


def _validated_url(url: str) -> str:
    """The address as it will be stored, or a refusal.

    The address is stored **as the user typed it** (trimmed). The adapter normalises
    `webcal://` to `https://` at fetch time, so the stored form and the fetched form can
    differ — which is right, because the stored form is what the user recognises.

    Four refusals:

    - **No usable scheme.** The address must have one of the three schemes above. This is a
      shape check, not a normalisation: the address is never rewritten on the way in.
    - **Credentials in the userinfo component.** `https://user:pass@host/...` carries a
      second secret inside a URL we are about to encrypt and store, and the redaction
      patterns are tuned for the path/query form. Refusing it is simpler and safer than
      trying to redact it everywhere.
    - **A port the fetch adapter would not allow.** See `_refused_port`.
    - **A host that is a denied literal address.** See `_refused_host`.

    The address is never echoed back in the error: it is a secret, and this error can reach
    an HTTP response (AD-13).
    """
    text = (url or "").strip()
    if not text:
        raise InvalidCalendarCredentialError(details={"field": "url"})

    try:
        parts = urlsplit(text)
    except ValueError:
        # `urlsplit` raises a bare `ValueError` on a malformed bracketed IPv6 host
        # ("https://[not-an-ip]/x"). It is not a `DomainError`, so it would escape to the
        # 500 handler — a server fault for what is a typo. Every other bad address
        # gets a calm 422, and this one does too.
        raise InvalidCalendarCredentialError(details={"field": "url"}) from None

    if not parts.scheme or parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise InvalidCalendarCredentialError(details={"field": "url"})
    if not parts.netloc:
        raise InvalidCalendarCredentialError(details={"field": "url"})
    if parts.username or parts.password or "@" in parts.netloc:
        raise InvalidCalendarCredentialError(details={"field": "url"})

    _refused_port(parts)
    _refused_host(parts.hostname)
    return text


#: The port each scheme means when the address does not name one. `webcal` is iCloud's
#: spelling of an `https` feed, so it means 443.
_DEFAULT_PORTS = {"https": 443, "webcal": 443, "webcals": 443}


def _refused_port(parts) -> None:
    """Refuse an address whose port the fetch adapter would not allow.

    **This is the same "invisible at connect time" problem the host pre-flight
    solves.** The hardened fetch client only connects to the ports in
    `SOURCE_FETCH["allowed_ports"]` (80 and 443), and it refuses any other one — on
    every hop. So an address like `https://example.com:8443/feed.ics` would be
    accepted here, stored with a live encrypted credential, shown to the user as
    connected, and then refused on **every single poll** — with the only evidence
    being a slug in the connection's error field.

    The ports are read from the same settings the fetch client reads, so the two
    cannot drift apart.
    """
    allowed = settings.SOURCE_FETCH["allowed_ports"]
    try:
        port = parts.port
    except ValueError:
        # `urlsplit`'s `port` property raises for a non-numeric or out-of-range port
        # ("https://host:99999/x"). Same rule as the host: a typo is a calm refusal, not
        # a server fault.
        raise InvalidCalendarCredentialError(details={"field": "url"}) from None

    port = port or _DEFAULT_PORTS.get(parts.scheme.lower())
    if port is not None and port not in allowed:
        raise InvalidCalendarCredentialError(details={"field": "url"})


def _refused_host(hostname: str | None) -> None:
    """Refuse an address whose host is a denied IP literal.

    **This is a pre-flight, not the policy.** The SSRF policy is enforced at *connect
    time* by `adapters.crawl.http.GuardedBackend`, which resolves the host itself and
    refuses any denied address — on every redirect hop, so DNS rebinding cannot bypass
    it. That check is the real one, and it is not optional.

    The pre-flight exists because a connect-time refusal is **invisible at connect
    time**. The user pastes an address, the row is created, and the first poll — up to a
    minute later, in a worker, with nobody watching — fails. The user has a stored
    connection they cannot use, and the only evidence is a log line. So the service
    refuses the obvious cases up front, while the user is still there to hear about it.

    **What it can and cannot see.** A host that is an IP *literal* is checked directly.
    A host that is a *name* is not resolved here — resolving it in a request is a DNS
    lookup with its own timeout, and a name that resolves to a denied address is caught
    at connect time anyway. So this check refuses `https://127.0.0.1/feed.ics` and
    `https://[::1]/feed.ics`, and says nothing about a name.

    **It cannot be bypassed.** The connect-time check still runs and still refuses, so a
    rebind between this check and the fetch does not get through.

    **The policy it consults is the configured one.** It reads
    `ports.fetch_policy.fetch_deny_policy()`, which is the real `is_denied` — and
    stays the real `is_denied` — unless the *test settings module* is in use. The
    test-only allowance lets a proof connect a calendar to a local fixture ICS server
    on loopback, which this pre-flight would otherwise refuse before the row is
    created; it is reachable only under `config.settings_test`, and
    `tests/e2e/test_loopback_allowance.py` proves that.

    The host is never empty here: the caller has already refused an address with no
    netloc, and `urlsplit` on an address that has one always yields a hostname.
    """
    # `urlsplit` keeps the brackets on an IPv6 literal, so they come off first.
    candidate = (hostname or "").strip("[]")
    try:
        address = ip_address(candidate)
    except ValueError:
        # Not a literal: a name. The connect-time check resolves it.
        return

    if fetch_deny_policy()(address):
        raise InvalidCalendarCredentialError(details={"field": "url"})


def _refused_duplicate(*, user_id, digest: str, exclude_pk=None) -> None:
    """Refuse an address the user already holds on **another** live connection.

    **This is the same refusal `connect_calendar` makes**, and it lives here so both
    commands say the same thing. Without it, a reconnect onto an address the user
    already holds falls through to the unique constraint and answers 500 — a server
    fault for an input the user can correct in one step.

    The row being reconnected is exempt: a reconnect *replaces* that row's own
    fingerprint, so the row must not count as a duplicate of itself. `exclude_pk` is
    how that exemption is expressed.
    """
    duplicate = (
        CalendarConnection.objects.using(PERSONAL)
        .filter(
            user_id=user_id,
            credential_fingerprint=digest,
            status__in=OCCUPYING_STATUSES,
        )
        .exclude(pk=exclude_pk)
        .first()
    )
    if duplicate is not None:
        raise InvalidCalendarCredentialError(details={"field": "url"})


#: The advisory lock's namespace. Distinct from onboarding's, so the two never block
#: each other — they lock different things.
_LOCK_PERSON = b"eventpulse24-cal"


def _user_lock_key(user_id) -> int:
    """The advisory-lock key for one user's calendar connections.

    Stable across processes: `blake2b`, never the per-process-salted `hash()`.
    """
    digest = blake2b(str(user_id).encode(), digest_size=8, person=_LOCK_PERSON).digest()
    return int.from_bytes(digest, "big", signed=True)


def _lock_user(user_id) -> None:
    """Serialise the calendar commands for one user.

    **Why an advisory lock and not a row lock.** The cap is a **count**, and a count is
    not a lock: two concurrent connects both read a count of zero, both pass the check,
    and both write a row — so a Free account ends up holding two calendars, and the
    loser of a same-address race gets a raw `IntegrityError` that reaches the client as
    a 500. A row lock cannot help either, because the row that would carry the lock is
    the very row that does not exist yet. An advisory lock is taken on a *key*, so it
    works whether or not any row exists.

    `pg_advisory_xact_lock` is **transaction-scoped**: the lock is released when the
    transaction commits or rolls back, so a crashed worker cannot leave a user's
    calendars wedged.
    """
    with connections[PERSONAL].cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_user_lock_key(user_id)])


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

    **The provider is validated here too**, for the same reason: the API layer may not
    import the model, so the set of known providers lives with the model — and a check
    that only one caller performs is a check another caller walks past.

    The three refusals are ordered by specificity, so the user is told the most precise
    truth: "already connected" beats "plan limit", because the cap counts *distinct*
    calendars and a calendar the user already has is already counted.

    Reconnecting a `needs_reconnect` connection updates that row in place — the credential,
    the fingerprint, the status and the poll schedule — rather than creating a second row
    for the same calendar. The row is matched by **status**, not by fingerprint: the
    provider revoked the old secret, so the address the user pastes now is a *new* one,
    and the row waiting for it is the one to reuse.

    **It requests a sync; it does not perform one (D9).** `next_poll_at` is set to the
    moment, so the connection is due immediately and the tick's dispatcher picks it up
    within 60 seconds. The command itself never fetches: AD-11 forbids long work in a
    request, and a fetch can take 30 seconds and download megabytes. Setting the due time
    is the durable expression of "please sync this soon", and it is the same pattern
    `ingestion`'s `register_source` uses.

    The address itself is never written to an audit row, and never appears in the returned
    object's `repr`.
    """
    moment = now or timezone.now()
    _validated_provider(provider)
    address = _validated_url(url)
    key = _key()
    digest = fingerprint(address, key)

    with transaction.atomic(using=PERSONAL):
        # The user's calendar commands are serialised for the length of this
        # transaction. The cap is a count, and a count read without a lock is a race:
        # two concurrent connects would both read zero and both write a row, leaving a
        # Free account with two calendars.
        _lock_user(user_id)

        # The checks are ordered by **specificity**: the most precise truth wins, so the
        # user is never told "plan limit" when the real answer is "already connected".
        #
        # 1. Is this exact calendar already connected and healthy? Then the answer is
        #    "already connected", not "plan limit" — the cap is about *distinct*
        #    calendars, and this one is already counted.
        #
        #    **Only `ACTIVE` counts here, not `NEEDS_RECONNECT`.** A revoked row that
        #    still holds this address is the *reuse* case below, not a duplicate: the
        #    user is reconnecting the calendar they already have. (The helper
        #    `_refused_duplicate` checks the occupying statuses, because a reconnect
        #    replaces a row's fingerprint rather than reusing it.)
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

        # 3. Only now does the cap apply. A `needs_reconnect` connection still occupies
        #    its slot (the user has not given it up), so the count is taken over the
        #    occupying statuses.
        #
        #    **The reuse path does not get a free pass.** A `needs_reconnect` row that
        #    is flipped to `active` is still one row, so it does not add a slot — but
        #    the cap is about *live calendars the user holds*, and skipping the check
        #    on this path let a user end up with two active calendars on a one-calendar
        #    plan. The count is taken over the occupying statuses either way; the
        #    reuse path simply does not add to it.
        occupying = _slot_count(user_id)
        if existing is not None:
            # The row being reused is already counted, so it does not add a slot.
            occupying -= 1
        if occupying >= FREE_TIER_CALENDAR_PROVIDER_CAP:
            raise CalendarProviderCapReached(
                details={
                    "cap": FREE_TIER_CALENDAR_PROVIDER_CAP,
                    # The approved copy is an **inline** prompt with a quiet "Upgrade"
                    # link, not a modal (EXPERIENCE.md §3, the Free-tier cap prompt; and
                    # §4, the Browse save-quota-exceeded line). So the hint is one calm
                    # sentence and the payload carries no modal-shaped field at all —
                    # no `modal`, no `title`, no `actions`, no `dismissable`.
                    "upgrade_hint": "Save more with Pro.",
                }
            )

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
            # D9: due immediately, so the dispatcher syncs it within a tick.
            connection.next_poll_at = moment
            # A claim left behind by a worker that died is cleared. The row is active and
            # due now, and a live claim would keep the dispatcher from picking it up until
            # the claim expired — so the user's first sync after reconnecting would wait
            # up to `CALENDAR_CLAIM_TTL` for no reason.
            connection.sync_claimed_at = None
            # The old validators belong to the old credential's feed. Keeping them would
            # make the provider answer 304 for a feed it has never seen this address's
            # events in.
            connection.etag = None
            connection.last_modified = None
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
                    "sync_claimed_at",
                    "etag",
                    "last_modified",
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
                # D9: due immediately, so the dispatcher syncs it within a tick.
                next_poll_at=moment,
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


def reconnect_calendar(
    *,
    connection: CalendarConnection,
    url: str,
    display_label: str = "",
    actor: Actor,
    now=None,
) -> CalendarConnection:
    """Replace a revoked calendar's credential and bring it back to life (AD-18, FR-50).

    A revoked connection keeps the events it imported (D6) and waits for the user to paste
    a new address. This command is that paste: the credential is replaced, the status
    returns to `active`, the error fields are cleared, and the connection is due
    immediately so the dispatcher syncs it within a tick (D9).

    **The imported events are kept.** The provider revoked the *address*, not the events
    (D6), and the user is reconnecting the very same calendar — throwing away their
    agenda because a secret expired would be destructive and irreversible.

    The new address is validated exactly as a connect validates one, and it is fingerprinted
    the same way, so the "one calendar per address" constraint holds across a reconnect.

    A connection that is already `active` is refused: there is nothing to reconnect, and
    silently replacing a working credential would make the user's calendar change
    identity without them asking.
    """
    moment = now or timezone.now()
    address = _validated_url(url)
    key = _key()
    digest = fingerprint(address, key)

    with transaction.atomic(using=PERSONAL):
        # **The status is re-read under a row lock, not trusted from the caller.**
        #
        # The check below used to happen *before* the transaction, on the row the
        # lookup handed in. A disconnect that committed in between was then silently
        # overwritten: the row came back as `active` with a live credential, and the
        # dispatcher started polling a calendar the user had just removed — after the
        # disconnect's purge had already deleted its events.
        #
        # Reading the row under `select_for_update` inside the transaction means the
        # status is the one that is true *now*, and a concurrent disconnect waits for
        # this transaction rather than being overwritten by it.
        locked = (
            CalendarConnection.objects.using(PERSONAL)
            .select_for_update()
            .filter(pk=connection.pk)
            .first()
        )
        if locked is None:
            raise CalendarConnectionNotFoundError(details={"connection_id": str(connection.pk)})

        if locked.status == CalendarConnection.Status.DISCONNECTED:
            # A disconnected connection has no credential and no poll schedule.
            # Reconnecting one would resurrect a row the user deliberately gave up.
            raise InvalidCalendarCredentialError(details={"field": "url"})
        if locked.status == CalendarConnection.Status.ACTIVE:
            raise InvalidCalendarCredentialError(details={"field": "url"})

        # Is this address one the user already holds on **another** live connection?
        # Then the reconnect would collide with it. Saying so plainly beats letting
        # the unique constraint raise a database error that reaches the client as a 500.
        _refused_duplicate(user_id=locked.user_id, digest=digest, exclude_pk=locked.pk)

        connection = locked
        connection.credential = address
        connection.credential_fingerprint = digest
        connection.status = CalendarConnection.Status.ACTIVE
        if display_label:
            connection.display_label = display_label
        connection.last_error_kind = None
        connection.last_error_at = None
        # D9: due immediately.
        connection.next_poll_at = moment
        # A claim left behind by a worker that died is cleared. The row is active and due
        # now, and a live claim would keep the dispatcher from picking it up until the
        # claim expired — so the user's first sync after reconnecting would wait up to
        # `CALENDAR_CLAIM_TTL` for no reason.
        connection.sync_claimed_at = None
        # The old validators belong to the old credential's feed.
        connection.etag = None
        connection.last_modified = None
        connection.save(
            using=PERSONAL,
            update_fields=[
                "credential",
                "credential_fingerprint",
                "status",
                "display_label",
                "last_error_kind",
                "last_error_at",
                "next_poll_at",
                "sync_claimed_at",
                "etag",
                "last_modified",
                "updated_at",
            ],
        )
        write_audit(
            actor=actor,
            action="calendar.reconnected",
            target_type="calendar_connection",
            target_id=connection.pk,
            details={"provider": connection.provider, "at": moment.isoformat()},
        )

    return connection


def disconnect_calendar(*, connection: CalendarConnection, actor: Actor, now=None) -> None:
    """Disconnect a calendar: destroy its credential, then purge its events (D7, D13).

    The order matters, and it is the safe one. The credential is destroyed **first**, in
    this transaction, so the user's revocation never depends on a purge job succeeding: if
    the purge fails, the secret is already gone.

    The row is **not** deleted here. It becomes `disconnected` with a `NULL` credential, and
    the retention sweep removes it later (AD-15). A row that lingered with a live
    credential would keep a secret alive after the user asked for it to be revoked.

    **The purge (D13).** FR-50: "disconnecting purges exactly that connection's events". The
    purge touches three tables, each through **its owner's interface**:

    | Step | Owner | How |
    |---|---|---|
    | the conflict pairs | `personalization` | `delete_personal_event` closes them |
    | the events | `personalization` | `delete_personal_event` |
    | the reminder plans | **`delivery`** | `remove_plans_for_targets` (AD-16) |

    The purge is scoped by `calendar_connection_id = connection.pk`, which is exact by
    construction: another connection's events and the user's own events are untouched.

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
            sync_claimed_at=None,
            etag=None,
            last_modified=None,
        )
        write_audit(
            actor=actor,
            action="calendar.disconnected",
            target_type="calendar_connection",
            target_id=connection.pk,
            details={"provider": connection.provider, "at": moment.isoformat()},
        )

    _purge_connection_events(connection=connection, actor=actor, now=moment)


def _owned_connection(*, user_id, connection_id: UUID) -> CalendarConnection:
    """The user's own connection row, or `CalendarConnectionNotFoundError`.

    **This is the scoping, in one place.** The API layer may not import
    `apps.personalization.models` (the `models-personalization` import contract), so the
    lookup that decides *whose* connection this is happens here, inside the service. The
    query is scoped by `user_id`, so another user's connection is not found — and the
    endpoint never learns whether the row exists for somebody else.

    The lookup is deliberately outside the command's own transaction: the row it returns
    is handed to a command that opens its own, and a row lock taken here would be
    released before that transaction began.

    **The credential is not decrypted here.** A row whose credential cannot be read (a
    rotated key id, a corrupted ciphertext) would raise from the *lookup*, and the user
    would be unable to disconnect the broken connection — the remedy would refuse
    itself. The commands that need the address fetch it themselves, inside their own
    transaction, where a decryption failure is a fault they can report.
    """
    row = (
        CalendarConnection.objects.using(PERSONAL)
        .filter(user_id=user_id, pk=connection_id)
        .only(
            "id",
            "provider",
            "status",
            "display_label",
            "user_id",
            "created_at",
        )
        .first()
    )
    if row is None:
        raise CalendarConnectionNotFoundError(details={"connection_id": str(connection_id)})
    return row


def reconnect_calendar_for_user(
    *,
    user_id,
    connection_id: UUID,
    url: str,
    display_label: str = "",
    actor: Actor,
    now=None,
) -> CalendarConnection:
    """Replace one of the user's own revoked connections' address.

    The user-scoped wrapper around `reconnect_calendar`: it finds the connection by id
    **and** by owner, so a connection belonging to somebody else reads as not found —
    not as forbidden — and the API layer never touches the model.
    """
    connection = _owned_connection(user_id=user_id, connection_id=connection_id)
    return reconnect_calendar(
        connection=connection,
        url=url,
        display_label=display_label,
        actor=actor,
        now=now,
    )


def disconnect_calendar_for_user(
    *,
    user_id,
    connection_id: UUID,
    actor: Actor,
    now=None,
) -> None:
    """Disconnect one of the user's own connections.

    The user-scoped wrapper around `disconnect_calendar`: it finds the connection by id
    **and** by owner, so a connection belonging to somebody else reads as not found —
    not as forbidden — and the API layer never touches the model.
    """
    connection = _owned_connection(user_id=user_id, connection_id=connection_id)
    disconnect_calendar(connection=connection, actor=actor, now=now)


def _purge_connection_events(*, connection: CalendarConnection, actor: Actor, now) -> int:
    """Delete exactly this connection's imported events, their pairs and their plans (D13).

    Each step goes through its owner's interface:

    1. The events are deleted with `delete_personal_event` — the same command the user's
       own delete uses, so the conflict pairs naming them close as
       `cleared_by_state_change` and each deletion writes its audit row.
    2. The reminder plans are deleted with `delivery`'s `remove_plans_for_targets`, because
       `delivery` owns `REMINDER_PLAN` and `personalization` may not write it (AD-16).

    The plans are deleted rather than left behind: a disconnected calendar's plans would
    be a growing pile of rows pointing at events that no longer exist.

    The credential is already gone by the time this runs, so a failure here leaves the
    user's revocation intact — the secret is destroyed either way.
    """
    imported = list(
        PersonalEvent.objects.using(PERSONAL)
        .filter(calendar_connection_id=connection.pk)
        .values_list("id", flat=True)
    )
    if not imported:
        return 0

    for event_id in imported:
        delete_personal_event(
            user_id=connection.user_id,
            event_id=event_id,
            actor=actor,
            now=now,
        )
    remove_plans_for_targets(
        user_id=connection.user_id,
        target_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        target_ids=tuple(imported),
        actor=actor,
        now=now,
    )
    return len(imported)


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


# ─────────────────────────────────────────────────────────────────────────────
# The reads
#
# The API layer may not import `apps.personalization.models` (the
# `models-personalization` import contract), so a list endpoint cannot query the ORM
# itself. These reads are the published way in.
#
# **They return a projection, not a model.** The projection has no field for the
# credential and no field for the fingerprint, so the guarantee that no response body
# carries the secret address is structural rather than careful: there is nowhere for it
# to go. The fingerprint is a keyed HMAC and so is not a secret, but it is not the user's
# business either, and a digest in a response body is one more thing to leak in a
# screenshot.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CalendarConnectionView:
    """One connection, as it is shown to the user.

    Every field here is safe to show. The two fields that are not — the credential and
    the fingerprint — have no representation in this class at all.

    `last_error_kind` is a **slug** (`revoked`, `transient`, …), never a message and
    never a URL: an `httpx` exception message contains the full request URL, which *is*
    the credential (AD-13). The model already stores only slugs; the projection keeps
    that discipline.
    """

    id: UUID
    provider: str
    status: str
    display_label: str
    #: When the last poll finished. Null if it never has.
    last_synced_at: datetime | None
    #: When the next poll is due. Null if the connection is not going to be polled.
    next_sync_at: datetime | None
    #: Whether a worker holds the claim right now.
    sync_in_progress: bool
    #: A slug, never a message and never a URL.
    last_error_kind: str | None


def _view(connection: CalendarConnection, *, now: datetime) -> CalendarConnectionView:
    """Project one row onto the shape that is shown to the user.

    **`sync_in_progress` is not just "is there a claim".** A claim older than
    `CALENDAR_CLAIM_TTL` is a **lost job** — a worker died holding it — and the
    connection becomes claimable again. Showing a stale claim as "syncing" would be a
    lie the user can see: the spinner would never stop. So the claim is only "in
    progress" while it is fresh.
    """
    claimed = connection.sync_claimed_at is not None
    fresh = claimed and connection.sync_claimed_at > now - CALENDAR_CLAIM_TTL
    return CalendarConnectionView(
        id=connection.id,
        provider=connection.provider,
        status=connection.status,
        display_label=connection.display_label,
        last_synced_at=connection.last_polled_at,
        next_sync_at=connection.next_poll_at,
        sync_in_progress=fresh,
        last_error_kind=connection.last_error_kind,
    )


#: The columns a read needs. **`credential` is not among them**, on purpose.
#:
#: `EncryptedTextField.from_db_value` decrypts every row it fetches, so a read that
#: loads the whole row decrypts every address it touches — for a projection that has no
#: field for it. That is not just wasted work: a row whose credential cannot be
#: decrypted (a rotated key id, a corrupted ciphertext) would raise
#: `CredentialDecryptionError` and take down the **whole list**, and — because the same
#: lookup backs the disconnect — would leave the user unable to disconnect the broken
#: row at all. Reading only the columns the projection needs means one unreadable
#: address cannot take the user's other calendars down with it.
_READ_COLUMNS = (
    "id",
    "provider",
    "status",
    "display_label",
    "last_polled_at",
    "next_poll_at",
    "sync_claimed_at",
    "last_error_kind",
    "created_at",
)


def list_calendar_connections(*, user_id, now: datetime) -> list[CalendarConnectionView]:
    """The user's calendar connections, as they are shown to the user.

    The user's own connections only: the query is scoped by `user_id`, so another
    user's connections are not in the result set to begin with.

    **The address is not in the projection**, and neither is the fingerprint — so there
    is nothing here to leak. What the user gets is the provider, the health of the
    connection, the times and the sync state, which is everything onboarding step 1
    needs to show "we're importing your calendar" without leaving the flow (FR-3).

    **The address is not even decrypted.** See `_READ_COLUMNS`: the credential column
    is not fetched, so no read decrypts a secret it has no use for.

    The order is oldest first, so the list does not reshuffle under the user as the
    connections are added.
    """
    rows = (
        CalendarConnection.objects.using(PERSONAL)
        .filter(user_id=user_id)
        .only(*_READ_COLUMNS)
        .order_by("created_at", "id")
    )
    return [_view(row, now=now) for row in rows]


def get_calendar_connection(
    *, user_id, connection_id: UUID, now: datetime
) -> CalendarConnectionView:
    """One of the user's own connections, or `CalendarConnectionNotFoundError`.

    **Another user's connection reads as not found, not as forbidden.** A 403 would
    confirm that the record exists, so a caller could probe for other users' connection
    ids by watching for the 403. The query is scoped by `user_id`, so the endpoint never
    learns whether the row exists for somebody else — and a `disconnected` connection is
    still the user's own row, so it reads as found: the user gave it up, they did not
    delete it, and the retention sweep has not run yet.

    Like the list, this read does not decrypt the credential — see `_READ_COLUMNS`.
    """
    row = (
        CalendarConnection.objects.using(PERSONAL)
        .filter(user_id=user_id, pk=connection_id)
        .only(*_READ_COLUMNS)
        .first()
    )
    if row is None:
        raise CalendarConnectionNotFoundError(details={"connection_id": str(connection_id)})
    return _view(row, now=now)


__all__ = [
    "ALLOWED_SCHEMES",
    "CalendarConnectionView",
    "connect_calendar",
    "disconnect_calendar",
    "disconnect_calendar_for_user",
    "get_calendar_connection",
    "list_calendar_connections",
    "reconnect_calendar",
    "reconnect_calendar_for_user",
    "reveal_credential",
]
