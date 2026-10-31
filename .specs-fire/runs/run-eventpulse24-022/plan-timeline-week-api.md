# Implementation Plan: "The Timeline week read — one week, day by day, conflicts decided"

**Work item**: `timeline-week-api`
**Intent**: `timeline-and-conflicts`
**Mode**: confirm
**Depends on**: `conflict-list-api`

---

## Approach

`GET /api/personal/timeline?week=YYYY-MM-DD` returns one Mon–Sun week in the **user's
timezone**, as seven days, each a time-ordered list of blocks — the user's personal
events and saved public events merged — with the conflict indicator already decided per
block.

The screen draws what it is given. The per-day bucketing across timezones, the
cross-midnight placement, and the indicator projection are logic, and logic belongs on
the server where it can be tested once. The endpoint is a **read**: it opens no
transaction, writes no audit row, and touches no model attribute.

### The four decisions this plan makes

The work item's acceptance criteria name three things the codebase does not yet have.
Each needed a decision rather than a lookup, so each is stated here.

---

### D1 — The block `kind` is `personal` / `public`, a new vocabulary

The AC says a block carries `kind` (`personal` / `public`). The codebase already has
`ConflictPair.SideKind` — `personal_event` / `saved_event` — but that names **a side of
a conflict pair**, not **a kind of thing the timeline draws**. They are different
vocabularies for different things, and conflating them would put a pair-side name on a
block the screen renders.

The UX spine uses exactly the AC's words: the block carries a visible text label
"Personal" / "Public event" (`EXPERIENCE.md` §Timeline), and the stripe tokens are
`color.warm.personal` / `color.cool.public`. So the wire shape is `personal` / `public`,
and a **new** literal `TimelineBlockKind` is introduced. The `ConflictSideKind` values
stay where they are.

### D2 — The indicator is true for an ACTIVE pair **and** for a RESOLVED `keep_both` pair

The AC says so, and FR-33's persistence line says so: *"After 'Keep both', indicator
remains permanently on both events as a calm permanent reminder."*

The codebase has two existing indicator projections and **neither** implements this:

| Helper | Rule | Why it is wrong here |
|--------|------|---------------------|
| `digest_read._conflicted_card_ids` | ACTIVE only | Correct for a digest card, which shows *open* conflicts. A resolved pair is not an open conflict. |
| `digest_candidates.list_conflict_pairs` | ACTIVE only | Same rule, same reason. |

`conflict_list.py` is the closest read — it returns active **and** resolved pairs and
excludes `cleared_by_state_change` — but it does the expensive catalog-title join and the
side lookups the timeline does not need.

So the timeline needs **its own** projection, and it needs the rule stated in one place:

> A block carries the indicator when it is a side of an **active** pair, or of a pair
> **resolved with `keep_both`**. Every other resolution — `edit_new`, `delete_new`,
> `update_existing`, `skip_public` — removes the indicator, because the conflict the
> user was reminded about is gone.

`cleared_by_state_change` never carries the indicator: nobody answered, and the side
that caused it went away.

**And the indicator is per day-cell, following the *pair's* overlap.** The AC says the
indicator "fires on the day-cell whose interval contains **the overlap**" — and the
overlap is between the two *conflicting* events, not the block's own span. So the block's
own span decides which cells it appears on, and the pair's overlap decides which of them
carry the flag:

- an event running Friday 22:00 → Saturday 02:00 that clashes on Friday lights **Friday's
  cell only** — its own span says it covers both days, but the *clash* is on Friday;
- a clash that itself straddles midnight lights **both** of its days.

For a **time** pair the window is the intersection of the two sides' intervals. For a
**duplicate** pair there is no overlap to intersect — the two sides are the same event
twice — so the window is the span the two sides share, which puts the indicator on the
day the duplicate actually sits.

### D3 — The range read must be **overlap**-bounded, not start-bounded

The AC says *"Reads are range-bounded (the existing `starts_after` / `starts_before`
services)"* and also *"a personal event running past midnight appears on each day it
covers"*.

Those two pull against each other, and the existing services only bound by **start**:

```python
queryset = queryset.filter(start_utc__gte=starts_after)
queryset = queryset.filter(start_utc__lte=starts_before)
```

An event that started on the Sunday *before* the week and runs into Monday is a block
on Monday's cell — and a start-bounded read **excludes it**. The same goes for an
open-ended event (`end_utc` is nullable): it has no end, so it runs from its start
onward and covers every day after it.

So the existing services are **extended** with an overlap bound rather than replaced.
The extension is backward-compatible: the current `starts_after` / `starts_before`
parameters keep their exact meaning, and the new parameter is optional and off by
default, so the two existing callers (`api.py:164`, `api.py:393`) are untouched.

The overlap bound is `end_utc >= window_start OR end_utc IS NULL`, combined with
`start_utc <= window_end`. An open-ended event has no end, so it is never excluded by
the lower bound.

### D4 — The week is a **local** week, cut in the user's zone

A week is not seven times 24 hours. The Monday–Sunday week is cut at local midnight in
the user's zone, so a DST week is 167 or 169 hours long, and a 23:30 local event is on
Friday evening no matter what the server's clock says.

The bounds are computed **by conversion**, not by arithmetic — the same rule
`digest_dates.local_date_for` follows. The day boundaries are the local midnights, read
in the user's zone.

The user's zone is the **digest preference's** zone, falling back to UTC. There is no
public reader for it today — three services each inline the same two-line idiom
(`digest_read.py:443`, `digest_composition.py:569`, `onboarding.py:262`). The timeline
needs it in one place, so a small public reader is added and the timeline calls it.
(The three existing copies are left alone: refactoring them is not this work item's
job, and the timeline's reader is a fourth *reader*, not a second *rule* — the rule
itself, "the preference's zone, else UTC", is one line and is now stated once.)

---

## The domain logic (pure, no database)

A new pure module, `backend/apps/personalization/services/timeline_days.py`, holds the
day arithmetic. It is pure so it can be tested against a DST week without a database —
the same reasoning as `digest_dates.py`, which exists as its own module precisely so
"which local day is this instant" cannot drift between two callers.

It answers four questions:

1. **`week_bounds(day, zone)`** — the local Monday 00:00 and the local Sunday 24:00, as
   UTC instants. Monday-start, and DST-correct by conversion.
2. **`local_days(start_utc, end_utc, zone)`** — the local dates an interval covers. An
   event is placed on the day its **local start** falls on (the AC's rule), and it
   **also** appears on every later day it covers — the cross-midnight rule.
3. **`week_days(day, zone)`** — the seven local dates.
4. **`day_bounds(local_date, zone)`** — one local day's UTC instants, for the
   cross-midnight containment test.

**An open-ended event** (`end_utc is None`) covers every day from its local start to the
end of the week — so it appears on each day of the week that is on or after its start.

**A zero-length event** (`end == start`) covers exactly one day: its start's.

**The indicator fires on every day-cell the event spans** (FR-33 (e): *"indicator
repeats on each day-cell the event spans"*). So the flag is computed **per cell**, not
per event: a multi-day event carries the indicator on each of its cells.

This is the one place where the AC's "the indicator fires on the day-cell whose
interval contains the overlap" is read literally: the cell's own local interval is what
the overlap is tested against, so a conflict that falls on Tuesday lights Tuesday's cell
even if the event also spans Wednesday.

---

## The service

A new module, `backend/apps/personalization/services/timeline.py`, holds the read.

It is a **read**: no transaction, no audit row, no model attribute touched. Every query
is scoped to the caller's `user_id`.

### The query budget — constant, not per-event

The AC says *"the query count is independent of the number of events"*. The read is
therefore:

| # | Query | Alias |
|---|-------|-------|
| 1 | the user's digest preference (the zone) | `personal` |
| 2 | the user's personal events overlapping the week | `personal` |
| 3 | the user's saved events overlapping the week | `personal` |
| 4 | the user's conflict pairs (active + `keep_both`-resolved) | `personal` |
| 5 | the catalog titles and zones for the week's saves | `catalog` |

**Five queries, whatever the number of events.** The catalog read is the batched
`get_public_events(event_ids=…)` — one query against the `catalog` alias for every
saved side in the week, which is the AD-2 / AD-3 wall: the title is read through the
catalog's published interface, never by a cross-schema query.

### The conflict-side bridge

A pair's `saved_event` side names the **save's** id. A public block carries the
**catalog** event's id, so it can route to `/events/:id`. The bridge between them is the
save row — the same mapping `digest_read.py:232-257` builds. A personal block's id
**is** the pair's `personal_event` side id, so it matches directly.

### A save whose catalog event has disappeared

The save is still the user's, and its snapshot still has a time — so the block is still
shown, with the snapshot's times and the catalog's zone, but **no title** and no
`available` flag (this is the timeline's shape: the AC asks for `name`, and there is no
name to give). This mirrors `conflict_list._saved_side`, which already models "the
catalog no longer holds the event".

---

## The endpoint

```
GET /api/personal/timeline?week=YYYY-MM-DD
```

- **`week` missing** → the current week in the user's zone.
- **`week` malformed** → 422. The parameter is typed as `date` in a Ninja query schema,
  so Django Ninja's own validation answers 422 with `invalid_request` — the same path
  every other malformed query in this codebase takes.
- **`week` any date in the wanted week** → the response names that week's Monday and
  Sunday. A date in the middle of the week selects the week that contains it.
- **anonymous** → 401, from the router's `auth=current_user`.

### The wire shape

```jsonc
{
  "week_start": "2026-11-02",     // the local Monday
  "week_end":   "2026-11-08",     // the local Sunday
  "timezone":   "America/Los_Angeles",
  "days": [
    {
      "date": "2026-11-02",
      "blocks": [
        {
          "kind": "personal",          // or "public"
          "id": "…",                   // the personal event id, or the CATALOG event id
          "name": "Coffee with Sam",
          "start_time_utc": "…",
          "end_time_utc": "…",         // null when open-ended
          "start_time_tz": "America/Los_Angeles",
          "conflict": true
        }
      ]
    }
    // … seven days, always
  ]
}
```

**Seven days, always.** Even an empty week returns seven day cells, each with an empty
`blocks` list — the screen draws seven columns and must not have to know whether the week
has anything in it.

**Blocks are time-ordered within a day**, by start then id.

**`start_time_tz` is the event's own zone** — the personal event's `start_time_tz`, or
the catalog event's zone for a public block. The AC says "the event's own zone", and the
day cut is the *user's* zone: those are two different zones, and a public event in
Berlin shown to a user in Los Angeles is on a different Los Angeles day than its own
clock suggests. The block carries both, so the screen can label it either way.

---

## Files to Create

- `backend/apps/personalization/services/timeline_days.py` — the pure day arithmetic
- `backend/apps/personalization/services/timeline.py` — the read service
- `backend/tests/personalization/test_timeline.py` — the tests

## Files to Modify

- `backend/apps/personalization/services/personal_events.py` — the overlap bound
- `backend/apps/personalization/services/saved_events.py` — the overlap bound
- `backend/apps/personalization/schemas.py` — the wire shapes
- `backend/apps/personalization/api.py` — the endpoint
- `frontend/lib/api/openapi.json`, `frontend/lib/api/schema.ts` — regenerated by
  `make client` (AD-19: never hand-edited)

---

## Tests

Every test names the rule it pins, in the house style (a full sentence describing the
rule, not `test_foo_bar`).

### The pure day arithmetic (no database)

- a week is Monday to Sunday, and a mid-week date selects the week that contains it
- the week's bounds are the local midnights, and a DST week is not 168 hours
- an event at 23:30 local is on that local day
- a cross-midnight event covers both days it spans
- an open-ended event covers every day from its start
- a zero-length event covers one day
- the days are the user's zone, not the server's

### The service

- the seven days are returned for an empty week
- the blocks are the personal events and the saved events, merged
- a public block carries the **catalog** event id, and the title from the catalog
- a save whose catalog event disappeared has no title and is still shown
- the indicator is true for both sides of an active pair
- the indicator is **still true** after `keep_both`
- the indicator is false after `delete_new`, `skip_public`, `update_existing`
- the indicator is false for a `cleared_by_state_change` pair
- the indicator repeats on each day-cell a multi-day event spans
- the query count does not grow with the number of events
- the read is scoped to the caller

### The endpoint

- the response names the week's Monday and Sunday and returns seven days
- a missing `week` means the current week in the user's zone
- a malformed `week` is a 422
- an anonymous caller is a 401

---

## Gate Results (to be filled in as the work proceeds)

| Gate | Result |
|------|--------|
| `pytest` (full backend suite) | |
| Coverage — overall (gate 80%) | |
| Coverage — `domain/` (gate 100%) | |
| `ruff check .` | |
| `ruff format --check .` | |
| `lint-imports` | |
| `makemigrations --check --dry-run` | |
| `make client` + `make lint-web` + `make test-web` | |

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-022*
