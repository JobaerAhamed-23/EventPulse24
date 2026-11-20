---
id: settings-privacy-ranking-transparency
title: FR-22's transparency promise has no surface — Settings → Privacy →
  Ranking algorithm version
intent: traceability-gap-closure
complexity: medium
mode: confirm
status: completed
depends_on:
  - fr22-published-formula
created: 2026-11-19
run_id: run-eventpulse24-048
completed_at: 2026-11-19T15:42:30.727Z
---

# Work Item: FR-22's transparency promise has no surface

## Description

**Split out of `fr22-published-formula` on 2026-11-19**, where the gap was found while
checking whether a user is currently shown the wrong formula.

They are not — and that is the whole finding. **Nothing in the frontend shows a formula
at all.** `frontend/app/settings/` holds `account`, `calendars`, `collections`, `digest`,
`general`, `profile`, `quiet-hours`, `reminders`, `sources` and `taste`. There is **no
`privacy` route**, and a search across `frontend/` for a weights table, a formula or an
amendment history returns nothing.

**This makes FR-22's transparency promise unkept rather than broken**, which is a better
state to be in and a worse one to leave untracked.

FR-22 does not merely describe a formula — its stated purpose is the *publication* of one:

> The formula and weights are **published in the PRD and immutable post-launch** to honor
> the "Trust through transparency" principle.

and it names the surface in its own testable consequences:

> Settings → Privacy → "Ranking algorithm version" shows the current weights and the
> last-amendment date.

`EXPERIENCE.md` §2 row 9 commits the same route to showing *"the formula, weights table,
bucket boundaries, amendment history, and pledge"*, and SM-8 measures it
(*"Privacy page dwell > 30s … Target: >40% of returning users"*) — a success metric for a
page that does not exist.

**Scope note.** `/settings/privacy` is specified as a whole MVP route (the 9th, per
ASSUM-2) carrying a data inventory, export (FR-52), deletion, training opt-out, the A-14
geo-IP consent toggle, the A-13 amendment-history timeline and a read-only mirror of
`/settings/sources`. **This work item covers the FR-22 ranking-transparency section and
whatever minimal route shell it needs.** The remaining sections are a larger gap and
should be their own item — some of their content already lives elsewhere (export is at
`components/settings/download-my-data.tsx` under `/settings/account`), so that item starts
with a reconciliation rather than a build.

## Acceptance Criteria

- [ ] `/settings/privacy` exists as an authed route and is reachable from the Settings navigation
- [ ] It shows the **five-term implemented formula** with each term's weight — the formula the product actually runs, never the PRD's four published components on their own
- [ ] It shows FR-22's bucket boundaries (≥0.85 → 5 dots, and so on) and states that an exact boundary falls to the **lower** bucket
- [ ] It shows the ranking algorithm version: the current amendment ID and its date, linking to the ADR — per FR-22's immutability policy
- [ ] The weights are **served by the backend from `shared.constants`**, never hard-coded in the frontend; a weight change moves the page without a frontend edit
- [ ] A contract test covers the new read endpoint, and `make client` regenerates `frontend/lib/api/` rather than it being hand-edited
- [ ] The amendment ID shown matches the one `fr22-published-formula` mints (**A-25**), not the colliding A-10

## Technical Notes

**The weights must come from the backend.** `RANKING_WEIGHT_*` and `RANKING_BUCKET_*` live
in `backend/shared/constants.py`, and `RANKING_WEIGHTS_AMENDMENT` names the ADR.
`backend/tests/shared/test_constants.py:166` already asserts the ADR lists every weight it
authorises. A frontend copy of those numbers would be a second source of truth for the one
page whose entire job is that there is only one — and it would drift silently, which is the
precise failure FR-22 exists to prevent.

**Read `domain/ranking.py`'s module docstring before writing any copy.** It explains why
the formula is five terms rather than FR-22's published four, why the absent terms are
absent from the expression rather than pinned to constants, and why `source_reliability` is
not an inert weight at launch. That reasoning is what the page has to communicate, and it
does not need re-deriving.

**This depends on `fr22-published-formula`** because the page displays an amendment ID and
a formula, and both are being corrected by that item. Building this first would surface the
A-10 collision to users.

**The score is a `Decimal` and the boundaries are exact.** If the page shows a worked
example, it must not compute it in JavaScript floats — `0.85` as a binary float is not
`Decimal("0.85")`, and a worked example that lands in the wrong bucket on the transparency
page would be worse than no worked example.

## Dependencies

- fr22-published-formula (the formula and amendment ID this page displays)
