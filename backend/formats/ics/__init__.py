"""iCalendar (RFC 5545), parsed once, for everyone who needs it.

The catalog pipeline parses ICS sources; the calendar adapter parses a user's ICS
calendar. Two implementations would be two places for the same bug, and they would
drift — so there is one, here.

**What this package produces.** `IcsEvent`s: the *format's* own facts, with no identity
policy and no UTC instant. Times are handed over **as written**: a `TZID` time is a naive
wall clock plus the zone name (Windows names mapped to IANA), a `Z` time is aware UTC, a
floating time is naive with no zone, and a `VALUE=DATE` is an all-day event.

**Why the times are not resolved here.** Resolving a time to an instant needs the
*venue's* zone, which the catalog pipeline has and a personal calendar does not. So the
resolution is the caller's: `domain.timezones.resolve_tz` does it, and both callers call
it. There is one timezone resolver in the codebase, and this package is not a second one.

**What this package does not do.** It never expands recurrence (FR-31): an `RRULE` master
is one candidate for its own `DTSTART`, and each `RECURRENCE-ID` override is another.
Identity — the `source_event_id` for the catalog, the `uid` for the calendar — is the
caller's decision too, made with `domain.dedup.ics_item_id`.
"""
