"""The real ICS calendar adapter (AD-18): one implementation for Google, Apple and Outlook.

**The fetch.** The adapter never opens a socket. It resolves `SourceFetchPort` from the
registry and calls `fetch()` — so the hardened client in `adapters/crawl/` does the SSRF
policy, the size limits, the deadline and the decompression budget, *unchanged*, and this
adapter cannot have a second, weaker copy of any of them. The one thing it asks for that
a source fetch does not is `allow_cross_host_redirect=True`: all three providers redirect
the address the user pasted to a CDN host. That relaxes the **host**, never the address
(`ports.fetch.CROSS_HOST_REDIRECT_NOTE`).

**The parsing.** `formats.ics.parser` — the same parser the catalog pipeline uses, so the
two importers cannot fork. The parser hands over times *as written*; this adapter resolves
them, because a personal calendar has no venue registry to resolve them later.

**The credential.** The secret ICS URL *is* the credential. It never reaches a log line,
an exception message, or a span (AD-13, AD-18). Every exception that leaves this module
is a `CalendarError` carrying a reason slug and never the URL, the host or the path.

**The three outcomes.** `CalendarRevokedError` (401, 403, 404, 410 — the user must
reconnect), `CalendarTransientError` (everything else that failed), and
`CalendarRefusedError` (our own refusal: a blocked scheme, a blocked address, an
oversized body). Only the first marks a connection revoked, so a provider's bad
afternoon never asks the user to reconnect a working calendar.
"""

import logging
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

from domain.dedup import ics_item_id
from domain.timezones import TzRejection, resolve_tz
from formats.ics.events import IcsEvent
from formats.ics.parser import parse_ics as parse_ics_events
from ports.calendar import (
    CalendarEntry,
    CalendarError,
    CalendarFeed,
    CalendarPort,
    CalendarRefusedError,
    CalendarResult,
    CalendarRevokedError,
    CalendarTransientError,
)
from ports.fetch import (
    FetchBlockedError,
    FetchError,
    FetchHTTPError,
    FetchLimits,
    FetchResult,
    FetchTooLargeError,
    SourceFetchPort,
)

logger = logging.getLogger(__name__)

# --- The limits (D7) -------------------------------------------------------------------------
#
# The calendar's own limits, not the source's. A calendar is a different shape from an RSS
# feed: a year of events is a few hundred kilobytes of XML, so 5 MB is still roughly ten
# years of events, and the tighter bound is worth having on a user-supplied URL.
#
# These are named constants in the adapter, not settings: they are a property of the
# adapter, not of the deployment. They are handed to the shared client as a `FetchLimits`,
# so the decompression budget, the deadline and the size cap are the *same code* as the
# source fetch's — only the numbers differ (D7).

MAX_ICS_BYTES = 5 * 1024 * 1024  # 5 MB decoded
MAX_REDIRECTS = 5
CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 15.0
TOTAL_TIMEOUT = 30.0
DNS_TIMEOUT = 3.0

#: The user agent the calendar fetch identifies itself with.
USER_AGENT = "EventPulse24-Calendar/1.0"


def calendar_limits() -> FetchLimits:
    """The calendar's own bounds, as the shared client's `FetchLimits`.

    A fresh instance per fetch: the limits are immutable, but building one here keeps the
    adapter's numbers in one place and the transport free of calendar knowledge.

    **The allowed ports are the deployment's, not the adapter's.** Every other bound
    here is a named constant — a property of what a calendar feed *is*. The port
    allowlist is different: it says which ports this deployment will open a socket to,
    and `apps.personalization.services.calendar_connections._refused_port` refuses an
    address whose port is not in it. So the two must read the **same** setting, or an
    address could be accepted at connect time and refused on every poll (or the other
    way round) — and the only evidence would be a slug in the connection's error field.

    Reading the same setting is what makes them unable to disagree.
    """
    from django.conf import settings

    return FetchLimits(
        user_agent=USER_AGENT,
        max_bytes=MAX_ICS_BYTES,
        dns_timeout=DNS_TIMEOUT,
        connect_timeout=CONNECT_TIMEOUT,
        read_timeout=READ_TIMEOUT,
        total_timeout=TOTAL_TIMEOUT,
        max_redirects=MAX_REDIRECTS,
        allowed_ports=frozenset(settings.SOURCE_FETCH["allowed_ports"]),
    )


#: The schemes a calendar address may use. `webcal://` is the iCloud spelling and is
#: normalised to `https://` — iCloud serves the feed over TLS, so normalising it to
#: `http://` would downgrade a secure fetch and produce a redirect to `https://` anyway.
ALLOWED_SCHEMES = frozenset({"https"})
WEBCAL_SCHEMES = frozenset({"webcal", "webcals"})

#: The status codes that mean "this credential is not usable any more" (FR-3).
REVOKED_STATUSES = frozenset({401, 403, 404, 410})


class IcsCalendarAdapter(CalendarPort):
    """Reads a personal ICS feed and produces `CalendarEntry`s.

    The fetch port is injected, so the adapter is testable without a socket — and so the
    adapter *mode* still means something: in `fake` mode the calendar adapter fetches from
    the fixture server, in `real` mode it fetches over the network, with the same SSRF
    protections either way.
    """

    def __init__(self, fetch_port: SourceFetchPort | None = None) -> None:
        self._fetch = fetch_port if fetch_port is not None else _registry_fetch_port()

    # --- The public operation ----------------------------------------------------------------

    def fetch_entries(self, feed: CalendarFeed) -> CalendarResult:
        """Fetch the feed and read its events.

        Raises `CalendarRevokedError`, `CalendarTransientError` or `CalendarRefusedError` —
        never a `FetchError` and never a library exception, so no traceback can carry the
        credential.
        """
        url = normalise_url(feed.url.reveal())
        response = self._fetch_calendar(url, feed)
        if response.not_modified:
            return CalendarResult(
                entries=[],
                etag=response.etag,
                last_modified=response.last_modified,
                not_modified=True,
            )
        entries, skipped = self._read_events(response.body)
        logger.info(
            "Calendar feed read",
            extra={
                "job": "calendar_fetch",
                "entry_count": len(entries),
                "skipped_count": sum(skipped.values()),
                "byte_count": len(response.body),
                "skipped": dict(skipped),
            },
        )
        return CalendarResult(
            entries=entries,
            etag=response.etag,
            last_modified=response.last_modified,
        )

    # --- The fetch ---------------------------------------------------------------------------

    def _fetch_calendar(self, url: str, feed: CalendarFeed) -> FetchResult:
        try:
            return self._fetch.fetch(
                url,
                etag=feed.etag,
                last_modified=feed.last_modified,
                allow_cross_host_redirect=True,
                limits=calendar_limits(),
                # **The URL is the credential** (AD-18), so the transport is told not to
                # write it. httpx logs the request URL at INFO, and a calendar's path
                # carries the provider's token — the end-to-end proof's credential-leak
                # sweep caught exactly that line. The adapter's own record ("Calendar
                # feed read", counts only) still says what happened.
                credential=True,
            )
        except FetchHTTPError as exc:
            raise _status_outcome(exc.status) from None
        except FetchTooLargeError as exc:
            raise CalendarRefusedError(details={"reason": exc.reason}) from None
        except FetchBlockedError as exc:
            # Our refusal, not the provider's — never a revocation.
            reason = exc.reason
            if exc.is_policy_refusal:
                raise CalendarRefusedError(details={"reason": reason}) from None
            raise CalendarTransientError(details={"reason": reason}) from None
        except FetchError as exc:
            raise CalendarTransientError(details={"reason": exc.reason}) from None
        except Exception as exc:  # a library exception must never escape with the URL in it
            raise CalendarTransientError(details={"reason": type(exc).__name__.lower()}) from None

    # --- The events --------------------------------------------------------------------------

    def _read_events(self, body: bytes) -> tuple[list[CalendarEntry], dict[str, int]]:
        """The entries in the feed, and the counts of the ones that could not be read."""
        parsed = parse_ics_events(body)
        if parsed.error is not None:
            # A malformed file may be a truncated download; the next poll may succeed.
            raise CalendarTransientError(details={"reason": parsed.error})

        entries: list[CalendarEntry] = []
        skipped: dict[str, int] = {}

        def skip(reason: str) -> None:
            skipped[reason] = skipped.get(reason, 0) + 1

        # An override replaces the master's own instance, whichever comes first in the
        # file. The two share an id — that is the point of the id — so the importer must
        # never see both, or the second would violate the unique constraint and the user
        # would lose an event.
        by_uid: dict[str, CalendarEntry] = {}
        overridden: set[str] = set()

        for event in parsed.events:
            entry = self._entry(event)
            if entry is None:
                skip(_skip_reason(event))
                continue
            if event.recurrence_id is not None:
                # The override wins over whatever shared its id.
                by_uid[entry.uid] = entry
                overridden.add(entry.uid)
                continue
            if entry.uid in overridden:
                continue  # the override already replaced this instance
            by_uid.setdefault(entry.uid, entry)

        entries = list(by_uid.values())

        for reason, count in parsed.skipped.items():
            skipped[reason] = skipped.get(reason, 0) + count
        return entries, skipped

    def _entry(self, event: IcsEvent) -> CalendarEntry | None:
        """One event as a `CalendarEntry`, or None when it cannot be placed.

        The times are resolved *here*, by the adapter, with the event's own zone: a
        personal calendar has no venue registry, so the pipeline's later resolution — which
        needs the venue's zone — has no place to happen.
        """
        if not event.uid:
            return None  # no id: nothing stable to import it under
        if event.start is None:
            return None

        if event.all_day and event.start_zone is None:
            # An all-day event names a *day*, not a time of day, and a day with no zone
            # has no local midnight to read it in. It is read at UTC midnight — the
            # convention every provider uses for an unzoned all-day event.
            return self._all_day_entry(event)
        if event.start.tzinfo is None and event.start_zone is None:
            return None  # a floating time denotes no moment

        resolution = resolve_tz(event.start, source_zone=event.start_zone, end=event.end)
        if isinstance(resolution, TzRejection):
            return None

        zone = resolution.zone
        starts_at = resolution.start_utc
        ends_at = resolution.end_utc or starts_at
        if ends_at < starts_at:
            return None

        return CalendarEntry(
            uid=self._uid(event, starts_at),
            title=event.title,
            starts_at=starts_at,
            ends_at=ends_at,
            tz=zone,
        )

    def _all_day_entry(self, event: IcsEvent) -> CalendarEntry | None:
        """An unzoned all-day event, read at UTC midnight.

        The parser hands the all-day span over as naive midnights, so reading it at UTC
        midnight is the same thing the parser's `start_instant` already says — the end
        simply has no instant of its own.
        """
        starts_at = event.start_instant
        if starts_at is None:
            return None
        ends_at = event.end.replace(tzinfo=UTC) if event.end is not None else starts_at
        if ends_at < starts_at:
            return None
        return CalendarEntry(
            uid=self._uid(event, starts_at),
            title=event.title,
            starts_at=starts_at,
            ends_at=ends_at,
            tz="UTC",
        )

    def _uid(self, event: IcsEvent, starts_at: datetime) -> str:
        """The entry's id, by the same rule the catalog uses.

        A plain event keeps its bare UID. A recurring instance — an `RRULE` master or a
        `RECURRENCE-ID` override — carries the instance instant, so the override of a
        master's *own* instance gets the **same** id as that master: the two are one
        event, and the override replaces it. An override of a *later* instance gets its
        own id, because it is a different event. `domain.dedup.ics_item_id` is that
        rule, so both importers agree.
        """
        if event.recurrence_id is not None:
            return ics_item_id(event.uid, _as_utc(event.recurrence_id))
        if event.has_rrule:
            return ics_item_id(event.uid, starts_at)
        return event.uid


def _as_utc(value: datetime) -> datetime:
    """An aware datetime as UTC; a naive one read as UTC (for the id only)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _skip_reason(event: IcsEvent) -> str:
    """Why one event was not read — a slug, never a value."""
    if not event.uid:
        return "no_uid"
    if event.start is None:
        return "no_event_start"
    if event.start.tzinfo is None and event.start_zone is None:
        return "floating_time"
    return "unplaceable_time"


def _status_outcome(status: int) -> CalendarError:
    """The error for an HTTP status.

    Exactly four codes mean the credential is no longer usable (FR-3). Everything else —
    including a `429` and any other `4xx` — is transient: a `400` caused by our own
    request is our fault, and asking the user to reconnect for it would be wrong.
    """
    if status in REVOKED_STATUSES:
        return CalendarRevokedError(details={"status": status})
    return CalendarTransientError(details={"status": status})


def normalise_url(url: str) -> str:
    """The URL to fetch: `webcal://` becomes `https://`, and nothing else is allowed.

    `http://` is **refused**, not upgraded: it would carry the credential in cleartext on
    the wire on every poll, and silently upgrading it would change the host the user
    typed. The refusal names the reason, and the user can paste the `https://` form.

    The *stored* credential keeps the form the user typed — normalising at write time
    would change what the user recognises and what the fingerprint was computed over. Only
    the fetched URL is normalised.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme in WEBCAL_SCHEMES:
        return urlunsplit(("https", parts.netloc, parts.path, parts.query, parts.fragment))
    if scheme not in ALLOWED_SCHEMES:
        raise CalendarRefusedError(details={"reason": "scheme"})
    return url.strip()


def _registry_fetch_port() -> SourceFetchPort:
    """The configured fetch port.

    Resolved through the registry rather than constructed here, so the adapter *mode*
    still decides where the bytes come from.
    """
    from ports.registry import get_fetch_port

    return get_fetch_port()
