---
id: timeline-and-conflicts
title: Unified Timeline & Conflict Review
status: completed
created: 2026-10-31
completed_at: 2026-10-31T10:27:58.269Z
---

# Intent: Unified Timeline & Conflict Review

## Goal

Ship the two MVP surfaces Amendment A-8 lifted from Phase 2 and the app still shows as "Coming soon": the **Unified Timeline** at `/timeline` (FR-32) and the **Conflict Review** at `/conflicts` (FR-33) — and make **every** conflict on them answerable, including the ones that involve a saved public event.

It realizes UJ-2 ("see what your week looks like before it happens") and gives a user's personal events their designed home. Today they have none: they are listed on `/` only by a stopgap added on 2026-10-31, under the digest the spec says must stand alone.

## Users

- **The user planning their week** (Flow 5, UJ-2), who opens Timeline, takes in the week's shape — personal and saved public events on one grid — spots the overlaps, and jumps to the event to fix one.
- **The user reviewing overlaps** (Flow 6), who opens `/conflicts`, sees what is still waiting for a decision and what was decided before, and answers the open ones.
- **The user who just added or saved something**, who needs to see it land somewhere rather than watch a sheet close on nothing.

## Problem

- **Two of the six authed routes are dead labels.** The sidenav and the bottom-tab render Timeline and Conflicts as inert "Coming soon" spans.
- **Personal events have no home.** The FIRE intent that built them (`personal-events-and-saved-catalog`) built the write path and the conflict machine, and no read surface. Until 2026-10-31 an added event was invisible; the fix was a list under the digest on `/`, which the spec's "home is the 3-card brief" rule forbids long-term.
- **Conflicts can be detected but not reviewed.** `ConflictPair` rows exist with `active` / `resolved` / `cleared_by_state_change`, and `ConflictPair`'s own docstring says the Timeline indicator and `/conflicts` read them — yet no endpoint lists them.
- **A conflict involving a saved public event cannot be answered anywhere.** The resolve endpoint takes personal events only (`ConflictResolutionIn`: "a client cannot name a saved event's id"), and its resolutions (`keep_both`, `edit_new`, `delete_new`, `update_existing`) do not include FR-33's "Skip {public event}". So `POST /api/personal/saved-events/{id}` can answer 409 with a pending pair the user has no way to close; the Detail Screen's Save says only "It overlaps …".

## Success Criteria

### Timeline — `/timeline` (FR-32, `Surface.Timeline`, Flow 5)

- **Desktop (`md+`)**: a Mon–Sun **week grid**, each column a time-ordered stack of event-blocks; the header row shows weekday and date in `Text.Meta`; **today's column carries `Indicator.Today`**; a week navigator `←` / `Today` / `→` sits above the grid.
- **Mobile (`sm`)**: a **single-day view** with a centred `← {date} →` day navigator and a "Today" pill (`timeline-mobile.html`).
- It shows the user's **personal events** and **saved public events** for the visible week, read through the existing range-filtered list endpoints.
- Each event-block has a **2px left stripe** — `color.warm.personal` / `color.cool.public` — **and** a visible "Personal" / "Public event" label. Colour is never the sole carrier of meaning.
- Both events of an **active** conflict pair render `Indicator.Conflict` (6px amber, `aria-label="Schedule conflict"`), including the cross-midnight rule: the indicator fires on the day-cell whose interval contains the overlap.
- **Read-only.** Tapping a **public** block routes to `/events/:id`; tapping a **personal** block opens the existing **Edit personal event** sheet. No drag, no inline edit, and tapping an empty day does nothing.
- **States** (EXPERIENCE.md §2): empty day "Quiet day."; empty week "Your week is quiet. Pulse Digest is the place to discover." + one `Text.Meta` "Open Pulse Digest" link; week-row skeletons while loading; "Couldn't reach Timeline. Try again." on error.
- Block `aria-label` carries name + time + "Personal" / "Public event"; focus ring is the terracotta stroke; reduced motion renders instantly.

### Conflict Review — `/conflicts` (FR-33, Flow 6, `conflicts-desktop.html`)

- Heading **"These days overlap."** (locked microcopy, §3); two sections, **Active (n)** and **Resolved (n)**.
- Each **active** pair shows both sides (stripe + label + name + time) and the actions for its kind; choosing one resolves it and the pair moves to Resolved on the next render.
- **Resolved** pairs are immutable history: the pair, the resolution in words ("Skipped public · Poetry reading · Fri Sep 11") and a `Text.Meta` timestamp, with no edit affordance. `cleared_by_state_change` pairs are not presented as a user's choice.
- **States**: "No overlaps." when there are none; skeleton rows while loading; "Couldn't analyze conflicts. Try again." on error. **No auto-refresh** (Flow 6: a passive pressure element).

### Every conflict is answerable (FR-33, FR-58)

- A new **list endpoint** returns the signed-in user's conflict pairs — active and resolved — with each side's kind, name and times, and the allowed actions. It reads only the caller's rows, and crosses into the catalog only through the published services (AD-2/AD-3).
- **Saved-public conflicts can be resolved** with FR-33's three actions: **Move {personal event}** (opens it in the edit sheet with the conflicting time highlighted), **Skip {public event}** (un-saves it), **Keep both — I'll manage**. The resolution is recorded on the pair, and the indicator rules follow FR-58: "Keep both" keeps the indicator as a calm permanent reminder.
- The **Detail Screen** offers the same three-action prompt when a Save clashes — replacing today's "It overlaps …" line — and, for an event in an active pair, from its conflict indicator.

### Navigation and the home page

- Timeline and Conflicts become **real routes** in the sidenav and the bottom-tab, with the active-route ink pill; "Coming soon" goes.
- **`/` returns to the 3-card digest alone.** The stopgap "Your personal events" list is removed. After adding from the header's "+ Add personal event", a calm inline line confirms it with a link to the Timeline, so a save never looks like nothing happened.

### Proof — tests that can fail

- Backend: the conflict list (ownership, both side kinds, statuses, ordering) and the saved-public resolutions, including the 409 → resolve round trip from a save.
- Frontend: week and day layouts, stripe-plus-label pairing, the conflict indicator on both sides, read-only routing, every empty/loading/error state, and the `/conflicts` sections.
- An **end-to-end proof** in the style of earlier intents: create and save overlapping events, see them on the Timeline with indicators, resolve on `/conflicts`, and watch the pair move to Resolved.
- `make client` stays the contract: the generated client is regenerated for the new endpoints and CI's diff check passes.

## Constraints

- **DESIGN.md and EXPERIENCE.md govern**, with `timeline-mobile.html` and `conflicts-desktop.html` as the visual references; where a mockup drifts from the spine, the spine wins (and the user is asked, as with the quick-add colour).
- **Spacing stays on the DESIGN.md scale** — `tests/spacing-scale.test.ts` enforces it.
- **AD-2 / AD-3**: personal and catalog data are joined in the application layer, never by a cross-schema query; `apps.personalization.models` is imported only from `apps.personalization`.
- **AD-19**: the frontend reaches the API only through the generated client; new endpoints go through `make client`.
- **Works fully offline** with the fake adapters (`ADAPTER_MODE=fake`), as every previous intent.
- **Read-only Timeline at MVP** (FR-32): no drag-to-reschedule, no month or day-of-month views, no inline edits.

## Notes

- **Out of scope, later intents:** `/browse`, the `/settings/*` routes, the SEO page `/events/near-me`, `/suggest`, the Detail Screen's right-hand column and reminder picker, Phase 3 conflict work (auto-rebook, suggested slots, public-vs-public conflicts).
- **Decisions captured with the user (2026-10-31):** scope is Timeline + Conflicts as one intent; saved-public conflicts are resolvable in this intent (not read-only); tapping a personal block opens the edit sheet rather than a new personal detail page; the home-page stopgap list is removed once Timeline ships.
- **Known data gap:** personal events created before Asia/Dhaka was offered (2026-10-31) may be stored in UTC; the Timeline shows them at their stored instant.
