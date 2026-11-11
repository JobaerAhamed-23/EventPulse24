---
work_item: per-day-quiet-hours-domain-and-model
intent: pro-tier-and-monetization
created: 2026-11-11
mode: validate
checkpoint_1: approved
---

# Design: Seven windows instead of one — reshaping quiet hours without breaking Free users

## Summary

FR-51 gives a Pro user seven quiet-hours windows, one per weekday. Quiet hours are
single-window in two places at once — `domain.quiet_hours.QuietHours` and
`NotificationPreference`'s column pair — and the shift sits on the delivery path, where a
mistake reaches a user as a notification at 3am.

The design rests on one observation about the existing code:

> **Every consumer of the window forwards it, untouched, to `shift_to_sendable`.** There are
> seven call sites across `scheduled_sends.py` and `reminder_plan_read.py`, and all seven
> read `preference.quiet_hours` and pass it as `window=`. Not one of them inspects `.start`,
> `.end`, `covers()` or `crosses_midnight`.

So the plumbing does not change. **The value's type changes and the plumbing is untouched** —
which is what makes a high-risk reshape into a small diff on the delivery path.

Three decisions follow from that, and one of them is the whole item.

## Scope

**In:** the domain's weekly type and its midnight rule; the storage shape; the migration; the
command's refusals; what the delivery path does for a lapsed Pro user; the tests.

**Out:** the API (`quiet-hours-pro-api`, item 8) and the UI (`frontend-pro-quiet-hours`,
item 9). This item ends at the service boundary: nothing user-facing changes, and a Free
user's delivery times are byte-for-byte what they were.

## Key Decisions

### 1. `QuietHours` is not touched. A weekly type wraps it.

`QuietHours` keeps its exact shape — `start`, `end`, `disabled`, `crosses_midnight`,
`covers()`. Every one of its 20-odd domain tests keeps passing unmodified, which is the
point: the single-window semantics are correct, documented at length, and carry the
hard-won DST and midnight reasoning. Reshaping them would put all of that back in play for
no gain.

`WeeklyQuietHours` is a new frozen value holding seven `QuietHours | None` slots, indexed by
`date.weekday()` (Monday 0 … Sunday 6).

**A single `QuietHours` remains a legal `window=` argument, meaning "this window, every
day".** That is not a compatibility shim — it is what a Free user's preference *is*, and it
means a Free user's send travels the identical code path it travels today.

### 2. The storage is a base window plus per-weekday overrides, not seven column pairs and not a replacement table

`NotificationPreference.quiet_hours_start` / `_end` **stay exactly as they are**, including
`notification_preference_quiet_hours_pair_ck`. They are the user's **base window**: "this
window, every day". A new child table holds **overrides**, at most one per weekday:

```
QuietHoursOverride            (delivery-owned, PERSONAL alias)
  user_id    UUIDField
  weekday    SmallIntegerField      0..6, checked
  start      TimeField
  end        TimeField
  unique (user_id, weekday)
  check weekday between 0 and 6
```

| | Seven column pairs | Replacement table | **Base + overrides** |
|---|---|---|---|
| Columns on a hot row | 14 | 0 | 2, unchanged |
| The existing check constraint | rewritten, 7× longer | dropped | **untouched** |
| Migration touches user data | no | **yes — must copy every row** | **no** |
| "This user has one window" | 6 null pairs | 7 identical rows, or 1 | **no rows** |
| A Free user's read | unchanged | **a join** | unchanged |

The decisive column is the third. The acceptance criterion says *"the migration invents
nothing… no Free user's delivery time moves as a result of this item."* Under base+overrides
the migration **writes no data at all** — it creates one empty table. There is no row to copy
wrongly, no default to fabricate, and nothing to get wrong in a backfill. The strongest form
of "the migration invents nothing" is a migration with no data step in it, and this is that.

It also gives the never-delete constraint for free: a lapsed Pro user's overrides are rows in
a table nobody deletes.

**The cost, stated plainly:** the weekly value needs the override rows, which is one extra
query where there was none. It is **per batch, not per send** — the delivery path already
loads the preference once per user per batch and forwards the value — so it is one query
added to a path that already makes several, not a query per notification.

### 3. The midnight rule: a window is anchored at its start, and the shift iterates to a fixpoint

**This is the single likeliest source of a 3am send, and it is the reason this item is
`validate`.**

**The rule: day D's window begins on day D.** A Friday 22:00–08:00 window is *Friday night* —
it begins Friday at 22:00 and runs into Saturday morning. It is **Friday's** window for the
whole of its length, including the part after midnight. Saturday's own window does not begin
until Saturday at 22:00 (or whenever Saturday's start is).

The alternative — evaluating each local instant against *its own* weekday's window with
`covers()` — is wrong, and wrong in the dangerous direction. Under it, Saturday's 23:00–09:00
window would "cover" Saturday 02:00 through its morning side, even though that morning
belongs to Friday night. The user's Saturday setting would silently govern Saturday *morning*
rather than Saturday *night*, which is not what "a window per weekday" means to anyone
setting one.

So, for a local instant on date `L`, exactly two windows can cover it:

- `L`'s own window, if the instant is at or after its start; and
- `L−1`'s window, if that window crosses midnight and the instant is before its end.

**When both cover it, the shift defers to the later end** — the acceptance criterion's
explicit case. Deferring to the earlier end would release the send into the middle of the
other window.

**And then it repeats.** Taking the later of the two ends is *not* sufficient, because the
instant it returns can land inside a *third* day's window:

> Monday 01:00–00:30 (crossing midnight, ending Tuesday 00:30) and Tuesday 00:00–23:00.
> A send due Monday 02:00 is in Monday's window, which ends Tuesday 00:30 — and Tuesday
> 00:30 is inside Tuesday's window, which runs to 23:00.

A single pass would send at 00:30 on Tuesday, inside quiet hours. So `shift_to_sendable`
**iterates until the instant is covered by nothing**, which is the same fixpoint the
single-window function already reaches in one step. The iteration is bounded at **8 passes**
(seven days plus one), so it terminates on any input.

**The degenerate case turned out not to exist.** The design as approved had the command
refusing a week with no sendable moment, via a pure `has_sendable_gap` check, on the
assumption that seven windows could tile a week. **They cannot**, and the item's own test
proved it before the code was written:

> A window spans `(end − start) mod 1440` minutes, which is at most **1439** — a span of 0
> is `disabled`, not 24 hours. Closing every seam around the week needs the seven spans to
> sum to the week's 10080 minutes, and seven windows sum to at most 7 × 1439 = **10073**.
> Every schedule leaves at least **seven minutes** open.

So `has_sendable_gap` was **removed rather than shipped**: it is a guard that can only ever
return one answer, protecting against a state the type system of the problem forbids, and a
command refusal that can never fire is a refusal nobody can test. The arithmetic moved into
`MAX_DEFERRALS`' docstring, and `test_every_schedule_leaves_a_sendable_moment` proves it by
brute force over the worst case the arithmetic allows — seven maximal windows at every
alignment of their starts, checked minute by minute.

`shift_to_sendable` keeps its bound and stays **total**: the loop is now provably finite,
and if the bound were somehow exhausted it returns the last end it computed rather than the
unshifted instant. A send that is late can be recovered; a send at 3am cannot.

### 4. A lapsed Pro user keeps their windows and loses their effect

The brief forbids deleting them, and the acceptance criterion forbids leaving the answer
implicit. So, explicitly:

**While a user is not Pro, their overrides are ignored and their base window applies.** The
rows stay. If they resubscribe, the seven windows come back exactly as they left them,
without the user re-entering anything.

The read asks `is_pro(user_id=...)` — the one published entitlement read, the same function
`save_cap.py` calls — and builds the weekly value from the overrides **only** when it returns
true. `apps.delivery` importing `apps.identity.services` is permitted: only
`apps.identity.models` is protected (`models-identity`), `apps` is a single layer, and
`apps/personalization/services/save_cap.py` already does exactly this.

**The risk this creates, named:** a lapse silently moves a Pro user's delivery times back to
their base window. That is the correct behaviour — they are not paying for seven windows any
more — but it is a *delivery-time change caused by a billing event*, and it is the only one
in this intent. It is called out here so that item 8's API can report the effective schedule
rather than the stored one, and the user is never shown seven windows that are not in force.

## Data Models Affected

| Model | Change |
|---|---|
| `NotificationPreference` | **None.** Columns, constraint and defaults all unchanged. |
| `QuietHoursOverride` | **New.** `delivery`-owned, `PERSONAL` alias, `RetentionCategory.PREFERENCE_SIGNALS` (the same category as the preference it qualifies). Registered in `TABLE_OWNERS` as `delivery_quiethoursoverride → delivery`. |

## Technical Approach

```python
# domain/quiet_hours.py — added; nothing existing is modified.

@dataclass(frozen=True)
class WeeklyQuietHours:
    """Seven windows, one per weekday, indexed by `date.weekday()` (Mon 0 … Sun 6).

    A `None` slot is a day with no quiet hours. A day's window *begins* on that day: a
    Friday 22:00-08:00 window is Friday night, and owns Saturday's small hours.
    """
    windows: tuple[QuietHours | None, ...]   # length 7, validated in __post_init__

    def for_weekday(self, weekday: int) -> QuietHours | None: ...

Window = QuietHours | WeeklyQuietHours

def shift_to_sendable(instant, *, window: Window | None, zone: str) -> datetime: ...
```

`shift_to_sendable` keeps its name, its keyword, its contract and its docstring's two
load-bearing boundary decisions. Internally it becomes: resolve the candidate windows for the
local date, take the latest end among those that cover, repeat; a single `QuietHours` resolves
to itself for every weekday, so the existing single-window path is the same arithmetic it is
today and its tests pin that it has not moved.

The service layer composes the value in **one place** — `notification_preferences._to_settings`,
the only producer of `preference.quiet_hours` — so the seven consumers continue to forward a
value whose construction they do not know about.

## Affected Files

| File | Change |
|---|---|
| `domain/quiet_hours.py` | `WeeklyQuietHours`, `has_sendable_gap`, the iterating shift |
| `apps/delivery/models.py` | `QuietHoursOverride` |
| `apps/delivery/migrations/00NN_quiethoursoverride.py` | **Schema only. No data step.** |
| `apps/delivery/services/notification_preferences.py` | Build the weekly value; the override commands and their refusals; audit rows |
| `apps/delivery/services/preferences_read.py` | `NotificationSettings.quiet_hours` becomes the weekly value; the **base pair** stays separately readable for the existing API response |
| `shared/constants.py` | The iteration bound; the weekday count |
| `tests/architecture/test_write_ownership.py` | The new table's owner |

**Unchanged, and asserted to be unchanged:** `scheduled_sends.py`, `reminder_plan_read.py`,
`delivery_sweep.py`, `schemas.py`, `preferences_api.py`.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| **A send at 3am** from the midnight rule | The rule is stated above and pinned by a test per branch, including the two-window overlap and the three-day chain. The shift is proven idempotent on its own output, as today. |
| A Free user's delivery time moves | The base columns, the constraint and the single-window code path are all untouched; the migration has no data step. A test asserts a Free user's computed `due_at` is identical before and after. |
| The entitlement read on the delivery path | One call per user per batch, beside the existing preference read. If it ever costs, the seam is one function. |
| The extra query regresses the batch | The override read is one query per batch. A test asserts the query count for a Free user is unchanged. |

## Implementation Checklist

1. `WeeklyQuietHours`, pure, with its own tests, before anything else. **Done** — and the
   tests retired `has_sendable_gap` before it shipped (see decision 3).
2. The iterating `shift_to_sendable`; the existing `test_quiet_hours.py` must pass **unmodified**.
3. `QuietHoursOverride` + the schema-only migration + `TABLE_OWNERS`.
4. The commands, their refusals and their audit rows.
5. `_to_settings` composes the weekly value, gated on `is_pro`.
6. The proof: weeknight vs weekend; midnight into the next day's window; the three-day chain;
   DST both directions; the disabled spelling; a lapsed Pro user; a Free user byte-for-byte.
