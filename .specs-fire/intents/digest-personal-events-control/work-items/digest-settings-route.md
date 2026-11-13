---
id: digest-settings-route
title: The Route — A Place for the Toggle to Live, and a Way to Find It
intent: digest-personal-events-control
complexity: medium
mode: confirm
status: completed
depends_on:
  - digest-preference-read-helper
  - personal-events-digest-toggle
created: 2026-11-13
run_id: run-eventpulse24-030
completed_at: 2026-11-13T01:33:17.124Z
---

# Work Item: The Route — A Place for the Toggle to Live, and a Way to Find It

## Description

The toggle is a control without a page. This item puts it on one.

**The house pattern for a settings route** is uniform across all four existing routes —
`account`, `collections`, `quiet-hours`, `reminders` — and this item follows it exactly:

1. `export const dynamic = "force-dynamic"` — a settings screen is per-user and never cached
2. `const session = await getSession()`, then `const destination = homeRoute(session)`;
   `redirect(destination)` if it is not null — an anonymous visitor goes to `/preview`, a
   half-onboarded one to `/onboarding`
3. If `session.kind !== "signed-in"`, render `<AppShell name="" email=""><SettingsStates /></AppShell>`
4. Read the data; if the read is `"unavailable"`, render `<AppShell name={displayName(...)} email={...}><SettingsStates /></AppShell>`
5. Otherwise render the page inside `AppShell`, with a header (`h1` + a one-line lede) and a content block capped at `max-w-(--layout-container-reading)`

`SettingsStates` (`components/settings/settings-states.tsx:14`) is the failure surface:
"Couldn't load your settings." plus a "Back to Pulse Digest" link.

**The discoverability problem is this item's real content.** There is **no `/settings`
index page** and **no settings sub-navigation** — `sidenav.tsx:131` states the convention
outright ("There is no `/settings` index page"), and the collections page records it
again: *"DESIGN.md's rule forbids adding routes to the nav."* The sidenav's single
"Settings" entry points at `/settings/reminders` and is active on every `/settings/*`
route.

So a new `/settings/digest` route would be **reachable but not discoverable**: a user
who wants to change what appears in their digest has no way to find the control, because
nothing in the UI lists the settings routes and nothing links to this one.

## Acceptance Criteria

- [x] A settings route exists that hosts the toggle, following the five-step house pattern above without deviation
- [x] The route is `force-dynamic`, redirects anonymous and half-onboarded visitors, and renders `SettingsStates` for both the not-signed-in and the unavailable-data case
- [x] The route has a sibling `loading.tsx`, as the other three settings routes do
- [x] The route's header carries an `h1` and a one-line lede that says what the screen is for, matching the other settings pages' tone
- [x] The page renders the toggle with the stored value on first paint
- [x] **The route is discoverable** — a user can reach it from the UI without knowing the URL. At minimum, a link from an existing settings page
- [x] **The sidenav is not modified.** Its active rule is already a prefix match on `/settings/`, so it needs no change, and `DESIGN.md`'s rule forbids adding nav rows
- [x] A test asserts the page renders the toggle's stored state, and that an anonymous request is redirected rather than served

## Technical Notes

- **Read `displayName()` from an existing route rather than re-deriving it.**
  `app/settings/reminders/page.tsx` has a local `displayName(email)` that takes the
  local part of the email, splits on `.`, `_` and `-`, and title-cases the parts. It is
  duplicated per route today — check whether the quiet-hours and collections routes have
  their own copies. If they do, **follow the existing pattern rather than refactoring
  them**; extracting a shared helper is a different change and is not in this intent's
  scope. If they already share one, reuse it.
- **Do not build a `/settings` index.** The convention is explicit and stated in two
  places. This item respects it.
- **Do not add a settings sub-nav.** Same reason. The `DESIGN.md` rule forbids adding
  routes to the nav, and the sidenav's prefix-match active rule already works.
- **Where the discoverability link goes.** The quiet-hours page already carries a
  "Pulse Digest" section (`app/settings/quiet-hours/page.tsx:150`), which makes it the
  natural place for a link to the digest settings. The reminders page is the sidenav's
  default target, so it is the other candidate. **Choose one, and do not add links to
  both** — a link in two places is two places to keep in sync.
- **If the route is `/settings/digest`, the sidenav needs nothing.** `sidenav.tsx:138-143`
  renders one `SidenavItem` with `href="/settings/reminders"` and
  `active={pathname.startsWith("/settings/")}`. A new `/settings/*` route is automatically
  marked active. This is the same rule the collections page relies on
  (`app/settings/collections/page.tsx:20-23`).
- **A "Back to Pulse Digest" link already exists inside `SettingsStates`** — do not add a
  second one.
- **Watch the `AppShell` props.** Every route passes `name` and `email`. The
  not-signed-in case passes empty strings; the unavailable case passes the real ones.
  This differs across the existing routes — match `reminders`, which is the sidenav's
  default target and therefore the most-seen settings page.

## Dependencies

- digest-preference-read-helper
- personal-events-digest-toggle
