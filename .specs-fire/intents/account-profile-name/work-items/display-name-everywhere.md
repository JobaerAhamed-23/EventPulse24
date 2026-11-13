---
id: display-name-everywhere
title: The Name Everywhere — One Helper, and Thirteen Pages That Stop Carrying
  Their Own
intent: account-profile-name
complexity: medium
mode: confirm
status: completed
depends_on:
  - profile-endpoint-and-contract
created: 2026-11-13
run_id: run-eventpulse24-032
completed_at: 2026-11-13T12:34:19.890Z
---

# Work Item: The Name Everywhere — One Helper, and Thirteen Pages That Stop Carrying Their Own

## Description

**The stored name has to reach the rail on every page.** `AppShell` takes a `name` prop
and threads it to `Sidenav` and `BottomTabNav` — the rail's account row and the mobile
bottom bar. Every page passes `name={displayName(session.user.email)}`, and
**`displayName` is copy-pasted into 13 files.**

Each copy is the same rule: take the email's local part, split it on `.`, `_` and `-`,
capitalise each word, join with spaces. `maya.ahmed@example.test` → `"Maya Ahmed"`. If
the local part has no separators, it is the whole local part, capitalised. If the local
part is empty, it is the email itself.

### The helper

`frontend/lib/display-name.ts` (new):

```ts
export function displayName(user: { name: string; email: string }): string
```

- `user.name` is non-empty → **that name**.
- Otherwise → **the existing email-local-part rule, verbatim**.

**The fallback is carried over byte-for-byte.** That is the point: **no existing screen
changes appearance** for anyone who has not set a name. The rule is not "close enough" —
it is the same function, and a test pins it.

**Why it has to become shared.** The fallback rule ("stored name if set, else
email-derived") must be applied in all 13 places. Pasting it a 14th time would make the
rule a thing that can differ from itself, in thirteen places, silently.

### The thirteen call sites

Every one of these changes from:

```tsx
<AppShell name={displayName(session.user.email)} email={session.user.email}>
```

to:

```tsx
<AppShell name={displayName(session.user)} email={session.user.email}>
```

and its **local `displayName` function is deleted**.

| File | Local helper at |
| --- | --- |
| `frontend/app/page.tsx` | 227 |
| `frontend/app/browse/page.tsx` | 167 |
| `frontend/app/conflicts/page.tsx` | 90 |
| `frontend/app/timeline/page.tsx` | 162 |
| `frontend/app/settings/page.tsx` | 126 |
| `frontend/app/settings/reminders/page.tsx` | 89 |
| `frontend/app/settings/quiet-hours/page.tsx` | 184 |
| `frontend/app/settings/digest/page.tsx` | 129 |
| `frontend/app/settings/calendars/page.tsx` | 78 |
| `frontend/app/settings/collections/page.tsx` | 137 |
| `frontend/app/settings/account/page.tsx` | 116 |
| `frontend/app/personal-events/[id]/reminders/page.tsx` | 118 |
| `frontend/app/events/[id]/page.tsx` | 663 |
| `frontend/app/events/[id]/reminders/page.tsx` | 119 |

**Two of these are not the same shape.** `app/events/[id]/page.tsx:583` and
`app/events/[id]/reminders/page.tsx:39` and
`app/personal-events/[id]/reminders/page.tsx:55` read:

```tsx
const name = session.kind === "signed-in" ? displayName(session.user.email) : "";
```

because those routes serve **both** a signed-in and an anonymous visitor. They become
`displayName(session.user)` inside the same guard — the guard stays, because the
anonymous case still needs the `""`.

### `frontend/lib/session.ts` — no change

`CurrentUser` is `components["schemas"]["CurrentUserOut"]`, so it picks up `name`
automatically once the schema is regenerated. **The session module needs no edit** — and
that is the point of deriving the type from the generated schema rather than writing it
out.

## Acceptance Criteria

- [ ] `frontend/lib/display-name.ts` exports `displayName(user: {name, email})`
- [ ] A user with a stored name gets **that name** — verbatim, not trimmed, not
      re-cased
- [ ] A user with **no** stored name (`""`) gets the **email-local-part rule**, and the
      result is **identical to what the old copies produced** — pinned by a test, not by
      reading
- [ ] The helper handles the empty-local-part case (an email like `@example.test`) by
      returning the email, as the old copies did
- [ ] The helper handles a local part with **no** separators, returning it capitalised
- [ ] The helper handles **each** separator — `.`, `_` and `-` — and a mix of them
- [ ] **All 13 local `displayName` functions are deleted.** No page carries its own copy
- [ ] Every `AppShell` call site passes the shared helper's result
- [ ] The three routes that serve anonymous visitors keep their `session.kind ===
      "signed-in"` guard, and still pass `""` for an anonymous visitor
- [ ] The rail shows the **stored** name on **every** page, not only on the profile
      screen
- [ ] `frontend/lib/session.ts` is **unchanged** — the type comes from the generated
      schema
- [ ] A test proves a user with a stored name sees it in the shell, and a user without
      one still sees the email-derived name
- [ ] Every test is verified by a mutation probe that makes it fail

## Technical Notes

- **`frontend/lib/display-name.ts` is a server-safe module.** It imports nothing — no
  `next/headers`, no `api` — so it can be imported by a server component, a client
  component or a test. **Do not** put it behind a `"use client"` banner.
- **The helper takes the whole user, not two arguments.** `displayName(user)` rather than
  `displayName(name, email)` — because the rule is *"the stored name if there is one,
  otherwise the address"*, and one object makes it impossible to pass the two in the
  wrong order.
- **A stored name of only whitespace is not a name.** The backend trims on write, so a
  stored name is already trimmed; the helper's emptiness check is `name === ""`. If a
  whitespace-only name ever reaches the frontend, trim it there too — but do not
  re-case a stored name.
- **Do not re-case the stored name.** A person's name is theirs; the display rule for
  the *email* exists because an address has no capitals, not because names should be
  capitalised.
- **The `settings-routes.test.ts` rule forbids hand-written `href="/settings…"` in a
  settings page** (line 147-157) — the profile page links nowhere by hand. The
  `SettingsNav` carries the navigation.
- **Two pages read the session twice in different shapes** — `app/settings/collections/page.tsx:61`
  and `app/settings/account/page.tsx:58` bind `const name = displayName(...)` once and
  use it in several `<AppShell>` calls. Keep that binding; only its argument changes.

## Dependencies

- `profile-endpoint-and-contract` — `session.user.name` only exists once
  `CurrentUserOut` carries it, and the regenerated schema is what types it.
