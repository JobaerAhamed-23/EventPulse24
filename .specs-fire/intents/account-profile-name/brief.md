---
id: account-profile-name
title: The Account Sheet, Reduced — and a Name Worth Calling Someone
status: completed
created: 2026-11-13
completed_at: 2026-11-13T13:17:30.487Z
---

# Intent: The Account Sheet, Reduced — and a Name Worth Calling Someone

## Goal

Give the account a real, settable **name**, and reduce the account sheet to **who you are
+ what you can do about it**: your name, your email, an "Edit your name" entry, and Sign
out — with the `Settings` and `Pricing` links removed.

## Users

Every signed-in user. The name is how the product addresses someone in the rail, the
bottom bar and the account sheet, and it is the first thing a person wants to change
about an account that only knows them by an address.

## Problem

The account sheet (`frontend/components/shell/account-menu.tsx`) today carries three
things: a `Settings` link, a `Pricing` link, and `Sign out`.

- The **`Settings` link is redundant**. The rail already has a Settings row, and
  `/settings` now exists as an index. The sheet's own docstring admits the link "is for
  the mobile overflow sheet, where this panel renders inline" — but the mobile overflow
  sheet sits *inside* the bottom bar, which itself carries a Settings destination. Two
  ways to the same place, one of them a dead end from the rail's perspective.
- The **`Pricing` link is an upsell in a panel about the account**. `/pricing` is a
  marketing page; the sheet is not the place for it.

But **"Edit your name" needs a name to edit, and the product has no name.** The backend
`User` model (`backend/apps/identity/models.py:23`) has only `email`;
`CurrentUserOut` (`backend/apps/identity/schemas.py:84`) carries only `id`, `email` and
`onboarding`. The frontend derives a display name from the email's local part via a
`displayName()` helper **copy-pasted into 12 separate pages** (`app/page.tsx:227`,
`app/browse/page.tsx:167`, `app/conflicts/page.tsx:90`, `app/timeline/page.tsx:162`,
`app/settings/page.tsx:126`, and each of the 6 settings routes).

So this is two things: the backend gets a settable name, and the frontend gets a profile
screen that edits it while the stored name replaces the email-derived one everywhere it
is displayed.

## Success Criteria

- The account sheet shows the name, the email, an **"Edit your name"** entry and **Sign
  out** — and **neither** a `Settings` row **nor** a `Pricing` row
- A signed-in user can set a name on a new **`/settings/profile`** screen, and the name
  survives a reload
- The stored name is what the sidenav, the bottom bar and every page show; a user with
  **no** name set still sees the email-derived name (the fallback must not blank it)
- The name is a **blank string when unset**, not `null` — "cleared" and "never set" are
  one state, not two
- The name write is a **named command** in `apps/identity/services/`, audited in the same
  transaction, with **no name in the audit details** (AD-5, AD-13)
- The audit row for a name change exists and **its details contain no name**
- `PUT /api/auth/profile` without a CSRF token is refused with 403; an anonymous caller
  is refused with 401
- The generated contract is **regenerated and committed** — `make client` output is in
  the tree, and `backend/tests/api/test_contract.py` is green (AD-19)
- The `displayName()` helper exists **once**, in `frontend/lib/display-name.ts`, and no
  page carries its own copy
- The e2e settings spec reaches `/settings/profile` by **clicking**, and the settings
  sub-nav links to it from every settings screen

## Constraints

- **AD-5** — the name write is a named command in `apps/identity/services/profile.py`,
  not a write in the API layer. `tests/architecture/test_no_direct_writes.py` enforces
  that the API layer touches no ORM.
- **AD-2 / AD-16** — the name field lives on `identity`'s `User`, the app that owns the
  account. `personalization` is not reachable into. `models-identity` (import-linter)
  keeps the model private to its app.
- **AD-3** — the field lives in the `personal` schema with the rest of `User`, and the
  command writes inside `transaction.atomic(using=PERSONAL)`.
- **AD-13** — the name is PII. The audit `details` carries the action and the target id
  and **no free text**; `write_audit`'s own docstring says *"counts and slugs, never free
  text"*.
- **AD-19** — the endpoint is added to Django Ninja and `make client` regenerates
  `frontend/lib/api/openapi.json` + `frontend/lib/api/schema.ts`. The committed schema
  is the contract; `backend/tests/api/test_contract.py:16` compares it to the live one.
- **CSRF** — every unsafe request calls `require_csrf(request)` first. The `/api/auth`
  router has no router-level `auth=`, so the handler calls it explicitly, exactly as
  `me` resolves the user itself.
- **AD-15** — the field is covered by `User.retention_category = ACCOUNT_IDENTITY`
  already; no new retention declaration is needed. The user's own export picks the new
  field up automatically, because the export serialises model fields generically.
- **`PUT`, not `PATCH`** — the frontend has no `api.PATCH` call site anywhere, and
  `/api/settings/notifications` is already a `PUT` with patch semantics. One verb for
  the product's settings writes.
- **The `displayName` fallback is unchanged** — the email-local-part rule is carried over
  **verbatim**, so no existing screen changes appearance for a user who has not set a
  name.
- **No spinner** — `frontend/styles/motion.test.ts` bans motion other than `.fade-in`.
  The settings islands use the **static** saving dot.
- **No `transition-*`, `duration-*`, `delay-*`, `ease-*` or `animate-*`** — the same
  token rule the rest of the frontend follows.
- **Tailwind classes are tokens only** — no arbitrary hex or px values.
- **`/settings/profile` follows the exact settings-route shape**:
  `tests/settings-routes.test.ts:102-145` asserts every settings page has ≥2
  `<AppShell name={…} email={session.user.email}>` branches, each immediately followed
  by `<SettingsNav />`. A page that misses that shape fails the test.

## Notes

**Decisions confirmed with the user** (2026-11-13):

1. The account sheet becomes **Profile link + Sign out only** — `Settings` and `Pricing`
   are removed.
2. The profile editor lives on a **new `/settings/profile` settings section**, not folded
   into `/settings/account`.
3. The stored name **replaces** the email-derived name in the rail, the bottom bar and
   every page, **falling back** to the email-derived name when no name is set.

**The source plan** this brief was captured from is
`/home/bs1346/.puku-cli/plans/glimmering-swimming-barto.md`. It carries the
file-by-file detail; this brief carries the intent.

**Why the account sheet's own docstring has to be rewritten, not just edited.** It
currently argues for the two links it is about to lose — *"Two links in here, and both
are real routes"*, *"`/pricing` is where a Free user reads what Pro adds"* — and it
states that *"Changing an email, changing a password while signed in and closing an
account have no endpoints yet, so the panel does not offer them"*. After this intent that
last sentence is **half false**: the name *does* have an endpoint. A docstring that
argues for a position the code has left is the same defect this codebase's docstrings
exist to prevent.

**What is deliberately not in scope.** Changing the email address, changing the password
while signed in, and closing the account still have no endpoints. The password is
changed by the reset flow, which ends the account's other sessions. The panel continues
not to offer them — an affordance that cannot work is the same lie as a link to a 404.
