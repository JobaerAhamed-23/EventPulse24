---
id: profile-screen-and-editor
title: The Profile Screen — a Section, a Route and an Editor
intent: account-profile-name
complexity: medium
mode: confirm
status: completed
depends_on:
  - profile-endpoint-and-contract
created: 2026-11-13
run_id: run-eventpulse24-032
completed_at: 2026-11-13T12:01:15.386Z
---

# Work Item: The Profile Screen — a Section, a Route and an Editor

## Description

**A new `/settings/profile` screen** with one thing on it: the name, editable in place.

### The section registration

`frontend/lib/settings-sections.ts` — the **one list** that both the settings index and
the sub-nav render. Add:

```ts
{
  href: "/settings/profile",
  label: "Profile",
  description: "Your name, and how we address you.",
}
```

**Placement: after `Account`**, the last entry. The mockup order
(`settings-desktop.html`) runs Notifications → Quiet hours → Calendar sync → Account, and
Profile is the account-adjacent section.

**Two docstrings in that file state counts and reasons this change invalidates**, and
they must be corrected rather than left to rot:
- the module docstring's *"Six `/settings/*` routes shipped one at a time"* — there are
  seven now;
- the *"Appearance, Privacy and Danger zone are not here"* paragraph — still **true**
  (none of those three are built), and its point is that **a row for a route that does
  not exist is the 404 link this whole file exists to prevent**. Profile is a route that
  *does* exist, so it belongs in the list; the paragraph's reasoning is unchanged even
  as the count moves.

`frontend/tests/settings-routes.test.ts` is **data-driven** and passes automatically once
the list and the page are both in place. It asserts in **both directions**: every section
in the list resolves to a real `page.tsx`, and every directory under `app/settings` with
a `page.tsx` is in the list. **Both halves must hold** — a page without a row fails the
second, a row without a page fails the first.

### The route

`frontend/app/settings/profile/page.tsx` — a server component, following the exact
five-step shape every other settings route uses:

1. `export const dynamic = "force-dynamic";`
2. `const session = await getSession(); const destination = homeRoute(session); if
   (destination !== null) redirect(destination);` — `redirect` throws, so it is called
   **outside** any try/catch.
3. The not-signed-in branch → `<AppShell name="" email=""><SettingsStates /></AppShell>`
4. The `unavailable` branch → `<AppShell name={…} email={…}><SettingsNav /><SettingsStates /></AppShell>`
5. The content → `<AppShell name={…} email={…}><SettingsNav />` + `<header>` with the
   `<h1>` and a subheading + the editor.

**`tests/settings-routes.test.ts:102-145` asserts this shape.** Every settings page must
have **≥2** `<AppShell name={…} email={session.user.email}>` branches, **each immediately
followed by** `<SettingsNav />`. A page that misses the shape fails the test — and the
reason the rule exists is that a settings screen without the sub-nav is a dead end.

`frontend/app/settings/profile/loading.tsx` — the same `data-settings-skeleton` shape as
the other routes (`app/settings/account/loading.tsx`). **No spinner** —
`frontend/styles/motion.test.ts` bans motion other than `.fade-in`.

### The editor

`frontend/components/settings/profile-name.tsx` — a client island, following the
inline-save pattern exactly (`components/settings/digest-delivery-time.tsx`,
`quiet-hours-window.tsx`):

- `"use client"`; one prop, `initialName: string`.
- State: `value`, `busy`, `saved: boolean`, and `failure: string | null` — **the failure
  is the message string, not a boolean**, so the API's own refusal is shown verbatim.
- A module-level `const FAILURE = "Couldn't save.";` — the route's own offline line.
- `save()`: `await api.PUT("/api/auth/profile", { body: { name: value } })`. On
  `response.error` → `setFailure(saveFailureMessage(response.error, FAILURE))` (from
  `components/settings/save-failure.ts:35`). On success → `setSaved(true)`.
- Renders `<SaveFeedback busy={busy} saved={saved} failure={failure} />` (from
  `components/settings/save-feedback.tsx`) — `role="status"` for the success, `role="alert"`
  for the failure, `data-save-failed`, and the **static** dot (`data-saving-dot`).
- **Saves on change, with no Save button** — the same control-saves-on-change rule the
  other settings islands follow.

**The failure split matters.** `saveFailureMessage` returns the API's message when the
body is the project error shape and the offline line otherwise. A user who typed a name
with a newline and was refused by the backend must read *the backend's refusal*, not
"Couldn't save."

## Acceptance Criteria

- [ ] `/settings/profile` exists and renders its own `<h1>`
- [ ] The section is in `SETTINGS_SECTIONS`, labelled "Profile", described as "Your name,
      and how we address you.", and placed after "Account"
- [ ] `tests/settings-routes.test.ts` passes — **both** directions: the list resolves to a
      real page, and the page is in the list
- [ ] The page has the exact settings-route shape: ≥2 `<AppShell name={…}
      email={session.user.email}>` branches, each immediately followed by `<SettingsNav />`
- [ ] The page redirects an anonymous visitor the way the other settings routes do
- [ ] The page has a `loading.tsx` with the `data-settings-skeleton` shape, and **no
      spinner** anywhere in it
- [ ] The editor saves through `api.PUT("/api/auth/profile", { body: { name } })`, and
      **not** through `fetch` and **not** through a hand-written URL
- [ ] A successful save shows "Saved." and a failed save shows a message — **the API's
      message when the API refused**, the offline line when the request never arrived
- [ ] The editor has **no Save button** — it saves on change, like the other islands
- [ ] The saving indicator is the **static dot** (`data-saving-dot`), not a spinner
- [ ] The failure is announced with `role="alert"` and carries `data-save-failed`
- [ ] The editor is a **client component**; the page stays a server component
- [ ] Tests cover: rendering the current name, a successful save, an API error, a thrown
      request, and the save payload — each verified by a mutation probe that makes it
      fail
- [ ] `frontend/app/settings/profile/page.test.tsx` covers the signed-in branch, the
      signed-out branch, and that `AppShell` receives the **stored** name when one is set
- [ ] No Tailwind class outside the token set, and no `transition-*` / `duration-*` /
      `delay-*` / `ease-*` / `animate-*`

## Technical Notes

- **Copy `app/settings/account/page.tsx` as the page's shape**, and
  `app/settings/digest/page.tsx` as the shape of a page with a form island on it.
- **The page test's style is `app/settings/account/page.test.tsx`**: a partial
  `vi.mock("@/lib/session", …)` that keeps `homeRoute` real, a `USER` fixture, and
  `render(await SettingsProfilePage())` — an async server component awaited in the test.
- **The island test's style is `components/settings/settings-inline-save.test.tsx`**:
  `vi.mock("@/lib/backend-client", () => ({ api: { PUT: (...args) => PUT(...args) } }))`
  and assert on `PUT.mock.calls[0]?.[1]?.body`.
- **The `USER` fixture needs a `name`.** It is typed against the regenerated
  `components["schemas"]["CurrentUserOut"]`, so `tsc` flags it. Add `name: ""` to the
  fixture in **every** test file that has one — the profile page test, the session test
  (`frontend/lib/session.test.ts`), and the settings page tests.
- **Vitest globals are off** — always import `describe`/`it`/`expect`/`vi`/`beforeEach`
  from `vitest`.
- **The editor does not own the session.** It receives `initialName` as a prop from the
  server page; it does not call `me` itself. The server already has the session.

## Dependencies

- `profile-endpoint-and-contract` — the editor calls `PUT /api/auth/profile`, and the
  page reads `session.user.name`, which only exists once `CurrentUserOut` carries it.
