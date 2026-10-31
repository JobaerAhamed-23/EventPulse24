# Plan: The Conflict Review screen (`frontend-conflicts-page`)

Work item: `/conflicts` (FR-33, Flow 6, `conflicts-desktop.html`).
Mode: **confirm** — one checkpoint, at the plan.

---

## 1. What the page is

`/conflicts` is a **review surface** for the conflict pairs the system has recorded.
Two sections — **Active (n)** (what still needs a decision) and **Resolved (n)** (what
was decided) — and an active pair's decision is made right there.

It is **not** the conflict prompt. `Sheet.ConflictResolution` (FR-58) is the forced
three-action sheet on the create/save path; this page is the place a user goes to
*review* pairs later and to answer the ones still open.

### Locked microcopy

| Thing | Text | Source |
|---|---|---|
| Page heading | **"These days overlap."** | AC + mockup `h1` |
| Section headings | **"Active (n)"**, **"Resolved (n)"** | AC + mockup |
| Empty state | **"No overlaps."** | AC |
| Error state | **"Couldn't analyze conflicts. Try again."** | AC + EXPERIENCE.md |
| Resolved resolution line | `"Skipped public · Poetry reading · Fri Sep 11"` | AC + mockup |

### The actions (FR-33)

The API returns the allowed action set per pair (`ConflictPairOut.actions`). The page
renders **only what the API allows**, worded per FR-33:

- **"Move {personal event}"** — `edit_new` (personal side) / `update_existing` (the other
  side)
- **"Skip {public event}"** — `skip_public` (saved side)
- **"Keep both — I'll manage"** — `keep_both`
- personal-vs-personal / duplicate wording that exists today — `delete_new` and the
  duplicate-kind variants

The sheet's `RESOLUTION_LABELS` currently says "Edit the new one" / "Update the existing
one" / "Skip the public event". **The Technical Note forbids a second copy of the
strings**, so the wording moves into one shared module and the review surface adds its
own *display* variants on top — see D1 below.

---

## 2. Decisions

### D1 — One shared wording module; the sheet keeps its copy, the review surface adds display variants

The Technical Note says: *"Reuse the conflict wording and action set from
`components/sheets/conflict-resolution.tsx` rather than writing a second copy of the
strings; if the inline layout needs them outside the sheet, extract them once."*

**Decision:** extract into a new `frontend/lib/conflict-wording.ts`:

- `RESOLUTION_HINTS` — the sheet's hint sentences, moved verbatim out of the sheet.
- `RESOLUTION_GLYPHS` — moved out of the sheet.
- `resolutionAria(resolution, context)` — the accessible name, built from the
  resolution plus a **context** (which event the action is about), so the accessible
  name says the action *and its consequence* as the AC requires.
- `reviewActionLabel(resolution, side)` — the **review surface's** visible label:
  `"Move {personal event}"`, `"Skip {public event}"`, `"Keep both — I'll manage"`, and the
  personal-vs-personal / duplicate variants.

The sheet imports the shared module and keeps its own `RESOLUTION_LABELS` (its labels
are prompt-relative: "the new one" / "the existing one"), but its hints, glyphs and aria
strings come from the shared module. The sheet's labels become **derived from the shared
module too**, so there is exactly one table.

**Why not just reuse the sheet's label verbatim?** The sheet's labels are relative to a
prompt that has a "new side"; the review surface has two symmetric sides and no "new"
one. "Edit the new one" would be a lie on a page where neither side is new. So the
*action set* is shared; the *label wording* is contextual and lives in one place.

### D2 — The resolution's target side is chosen by the button, not inferred

`ConflictResolutionIn.side` names the side the action is about, and the pair row is
symmetric. So each rendered action button **knows which side it acts on**:

- `edit_new` → the **personal** side (the one the user moves)
- `update_existing` → the **other** side
- `delete_new` → the **personal** side
- `skip_public` → the **saved** side
- `keep_both` → **no side** (the server accepts a null/omitted side for it)

**The client picks the side from the pair's own kinds.** A pair with a personal side and
a saved side: "Move" targets the personal side; "Skip" targets the saved side. A
personal-vs-personal pair: "Move" targets one, the other actions target the other. A
duplicate pair: the wording changes but the side choice is the same rule.

**No side is inferred from `left`/`right`** — those are sorted by id, not by role. The
role comes from `kind`.

### D3 — Move opens the edit sheet with the conflicting time highlighted

"Move" posts `edit_new` (personal side) or `update_existing` (the other side), then
**opens that side in the edit sheet with the start time highlighted** — the same
`PersonalEventsPanel` driving contract the Timeline uses.

**The edit sheet is driven, not owned.** `PersonalEventsPanel` already accepts
`editingEvents` / `editingEventId` / `onEditingEventChange` (the pattern the Timeline
panel uses), and `highlightStartTime` is what the panel sets internally. The panel needs
one addition: a **driven** highlight flag, so the driving surface can say "open it with
the time highlighted" without the panel inventing it. The Timeline already owns its
panel; the Conflicts page mounts its own panel instance for the same reason.

The zone comes from `ConflictListSideOut.start_time_tz` — the conflict list **does**
carry the side's display zone (unlike the 409's `ConflictSideOut`), so no fabrication
and no empty-zone fallback here.

### D4 — The read is server-side; the write is client-side; the page re-reads

- **Read:** `GET /api/personal/conflicts` on the server, through a new
  `frontend/lib/conflict-list-read.ts` mirroring `lib/timeline-read.ts` — `sessionHeaders()`
  forwarded, and `unavailable` (not "empty") on failure.
- **Write:** the client posts to `/api/personal/events/conflicts/{pair_id}/resolve`, then
  calls `router.refresh()` — the same pattern `PersonalEventsPanel` uses. The page is a
  server component, so the refresh re-runs the read and the pair moves Active → Resolved.
- **No auto-refresh.** No polling, no `setInterval`. The page re-reads only after a
  user action.

### D5 — The active pair is a client island; the page stays a server component

The action buttons post, and "Move" opens a sheet — both need client state. So
`frontend/components/conflicts/conflicts-panel.tsx` is a `"use client"` island holding
the pairs, the in-flight pair, the error line, and the driven edit sheet. The server
component renders the heading, the states, and hands the pairs to the island.

**The counts are the server's.** "Active (n)" / "Resolved (n)" come from
`active.length` / `resolved.length` — the server already split them.

### D6 — Failure is calm and the pair stays active

A failed resolution sets a calm inline message on the pair
(**"Couldn't record that choice. Try again."** — the sheet's own wording) and **does not**
remove the pair, does not clear the buttons, and does not re-read. The pair stays Active
until the user succeeds. The buttons re-enable.

### D7 — The nav becomes a real link in both rails

- **Sidenav:** the Conflicts row becomes `<Link href="/conflicts">` with
  `aria-current="page"` when active. "Coming soon" goes.
- **Bottom tab:** the Conflicts slot becomes `<a href="/conflicts">` with
  `aria-current="page"` and the terracotta underline when active.

Both use the existing `SidenavItem` / `TabSlot` components — they already support
`href` and `active`; only the call sites change.

### D8 — Section presence follows the data

- **Active absent** when there are no active pairs but there are resolved ones
  (EXPERIENCE.md: *"For a user with resolved-but-no-active pairs, the Resolved section
  renders; Active is absent."*).
- **Resolved absent** when there are no resolved pairs (symmetry — a page that says
  "Resolved (0)" over an empty list is a section that says nothing).
- **Both absent** → the empty state: **"No overlaps."** + the microcopy link
  *"Conflicts appear here as you save events."* and a `Text.Meta` **"What counts as a
  conflict?"** link.

### D9 — The accessible name says the action and its consequence

Each action's `aria-label` names the action and what it will do to *this* pair:

- `"Move Work standup to a different time"` (the mockup's own wording)
- `"Skip Designers coffee chat"`
- `"Keep both events. The conflict indicator remains on both."`

These are built by the shared `resolutionAria(resolution, context)`, so the sheet and
the review surface cannot drift.

### D10 — The page is signed-in only, like `/timeline`

`getSession()` → `homeRoute(session)` redirect for anonymous / half-onboarded users; an
unreadable session renders the error state (never somebody else's conflicts).

---

## 3. Files

### New

| File | What |
|---|---|
| `frontend/lib/conflict-wording.ts` | The shared wording module (D1): hints, glyphs, `resolutionAria`, `reviewActionLabel`, and the sheet's labels derived from it. |
| `frontend/lib/conflict-wording.test.ts` | The wording's unit tests. |
| `frontend/lib/conflict-list-read.ts` | The server read (D4): `readConflicts()` → `{kind:"pairs", pairs}` \| `{kind:"unavailable"}`. |
| `frontend/lib/conflict-list-read.test.ts` | Cookie forwarding, the path, the failure modes. |
| `frontend/app/conflicts/page.tsx` | The server page (D4, D5, D10). |
| `frontend/app/conflicts/page.test.tsx` | Page-level tests: heading, sections, counts, empty, error. |
| `frontend/components/conflicts/conflicts-panel.tsx` | The client island (D3, D5, D6). |
| `frontend/components/conflicts/conflict-pair-card.tsx` | One active pair: two sides side by side + the actions. |
| `frontend/components/conflicts/conflict-side.tsx` | One side: stripe + "Personal"/"Public event" + name + local time. |
| `frontend/components/conflicts/resolved-pair-row.tsx` | One resolved pair: history, no affordance. |
| `frontend/components/conflicts/conflicts-states.tsx` | The empty / skeleton / error states. |
| `frontend/components/conflicts/conflicts-panel.test.tsx` | Each action wired to the right request; Move opening the sheet; failure staying active. |
| `frontend/components/conflicts/conflict-side.test.tsx` | The stripe/label pairing; the unavailable side. |
| `frontend/tests/conflicts-a11y.test.tsx` | The axe-core gate + the 44px target check. |

### Modified

| File | What |
|---|---|
| `frontend/components/sheets/conflict-resolution.tsx` | Imports the shared wording module; its local `RESOLUTION_LABELS`/`RESOLUTION_GLYPHS` go (D1). |
| `frontend/components/sheets/conflict-resolution.test.tsx` | Updated for the extraction; the wording must not change. |
| `frontend/components/personal-events-panel.tsx` | A driven `highlightStartTime` (D3), so a driving surface can open the sheet with the time highlighted. |
| `frontend/components/shell/sidenav.tsx` | Conflicts becomes a real link (D7). |
| `frontend/components/shell/bottom-tab-nav.tsx` | Conflicts becomes a real link (D7). |
| `frontend/components/shell/timeline-nav.test.tsx` | Renamed/extended: the nav test now covers the Conflicts link in both rails. |

---

## 4. Acceptance criteria → implementation

| AC | How |
|---|---|
| Heading + sections | `<h1>These days overlap.</h1>`; `<h2>Active (n)</h2>` / `<h2>Resolved (n)</h2>`. |
| Active pair shows both sides side by side | `conflict-pair-card.tsx`: a 2-column grid, each side a `conflict-side.tsx` with a 2px stripe + a visible "Personal"/"Public event" label + the name + the local time. **Colour is never the sole carrier** (WCAG 1.4.1). |
| The actions the API allows, FR-33 wording | `pair.actions` is mapped through the shared module; a name outside the closed set renders nothing. |
| Choosing an action posts the resolution | The island posts `{resolution, side:{kind,id}}` — the side from D2. |
| Move opens the personal side with the time highlighted | `edit_new` → personal side; `update_existing` → the other side; the island opens the driven panel with `highlightStartTime` true. |
| After success the page re-reads | `router.refresh()` (D4). |
| A failed action says so calmly, pair stays active | D6. |
| Resolved pair is history | `resolved-pair-row.tsx`: both sides, the resolution in words, a `Text.Meta` timestamp, **no button**. |
| "No overlaps." / skeleton / error | `conflicts-states.tsx`. |
| No auto-refresh | No timer anywhere; the only re-read is after a write. |
| Conflicts is a real link in both rails | D7. |
| Accessible names say the action and its consequence | D9, from the shared module. |
| axe passes; ≥44px targets | The a11y test file; the action buttons use `py-3` + `px-4` (≥44px tall). |
| Tests | The five test files above. |

---

## 5. Test plan

1. `frontend/lib/conflict-wording.test.ts` — the label and aria builders; the side
   picker; a resolution outside the closed set is rejected.
2. `frontend/lib/conflict-list-read.test.ts` — cookie forwarding; `GET /conflicts`; the
   three failure modes are `unavailable`, never "empty".
3. `frontend/app/conflicts/page.test.tsx` — heading; both sections with their counts;
   Active absent when empty; Resolved absent when empty; "No overlaps."; the error state.
4. `frontend/components/conflicts/conflicts-panel.test.tsx` — each action posts the right
   resolution **and the right side**; Move opens the sheet with the time highlighted; a
   failed action leaves the pair Active and shows the calm message; a success re-reads.
5. `frontend/components/conflicts/conflict-side.test.tsx` — the stripe/label pairing; an
   unavailable side says "Event no longer available".
6. `frontend/tests/conflicts-a11y.test.tsx` — axe over the populated page, the empty page
   and the error page; every action target ≥44px.
7. The nav test — the Conflicts link in both rails, with `aria-current="page"`.

**Gates:** `npx next build` · `npx tsc --noEmit` · `make lint-web` (eslint + tsc +
prettier) · `npx vitest run` (the whole suite, so nothing regressed).

---

## 6. Risks

- **D1's extraction touches the sheet.** The sheet's existing tests pin its wording, so
  a wording drift is caught. The extraction is a move, not a rewrite.
- **D3's driven highlight.** `PersonalEventsPanel` currently owns `highlightStartTime`.
  Adding a driven prop means the panel must **derive** it rather than sync it in an
  effect (React's `react-hooks/set-state-in-effect` rule). The driven path resolves
  during render, as the panel's editing state already does.
- **The `kind` → side mapping.** A pair's kinds decide which side each action targets.
  The mapping is unit-tested against all four kind combinations (personal/personal,
  personal/saved, saved/saved, and the duplicate kind).
