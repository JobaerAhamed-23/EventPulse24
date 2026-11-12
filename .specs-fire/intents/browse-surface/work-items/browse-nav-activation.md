---
id: browse-nav-activation
title: Retire the Three "Coming Soon" Stubs
intent: browse-surface
complexity: low
mode: autopilot
status: pending
depends_on: [frontend-browse-shell-and-grid]
created: 2026-11-12
---

# Work Item: Retire the Three "Coming Soon" Stubs

## Description

Three places render Browse as an inert `<span aria-disabled="true">` with a "Coming soon"
note, because a link to a 404 would be a lie. Once `/browse` exists, the lie inverts: the
stub now claims there is nothing there when there is.

This item flips all three to real links and deletes the inert-row machinery that only Browse
used.

## Acceptance Criteria

- [ ] `components/shell/sidenav.tsx:96` becomes a real `SidenavItem` with `href="/browse"`
      and an `active` rule, like every other route row
- [ ] `components/shell/more-menu.tsx`'s inert row becomes a real link, and the sheet row
      carries `aria-current="page"` when Browse is the current route — the **More** control
      itself still carries none, because it is a control and not a route
- [ ] `components/shell/bottom-tab-nav.tsx`'s Browse handling is updated, and the
      visually-hidden "Coming soon" text is removed where it referred to Browse
- [ ] **No `aria-disabled` Browse row remains anywhere** — asserted by a test
- [ ] The inert-row component or branch is deleted if Browse was its only remaining user; if
      another route still needs it, it stays and the run log says which
- [ ] The doc comments that explain *why* Browse was inert are updated rather than left
      describing a state that no longer exists — `sidenav.tsx:32` and `more-menu.tsx:19` both
      say "Browse is not built yet" in prose
- [ ] The existing `nav-routes.test.tsx` is updated and still asserts the locked six-route
      order: Digest / Timeline / Add / Browse / Conflicts / Settings
- [ ] The onboarding five-route variant is **unchanged** — it omits Browse on purpose, and
      that is still correct

## Technical Notes

The rule these components state is worth preserving in the edit: an inert route is a
`<span>`, not an anchor with `aria-disabled`, because *"the attribute is a hint, not a
mechanism"*. Nothing here should weaken that rule for whatever route is deferred next.

`g b` is **not** in scope. No keyboard shortcut layer exists in this frontend — a search for
`keydown` handlers found none — so `g b` would be the only member of a six-shortcut set.
It is deferred to its own intent, as recorded in the brief.

## Dependencies

- frontend-browse-shell-and-grid
