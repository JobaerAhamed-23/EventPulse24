---
id: schema-org-jsonld
title: Structured data a crawler believes — the Schema.org Event projection
intent: public-pages-and-seo
complexity: medium
mode: confirm
status: completed
depends_on:
  - public-event-read-by-slug
created: 2026-11-01
run_id: run-eventpulse24-024
completed_at: 2026-11-02T06:12:08.387Z
---

# Work Item: Structured data a crawler believes — the Schema.org Event projection

## Description

The JSON-LD block the public page embeds. AD-12 is explicit: *"Schema.org `Event` JSON-LD is emitted from the same data the page renders."* Two sources of truth for one page is how a page ends up claiming tickets are available under a heading that says cancelled — and a mismatch between visible content and structured data is also precisely what earns a structured-data penalty.

Mapping `Event.status` and `is_sold_out` onto Schema.org's vocabulary is **logic**, and this project puts logic on the server where it is tested once. The page receives a finished object and embeds it verbatim — the same rule `timeline-week-api` set down: *"The screen should draw what it is given."*

## Acceptance Criteria

- [ ] A **pure projection** from the public read's payload to a Schema.org `Event` object. No database access, no second query — it takes the DTO the page already has.
- [ ] `eventStatus` is derived, never hardcoded: `scheduled` → `EventScheduled`, `postponed` → `EventPostponed`, `cancelled` → `EventCancelled`. A `superseded` event never reaches this projection (it 404s upstream).
- [ ] `offers.availability` reflects `is_sold_out` → `SoldOut`, otherwise `InStock`. An event with no known price emits **no `offers` block at all** rather than a fabricated zero — an invented price is worse than a missing one.
- [ ] `startDate` / `endDate` are **timezone-correct**: emitted with the offset implied by `start_time_tz`, per ARCHITECTURE-SPINE.md:565 ("SEO public URLs (FR-26) include the timezone in Schema.org Event JSON-LD"). Computed through `domain/timezones.py`, not by string-formatting UTC.
- [ ] `location` is a `Place` with the venue name and whatever address parts exist. A **venue-less event omits `location`** rather than emitting an empty `Place`.
- [ ] `eventAttendanceMode` is stated where it is known and omitted where it is not — never defaulted to `Offline` for an event the registry says nothing about.
- [ ] No field is invented. Per **ASSUMPTION-9**, the page reflects the registry's source of truth only; a missing value is omitted, never filled with a plausible one.
- [ ] Tests: each of the three statuses, sold-out and not, an event in a non-UTC zone and one across a DST boundary, a venue-less event, an event with no description, and a validation test asserting the emitted object parses as valid Schema.org `Event`.

## Technical Notes

`public-event-page-desktop.html` carries a real worked example of the target shape in its `<script type="application/ld+json">` block — use it as the reference for field selection, not as a literal template (its values are mock data).

The projection's output is handed to the frontend as part of the public read response so the page embeds it without reshaping it.

## Dependencies

- public-event-read-by-slug
