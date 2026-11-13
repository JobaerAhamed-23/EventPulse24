---
id: personal-events-digest-toggle
title: The Toggle — Personal Events In or Out of the Pulse Digest
intent: digest-personal-events-control
complexity: medium
mode: confirm
status: completed
depends_on:
  - digest-preference-read-helper
created: 2026-11-13
run_id: run-eventpulse24-030
completed_at: 2026-11-13T01:23:09.131Z
---

# Work Item: The Toggle — Personal Events In or Out of the Pulse Digest

## Description

Build the control a user actually touches: a button on a settings screen that turns
personal events out of the Pulse Digest, and back on again.

**The constraint that shapes this whole item:** `DigestPreferenceIn` requires
`delivery_time` and `timezone` — they are not optional
(`backend/apps/personalization/schemas.py:653-654`, generated
`frontend/lib/api/schema.ts:2569,2576`). The endpoint has no "patch one field" mode. So
the toggle **cannot send only its own field**: it must read the stored delivery time and
timezone and send them back unchanged alongside the flag.

That round-trip is safe, and it is already the product's rule.
`components/settings/digest-delivery-time.tsx:15-16` says it in its own docstring:

> **The zone travels with the time.** `DigestScheduleIn` says it plainly: *"Both or
> neither. A wall clock without its zone is not a schedule."* So this sends the zone it
> read, unchanged, alongside the new time.

The endpoint honours it: `set_digest_preference()` (`services/onboarding.py:369-372`)
always writes the delivery time and zone, and writes the opt-out **only when the field is
not `None`** — an omitted field means "leave it alone". The audit row it writes
(`onboarding.digest_preference_set`) records the time and zone, and the boolean gets its
own audit row only through the narrow command. **This item therefore reuses the wide
write path and does not touch the backend.**

**Where the control lives is this item's one open decision**, recorded in the brief:
folding it into an existing settings route, or giving it its own `/settings/digest` route.
The trade-off is in the technical notes below.

## Acceptance Criteria

- [x] The toggle renders with the **stored** value — a user who opted out sees it off on load, and a user who never touched it sees it on
- [x] Clicking it saves **inline, with no Save button**, following `digest-delivery-time.tsx`: `idle → saving → saved ✓`
- [x] The save sends `include_personal_events` **together with** the stored `delivery_time` and `timezone`, unchanged — the "both or neither" rule
- [x] The save sends **no other field** — no `city`. A test asserts the body has exactly three keys
- [x] The toggle's state after a save is **the server's answer**, not the user's optimistic guess
- [x] A failure shows the failure line: the API's own message when the API refused, and the route's own line when the request never arrived — the `saveFailureMessage(error, offline)` split
- [x] The button is a `<button type="button">` with **`aria-pressed`** carrying the state and a **stable accessible name** — the house pattern from `components/state/detail-mute-control.tsx:86-101`, explicitly **not** `role="switch"`
- [x] The visible text beside the control says which state it is in, so state is never carried by colour alone
- [x] The control uses **existing design tokens only** — no new hex, no new CSS variable, no new spacing token
- [x] The toggle's own button **does not use `bg-warm-personal`** — `pulse-card.test.tsx:220-228` asserts interactive surfaces never carry stripe colours
- [x] A test asserts the body of the PUT, that no other field was sent, that success shows "Saved.", and that failure shows the failure line
- [x] A test asserts the accessible name is stable across both states and that `aria-pressed` flips

## Technical Notes

- **The house toggle pattern is `<button>` + `aria-pressed`.** There is **no** switch,
  checkbox, or `role="switch"` component in the codebase — a grep for `role="switch"`,
  `type="checkbox"`, and `role="checkbox"` returns zero hits outside comments.
  `components/state/detail-mute-control.tsx` is the closest precedent: a stable
  `aria-label`, `aria-pressed={isMuted}`, visible text that flips, optimistic local state
  with rollback on failure, and a `busy` disable.
- **`reminders/reminder-picker.tsx:20` records why.** The chips are `<button>`s with
  `aria-pressed`, *not* the mockup's `role="switch"` toggles. The docstring says the
  Detail Screen used to use `role="switch"`. The house decision was made and written down;
  this item follows it rather than reopening it.
- **Round-trip the two required fields.** Read them from the helper and send them back
  unchanged. The stored `delivery_time` is `HH:MM:SS`; `DigestPreferenceIn.delivery_time`
  is a `time`, and `_validated_delivery_time` (`services/onboarding.py:216-226`) refuses a
  tz-aware time — so send the **wall clock** exactly as read, never a zoned instant.
- **Do not invent a "patch" endpoint.** The narrow command
  `set_include_personal_events()` (`services/digest_preferences.py:259-285`) exists and is
  tested, but **it is not wired to any endpoint**, and the endpoint that is wired
  (`put_digest_preference` → `set_digest_preference`) always writes time and zone. Adding
  an endpoint is a backend change, which this intent forbids.
- **Use `SaveFeedback` as-is.** Its props are `{ busy, saved, failure }` — fully generic,
  not time-shaped. Success is `"Saved."` in a `role="status" aria-live="polite"` div; a
  failure is a `role="alert"` paragraph; busy is a static dot (no spinners, per
  `EXPERIENCE.md`). The route's failure line should be `"Couldn't save."`, matching
  `digest-delivery-time.tsx:47`.
- **One status region per page.** `detail-mute-control.tsx:215-228` forbids a second
  `role="status"` on a page. If the toggle lands on a route that already has one, reuse
  it rather than adding another.
- **Tokens.** `frontend/styles/tokens.css` resets Tailwind's palette entirely via
  `@theme static { --color-*: initial; ... }`, so only the declared tokens exist as
  utilities. `styles/tokens.test.ts` pins every colour against `DESIGN.md` — **adding a
  hex means editing `DESIGN.md` too**, and this item adds no colour.
- **Route placement — the open decision.** Two options:
  - **(a) Fold into an existing settings route.** `/settings/reminders` and
    `/settings/quiet-hours` are standalone pages with no shared settings layout
    (`find app -name layout.tsx` returns only `app/layout.tsx`). Adding a section to one
    of them needs no new route, no sidenav change, and no discoverability work — but
    mixes digest-content preferences into a page about something else.
  - **(b) A new `/settings/digest` route.** The sidenav needs **no change** — its active
    rule is a prefix match on `pathname.startsWith("/settings/")` (`sidenav.tsx:141`), so
    the route marks Settings active automatically. But **there is no settings index and no
    settings sub-nav**, so a new route is *reachable* and *not discoverable*; it needs a
    link from somewhere, and the settings pages have no natural cross-link today.
  - **Recommendation: (b)**, on the condition that the item adds a discoverable link
    (e.g. from the quiet-hours page, which already carries a "Pulse Digest" section at
    `quiet-hours/page.tsx:150`). A dedicated route matches how the product has been
    building — one route per settings concern, each a standalone page — and it leaves
    room for FR-7's delivery-tolerance work later without crowding an unrelated page.
    If (b) is chosen, the route also needs a sibling `loading.tsx`, as the other three
    settings routes have.
- **Do not touch `frontend/lib/api/schema.ts` or `openapi.json`.** No backend schema
  change, so no regeneration. `make client` followed by
  `git diff --exit-code frontend/lib/api/` must stay clean — that is the AD-19 CI gate.

## Dependencies

- digest-preference-read-helper
