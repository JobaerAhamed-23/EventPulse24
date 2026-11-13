---
id: contract-and-e2e-proof
title: The Proof — the Contract Checks and the Browser Walk
intent: account-profile-name
complexity: medium
mode: confirm
status: completed
depends_on:
  - reduced-account-sheet
  - display-name-everywhere
created: 2026-11-13
run_id: run-eventpulse24-032
completed_at: 2026-11-13T13:17:30.478Z
---

# Work Item: The Proof — the Contract Checks and the Browser Walk

## Description

**Two checks that do not fail on their own.**

### The AD-19 endpoint coverage

`frontend/tests/ad19-endpoint-coverage.test.ts` holds a hand-kept `NEW_ENDPOINTS` list
(line 68). Each entry names a path, a method, the **generated operation id**, and the
**frontend modules that call it**. The file then asserts four things per entry: the
endpoint is in the committed schema; it has the expected operation id; the operation id
is bound in the generated TypeScript; and each named caller reaches the path **through
the generated client** and does not define its own `api`.

Add the two new operations:

```ts
{
  path: "/api/auth/me",
  method: "get",
  operationId: "<read the generated id>",
  caller: ["lib/session.ts"],
},
{
  path: "/api/auth/profile",
  method: "put",
  operationId: "<read the generated id>",
  caller: ["components/settings/profile-name.tsx"],
},
```

**Read the operation ids out of the regenerated `openapi.json`.** They carry the Django
app's dotted path (`apps_identity_api_…`) and are **generated, not chosen**. Do not
assume them — a wrong id fails the test with a message that names the mismatch, which is
the test working, not the test being fussy.

**A note on `GET /api/auth/me`.** It is not a new endpoint, but it is a **changed**
contract — it now carries a field the frontend depends on — and nothing else in this
repo's coverage list would notice that. Listing it makes the dependency explicit: if
`me` ever stops carrying the name, this entry's caller check and the session test fail
together.

### The e2e settings navigation

`frontend/e2e/settings-navigation.spec.ts` holds a **hardcoded** `SECTIONS` array
(line 76) — six `{label, path, heading}` rows. **It is the one thing in this change that
is not data-driven**, and it **will break** when the seventh section is added. Add:

```ts
{ label: "Profile", path: "/settings/profile", heading: "Profile" },
```

**The heading must match the page's `<h1>` exactly.** The spec asserts
`getByRole("heading", { level: 1, name: section.heading })`, and the other rows already
show the rule in action: the section labelled "Calendars" has the heading
**"Calendar sync"**, because the nav label and the page heading are allowed to differ
where the screen warrants it. The profile page's `<h1>` is "Profile", so the row's
heading is "Profile".

This spec exists because **four of the six settings screens once worked, had passing
page tests, and could not be reached by clicking** (`settings-routes.test.ts`'s own
header). The hardcoded array is the price of that guarantee: it is hand-written, so it
must be updated by hand — and when it is not, the spec fails, which is the point.

### The fixtures

The `USER` fixture is typed against the regenerated
`components["schemas"]["CurrentUserOut"]`, so **`tsc` flags every fixture that lacks a
`name`**. Add `name: ""` to the fixture in:

- `frontend/lib/session.test.ts`
- `frontend/app/settings/profile/page.test.tsx` (new)
- every existing settings page test with a `USER` fixture

### The browser walk

The e2e spec proves the settings surface is navigable. **This item's own proof is the
manual walk**, because the properties it proves are the ones no unit test can see:

1. Sign in, click the name in the left rail → the sheet shows the name, the email,
   **"Edit your name"** and **Sign out** — and **no** Settings row and **no** Pricing
   row.
2. Click "Edit your name" → `/settings/profile` renders, with its own `<h1>`.
3. Type a name, blur → **"Saved."** appears. Reload → **the name persisted**.
4. The rail now shows the **stored name**, not the email local part — on the profile
   screen **and** on every other page.
5. `GET /api/auth/me` returns the name; the audit row for `user_name_changed` exists and
   **its details contain no name**.
6. `PUT /api/auth/profile` with no CSRF token → **403**.

**The negative case, which is the one that breaks silently:** a user with **no** name set
still sees the email-derived name in the rail. A fallback that blanks the name would
look like a working feature and hide every user who never set one.

## Acceptance Criteria

- [ ] `NEW_ENDPOINTS` carries both new operations, with the operation ids **read from
      the regenerated `openapi.json`**
- [ ] The `me` entry names `lib/session.ts` as its caller, and the profile entry names
      `components/settings/profile-name.tsx`
- [ ] `frontend/tests/ad19-endpoint-coverage.test.ts` passes
- [ ] The e2e `SECTIONS` array carries the Profile row, and the heading matches the
      page's `<h1>` **exactly**
- [ ] `frontend/e2e/settings-navigation.spec.ts` passes — every settings screen is
      reachable from the index **by clicking**, and every screen reaches every other
      **through the sub-nav**
- [ ] Every `USER` fixture in the frontend has a `name`, and `pnpm typecheck` is green
- [ ] `pnpm test` (Vitest), `pnpm typecheck` and `pnpm lint` are all green
- [ ] The backend suite is green, including `tests/api/test_contract.py` and
      `tests/e2e/test_state_change_contract.py`
- [ ] `make client` leaves the tree **unchanged** — the committed schema is the live
      schema
- [ ] The browser walk above is performed and recorded — **including the negative
      case**, a user with no name set still seeing the email-derived name
- [ ] The audit row for a name change exists, and its `details` contain **no name**

## Technical Notes

- **The frontend suite needs Node 24.** The repo's default v20 makes the whole frontend
  suite fail with 100 undici/zstd errors. **Export the nvm v24.22.1 `PATH` first.**
- **`api.PUT` is not matched by the sweep at line 456**, which regex-matches
  `api.(GET|POST|PATCH|DELETE)(`. That is a **pre-existing gap** in that check, not
  something this change introduces — the `PUT` endpoints already in `NEW_ENDPOINTS` are
  covered by their own explicit entries, which is exactly how the profile `PUT` is
  covered. **Do not "fix" the sweep in this pass**; widening it is a separate change
  with its own blast radius, and it would go red on endpoints this intent does not own.
- **`tests/digest-home-boundary.test.ts:405` asserts on the account-menu source.** It
  checks that `<AccountMenu ` and `<AccountPanel ` are present — both unchanged — so it
  should pass. **Verify it does**; if it fails, the failure is real and is not to be
  worked around by editing the assertion.
- **The e2e spec signs in once per test** and `AUTH_THROTTLE_SIGN_IN_ACCOUNT` is five an
  hour, so the spec resets the throttle in `beforeEach` (line 88-91). A new test added
  to this file inherits that reset — but a test that signs in **twice** would not.
- **`make test-e2e` needs the stack up** (`make up`) and the catalog seeded — it depends
  on `seed-browse-for-test`.

## Dependencies

- `reduced-account-sheet` — the browser walk asserts the sheet's contents, which this
  item changes.
- `display-name-everywhere` — the walk asserts the rail shows the stored name on every
  page, which this item makes true.
