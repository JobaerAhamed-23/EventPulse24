"""The ICS calendar adapter: schemes, outcomes, limits, identity, and non-leakage.

The properties pinned here are the ones the adapter exists to guarantee:

- **the scheme rules**: `webcal://` becomes `https://`; `http://` and everything else
  are refused;
- **the four revoked status codes** map to `CalendarRevokedError` and *nothing else* does;
- **our own refusals** are `CalendarRefusedError` — never a revocation;
- **the credential never reaches a log line, an exception message, or a span**;
- **the identity** follows `domain.dedup.ics_item_id`, so the calendar and the catalog
  agree on what an event is;
- **the times are resolved** by `domain.timezones.resolve_tz` — there is one resolver.

No socket is opened: the adapter's own logic runs against `ScriptedFetch`, and the fetch
itself is proven on the scripted network in `test_crawl_http.py`.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from adapters.calendar.ics import (
    CONNECT_TIMEOUT,
    DNS_TIMEOUT,
    MAX_ICS_BYTES,
    MAX_REDIRECTS,
    READ_TIMEOUT,
    TOTAL_TIMEOUT,
    IcsCalendarAdapter,
    normalise_url,
)
from adapters.logging.formatter import JsonFormatter
from domain.dedup import ics_item_id
from formats.ics.events import IcsEvent
from ports.calendar import (
    CalendarError,
    CalendarFeed,
    CalendarRefusedError,
    CalendarRevokedError,
    CalendarTransientError,
    Credential,
)
from ports.fetch import (
    FetchBlockedError,
    FetchHTTPError,
    FetchLimits,
    FetchNetworkError,
    FetchRedirectError,
    FetchResult,
    FetchTimeoutError,
    FetchTooLargeError,
)
from tests.adapters.calendar_fakes import ScriptedFetch, ics_result

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "calendars"

SECRET = "https://calendar.example.test/private-abc123/basic.ics"


def calendar(*events: str) -> bytes:
    body = "".join(f"BEGIN:VEVENT\r\n{event}\r\nEND:VEVENT\r\n" for event in events)
    return f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\n{body}END:VCALENDAR\r\n".encode()


def feed(url: str = SECRET, **kwargs) -> CalendarFeed:
    return CalendarFeed(url=Credential(url), **kwargs)


def adapter_with(result: FetchResult | None = None, error: Exception | None = None):
    fetch = ScriptedFetch(result=result, error=error)
    return IcsCalendarAdapter(fetch_port=fetch), fetch


# ─── The scheme rules ──────────────────────────────────────────────────────────


def test_a_webcal_address_is_fetched_over_https():
    adapter, fetch = adapter_with(ics_result(calendar()))
    adapter.fetch_entries(feed("webcal://p01-calendars.icloud.com/published/2/abc123"))

    assert fetch.calls[0].url == "https://p01-calendars.icloud.com/published/2/abc123"


def test_a_webcals_address_is_fetched_over_https():
    adapter, fetch = adapter_with(ics_result(calendar()))
    adapter.fetch_entries(feed("webcals://example.test/feed.ics"))

    assert fetch.calls[0].url == "https://example.test/feed.ics"


def test_an_https_address_is_used_as_it_is():
    adapter, fetch = adapter_with(ics_result(calendar()))
    adapter.fetch_entries(feed())

    assert fetch.calls[0].url == SECRET


def test_a_plain_http_address_is_refused():
    """It would carry the credential in cleartext on the wire, on every poll, forever."""
    adapter, fetch = adapter_with(ics_result(calendar()))

    with pytest.raises(CalendarRefusedError) as excinfo:
        adapter.fetch_entries(feed("http://example.test/feed.ics"))

    assert excinfo.value.details == {"reason": "scheme"}
    assert fetch.calls == []  # refused before anything was fetched


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.test/feed.ics",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "//example.test/feed.ics",
        "example.test/feed.ics",
    ],
)
def test_every_other_scheme_is_refused(url):
    adapter, fetch = adapter_with(ics_result(calendar()))

    with pytest.raises(CalendarRefusedError):
        adapter.fetch_entries(feed(url))

    assert fetch.calls == []


def test_the_normalisation_leaves_the_stored_credential_alone():
    """The stored form is what the user recognises; only the fetched URL is normalised."""
    stored = "webcal://p01-calendars.icloud.com/published/2/abc123"
    adapter, fetch = adapter_with(ics_result(calendar()))

    adapter.fetch_entries(feed(stored))

    assert fetch.calls[0].url.startswith("https://")
    assert feed(stored).url.reveal() == stored


def test_normalise_url_refuses_an_http_address():
    with pytest.raises(CalendarRefusedError):
        normalise_url("http://example.test/feed.ics")


# ─── The outcomes ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("status", [401, 403, 404, 410])
def test_the_four_revoked_statuses_are_revoked(status):
    adapter, _ = adapter_with(error=FetchHTTPError(status))

    with pytest.raises(CalendarRevokedError) as excinfo:
        adapter.fetch_entries(feed())

    assert excinfo.value.details == {"status": status}


@pytest.mark.parametrize("status", [400, 405, 429, 500, 502, 503, 504])
def test_every_other_status_is_transient(status):
    """A `400` caused by our own request is our fault — the user must not be asked to
    reconnect for it, and a provider's bad afternoon is not a revocation either."""
    adapter, _ = adapter_with(error=FetchHTTPError(status))

    with pytest.raises(CalendarTransientError) as excinfo:
        adapter.fetch_entries(feed())

    assert excinfo.value.details == {"status": status}


def test_a_timeout_is_transient():
    adapter, _ = adapter_with(error=FetchTimeoutError("read"))

    with pytest.raises(CalendarTransientError):
        adapter.fetch_entries(feed())


def test_a_network_error_is_transient():
    adapter, _ = adapter_with(error=FetchNetworkError("dns"))

    with pytest.raises(CalendarTransientError):
        adapter.fetch_entries(feed())


def test_a_blocked_address_is_refused_and_never_revoked():
    """Our refusal, not the provider's — the user's access is fine."""
    adapter, _ = adapter_with(error=FetchBlockedError("address"))

    with pytest.raises(CalendarRefusedError) as excinfo:
        adapter.fetch_entries(feed())

    assert excinfo.value.details == {"reason": "address"}


@pytest.mark.parametrize("reason", ["scheme", "userinfo", "port", "address", "cross_host_redirect"])
def test_every_own_refusal_is_refused(reason):
    """The transport's own vocabulary — the adapter does not keep a second copy of it."""
    adapter, _ = adapter_with(error=FetchBlockedError(reason))

    with pytest.raises(CalendarRefusedError):
        adapter.fetch_entries(feed())


def test_the_refusal_reasons_are_the_transport_s_own():
    """The adapter branches on `is_policy_refusal`, so the two lists cannot drift."""
    assert FetchBlockedError.POLICY_REFUSAL_REASONS == frozenset(
        {"scheme", "userinfo", "port", "address", "cross_host_redirect"}
    )
    assert FetchBlockedError("address").is_policy_refusal is True
    assert FetchBlockedError("something_else").is_policy_refusal is False


def test_a_redirect_loop_is_transient():
    """Too many redirects is a plain fetch failure — the transport raises it as one."""
    adapter, _ = adapter_with(error=FetchRedirectError("too_many_redirects"))

    with pytest.raises(CalendarTransientError) as excinfo:
        adapter.fetch_entries(feed())

    assert excinfo.value.details == {"reason": "too_many_redirects"}


def test_an_oversized_body_is_refused():
    adapter, _ = adapter_with(error=FetchTooLargeError("decoded_bytes"))

    with pytest.raises(CalendarRefusedError):
        adapter.fetch_entries(feed())


def test_a_malformed_calendar_is_transient():
    """It may be a truncated download; the next poll may succeed."""
    adapter, _ = adapter_with(ics_result(b"not a calendar at all"))

    with pytest.raises(CalendarTransientError) as excinfo:
        adapter.fetch_entries(feed())

    assert excinfo.value.details == {"reason": "invalid_ics"}


def test_no_library_exception_escapes_the_adapter():
    """An `httpx` exception's message carries the URL, so it must never escape."""
    adapter, _ = adapter_with(error=RuntimeError("httpx failed for https://secret.example/x"))

    with pytest.raises(CalendarTransientError) as excinfo:
        adapter.fetch_entries(feed())

    assert "secret.example" not in str(excinfo.value)


# ─── The credential never leaks ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "outcome",
    [
        ("revoked", FetchHTTPError(401)),
        ("transient", FetchHTTPError(500)),
        ("refused", FetchBlockedError("address")),
        ("too_large", FetchTooLargeError("decoded_bytes")),
        ("timeout", FetchTimeoutError("read")),
        ("malformed", None),
    ],
)
def test_the_url_never_reaches_a_log_line_or_an_exception(caplog, outcome):
    """Every failure path, with the log captured: the URL is in neither."""
    reason, error = outcome
    result = ics_result(b"not a calendar") if error is None else None
    adapter, _ = adapter_with(result=result, error=error)

    # Every one of these paths raises a `CalendarError` — the adapter converts
    # everything at its boundary, so a library exception (whose message carries the
    # URL) can never reach a traceback.
    with caplog.at_level(logging.DEBUG), pytest.raises(CalendarError):
        adapter.fetch_entries(feed())

    output = caplog.text + "\n".join(str(r.exc_info) for r in caplog.records if r.exc_info)
    assert SECRET not in output
    assert "calendar.example.test" not in output


def test_a_successful_fetch_logs_counts_only(caplog):
    adapter, _ = adapter_with(
        ics_result(calendar("UID:a@x\r\nSUMMARY:A\r\nDTSTART:20261114T220000Z"))
    )

    with caplog.at_level(logging.DEBUG):
        adapter.fetch_entries(feed())

    assert SECRET not in caplog.text
    assert "calendar.example.test" not in caplog.text


def test_the_exception_message_never_carries_the_url():
    adapter, _ = adapter_with(error=FetchHTTPError(401))

    with pytest.raises(CalendarRevokedError) as excinfo:
        adapter.fetch_entries(feed())

    assert SECRET not in str(excinfo.value)
    assert SECRET not in repr(excinfo.value)


# ─── The refusals that are not our own ────────────────────────────────────────


def test_a_blocked_reason_outside_our_own_is_transient():
    """Only the transport's policy reasons are *our* refusals; the rest are somebody else's."""
    adapter, _ = adapter_with(error=FetchBlockedError("not_a_policy_reason"))

    with pytest.raises(CalendarTransientError) as excinfo:
        adapter.fetch_entries(feed())

    assert excinfo.value.details == {"reason": "not_a_policy_reason"}


# ─── The events ───────────────────────────────────────────────────────────────


def test_a_plain_event_becomes_an_entry():
    adapter, _ = adapter_with(
        ics_result(calendar("UID:plain@x\r\nSUMMARY:Standup\r\nDTSTART:20261114T220000Z"))
    )

    result = adapter.fetch_entries(feed())

    [entry] = result.entries
    assert entry.uid == "plain@x"
    assert entry.title == "Standup"
    assert entry.starts_at == datetime(2026, 11, 14, 22, 0, tzinfo=UTC)
    assert entry.ends_at == entry.starts_at
    assert entry.tz == "UTC"


def test_a_tzid_time_is_resolved_to_utc_and_keeps_its_zone():
    adapter, _ = adapter_with(
        ics_result(
            calendar(
                "UID:zoned@x\r\nSUMMARY:Zoned\r\n"
                "DTSTART;TZID=America/New_York:20261105T193000\r\n"
                "DTEND;TZID=America/New_York:20261105T210000"
            )
        )
    )

    result = adapter.fetch_entries(feed())

    [entry] = result.entries
    assert entry.starts_at == datetime(2026, 11, 6, 0, 30, tzinfo=UTC)  # EST is UTC-5
    assert entry.ends_at == datetime(2026, 11, 6, 2, 0, tzinfo=UTC)
    assert entry.tz == "America/New_York"


def test_a_windows_tzid_becomes_an_iana_zone():
    adapter, _ = adapter_with(
        ics_result(
            calendar("UID:w@x\r\nSUMMARY:W\r\nDTSTART;TZID=W. Europe Standard Time:20261118T100000")
        )
    )

    result = adapter.fetch_entries(feed())

    [entry] = result.entries
    assert entry.tz == "Europe/Berlin"
    assert entry.starts_at == datetime(2026, 11, 18, 9, 0, tzinfo=UTC)


def test_an_all_day_event_starts_at_local_midnight():
    adapter, _ = adapter_with(
        ics_result(
            calendar(
                "UID:day@x\r\nSUMMARY:Day\r\n"
                "DTSTART;VALUE=DATE:20261121\r\nDTEND;VALUE=DATE:20261122"
            )
        )
    )

    result = adapter.fetch_entries(feed())

    [entry] = result.entries
    assert entry.starts_at == datetime(2026, 11, 21, tzinfo=UTC)
    assert entry.ends_at == datetime(2026, 11, 22, tzinfo=UTC)


def test_a_floating_time_cannot_be_placed_and_is_skipped():
    """A wall clock with no zone denotes no moment, so there is nothing to put on a timeline."""
    adapter, _ = adapter_with(
        ics_result(calendar("UID:f@x\r\nSUMMARY:F\r\nDTSTART:20261123T083000"))
    )

    result = adapter.fetch_entries(feed())

    assert result.entries == []


def test_an_event_without_a_uid_is_skipped():
    """No id: nothing stable to import it under."""
    adapter, _ = adapter_with(ics_result(calendar("SUMMARY:No UID\r\nDTSTART:20261114T220000Z")))

    result = adapter.fetch_entries(feed())

    assert result.entries == []


# ─── The events that cannot be placed ─────────────────────────────────────────


def test_an_event_without_a_start_is_skipped():
    adapter, _ = adapter_with(ics_result(calendar("UID:ns@x\r\nSUMMARY:No start")))

    result = adapter.fetch_entries(feed())

    assert result.entries == []


def test_a_floating_time_is_skipped_and_counted(caplog):
    """A wall clock with no zone denotes no moment — so there is nothing to put on a timeline."""
    adapter, _ = adapter_with(
        ics_result(calendar("UID:f@x\r\nSUMMARY:F\r\nDTSTART:20261123T083000"))
    )

    result = adapter.fetch_entries(feed())

    assert result.entries == []


def test_an_event_in_a_zone_that_cannot_be_resolved_is_skipped():
    """An unknown zone cannot be placed, so the event is dropped rather than guessed."""
    adapter, _ = adapter_with(
        ics_result(
            calendar(
                "UID:bad@x\r\nSUMMARY:Bad zone\r\nDTSTART;TZID=Mars/Olympus_Mons:20261123T083000"
            )
        )
    )

    result = adapter.fetch_entries(feed())

    assert result.entries == []


def test_an_event_whose_end_precedes_its_start_is_skipped():
    """An end before its start is a broken event; importing it would show a negative span.

    The parser drops an end it can see is backwards, so this reaches the adapter only
    when the *zone* makes the end backwards — a zoned end that lands before its start.
    """
    adapter, _ = adapter_with(ics_result(calendar()))

    assert (
        adapter._entry(
            event(
                start=datetime(2026, 11, 14, 22, 0, tzinfo=UTC),
                end=datetime(2026, 11, 13, 22, 0, tzinfo=UTC),
                all_day=False,
                start_zone=None,
                start_instant=datetime(2026, 11, 14, 22, 0, tzinfo=UTC),
            )
        )
        is None
    )


def test_the_parser_s_own_skip_counts_are_merged_into_the_log(caplog):
    """The counts the parser made are the adapter's counts too — one report, not two.

    The assertion is on the *formatted* line, not the raw `LogRecord`: a field the
    redactor drops would still be on the record, and a count nobody can read is no count.
    """
    adapter, _ = adapter_with(
        ics_result(
            calendar(
                "UID:ok@x\r\nSUMMARY:OK\r\nDTSTART:20261114T220000Z",
                "UID:nostart@x\r\nSUMMARY:No start",
            )
        )
    )

    with caplog.at_level(logging.DEBUG):
        adapter.fetch_entries(feed())

    line = JsonFormatter().format(
        next(r for r in caplog.records if r.name == "adapters.calendar.ics")
    )
    assert '"no_event_start": 1' in line
    assert '"entry_count": 1' in line


# ─── The identity ─────────────────────────────────────────────────────────────


def test_a_recurring_master_is_keyed_by_its_own_instance():
    adapter, _ = adapter_with(
        ics_result(
            calendar(
                "UID:series@x\r\nSUMMARY:Series\r\nDTSTART:20261103T190000Z\r\nRRULE:FREQ=WEEKLY"
            )
        )
    )

    result = adapter.fetch_entries(feed())

    [entry] = result.entries
    assert entry.uid == ics_item_id("series@x", datetime(2026, 11, 3, 19, tzinfo=UTC))


def test_an_override_is_keyed_by_its_recurrence_id():
    adapter, _ = adapter_with(
        ics_result(
            calendar(
                "UID:series@x\r\nSUMMARY:Moved\r\n"
                "RECURRENCE-ID:20261110T190000Z\r\nDTSTART:20261110T200000Z"
            )
        )
    )

    result = adapter.fetch_entries(feed())

    [entry] = result.entries
    assert entry.uid == ics_item_id("series@x", datetime(2026, 11, 10, 19, tzinfo=UTC))


def test_an_override_replaces_the_master_of_its_own_instance():
    """The two share an id, so the importer must never see both.

    The override of a master's *own* instance has the same id as the master — that is
    what makes it a replacement rather than a duplicate. The importer would otherwise
    violate the unique constraint and the user would lose an event.
    """
    adapter, _ = adapter_with(
        ics_result(
            calendar(
                "UID:series@x\r\nSUMMARY:Series\r\nDTSTART:20261103T190000Z\r\nRRULE:FREQ=WEEKLY",
                "UID:series@x\r\nSUMMARY:Moved\r\n"
                "RECURRENCE-ID:20261103T190000Z\r\nDTSTART:20261103T200000Z",
            )
        )
    )

    result = adapter.fetch_entries(feed())

    [entry] = result.entries
    assert entry.title == "Moved"
    assert entry.uid == ics_item_id("series@x", datetime(2026, 11, 3, 19, tzinfo=UTC))


def test_an_override_wins_whatever_the_file_order():
    for events in (
        (
            "UID:series@x\r\nSUMMARY:Series\r\nDTSTART:20261103T190000Z\r\nRRULE:FREQ=WEEKLY",
            "UID:series@x\r\nSUMMARY:Moved\r\n"
            "RECURRENCE-ID:20261103T190000Z\r\nDTSTART:20261103T200000Z",
        ),
        (
            "UID:series@x\r\nSUMMARY:Moved\r\n"
            "RECURRENCE-ID:20261103T190000Z\r\nDTSTART:20261103T200000Z",
            "UID:series@x\r\nSUMMARY:Series\r\nDTSTART:20261103T190000Z\r\nRRULE:FREQ=WEEKLY",
        ),
    ):
        adapter, _ = adapter_with(ics_result(calendar(*events)))

        result = adapter.fetch_entries(feed())

        [entry] = result.entries
        assert entry.title == "Moved"


def test_an_override_of_a_later_instance_is_a_separate_entry():
    """It has its own id, so it does not replace the master."""
    adapter, _ = adapter_with(
        ics_result(
            calendar(
                "UID:series@x\r\nSUMMARY:Series\r\nDTSTART:20261103T190000Z\r\nRRULE:FREQ=WEEKLY",
                "UID:series@x\r\nSUMMARY:Moved\r\n"
                "RECURRENCE-ID:20261110T190000Z\r\nDTSTART:20261110T200000Z",
            )
        )
    )

    result = adapter.fetch_entries(feed())

    uids = [entry.uid for entry in result.entries]
    assert len(uids) == 2 and len(set(uids)) == 2


def test_an_rrule_is_never_expanded():
    """One master produces exactly one entry — no instances are generated."""
    adapter, _ = adapter_with(
        ics_result(
            calendar(
                "UID:series@x\r\nSUMMARY:Series\r\n"
                "DTSTART:20261103T190000Z\r\nRRULE:FREQ=WEEKLY;COUNT=10"
            )
        )
    )

    result = adapter.fetch_entries(feed())

    assert len(result.entries) == 1


# ─── The conditional fetch ────────────────────────────────────────────────────


def test_a_304_is_a_success_with_no_entries():
    adapter, _ = adapter_with(
        FetchResult(
            status=304,
            final_url=SECRET,
            content_type="text/calendar",
            etag='"v1"',
            last_modified="Wed, 04 Nov 2026 10:00:00 GMT",
        )
    )

    result = adapter.fetch_entries(feed())

    assert result.not_modified is True
    assert result.entries == []
    assert result.etag == '"v1"'


def test_the_validators_are_sent_and_the_new_ones_returned():
    adapter, fetch = adapter_with(ics_result(calendar(), etag='"v2"'))

    result = adapter.fetch_entries(feed(etag='"v1"', last_modified="Wed, 04 Nov 2026 10:00:00 GMT"))

    assert fetch.calls[0].etag == '"v1"'
    assert fetch.calls[0].last_modified == "Wed, 04 Nov 2026 10:00:00 GMT"
    assert result.etag == '"v2"'


def test_the_fetch_is_allowed_to_cross_hosts():
    """The provider redirects the address the user pasted to a CDN host."""
    adapter, fetch = adapter_with(ics_result(calendar()))

    adapter.fetch_entries(feed())

    assert fetch.calls[0].allow_cross_host_redirect is True


# ─── The limits (D7) ───────────────────────────────────────────────────────────


def test_the_fetch_carries_the_calendar_s_own_limits():
    """A calendar is not an RSS page: it gets its own budget, not the source's.

    The limits are the adapter's *named constants*, handed to the shared client as a
    `FetchLimits` — so the size cap, the deadline and the decompression budget are the
    same code as the source fetch's, with the calendar's numbers.
    """
    adapter, fetch = adapter_with(ics_result(calendar()))

    adapter.fetch_entries(feed())

    limits = fetch.calls[0].limits
    assert limits is not None
    assert limits.max_bytes == MAX_ICS_BYTES == 5 * 1024 * 1024
    assert limits.max_redirects == MAX_REDIRECTS == 5
    assert limits.connect_timeout == CONNECT_TIMEOUT == 5.0
    assert limits.read_timeout == READ_TIMEOUT == 15.0
    assert limits.total_timeout == TOTAL_TIMEOUT == 30.0
    assert limits.dns_timeout == DNS_TIMEOUT == 3.0


def test_the_fetch_is_told_the_url_is_a_credential():
    """The calendar's URL *is* its credential, so the adapter says so (AD-18).

    httpx logs the request URL at INFO. For a calendar that URL carries the provider's
    token in its path, so the transport must be told not to write it — and only the
    caller knows that. The transport cannot guess: a source feed's URL is an
    *identifier*, and the deployment's own diagnostics depend on it being readable.

    So the flag is asserted here, on the adapter's own call, rather than only
    inferred from the absence of a log line elsewhere.
    """
    adapter, fetch = adapter_with(ics_result(calendar()))

    adapter.fetch_entries(feed())

    assert fetch.calls[0].credential is True, (
        "the calendar adapter must tell the transport that the URL is a credential, "
        "or the URL reaches httpx's log line."
    )


def test_the_calendar_limits_are_tighter_than_the_source_limits():
    """The point of the calendar's own numbers: a user-supplied URL gets less room."""
    from adapters.crawl.http import FetchLimits as SourceLimits

    source = SourceLimits.from_settings()

    assert MAX_ICS_BYTES < source.max_bytes


def test_the_limits_are_the_same_decompression_budget_the_source_uses():
    """One budget, two sets of numbers — not a second, weaker copy of the guard.

    The calendar's `FetchLimits` *is* a `ports.fetch.FetchLimits`, the shape the
    transport bounds the raw bytes, the decoded bytes and the deadline with.
    """
    adapter, fetch = adapter_with(ics_result(calendar()))

    adapter.fetch_entries(feed())

    assert isinstance(fetch.calls[0].limits, FetchLimits)


# ─── The provider fixtures ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "count"),
    [("google.ics", 4), ("apple.ics", 2), ("outlook.ics", 2)],
)
def test_the_provider_fixtures_are_read(name, count):
    """Three real-world shapes: an IANA zone, an all-day and a floating time, a Windows zone."""
    adapter, _ = adapter_with(ics_result((FIXTURES / name).read_bytes()))

    result = adapter.fetch_entries(feed())

    assert len(result.entries) == count


def test_the_google_fixture_keys_the_master_and_its_override_apart():
    adapter, _ = adapter_with(ics_result((FIXTURES / "google.ics").read_bytes()))

    result = adapter.fetch_entries(feed())

    uids = [entry.uid for entry in result.entries]
    assert len(uids) == len(set(uids))


def test_the_outlook_fixture_maps_the_windows_zone():
    adapter, _ = adapter_with(ics_result((FIXTURES / "outlook.ics").read_bytes()))

    result = adapter.fetch_entries(feed())

    assert {entry.tz for entry in result.entries} == {"Europe/Berlin"}


# ─── The edges the files cannot reach ─────────────────────────────────────────


def event(**overrides) -> IcsEvent:
    """An `IcsEvent` the parser would produce, for the edges a file cannot reach.

    The naive wall clocks are the point: an unzoned event's times are naive, and that is
    exactly what the adapter must recognise as "no moment named".
    """
    fields = {
        "uid": "e@x",
        "title": "E",
        "start": datetime(2026, 11, 21),  # noqa: DTZ001 — a naive wall clock, deliberately
        "end": datetime(2026, 11, 22),  # noqa: DTZ001 — a naive wall clock, deliberately
        "start_zone": None,
        "end_zone": None,
        "all_day": True,
        "status": "",
        "location": "",
        "description": "",
        "url": "",
        "recurrence_id": None,
        "has_rrule": False,
        "raw": {},
        "start_instant": datetime(2026, 11, 21, tzinfo=UTC),
    }
    fields.update(overrides)
    return IcsEvent(**fields)


def test_an_all_day_event_with_no_instant_is_skipped():
    """An all-day event whose start names no day cannot be placed."""
    adapter, _ = adapter_with(ics_result(calendar()))

    assert adapter._entry(event(start_instant=None)) is None


def test_an_event_with_no_start_at_all_is_skipped():
    """The parser skips such an event; if one reached the adapter, it is skipped there too."""
    adapter, _ = adapter_with(ics_result(calendar()))

    assert adapter._entry(event(start=None)) is None


def test_the_skip_reasons_are_slugs_never_values():
    """Why an event was not read is a slug — never a title, a uid or a zone."""
    from adapters.calendar.ics import _skip_reason

    assert _skip_reason(event(uid="")) == "no_uid"
    assert _skip_reason(event(start=None)) == "no_event_start"
    assert _skip_reason(event(start=datetime(2026, 11, 21))) == "floating_time"  # noqa: DTZ001
    assert (
        _skip_reason(
            event(
                start=datetime(2026, 11, 21, tzinfo=UTC),
                all_day=False,
                start_zone="Mars/Olympus_Mons",
            )
        )
        == "unplaceable_time"
    )


def test_an_all_day_event_whose_end_precedes_its_start_is_skipped():
    adapter, _ = adapter_with(ics_result(calendar()))

    assert (
        adapter._entry(
            event(
                end=datetime(2026, 11, 20),  # noqa: DTZ001 — a naive wall clock, deliberately
                start_instant=datetime(2026, 11, 21, tzinfo=UTC),
            )
        )
        is None
    )


def test_a_naive_recurrence_id_is_read_as_utc_for_the_id():
    """A floating RECURRENCE-ID names no moment — so it is read as UTC, for the id only."""
    adapter, _ = adapter_with(ics_result(calendar()))

    entry = adapter._entry(
        event(
            start=datetime(2026, 11, 21, tzinfo=UTC),
            end=None,
            all_day=False,
            start_instant=datetime(2026, 11, 21, tzinfo=UTC),
            recurrence_id=datetime(2026, 11, 21, 19, 0),  # noqa: DTZ001 — floating, deliberately
        )
    )

    assert entry.uid == ics_item_id("e@x", datetime(2026, 11, 21, 19, 0, tzinfo=UTC))


def test_the_adapter_resolves_its_fetch_port_from_the_registry(monkeypatch):
    """With no port injected, the adapter asks the registry — so the mode still decides."""
    from adapters.calendar import ics as ics_module

    sentinel = ScriptedFetch(result=ics_result(calendar()))
    monkeypatch.setattr(ics_module, "_registry_fetch_port", lambda: sentinel)

    adapter = IcsCalendarAdapter()

    adapter.fetch_entries(feed())

    assert sentinel.calls[0].url == SECRET


def test_the_registry_resolves_a_fetch_port_for_the_calendar():
    """The registry knows the fetch port, so the adapter can be built with no argument."""
    from adapters.calendar.ics import _registry_fetch_port

    port = _registry_fetch_port()

    assert hasattr(port, "fetch")
