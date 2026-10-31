---
id: timeline-week-api
title: The Timeline week read — one week, day by day, conflicts decided
intent: timeline-and-conflicts
complexity: medium
mode: confirm
status: completed
depends_on:
  - conflict-list-api
created: 2026-10-31
run_id: run-eventpulse24-022
completed_at: 2026-10-31T08:21:32.768Z
---

# Work Item: The Timeline week read — one week, day by day, conflicts decided

## Description

`GET /api/personal/timeline?week=YYYY-MM-DD`: one Mon–Sun week in the **user's timezone**, as seven days, each a time-ordered list of blocks — the user's personal events and saved public events merged — with the **conflict indicator already decided** per block.

The screen should draw what it is given, as the digest does: the per-day bucketing across timezones and the cross-midnight indicator rule are logic, and logic belongs on the server where it can be tested once.

## Acceptance Criteria

- [ ] `week` is any date in the wanted week; the response names the week's Monday and Sunday and returns **seven days**, each with its date and its blocks. Missing or invalid `week` means the current week in the user's zone; a malformed value is a 422.
- [ ] Days are cut in the **user's timezone** (the digest preference zone, falling back to UTC), not the server's; an event is placed on the day its local start falls on.
- [ ] A block carries `kind` (`personal` / `public`), the id the screen needs to act on it (the personal event id, or the **catalog** event id for a saved event so it can route to `/events/:id`), name, start, end, the event's own zone, and `conflict: true|false`.
- [ ] `conflict` is true for both sides of an **active** pair (and stays true after **keep both**, per FR-58); false otherwise.
- [ ] **Cross-midnight**: a personal event running past midnight appears on each day it covers, and the indicator fires on the day-cell whose interval contains the overlap (FR-33 addendum) — both cells of a multi-day event, not just one.
- [ ] Reads are range-bounded (the existing `starts_after` / `starts_before` services) and the query count is independent of the number of events.
- [ ] Caller only; anonymous is 401. Schemas and regenerated client (AD-19).
- [ ] Tests: week boundaries in a non-UTC zone (including a DST change week), an event at 23:30 local, a cross-midnight event, both indicator states, a saved event whose catalog event disappeared, and an empty week.

## Technical Notes

Reuse `conflict-list-api`'s side-naming (catalog titles via the published read service) rather than writing a second projection.

## Dependencies

- conflict-list-api
