---
id: place-on-the-profile-screen
title: Where You Are — Surfaced, Not Stored Again
intent: account-profile-expansion
complexity: medium
mode: confirm
status: completed
depends_on: []
created: 2026-11-19
run_id: run-eventpulse24-053
completed_at: 2026-11-19T00:00:00Z
---

# Work Item: Where You Are — Surfaced, Not Stored Again

## Description

**The product already knows where the user is, and knows how it found out.**
`DigestPreference` (`backend/apps/personalization/models.py`) holds `city` and
`city_source`, and that second column is load-bearing: its docstring records that
without it *"a user whose city was inferred and a user whose city they chose look
identical"* — which is what keeps the digest's fallback honest rather than invisible.
`components/settings/home-city.tsx` and `digest-timezone.tsx` already edit both.

**So this item adds no column, no endpoint and no address field.** It surfaces the
existing controls on the profile screen, because "where am I" is a thing a person looks
for under *profile*, not under *digest*.

**The one real decision is whether the controls move or appear twice.** Two copies of
the same control on two screens is two places to keep in sync and two answers when they
drift. **Recommended: they move, and the screen that held them links to where they
went** — the previous intent did exactly this when it removed the account sheet's
`Settings` and `Pricing` rows, on the grounds that two ways to one place leaves one of
them a dead end. The alternative — rendering the same island in both places — is
defensible only if it is literally the same component instance with no duplicated state,
and that must be demonstrated rather than claimed.

**The city is weak location data about a real person.** Its model docstring says it is
never in `__str__`, and is deliberately **not** encrypted because it is not a
credential. Moving where it is *edited* must not change where it is *logged*, and it
must not end up in an audit detail or an error message (AD-13).

## Acceptance Criteria

- [x] The home city and the timezone are reachable and editable from `/settings/profile`
- [x] **No new column, no new model, no new endpoint** — asserted by the absence of a
      migration in this item
- [x] **Exactly one** editing surface for the city exists in the product; if a control
      is rendered in two routes it is the same component with one source of truth, and
      that is demonstrated by a test
- [x] Whichever screen no longer holds the control **links to where it went**; no dead
      end and no removed control that leaves a hole
- [x] `city_source` keeps working — a city the user chose and a city that was inferred
      stay distinguishable after the move
- [x] The settings sub-nav (`settings-nav.tsx`) stays correct from **every** settings
      screen
- [x] Existing tests for the moved components still pass, or are moved with them —
      **not deleted**
- [x] `axe-core` passes
- [x] The city appears in no new log line, audit detail or error message (AD-13)
- [x] Run the frontend under **Node 24**

## Reconciliation Note: The Frontmatter Was Stale, Not The Work

**On 2026-11-20 this file still read `status: pending` while `state.yaml` read
`completed` for the same item.** The state file was right and this file was wrong —
the work had shipped and been verified, but the work item's own frontmatter was
never updated with it.

**Every acceptance criterion above was checked against the code before being ticked,
rather than against the state file**, because a stale status on one side of a
reconciliation is exactly the case where trusting either side blind is unsafe:

| Criterion | Evidence |
|---|---|
| City reachable from `/settings/profile` | `HomeCity` imported and rendered at `frontend/app/settings/profile/page.tsx:5,253` |
| No new column, model or endpoint | No migration carries this item's name; the city stays on `DigestPreference` |
| Exactly one editing surface | `HomeCity` renders only under `app/settings/profile`; `grep` finds no second mount |
| The old screen points to where it went | `data-city-moved-note` at `frontend/app/settings/account/page.tsx` — a **signpost, not a link**, because `tests/settings-routes.test.ts` forbids hand-written links between settings screens |
| `city_source` still distinguishes chosen from inferred | `citySourceNote(city, source)` and `response.data.digest.city_source` in `components/settings/home-city.tsx:79,140` |
| Sub-nav correct from every settings screen | `tests/settings-routes.test.ts` walks every signed-in branch of every screen |
| Moved components' tests still pass, not deleted | `components/settings/home-city.test.tsx` — 10 tests, still present and green |
| `axe-core` passes | `tests/profile-a11y.test.tsx` — 7 axe assertions, including the no-picture and failed-read branches |
| No new log, audit detail or error message | No new logging in the moved path; AD-13 unchanged |
| Node 24 | Suite run under `v24.22.1` — **76 tests, 5 files, all green** |

**The lesson worth keeping: `state.yaml` and the work item's frontmatter are two
copies of one fact, and this project has now drifted on that fact once.** The
work item's own `status:` line is the copy a reader opens first, so it is the copy
that must not lie.

## Technical Notes

- **Check `app/settings/general/page.tsx` and its sibling tests** before moving
  anything: `retired-routes.test.tsx` suggests this project has form in retiring routes
  properly, and that test is the pattern for doing it again.
- **`personalization` is read through its published service, not reached into**
  (AD-2/AD-16). The frontend talks to the endpoint that already exists.
- **This item is independent of both the avatar and the email halves** and can run in
  parallel with either.

## Dependencies

(none)
