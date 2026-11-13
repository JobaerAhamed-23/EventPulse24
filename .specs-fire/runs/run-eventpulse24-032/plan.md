---
run: run-eventpulse24-032
work_item: user-name-model-and-command
intent: account-profile-name
mode: confirm
checkpoint: plan
approved_at: 2026-11-13T09:52:00Z
---

# Implementation Plan: The Name on the Account — the Field and the Command That Writes It

## Approach

**Two changes, and nothing else moves.**

1. **The field.** `User.name = models.CharField(max_length=120, blank=True, default="")`,
   added after `email` on `backend/apps/identity/models.py`. Blank, not null: `""` is the
   single "no name set" state, and the email-derived fallback is a *display* concern the
   backend must not guess at. `User.retention_category` is already
   `RetentionCategory.ACCOUNT_IDENTITY`, so the new column inherits the category and
   AD-15 needs no new declaration. The migration is `0005_user_name.py`.

2. **The command.** `backend/apps/identity/services/profile.py` (new) with
   `set_user_name(*, user_id: UUID, name: str) -> None`, published from
   `apps/identity/services/__init__.py` (imports + `__all__`) because the services module
   **is** the app's published interface (AD-2; the `models-identity` import-linter
   contract keeps the model private to `apps.identity`).

**The command's shape follows `ensure_account` (`services/accounts.py`)**, which is the
closest thing in the codebase to it: one write, one audit row in the same transaction, an
actor by value, and no PII in the details.

**The rules, and why each one is what it is:**

- **Trim, then collapse internal whitespace.** `"  Maya   Ahmed "` → `"Maya Ahmed"`. A
  name is stored as it will be rendered, on one line, in the rail and the bottom bar.
- **Cap at 120 characters**, matching the column. A name that is 121 characters is a
  name; the column is the limit the product set, so the value is truncated rather than
  refused. (Truncation over refusal is a decision, recorded rather than left to chance.)
- **Empty is legal.** A whitespace-only name stores as `""` — "no name set", which the
  frontend renders as the email-derived fallback. Clearing your name is a thing a person
  does; it is not a refusal.
- **Control characters and newlines are refused**, with `domain.errors.ValidationError`
  → a 422 via `config/errors.py`. A newline in the name would break the one-line layout
  it is rendered in, and it is not a name.
- **The write lands inside `transaction.atomic(using=PERSONAL)`** (AD-3), and the audit
  row is written **in the same transaction** (AD-5). `write_audit` raises if it is not,
  which is what keeps an audit row from committing apart from its mutation.
- **The audit `details` carry no name.** `write_audit`'s own docstring says *"details
  must carry counts and slugs, never free text"*, and the name is PII (AD-13).
  `ensure_account` sets the precedent — `details={"method": "password", "at": ...}` and
  **not** the address. The action names the account and the row is one lookup away.

**The command takes a `user_id`, not a `User`** — a command that took a model instance
would invite a caller to pass an unsaved one. The row is looked up inside the
transaction.

**Validation lives in the command, not the API layer.** The API layer must not touch the
ORM (`tests/architecture/test_no_direct_writes.py`), and the domain-error mapping
happens once, in `config/errors.py`. A refusal raised in the command reaches the client
as a 422 with the project's error shape.

**No endpoint, no UI.** Those are the next two work items. This item is the seam: after
it lands the backend can hold a name and can be asked to change one, and nothing else
has moved.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/apps/identity/services/profile.py` | The `set_user_name` command — validation, the write, the audit row |
| `backend/apps/identity/migrations/0005_user_name.py` | The migration that adds `User.name` |
| `backend/tests/identity/test_profile_command.py` | The command's tests: trimming, whitespace, truncation, refusal, the audit row, and that the details carry no name |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/apps/identity/models.py` | Add `name = models.CharField(max_length=120, blank=True, default="")` after `email` |
| `backend/apps/identity/services/__init__.py` | Import `set_user_name` from `services.profile` and add it to `__all__` |
| `backend/tests/identity/test_models.py` | Assert the new field's default, its blank, and that a whitespace-only value is not refused by the column |

## Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/identity/test_profile_command.py` | Trimming; internal-whitespace collapse; whitespace-only → `""`; over-long → truncated to 120; newline/control character → `ValidationError` with **nothing written**; the write is inside `transaction.atomic(using=PERSONAL)`; the audit row is in the same transaction; the action is `user_name_changed`; `target_type` is `"User"`; `target_id` is the user's id; **the details carry no name**; the command is callable without an actor label |
| `backend/tests/identity/test_models.py` | The field's default is `""`; the column is blank-not-null; the row round-trips a name |

## Technical Details

- **`User.save()` normalises the email** (`models.py:74-78`). The name needs no
  equivalent: it is not a key, not unique, and the case is the person's.
- **`write_audit` raises `AuditOutsidePersonalTransaction`** outside an atomic PERSONAL
  block (`services/audit.py:44`). The transaction is not optional plumbing here — it is
  what keeps the audit row from being committed apart from the mutation.
- **The audit `details` are `{}`.** The action names the account; the row is one lookup
  away. `details={}` is what `ensure_account` would write if it had nothing to say.
- **The control-character check runs on the raw input, before the trim.** A newline
  surrounded by spaces is still a newline.
- **`Actor.user(user_id)` carries an id and no label**, so no email reaches a row
  (`shared/actor.py:38`). The command takes the `Actor` it is given; it does not build
  one from a request.
- **The migration is generated, not hand-written.** `makemigrations identity` writes it;
  it is reviewed rather than authored.
- **`lint-imports` must stay green.** `models-identity` says only `apps.identity` may
  import `apps.identity.models`; the command lives inside `apps.identity`, so it holds.
- **No `using=` is ever omitted.** `transaction.atomic(using=PERSONAL)` and
  `User.objects.using(PERSONAL)` — a bare `atomic()` silently means personal and is
  flagged by `tests/architecture/test_database_alias.py`.

---
*Plan approved at checkpoint. Execution follows.*

---

## Work Item: profile-endpoint-and-contract

### Approach

**Two endpoints on the `/api/auth` router, and a regenerated contract.**

The router (`backend/apps/identity/api.py:96`) has **no router-level `auth=`** — sign-up
and sign-in are how a session is *created*, so requiring a session to get one would be
circular. Every handler therefore resolves the user itself, exactly as `me` does. The new
write follows that same shape.

1. **`GET /api/auth/me` — extended, not replaced.** `CurrentUserOut` gains
   **`name: str`**. `me` is already *"who is making this request"*, and the frontend
   needs the name on **every** page — the rail, the bottom bar, every screen's
   `AppShell`. `frontend/lib/session.ts` already reads `me` for the session, so a second
   endpoint for the same user would be a second round-trip for the same row.

   The field is `""` when unset, matching the model's blank default. It is spelled out
   **explicitly**, which is the point of `CurrentUserOut`'s rule that it carries *"no
   password field, no permission field and no catch-all, so nothing internal can ride
   along"* — a catch-all would have let a new column leak by accident; an explicit field
   does not.

2. **`PUT /api/auth/profile` — new.** Body `ProfileIn { name: str }`; answer
   `ProfileOut { id, email, name }`. Declared statuses: `{200: ProfileOut, 403: ErrorOut,
   422: ErrorOut}`. Declaring them is what puts `ErrorOut` in the generated client, so the
   frontend can read the message it has to show — the same reason `signup` declares
   `403`/`422`/`429`.

   The handler, in this order:
   1. `require_csrf(request)` **first** — the router has no router-level auth, so the
      check is explicit, exactly as in `signup` (`api.py:167`), `signin` (210) and
      `signout` (234);
   2. resolve the user — `current_user(request)` raises the 401 for an anonymous caller;
   3. call `set_user_name(user_id=user.pk, name=body.name)` — the **named command**,
      not an ORM write (AD-5; `tests/architecture/test_no_direct_writes.py` scans this
      file);
   4. return the updated profile.

   **`ProfileOut` carries the email and the id as well as the name**, so the client can
   update what it knows without a second `me` call after a save.

**`PUT`, not `PATCH`.** The frontend has **no `api.PATCH` call site anywhere** — the only
mention of "PATCH" in the frontend is a comment in `lib/csrf.ts:37` — and
`/api/settings/notifications` is already a `PUT` with patch semantics
(`apps/delivery/preferences_api.py:86`). One verb for the product's settings writes. A
second verb for the same write would put two shapes for one operation into the contract.

**The contract is generated, never hand-written (AD-19).** `make client` rewrites
`frontend/lib/api/openapi.json` and `frontend/lib/api/schema.ts`; **both are committed**.
This is not optional bookkeeping:
- `backend/tests/api/test_contract.py:16` compares the committed `openapi.json` to the
  live schema and **fails** when they differ;
- `backend/tests/e2e/test_state_change_contract.py:88` asserts `make client` leaves the
  tree unchanged;
- CI's contract job runs `make client` then `git diff --exit-code frontend/lib/api/`.

**The operation ids are generated, not chosen.** They carry the Django app's dotted path
(`apps_identity_api_…`). The exact ids are **read out of the regenerated
`openapi.json`**, not assumed.

**The refusal's `details` do not echo the input (AD-13).** The name is PII; the refusal's
details say *what was wrong with the input*, not what the input was.

**`me`'s onboarding read stays read-only.** Its own comment says an expired onboarding is
*reported* as step 1 and *"the row is left for the next command to restart"* — because
`me` is a `GET`, and a `GET` is never CSRF-checked, so a write behind one would be a
cross-site write. The name write lives behind `PUT /profile`, which **is** CSRF-checked.

### Files to Modify

| File | Changes |
|------|---------|
| `backend/apps/identity/schemas.py` | `CurrentUserOut.name: str`; add `ProfileIn`, `ProfileOut` |
| `backend/apps/identity/api.py` | `me` returns the name; add the `PUT /profile` handler; import the new schemas and `set_user_name` |
| `backend/tests/identity/test_auth_api.py` | `me`'s payload assertion gains `name: ""` |
| `backend/tests/identity/test_profile_api.py` (new) | The endpoint's tests |
| `frontend/lib/api/openapi.json`, `frontend/lib/api/schema.ts` | Regenerated by `make client` — **committed** |

### Tests

| Test | What it pins |
|------|--------------|
| `me` returns `name: ""` for a user with no name | The field is `""`, not `null`, and not a 404 |
| `me` returns the stored name | The read-back path |
| `PUT /profile` saves the name and returns the updated profile | The write path and the response shape |
| `PUT /profile` with no CSRF token → **403** | The check happens **before** any work |
| `PUT /profile` from an anonymous caller → **401** | The resolver's refusal |
| `PUT /profile` with a refused name (newline) → **422** with `{code, message, details}` | The command's refusal reaches the client |
| `PUT /profile` with a whitespace-only name → stored as `""` | "No name set" is legal |
| `PUT /profile` with an over-long name → truncated to 120 | The column's limit is the product's limit |
| The audit row exists and its details carry no name | AD-13, at the HTTP edge |
| The endpoint writes no ORM row itself | AD-5 — asserted against `test_no_direct_writes.py` |
| The endpoint is declared `PUT`, and the OpenAPI schema says `put` | The verb is one, in the contract |

### Technical Details

- **`ErrorOut` is `shared.errors.ErrorOut`** — the shared shape, not a local one.
- **`ProfileOut.id` is a `UUID`**, the same as `CurrentUserOut.id`.
- **The handler does not import `apps.identity.models`.** It calls the command through
  `apps.identity.services` — the app's published interface (AD-2) — so the
  `models-identity` import contract holds and AD-5's scan finds no write.
- **The name is read from the resolved user**, not re-fetched: `current_user(request)`
  returns the `User` instance, and the command re-reads the row inside its own
  transaction anyway.
- **`make client` must be run before the contract test is trusted.** The contract test
  compares the committed file to the live schema, so a stale file is a red test, not a
  green one.


---

## Work Item: profile-screen-and-editor

### Approach

**One new settings section, one new route, one new island.** The section goes into
`SETTINGS_SECTIONS` — the one list both the index and the sub-nav render — so it is
reachable from every settings screen and from the index the moment the row exists.
The route follows the house five-step shape exactly (the shape
`tests/settings-routes.test.ts:102-145` asserts), and the editor is a client island
that follows the inline-save pattern the other settings controls use.

**The editor saves on change and has no Save button.** That is the rule the other
settings islands follow, and it is what makes the screen feel like the rest of
Settings rather than a form from somewhere else.

**The failure line is the API's, when the API refused.** `saveFailureMessage` returns
the API's own message when the body is the project error shape and the route's
offline line otherwise. A user who typed a name the backend refused — a name with a
newline — must read *the backend's refusal*, not "Couldn't save." That split is the
whole reason the failure is stored as a **message string** rather than a boolean.

**The editor does not own the session.** It takes `initialName` as a prop from the
server page; it does not call `me` itself. The server already has the session, and a
second read would be a second answer to a question already answered.

**The name the rail shows is not this item's job.** The rail, the bottom bar and every
page get the stored name in the next item; here the page passes `session.user.name`
through, and the local `displayName` copy is left exactly where it is — replacing it
is `display-name-everywhere`'s work, and doing it here would put two items in one
diff.

### Files to Create

- `frontend/app/settings/profile/page.tsx` — the route.
- `frontend/app/settings/profile/loading.tsx` — the skeleton.
- `frontend/app/settings/profile/page.test.tsx` — the page test.
- `frontend/components/settings/profile-name.tsx` — the editor island.
- `frontend/components/settings/profile-name.test.tsx` — the island test.

### Files to Modify

- `frontend/lib/settings-sections.ts` — the Profile row, and the two docstrings that
  state counts this change invalidates.
- `frontend/tests/endpoint-coverage.test.ts` — **remove** the `PUT /api/auth/profile`
  entry from `DECLARED_UNCALLED`, because its caller now exists.
- `frontend/tests/ad19-endpoint-coverage.test.ts` — add the endpoint to
  `NEW_ENDPOINTS` with the operation id `apps_identity_api_put_profile` and the
  caller `components/settings/profile-name.tsx`.
- `frontend/app/settings/account/page.test.tsx` — the `USER` fixture gains
  `name: ""` (it is typed against `CurrentUserOut`, so `tsc` flags it).

### Tests

- `frontend/components/settings/profile-name.test.tsx` — the island:
  - it renders the current name;
  - a successful save calls `api.PUT("/api/auth/profile", { body: { name } })` and
    shows "Saved.";
  - an API error shows **the API's message**, not the offline line;
  - a thrown request shows the offline line;
  - the payload is exactly `{ name }`;
  - it has **no Save button**;
  - the in-flight indicator is the static dot, never a spinner;
  - the failure is `role="alert"` and carries `data-save-failed`;
  - the chosen name is kept when the save fails.
- `frontend/app/settings/profile/page.test.tsx` — the page:
  - the signed-in branch renders the heading and the editor;
  - the signed-out branch renders the states block;
  - `AppShell` receives the **stored** name when one is set.
- `frontend/tests/settings-routes.test.ts` — data-driven; passes once the list and the
  page are both in place, and it asserts **both directions**.

### Technical Details

- **The route's shape, per `tests/settings-routes.test.ts`:** at least two
  `<AppShell name={…} email={session.user.email}>` branches, each **immediately
  followed** by `<SettingsNav />`. The signed-out branch is `name="" email=""` and is
  deliberately bare.
- **The page has no read of its own.** There is no `readProfile()` module, because the
  session already carries the name — `CurrentUserOut.name` is what the endpoint added.
  A read module here would be a second answer to a question already answered.
- **The editor's input** takes the styling from `components/collections/collection-manager.tsx`:
  `min-h-[44px] rounded-control border border-border-subtle bg-surface-elevated px-3 py-2
  text-ink-primary [font:var(--type-scale-body-md)]` — all of it inside the token set.
- **`maxLength` on the input is 120** — the column's limit, which the backend
  truncates to anyway. The attribute is a courtesy, not a rule: the server is the one
  that decides.
- **The island's props are `initialName: string`** — one prop. The island does not
  read the session, and it does not fetch the name.
- **The editor saves on every change**, like `DigestDeliveryTime` — except that an
  **emptied** name *is* saved, because an empty name is legal: it means "no name set",
  and the backend stores `""`.
- **The offline line is `"Couldn't save."`** — the same short line the quiet-hours and
  delivery-time routes use, because the same thing happened.
- **Vitest globals are off** — `describe`/`it`/`expect`/`vi`/`beforeEach` are imported
  from `vitest`.
- **The `USER` fixture** is typed against `components["schemas"]["CurrentUserOut"]`, so
  `tsc` flags a fixture with no `name`.

### The contract cleanup this item owes

The previous item left a **debt with a deadline** in
`frontend/tests/endpoint-coverage.test.ts`: `PUT /api/auth/profile` is in
`DECLARED_UNCALLED` because the endpoint landed before the editor that calls it. That
file's own stale-entry check fails the day the caller exists — so the entry **must** be
removed in this item, and the endpoint must move into
`frontend/tests/ad19-endpoint-coverage.test.ts`'s `NEW_ENDPOINTS` with its real caller.

### Acceptance Criteria Mapping

| Criterion | Where it is proved |
|-----------|--------------------|
| `/settings/profile` exists and renders its own `<h1>` | `page.test.tsx` |
| The section is in `SETTINGS_SECTIONS`, after "Account" | `settings-sections.ts` + `settings-routes.test.ts` |
| The page has the exact settings-route shape | `tests/settings-routes.test.ts` (already written) |
| The page redirects an anonymous visitor | `page.test.tsx` |
| `loading.tsx` has the skeleton shape and no spinner | `styles/motion.test.ts` (already written) |
| The editor saves through `api.PUT` | `profile-name.test.tsx` |
| A successful save shows "Saved."; a failed one shows a message | `profile-name.test.tsx` |
| No Save button | `profile-name.test.tsx` |
| The static dot, not a spinner | `profile-name.test.tsx` |
| `role="alert"` and `data-save-failed` | `profile-name.test.tsx` |
| The editor is a client component; the page is a server one | `"use client"` / no `"use client"` |
| The endpoint's caller is registered | `ad19-endpoint-coverage.test.ts` |

---

## Work Item: reduced-account-sheet

### Approach

**One file changes, and one file is created.** `frontend/components/shell/account-menu.tsx`
loses its `Settings` link and its `Pricing` link and gains an **"Edit your name"** link
to `/settings/profile`. Its module docstring is rewritten, because **the docstring
currently argues for the two links this item removes** — and that is the defect this
codebase names in its own rule: *a docstring that argues for a position the code has
left is the same defect these docstrings exist to prevent.*

**Nothing else changes.** `AccountMenu` (the rail's button and the sheet it opens),
`Avatar`, the `AccountProps` type and `SignOutButton` at the bottom of the panel are
untouched — **the `AccountProps` type must keep its shape**, because
`more-menu.tsx:8` and `bottom-tab-nav.tsx:7` both import it.

**One change fixes both breakpoints, and both are tested.** The rail opens
`AccountPanel` in a `Sheet`; `more-menu.tsx:86` renders the same panel *inline*, because
a sheet opened from inside a sheet is a second overlay level and `Sheet` keeps there
being exactly one. **"It works in the rail" is not a claim about the phone**, so the
More sheet is rendered and asserted too.

### Files to Create

- `frontend/components/shell/account-menu.test.tsx` — the panel, the rail's row, and the
  bottom bar's inline rendering.

### Files to Modify

- `frontend/components/shell/account-menu.tsx` — the two links out, one link in, and the
  docstring rewritten.

### Tests

- The panel shows the name and the email.
- The panel offers **"Edit your name"**, pointing at `/settings/profile`.
- The panel has **no** `Settings` row and **no** `Pricing` row.
- **Sign out is still there, and still the last thing in the panel.**
- The rail's row opens the sheet, and the sheet carries the same panel.
- **The More sheet renders the same panel inline, with the same link.**

**The router is mocked** because `SignOutButton` calls `useRouter()` — it calls
`router.replace("/signin")` after the sign-out POST. The panel's own links are plain
`<Link>`s, so nothing else needs it.

### Technical Details

- **The link's copy is "Edit your name", not "Profile".** The section in the settings
  nav is "Profile"; the link says what it does. The rail's Settings row points at the
  index, and the index carries the Profile row — **so the two labels are different on
  purpose.**
- **The styling is the links it replaces'** — `text-ink-secondary underline
  underline-offset-4 [font:var(--type-scale-body-sm)]` — not a button, not a heading.
- **`SignOutButton` stays where it is.** Its own docstring says it lives in *"the
  account surface (`AccountPanel`)"*, and the topbar-quiet rule keeps account
  affordances out of the topbar.
- **The docstring's three claims are each handled explicitly**: no more *"two links in
  here"*; no more defence of the Pricing link; and the *"no endpoints yet"* sentence is
  corrected to say that **the name is the one thing that can be changed**, while the
  email, the password-while-signed-in and closing the account still cannot be.

### Acceptance Criteria Mapping

| Criterion | Where it is proved |
|-----------|--------------------|
| The sheet renders the name, the email, "Edit your name" and Sign out | `account-menu.test.tsx` |
| No `Settings` row | `account-menu.test.tsx::does not offer a Settings row` |
| No `Pricing` row | `account-menu.test.tsx::does not offer a Pricing row` |
| "Edit your name" links to `/settings/profile`, which exists | `account-menu.test.tsx::points 'Edit your name' at the profile screen, which exists` |
| Styled like the links it replaces | `account-menu.test.tsx::offers 'Edit your name'` (the styled-as-a-button probe) |
| `SignOutButton` is still last | `account-menu.test.tsx::still offers Sign out, and it is the last thing in the panel` |
| The panel still opens as a `Sheet` and still renders inline | `account-menu.test.tsx` (the rail's row and the More sheet) |
| The docstring makes the three corrected claims | the module's own docstring, read against the code |
| Both breakpoints are correct | `account-menu.test.tsx::the bottom bar's More sheet` |

## Work Item: display-name-everywhere

### Approach

**One module is created, and fifteen pages are edited.** The rule — *the stored name if
there is one, the email-derived name otherwise* — lived in **fifteen copies**, five lines
each, in fifteen page files. **Each copy looked correct, which is exactly why the rule
could drift without anything failing.**

**So the copies are deleted and one helper takes their place.**

`frontend/lib/display-name.ts` exports:

```ts
export function displayName(user: { name: string; email: string }): string
```

- **The stored name wins, verbatim.** Not trimmed, not re-cased, not split on anything.
  A person's name is theirs.
- **Otherwise the email-derived name**, by **the old rule, byte for byte** — so *no
  existing screen changes appearance* for anyone who has not set a name.

**It takes the whole user rather than two positional arguments.** The rule is *"the
stored name if there is one, otherwise the address"*, and one object makes it impossible
to pass the two in the wrong order — which is the mistake two positional arguments
invite.

**The module imports nothing and carries no `"use client"` banner.** It is imported by
server components, client components and tests alike, so it must be safe on every side
of the boundary.

### Files to Create

- `frontend/lib/display-name.ts` — the helper.
- `frontend/lib/display-name.test.ts` — what the helper does.
- `frontend/tests/display-name.test.ts` — **that every page goes through it.** This is a
  filesystem-level test: *"every page derives the name the same way"* is a fact about
  the *set* of files under `app/`, and no render of any one page can see it.
- `frontend/tests/stored-name-in-shell.test.tsx` — **that the name arrives.** The chain
  is four links long — the session carries it, the page reads it, the page hands it to
  `AppShell`, the shell hands it to the rail — and a link dropped anywhere in that
  chain is invisible to the other two files.

### Files to Modify

The **fifteen** pages: `app/page.tsx`, `app/browse/page.tsx`, `app/conflicts/page.tsx`,
`app/timeline/page.tsx`, `app/settings/page.tsx`, `app/settings/{reminders,quiet-hours,
digest,calendars,collections,account,profile}/page.tsx`,
`app/personal-events/[id]/reminders/page.tsx`, `app/events/[id]/page.tsx`,
`app/events/[id]/reminders/page.tsx`.

**Each one**: the local `displayName` function is deleted, the call becomes
`displayName(session.user)`, and the import is inserted in its sorted `@/lib/*`
position.

**And the test fixtures.** The `USER` fixture in **23 test files** is an untyped plain
object, so `tsc` did not flag it — but the pages now read `session.user.name`, and the
runtime said `Cannot read properties of undefined`. **Every fixture gained `name: ""`.**

### Tests

- The helper's behaviour, pinned case by case — including the fallback's exact old
  behaviour: the dot, the underscore, the hyphen, the mix, the collapsed run, the empty
  local part, the separators-only local part, and the first-letter-only capitalisation.
- The stored name wins, verbatim — not re-cased, not trimmed, not split on separators.
- **No page carries its own copy** — the rule, not the identifier: a page that derives a
  name from an email is carrying a copy, whatever it called the function.
- **Every page that names somebody calls the helper with the whole user.**
- **No page passes a hand-built name to the shell** — the name must be *traceable* to
  the helper, whether it is the call itself or a local binding whose definition is
  exactly the call.
- **A user with a stored name sees it in the rail, and a user without one still sees
  the email-derived name.**

### Technical Details

- **The fallback is the old function, not "something sensible".** The work item is
  explicit: *no existing screen changes appearance* for anyone who has not set a name.
  Not "close enough" — *the same function*, and a test pins it.
- **The stored name is not split on separators.** The email rule splits on `.`, `_` and
  `-`; a name is not an address, and "van der Berg" is one word to the person who owns
  it.
- **The helper is server-safe by construction** — no imports at all. A module that
  imports nothing cannot break the server/client boundary.
- **The stored name's two spellings differ on purpose.** The shell test uses the email
  `maya.ahmed@example.test` (fallback: `"Maya Ahmed"`) and the stored name
  `"Ada Lovelace"`. **If they were the same string, the test could not tell "the stored
  name was used" from "the fallback was used"** — it would pass either way.

### Acceptance Criteria Mapping

| Criterion | Where it is proved |
|-----------|--------------------|
| All 15 local `displayName` functions are deleted | `tests/display-name.test.ts::no page carries its own copy of the display-name rule` |
| Every page calls the shared helper with the whole user | `tests/display-name.test.ts::every page that names somebody calls the shared helper with the whole user` |
| No page passes a hand-built name to the shell | `tests/display-name.test.ts::no page passes a hand-built name to the shell` |
| A stored name is shown verbatim | `lib/display-name.test.ts::a user with a stored name` |
| The fallback is the old rule, exactly | `lib/display-name.test.ts::a user with no stored name` |
| A user with a stored name sees it in the shell | `tests/stored-name-in-shell.test.tsx::shows a user with a stored name by that name` |
| A user without one still sees the email-derived name | `tests/stored-name-in-shell.test.tsx::shows a user with no stored name the email-derived name` |
| The helper is server-safe | `tests/display-name.test.ts::is a server-safe module — no client banner and no imports` |

## Work Item: contract-and-e2e-proof

### Approach

The work item asks for two things: **the contract is committed and true**, and **the
name is proved in a browser**.

**The contract was already in place** — `make client` had regenerated
`lib/api/openapi.json` and `lib/api/schema.ts`, and `tests/api/test_contract.py` (the
committed schema against the live one) and `tests/e2e/test_state_change_contract.py`
("`make client` leaves the tree unchanged") both passed. **That part was verification,
not work**: the schema was already committed, and re-running `make client` left the
tree clean.

**The e2e proof did not exist, and it turned out to be where the work was.**

Three e2e files are involved:

- **`e2e/settings-navigation.spec.ts`** — the settings surface is navigable. **The
  `SECTIONS` array is hand-written**, and it was missing the Profile row. Adding it was
  one line — but the *reason* it is hand-written is the whole point of the file: *"a
  hand-written list is a list somebody has to remember to update"*, and this spec fails
  when they do not.
- **`e2e/helpers.ts`** — the shared helpers. **`resetSignInThrottle` was duplicated**:
  the settings-navigation spec had its own copy, and the profile-name spec needed one
  too. **Two copies of the throttle reset is two things to keep in sync**, and the
  helper file is where the *other* shared helpers already live.
- **`e2e/profile-name.spec.ts`** — new. The name, end to end, in a real browser.

### Files to Create

- `frontend/e2e/profile-name.spec.ts` — **seven tests**, driving the real stack:
  the sheet's contents; the two closed doors (asserted on the **href**, not the
  label); typing a name and it surviving a reload; the rail showing the stored name on
  three screens; the no-name fallback; clearing the name falling back again; and a
  refused name showing the API's own message.

### Files to Modify

- `frontend/e2e/settings-navigation.spec.ts` — the Profile row in `SECTIONS`, the
  `SECTIONS` count in the header docstring, and the removal of the spec's **own copy**
  of `resetSignInThrottle` in favour of the shared helper.
- `frontend/e2e/helpers.ts` — `resetSignInThrottle` and `setName` are now exported from
  here.

### Tests

- `frontend/e2e/profile-name.spec.ts` — 7 tests, all passing against the real stack.
- `frontend/e2e/settings-navigation.spec.ts` — 5 tests, all passing against the real
  stack.

### Technical Details

- **The name is account state, and it outlives a test.** A test that sets a name leaves
  it behind, and the next test — and the next *run* — inherits it. **The first run of
  the file proved it**: the "a user with no name set" test failed because a previous
  test had set a name, and the rail showed it. So the name is cleared in `beforeEach`,
  **through the product's own endpoint**, with the empty string that *is* the account's
  "no name set" state.
- **And the page is reloaded after the clear, because the rail is drawn from the
  server.** The sign-in landed on a page the server rendered with whatever name the
  account held *then*; clearing the account afterwards does not redraw the rail.
  **The second run proved this**: without the reload, "a user with no name set" still
  failed — the account said "no name" and the screen said "Maya Ahmed".
- **A line break cannot be tested through a single-line input.** The field is
  `<input type="text">`, and the HTML value sanitization algorithm strips `\r` and `\n`
  from a single-line input's value — so a newline typed into it never reaches the
  field, let alone the API. **The first version of the test filled the field with
  `"Maya\nAhmed"` and waited for a refusal that could never arrive.** The refusal is
  now driven by **BEL** (`\u0007`), which the browser does not strip and the backend
  does refuse — the same refusal a newline would earn, reached by the only road the
  browser leaves open.
- **The bell is written as an escape, not as a literal.** A control character in source
  is invisible: a reader cannot see it, a formatter may strip it, and a diff shows
  nothing where the character was.

### Acceptance Criteria Mapping

| Criterion | Where it is proved |
|-----------|--------------------|
| The committed contract is the live contract | `backend/tests/api/test_contract.py` |
| `make client` leaves the tree unchanged | `backend/tests/e2e/test_state_change_contract.py` |
| Every settings screen is reachable by clicking, including Profile | `e2e/settings-navigation.spec.ts::every settings screen is reachable from the index, by clicking` |
| The account sheet offers the name, "Edit your name" and Sign out | `e2e/profile-name.spec.ts::the account sheet offers the name, the edit link and Sign out` |
| The sheet offers no Settings row and no Pricing row | `e2e/profile-name.spec.ts::the sheet offers no Settings row and no Pricing row` |
| Typing a name saves it, and it survives a reload | `e2e/profile-name.spec.ts::typing a name saves it, and it survives a reload` |
| The rail shows the stored name, on every screen | `e2e/profile-name.spec.ts::the rail shows the stored name, on this screen and on every other` |
| A user with no name set still sees the email-derived name | `e2e/profile-name.spec.ts::a user with no name set still sees the email-derived name` |
| Clearing the name falls back again | `e2e/profile-name.spec.ts::clearing the name falls back again` |
| The API's own refusal is shown, verbatim | `e2e/profile-name.spec.ts::a name carrying a control character is refused, and the API's own message is shown` |

---

## Work Item: live-name-in-the-shell

> **This work item was not in the original plan. It was found by the e2e proof above,
> and it is the most important thing this run produced.**

### The finding

**The rail is a server render, and a server render is a photograph.** Every page reads
the session on the server, derives the display name from it, and hands that name to
`AppShell`, which hands it to the sidenav, the bottom bar and the account sheet. **That
name is fixed for the life of the render.**

So a person who types their name on `/settings/profile`, sees "Saved.", and looks up at
the rail **sees the old one**. And the rail is on every page, and the account sheet is
opened from it — so the product contradicts itself: the sheet says "here is who you
are", and the row it was opened from says something else.

**A save that does not show up is a save that did not happen.**

The profile page's own docstring had recorded this as a known limitation — *"So the rail
is stale until the next load … it is said here rather than left to be discovered"* — but
**the user's requirement was that the stored name replaces the email-derived name in the
rail, the bottom bar and every page**, and the e2e test proved the requirement was not
met. A documented limitation is still a limitation.

### Approach

**The same shape as the live save allowance.** `browse-quota-provider` exists because
the server states the fact and the client shows the fact it was given — but a client
that is given the fact *once*, at page load, and never hears about it again is a client
showing a stale fact. **The allowance was worth a provider; so is the name.**

**A module-level store, read with `useSyncExternalStore`.**

- **Not a React context.** The provider would have to sit *above* the rail, and the rail
  is rendered by `AppShell`, which every page mounts by hand. **A provider means
  fifteen pages each wrapping their own `<AppShell>`** — and the fifteen pages are
  exactly the thing the display-name work just finished consolidating.
- **Not a prop.** The writer is a page's island and the reader is the shell; they are
  in different subtrees, and the content is server-rendered while the rail is not.
- **Not `router.refresh()`.** It re-runs every server read on the page, and it is a
  whole-page re-render for one string.

**The store holds the *display* name, not the stored name.** The two are different
questions, and the display question is the one the shell asks. **So the island holds
the address too**, and derives the display name with the *same* shared helper the pages
use — one rule, one implementation, and no second copy to keep in sync.

**Only the two leaves that display the name read the store** — `AccountMenu` (the rail
row) and `AccountPanel` (the sheet). `Sidenav` and `BottomTabNav` only forward the
name, so **neither changed**.

### Files to Create

- `frontend/lib/session-name.ts` — the store: `publishName(name)` and
  `useLiveName(seed)`.
- `frontend/tests/live-display-name.test.tsx` — **six tests**: the seed is what the
  page was rendered with; a save moves the rail; the *server's* answer is published,
  not the typed one; clearing falls back again; a refused save publishes nothing; an
  offline failure publishes nothing.

### Files to Modify

- `frontend/components/shell/account-menu.tsx` — `AccountMenu` and `AccountPanel` read
  the live name, keeping their `name` prop as the seed.
- `frontend/components/settings/profile-name.tsx` — takes an `email` prop and publishes
  the display name after the server accepts the write.
- `frontend/app/settings/profile/page.tsx` — passes `email`; the docstring's "the rail
  is stale until the next load" is replaced by the truth.
- `frontend/components/settings/profile-name.test.tsx` — the `email` prop on every
  render.

### Tests

- `frontend/tests/live-display-name.test.tsx` — 6 tests.
- **9 mutation probes, all caught.**

### Technical Details

- **The published name is newer than the render, by construction.** It was published
  *after* the page was rendered, by a save the server had already accepted — so when
  the two disagree, the published one is the one the account holds.
- **The seed is a fallback, not the truth.** The overwhelmingly common case is that
  nothing has been published this session, and then the server-rendered name is the
  only answer there is.
- **The store survives a navigation, and that is correct.** A soft navigation re-renders
  the server components, which read the name the account now holds — the same name the
  store holds, because the save went through the API first. **The two agree.**
- **A hard reload empties the store**, and the seed takes over — the right direction:
  the server is the source of truth, and a reload asks it.
- **The genuinely stale case is another tab.** That is the same bargain the live save
  allowance makes, and the right one.
- **The publish happens only after the server accepted the write.** Publishing earlier
  would publish a guess: the server trims, collapses and caps, so the account's name is
  not always the one that was typed.
- **The failure branches publish nothing.** A refused save changed nothing, and an
  offline failure changed nothing, and a rail showing a name the account does not hold
  is worse than a stale one.

### Acceptance Criteria Mapping

| Criterion | Where it is proved |
|-----------|--------------------|
| The rail shows the name the account holds, after a save | `tests/live-display-name.test.tsx::moves to the saved name` |
| The sheet shows it too | `tests/live-display-name.test.tsx::moves to the saved name` (the sheet assertion) |
| The *server's* name is published, not the typed one | `tests/live-display-name.test.tsx::publishes the name the server stored, not the one that was typed` |
| Clearing falls back rather than blanking | `tests/live-display-name.test.tsx::falls back again when the name is cleared` |
| A refused save moves nothing | `tests/live-display-name.test.tsx::does not move when the save was refused` |
| An offline failure moves nothing | `tests/live-display-name.test.tsx::does not move when the request never reached the API` |
| A page that never saved a name shows the server-rendered one | `tests/live-display-name.test.tsx::shows the name the page was rendered with, before anything is saved` |
| The end-to-end property, in a browser | `e2e/profile-name.spec.ts::the rail shows the stored name, on this screen and on every other` |
