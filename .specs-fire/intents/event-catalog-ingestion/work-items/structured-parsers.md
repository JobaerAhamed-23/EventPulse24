---
id: structured-parsers
title: Structured Source Parsers (JSON-LD, RSS, ICS)
intent: event-catalog-ingestion
complexity: medium
mode: confirm
status: pending
depends_on: [event-identity-and-tz-domain]
created: 2026-10-28
---

# Work Item: Structured Source Parsers (JSON-LD, RSS, ICS)

## Description

Turn fetched structured content into normalized candidate event records without any LLM call (FR-14 structured path, FR-56). There is one parser per acquisition method, and all three emit the same candidate shape that the pipeline resolves.

## Acceptance Criteria

- [ ] The normalized candidate type has these fields:
  - `source_event_id`, title and canonical URL
  - `start_local` with its tz exactly as written (an offset or IANA name, or none)
  - an optional end
  - venue name and city
  - status hints (cancelled, postponed, sold out)
  - an optional `series_id`
- [ ] **JSON-LD parser:** extracts every schema.org `Event` (and its subtypes) from `<script type="application/ld+json">` blocks, including `@graph` and arrays. It maps `eventStatus` (`EventCancelled`, `EventPostponed`, `EventRescheduled`) and `offers.availability` (`SoldOut`) to status hints. HTML is never rendered or executed.
- [ ] **RSS parser:** reads RSS 2.0 and Atom entries, and uses the entry guid/id as `source_event_id`. Entries with no parseable event start are skipped with a counted reason, not guessed.
- [ ] **ICS parser:** handles `VEVENT` with `UID`, `DTSTART`/`DTEND` in UTC, with `TZID` or floating, and with `STATUS:CANCELLED`. `RECURRENCE-ID` instances become distinct candidates that share a `series_id` (FR-15). RRULE expansion beyond listed instances is out of scope. The parser is reusable by the later email-ICS mailbox path.
- [ ] Every parser:
  - is a pure function from bytes plus source context to candidates plus skip reasons
  - never raises on malformed input: it returns a parse error
  - strips markup from text fields and keeps no raw HTML (AD-9)
- [ ] Recorded fixtures live in `backend/tests/fixtures/sources/`: at least one valid file and one malformed file per method. They cover:
  - an event with an explicit offset
  - an event with no offset but a venue city
  - an event with no timezone at all
  - a cancelled event
  - a recurring ICS series
- [ ] The parsing libraries are chosen, pinned and recorded in `tech-stack.md`.
- [ ] Tests cover each fixture, including malformed input, oversized fields and script/HTML injection in text fields.
- [ ] `import-linter` contracts still pass.

- [ ] ICS `source_event_id` comes from `domain.dedup.ics_item_id(uid, recurrence_start_utc)`, so recurring instances that reuse one UID stay distinct under rule (a). This was handed on from run-eventpulse24-011.
- [ ] Windows zone names from Outlook ICS (`TZID:Eastern Standard Time`) map to IANA names through an explicit, tested table before reaching `domain.timezones.resolve_tz`. Unmapped names pass through and are ignored by `canonical_zone`, so the time falls back to the venue tz.
- [ ] Parsers hand times over exactly as written: naive for a wall-clock time, or aware with the source's fixed offset (`Z` counts as UTC). They never convert to UTC themselves.

## Technical Notes

- PRD FR-14 (a JSON-LD source is parsed without an LLM call), FR-56 and FR-60 (keep tz "as written" so the domain resolver decides the tier). Spine AD-9.
- **Location:** in `apps/ingestion/` (for example `parsers/`), or in an adapter if a third-party library warrants isolation. Decide at plan time under AD-2.
- **The parser does not decide identity or timezone tier.** It hands raw facts to `event-identity-and-tz-domain`.
- **Deferred here from the `catalog-data-model` design review (add tests for each):**
  - **No native item ID:** an RSS item without a `guid`, or JSON-LD without `@id`, gets a **stable derived `source_event_id`** (for example, a hash of the canonical URL, title, and start). It is never empty, because `Event` and `ExtractedRecord` check this (design D22).
  - **All-day ICS events** (`DTSTART;VALUE=DATE`) need a documented normalization: a start at local midnight in the venue or source tz, and an end at the next local midnight.
  - **Overnight events** whose local end time is earlier than the start time ("22:00–02:00") roll the end to the next day, so `end_time_utc >= start_time_utc` holds.
  - **Raw times:** the as-written time text goes into the candidate (stored in `ExtractedRecord.payload`), and the normalized `YYYY-MM-DDTHH:MM:SS` wall-clock time goes to `start_time_local`.

## Dependencies

- event-identity-and-tz-domain
