---
id: frontend-personal-and-conflict-surfaces
title: Personal Event & Conflict Resolution Frontend Surfaces
intent: personal-events-and-saved-catalog
complexity: medium
mode: confirm
status: completed
depends_on:
  - personalization-write-services
created: 2026-10-29
run_id: run-eventpulse24-019
completed_at: 2026-10-29T05:14:06.298Z
---

# Work Item: Personal Event & Conflict Resolution Frontend Surfaces

## Description

Builds the three user-facing surfaces this intent needs:

- **`Sheet.PersonalEventCreate`** — the create form.
- **`Sheet.PersonalEventEdit`** — the edit form, with the conflicting time pre-highlighted when the user chose "Edit the new one".
- **`Sheet.ConflictResolution`** — the forced three-action conflict prompt.

The UX spine specifies all three in detail, and the mockups already exist. This work item **implements the existing design**; it does not design a new one.

The conflict prompt is the app's first test of the calm promise. FR-58 is explicit: exactly three buttons, **no dismiss, no X**, and the creation flow cannot complete until the user picks one. The prompt is informational once resolved — the amber indicator persists on both cards after "Keep both" — and it never auto-dismisses.

The design tokens this work item needs **already exist** in `frontend/styles/tokens.css`, in both the light and dark themes:

```css
--color-warm-personal: #a8765c;   /* light */
--color-warm-personal: #c8967a;   /* dark  */
--color-warn-amber:    #b8893d;   /* light */
--color-warn-amber:    #d8a86a;   /* dark  */
```

## Acceptance Criteria

- [ ] **`Sheet.PersonalEventCreate`** exists as a `<dialog>`-based sheet, following the UX spine. Fields: name, start date, start time, an **explicit timezone selector**, optional end time, location, notes. The timezone is a first-class required field, not an inferred browser default.
- [ ] **`Sheet.PersonalEventEdit`** reuses the create sheet's field vocabulary and supports the "conflicting time pre-highlighted" state.
- [ ] **`Sheet.ConflictResolution`** presents **exactly three** actions, matching the PRD's labels: "Keep both — I'll manage", "Edit the new one" (relabelled "Update the existing one" for duplicates), "Delete the new one". There is **no dismiss button, no X button, and no backdrop-click-to-close**. The user cannot complete the flow without choosing one.
- [ ] For a **duplicate** prompt, the second action is relabelled "Update the existing one" and opens the *existing* event in edit mode, not the new one.
- [ ] The conflict sheet's copy follows the UX spine's verbatim strings: header "These overlap.", subhead "You've already saved {conflicting event name}. Choose how to handle it." (for the saved-public-event case), and the header variant "This overlaps with another event." The voice is calm — no alarm words, no exclamation marks.
- [ ] The conflict sheet shows the two affected events as small stacked cards, each with the amber conflict dot, and the new event marked "NEW" in a terracotta pill.
- [ ] The conflict dot is a **filled circle** in `--color-warn-amber`, 8–10px, positioned top-right, with `aria-label="Schedule conflict"`. It is **never red** and never uses `--color-signal-warn` for a different meaning.
- [ ] **Colour is never the sole carrier of meaning.** The warm-personal stripe is always paired with the visible text label "Personal"; the conflict dot always carries its `aria-label`; distinctness from the Source Badge and the Confidence Pulse is by **shape and position**, not colour.
- [ ] The conflict sheet is the **single overlay level** — above the bottom-tab nav on mobile and above the sidenav on desktop, so the user cannot navigate away from a forced choice.
- [ ] The sheet's live region announces "Schedule conflict. Three choices." on open (`aria-live="assertive"`), and focus moves to the header.
- [ ] Each action button has an `aria-label` describing both the action and its consequence, e.g. "Keep both events. The conflict indicator remains on both."
- [ ] The prompt **persists**: backgrounding it and returning leaves it open. There is no timeout that auto-dismisses it.
- [ ] The delete action requires a **confirmation** before the deletion completes (FR-58).
- [ ] Personal events use `--color-warm-personal` for their stripe/label, matching `component.card.pulse.digest.category.personal` and `component.timeline.event-block`.
- [ ] The UI follows the project conventions: **no component library**, no animation library, vanilla components over the CSS custom-property token layer, `<dialog>` for modals and sheets, a hand-rolled tooltip. One 240ms opacity transition only, collapsing to `transition: none` under `prefers-reduced-motion`.
- [ ] No new colour tokens, no new hex values and no new CSS variables are introduced. Every colour used is already in `tokens.css`.
- [ ] The API is reached only through `lib/backend-client.ts` (`openapi-fetch` over the generated `paths`), typed from the regenerated `lib/api/schema.ts`.
- [ ] Vitest tests cover: the form's required-timezone validation; the three conflict actions and their labels; the duplicate relabelling; the absence of a dismiss affordance; the `aria-label`s; and the warm-personal colour pairing.
- [ ] An accessibility test (or the existing axe setup) confirms the conflict sheet has no keyboard-reachable dismiss path.

## Technical Notes

The mockups are the visual source of truth and already exist:

- `mockups/personal-event-create-desktop.html`
- `mockups/personal-event-edit-desktop.html`
- `mockups/conflict-prompt-desktop.html`
- `mockups/conflict-indicator-card-state-desktop.html`

Read them before writing the components. The UX spine (`EXPERIENCE.md` §`Sheet.ConflictResolution`) documents the behaviour these mockups show — the "Pulse Card sync after resolution" paragraph, for example, specifies that on any of the three actions the Pulse Card cache for **both** events in the pair is invalidated, and that the Timeline event-blocks sync on the next Timeline render with no manual refresh.

**On the Pulse Card.** The conflict indicator on a Pulse Card is the Pulse Digest intent's card. This work item builds the sheet and the resolution behaviour, and makes the indicator's **data** available and correct. If the digest card does not exist yet, the indicator is proven in the conflict sheet's stacked cards and in the saved-events list instead. Do not build a second, divergent Pulse Card implementation here — that is the exact failure mode the intent brief warns about when it defers FR-19.

**The `a { color: inherit; text-decoration: none; }` reset.** The UX spine records a real bug from the 2026-09-06 mockup migration batch: pages that gained the sidenav shell without the link reset showed browser-default underlines under every nav item. `personal-event-edit-desktop.html` was one of the affected files. If any sidenav shell is applied in this work item, the reset must go in with it.

**Where surfaces live.** The frontend is a Next.js App Router app. The existing routes are `app/page.tsx` and `app/dev/health/`. Personal events are a modal sheet reached from a nav item ("Add" in the six-route sidenav), not a standalone route — the UX spine's sidenav is Digest / Timeline / Add / Browse / Conflicts / Settings, where "Add" opens `Sheet.PersonalEventCreate`. Building an `/add` **route** as well would create two entry points for the same surface.

**Server components.** The stack is "Server components + the generated API client. No global client state library". The create/edit/conflict sheets are interactive, so they are client components. The list of personal events can be a server component reading through the API client. Do not introduce a state library for this.

## Dependencies

- personalization-write-services
