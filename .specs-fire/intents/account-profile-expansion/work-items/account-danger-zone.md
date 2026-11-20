---
id: account-danger-zone
title: The Danger Zone — a Place to Put What Cannot Be Undone
intent: account-profile-expansion
complexity: low
mode: autopilot
status: completed
depends_on:
  - account-deletion-and-avatar-removal
created: 2026-11-20
run_id: run-eventpulse24-054
completed_at: 2026-11-20T07:56:26.799Z
---

# Work Item: The Danger Zone — a Place to Put What Cannot Be Undone

## Description

**The container the other two account-deletion surfaces hang on.**

`/settings/privacy` exists — it holds the published ranking formula (FR-22) — but it
has **no danger zone**. Its own docstring says so, and so does
`frontend/lib/settings-sections.ts:46`:

> **Appearance and Danger zone are not here**, because they are not built.

**This item builds the danger zone and nothing else.** It is the section, the row, the
nav row that names it, and the two states the section can be in. It starts no deletion
and cancels none.

**Why it is a separate item at all, when it is only a section.** Because the modal and
the cancel surface are two mutually-referencing pieces of the same section, and folding
the section into either of them creates a deadlock:

- The **modal** needs the danger zone to open from, and its copy needs the cancel
  surface to be true
- The **cancel surface** needs the danger zone to live in, and the danger zone needs the
  modal to start a request

**Putting the section in its own item breaks the circle** — and it is the right shape
anyway, because the section is the thing that has to exist before either of its two
states can be hung on it.

## What the section is

**A-16's mockup** — `_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/mockups/account-delete-confirmation-modal-desktop.html` —
places it at `/settings/privacy` → Danger zone, below the privacy page's other rows:

```
Danger zone
  Export your data            [Request export]
  Delete account              Delete account →
```

**The "Delete account" row carries the terracotta accent** (`--accent-terracotta`), per
the mockup's `.danger` class — the same treatment the personal-event delete row already
uses, and the project's own rule that terracotta is reserved for destructive actions.

**"Permanent. Cannot be undone." is the mockup's subtitle for the row** — and it is
**almost, but not quite, true**: the grace period means the deletion can be called off
for thirty days. The row's subtitle must not say "cannot be undone" while the engine
holds a thirty-day grace period. The mockup predates the engine; the copy must not.

## The two states

**The section is a two-state thing, and the state is driven by whether a deletion is
pending** — a fact the frontend cannot currently know. So the section has to render
both states, and it needs a read to do it.

| State | What it shows |
|---|---|
| **No pending deletion** | The **"Delete account →"** row, opening the modal |
| **A deletion is pending** | The scheduled date, and a **"Keep my account"** action — and **not** the "Delete account" row |

**Exactly one state at a time.** A section that shows both a "Delete account →" row and
a "Keep my account" button is a section offering two contradictory instructions.

**And it is rendered unconditionally** — a signpost or a row that depends on a read
that can fail is a row that vanishes, and a danger zone that vanishes is the opposite of
what a danger zone is for. **If the pending-deletion read fails, the section must show
the state it can prove** — which is the request row, because "no pending deletion I can
see" and "no pending deletion" are different, and only the first is provable.

**This is where the read decision bites, and it is why this item is not merely
cosmetic.** The pending state needs `CurrentUserOut` to carry the pending-deletion
fields — which is `account-deletion-cancel-surface`'s work, because that item owns the
contract change.

**So this item's dependency on the cancel surface is real and unavoidable: the danger
zone cannot know which state to render without the read.** The dependency runs one way
— cancel-surface depends on danger-zone's *section*, and danger-zone depends on
cancel-surface's *read*. **That is a cycle, so the cycle has to be broken by
sequencing rather than by dependency.**

**The break: the read ships first, alone.** The pending-deletion fields land on
`CurrentUserOut` without any surface using them; then the danger zone lands in one
state; then the modal and the cancel row land on it. **The fields are the seam.**

## Acceptance Criteria

- [ ] A **danger zone section** exists at `/settings/privacy`, below the ranking
      formula, holding the account-level destructive rows
- [ ] The section is **reached by the settings sub-nav**, and the Privacy row's
      description **describes what is behind it** — a nav row promising "your data"
      over a page that explains ranking is the failure that page's docstring records
- [ ] The **"Delete account →"** row carries the terracotta treatment, matching the
      mockup and the project's rule that terracotta is reserved for destructive actions
- [ ] The row's subtitle **does not say "Permanent. Cannot be undone."** — the engine
      holds a thirty-day grace period, and the copy has to be true of it
- [ ] The section renders **exactly one** of the two states, never both
- [ ] The section **renders even when the pending-deletion read fails**, showing the
      request row rather than vanishing
- [ ] The **"Export your data" row stays where it is** — on `/settings/account`, where
      it already lives — so this item moves nothing
- [ ] `axe-core` passes on the section in both states
- [ ] `tests/settings-routes.test.ts` stays green, and the Privacy row is still
      accurate
- [ ] Run the frontend under **Node 24**

## Technical Notes

- **Read `account-deletion-and-avatar-removal.md` first.** The grace period is the fact
  that decides what the row's subtitle may claim.
- **The section is a server component.** Its state comes from a read the page makes;
  the modal that opens from it is a client component.
- **`/settings/privacy` currently reads `readRankingTransparency()` and can render an
  `unavailable` state.** The danger zone must be reachable in that branch too, or a
  failed ranking read silently removes the section — which would make the danger zone
  disappear precisely when the page is unhealthy.
- **The nav row's description is part of this item.** `SETTINGS_SECTIONS` in
  `frontend/lib/settings-sections.ts` carries a label and a description per route, and
  both change when the page behind them changes.
- **Do not put the danger zone on `/settings/profile`.** A destructive irreversible
  control beside an avatar upload invites the accidental click; A-16 chose the privacy
  route, and the separation is the point.

## Dependencies

- `account-deletion-and-avatar-removal` — the engine whose grace period decides what the
  row may claim
