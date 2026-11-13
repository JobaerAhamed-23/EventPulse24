---
run: run-eventpulse24-032
intent: account-profile-name
generated: 2026-11-13T11:00:00Z
status: passed
---

# Code Review Report

This is a **wide** run — six work items, and each one appends its section below. The
sections are in the order the items were executed, and each says which work item it
belongs to.

---

## Work Item: user-name-model-and-command

**Run**: run-eventpulse24-032
**Intent**: account-profile-name
**Work Item**: user-name-model-and-command
**Reviewed**: 2026-11-13T10:40:00Z
**Files Reviewed**: 6

---

### Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 1 | 0 | 0 |
| Security | 0 | 0 | 0 |
| Architecture | 1 | 0 | 0 |
| Testing | 0 | 0 | 0 |
| **Total** | **2** | **0** | **0** |

**Tests Status**: Passing — 44/44 in the item's suites, 990/990 architecture, 19/19
import-linter contracts, `manage.py check` green, 100% line coverage on the new module.

---

### Files Reviewed

- `backend/apps/identity/services/profile.py` (created)
- `backend/apps/identity/migrations/0005_user_name.py` (created)
- `backend/tests/identity/test_profile_command.py` (created)
- `backend/apps/identity/models.py` (modified)
- `backend/apps/identity/services/__init__.py` (modified)
- `backend/tests/identity/test_models.py` (modified)

---

### Auto-Fixed Issues

These issues were automatically fixed (mechanical, non-semantic changes):

#### 1. [Code Quality] An unused import, left behind by dropping a parameter

- **File**: `backend/tests/identity/test_profile_command.py`
- **Description**: The `Actor` import became unused when the command's optional `actor`
  parameter was dropped. Ruff did not flag it (the file still referenced `Actor` at the
  moment of the drop) and the leftover import was a dead name.
- **Diff**:

```diff
 from apps.identity.services.profile import NAME_MAX_LENGTH, set_user_name
 from domain.errors import ValidationError
-from shared.actor import Actor
 from shared.db import PERSONAL
```

#### 2. [Architecture] The write did not name its database alias

- **File**: `backend/apps/identity/services/profile.py:106`
- **Description**: `user.save(update_fields=["name"])` did not name the alias. The row was
  fetched with `.using(PERSONAL)`, so the write landed on the right schema — but the
  codebase names the alias explicitly on every write, and every sibling in
  `apps/identity/services/` does: `password_reset.py:159` is
  `user.save(using=PERSONAL, update_fields=["password"])`, `data_export.py:150` is
  `row.save(using=PERSONAL, update_fields=[…])`. This was the **only** alias-less
  `save()` in the module.
- **Rationale**: AD-3 says every database call names its alias, because `default`
  silently means personal. The tree scan (`tests/architecture/test_database_alias.py`)
  does not catch an alias-less `save()`, so only the convention caught it.
- **Diff**:

```diff
-        user.save(update_fields=["name"])
+        user.save(using=PERSONAL, update_fields=["name"])
```

---

### Applied Suggestions

No suggestions were applied. Two findings were **raised, decided and applied** during
the review — they are recorded here because they changed the shape of the command, not
just a line of it.

#### 1. [Architecture] The command's published signature was widened

- **File**: `backend/apps/identity/services/profile.py`
- **Description**: The command was written as
  `set_user_name(*, user_id: UUID, name: str, actor: Actor | None = None)`. The work
  item specifies `set_user_name(*, user_id: UUID, name: str) -> None`, and the sibling
  commands do not expose an actor either: `sign_up` and `reset_password` both build
  `Actor.user(user.pk)` internally. The optional parameter widened the app's published
  interface for a case that does not exist — the only caller is the endpoint, acting as
  the account itself.
- **Rationale**: The coding standards say *"every command takes an explicit `Actor`"* —
  but that is about the **audit row** getting an actor rather than a `request`, not
  about the signature exposing one. `sign_up` and `reset_password` are the precedent,
  and the work item's own signature is explicit.
- **Risk Level**: Low — the parameter was new in this change, so nothing depended on it.
- **Decision**: **Applied.** The parameter was dropped, the command builds
  `Actor.user(user.pk)` internally, and the test that exercised the parameter was
  removed.

#### 2. [Testing] The transaction test asserted on source text rather than on behaviour

- **File**: `backend/tests/identity/test_profile_command.py`
- **Description**: `test_the_write_is_inside_a_personal_transaction` read the command's
  own source and asserted that the string `transaction.atomic(using=PERSONAL)` appeared
  in it. The mutation probe found the hole: **dedenting the audit write out of the
  `with` block leaves that string intact, so the test still passed** with the audit row
  written outside the transaction. A test that reads the code under test proves the
  code says what it says, not that it does what it says.
- **Rationale**: The property that matters is *"the audit row commits with the
  mutation, or neither does"*. That is provable behaviourally: patch
  `transaction.atomic` to fail, and the command must write neither the name nor the
  row.
- **Risk Level**: Low — the test was strengthened, and the source-reading assertion was
  kept alongside it for the **alias** rule, which *is* a syntax rule (and is scanned
  independently by `tests/architecture/test_database_alias.py`).
- **Decision**: **Applied.** A behavioural test was added
  (`test_set_user_name_cannot_write_an_audit_row_outside_a_transaction`), and the
  mutation probe was re-pointed at the transaction itself. The probe count went from 12
  to **13**, and all 13 are caught.

---

### Skipped Suggestions

No suggestions were skipped.

---

### Notes on What Was Checked and Found Correct

- **`User.save()`'s email normalisation against `update_fields=["name"]`** — `save()`
  sets `self.email = normalise_email(self.email)` before calling `super().save()`.
  With `update_fields=["name"]` only the `name` column is written, so the
  normalisation is a no-op on the wire. Correct.
- **The get/save race** — two concurrent renames are last-write-wins, which is the
  right semantic for "set my name to X". `password_reset.py` behaves the same way. No
  lock is needed.
- **The truncation/collapse order** — the collapse happens before the cap, so a name is
  collapsed to its final form and *then* truncated to 120. Truncating first could
  leave a name ending mid-word at a collapsed boundary. Correct as written.
- **`User.DoesNotExist` on an unknown id** — the command looks the row up inside the
  transaction, so an unknown account raises rather than writing an audit row for an
  account that does not exist.
- **The `name` field's retention** — `User.retention_category` is already
  `RetentionCategory.ACCOUNT_IDENTITY`, so the new column inherits it and AD-15 needs
  no new declaration. `manage.py check` confirms it.
- **The export** — `apps/identity/services/export_serializer.py` serialises model fields
  generically from the retention registry, so the new column lands in a user's own
  export (FR-52) with no change to the exporter.
- **The migration** — generated by `makemigrations identity`, not hand-written.
  `makemigrations --check --dry-run` reports no changes.
- **PII** — the name appears in no log line, no audit detail and no actor label. The
  test asserts `row.details == {}` **and** that neither "Maya" nor "Ahmed" appears in
  it, rather than only asserting the shape.

---

## Work Item: profile-endpoint-and-contract

**Run**: run-eventpulse24-032
**Intent**: account-profile-name
**Work Item**: profile-endpoint-and-contract
**Reviewed**: 2026-11-13T11:30:00Z
**Files Reviewed**: 8

---

### Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 2 | 0 | 0 |
| Security | 0 | 0 | 0 |
| Architecture | 1 | 2 | 0 |
| Testing | 0 | 2 | 0 |
| **Total** | **3** | **4** | **0** |

**Tests Status**: Passing — 60 in the item's own suites, 1424 across
`tests/identity` + `tests/architecture` + the contract tests, 12/12 mutation probes
caught, `ruff check` and `ruff format --check` clean, frontend `pnpm test` 2403/2403
and `pnpm typecheck` clean.

---

### Files Reviewed

- `backend/apps/identity/api.py` (modified)
- `backend/apps/identity/schemas.py` (modified)
- `backend/apps/identity/services/profile.py` (modified)
- `backend/tests/identity/test_profile_api.py` (created)
- `backend/tests/identity/test_profile_command.py` (modified)
- `backend/tests/identity/test_auth_api.py` (modified)
- `frontend/lib/session.test.ts` (modified)
- `frontend/tests/endpoint-coverage.test.ts` (modified)

---

### Auto-Fixed Issues

These issues were automatically fixed (mechanical, non-semantic changes):

#### 1. [Code Quality] An unused local variable

- **File**: `backend/tests/identity/test_profile_api.py`
- **Description**: `test_me_returns_the_stored_name` bound the factory's result to
  `user` and then never used it — the assertion reads the name off the *response*.
  Ruff's `F841` caught it.
- **Diff**:

```diff
-    user = UserFactory(email="maya@example.test", plain_password=PASSWORD, name="Maya Ahmed")
+    UserFactory(email="maya@example.test", plain_password=PASSWORD, name="Maya Ahmed")
```

#### 2. [Code Quality] A formatting nit in the endpoint's description string

- **File**: `backend/apps/identity/api.py`
- **Description**: `ruff format --check` flagged the hand-wrapped `description=`
  string of the new `PUT /profile` route. `ruff format` rewrapped it. The string's
  content is unchanged — this is the formatter, not an edit.

#### 3. [Architecture] The module docstring's endpoint count was stale

- **File**: `backend/apps/identity/api.py`
- **Description**: The docstring said *"Seven endpoints, plus one that issues the CSRF
  token"* and then listed eight. Adding `PUT /profile` made the count seven *before*
  the CSRF one, so the sentence needed to say **eight**.
- **Diff**:

```diff
-Seven endpoints, plus one that issues the CSRF token:
+Eight endpoints, plus one that issues the CSRF token:
```

---

### Applied Suggestions

Four findings were **raised, decided and applied**. They are recorded here because
each changed the *shape* of the claim the code makes, not just a line of it.

#### 1. [Testing] The "CSRF check is first" comment overstated the guarantee

- **File**: `backend/apps/identity/api.py` (the `put_profile` docstring)
- **Description**: The handler's comment said *"**The CSRF check is first.**"* and
  *"an unsafe request without a token is refused as a cross-site write rather than as
  an authentication problem."* That is **not** what the code does. Ninja parses and
  validates the request body **before the handler is called**, so a request with a bad
  token *and* a malformed body is answered `422 invalid_request` — the token is never
  looked at. The comment was a stronger claim than the code supports, and it would
  have been read as a guarantee.
- **Rationale**: The claim that is actually true — and the one that matters — is
  *"the CSRF check comes before the **write**"*. The write cannot happen either way: a
  body that never parsed is never handed to the command.
- **Risk Level**: Low — a comment was corrected, and a test was added to pin the exact
  boundary so the comment cannot quietly grow again.
- **Decision**: **Applied.** The comment now says *"**The one thing that happens
  before this is the body's own validation**"*, names the resulting `422`, and says
  explicitly that the claim is *"the CSRF check comes before the **write**"* and not
  *"before anything at all"*. The new test
  `test_the_csrf_check_does_not_run_before_the_body_is_validated` pins the boundary:
  a body that is not a `ProfileIn` is answered `422 invalid_request` with no token.

#### 2. [Testing] The CSRF-ordering test had a vacuous assertion

- **File**: `backend/tests/identity/test_profile_api.py`
- **Description**: `test_the_csrf_check_runs_before_the_resolver` asserted that a
  signed-in caller without a token got a `403`. That is a real assertion — but it
  cannot distinguish *"the check runs before the resolver"* from *"the resolver ran
  first and the check ran anyway"*. The property the test's name claims is about
  **two requests agreeing**, and only one of them was made.
- **Rationale**: The reason the ordering exists is that the refusal must not depend on
  the session at all: an anonymous caller with no token and a signed-in caller with no
  token are refused *identically*. A body that named the session state would be the
  oracle the ordering prevents.
- **Risk Level**: Low — a test was strengthened, and it is now stronger than the one it
  replaced.
- **Decision**: **Applied.** The test now makes **both** requests and compares them
  byte-for-byte: same status, and `signed_in_response.content == anonymous_response.content`.
  It also asserts nothing was written.

#### 3. [Testing] The malformed-body 422 asserted only the status

- **File**: `backend/tests/identity/test_profile_api.py`
- **Description**: `test_put_profile_refuses_a_body_with_no_name_with_a_422` asserted
  `response.status_code == 422` and nothing else. There are **two** 422s on this
  endpoint — `invalid_request` (Ninja refuses the *shape* of the body, before the
  handler) and `invalid_input` (the command refuses the *value*) — and a test that
  asserts only the status would pass even if the command's refusal path were entirely
  broken, because the shape refusal alone satisfies it.
- **Rationale**: The frontend branches on the code, so the code is the part that
  matters, and the two codes mean different things.
- **Risk Level**: Low — the test was strengthened, and a second test was added.
- **Decision**: **Applied.** The malformed-body test now asserts
  `response.json()["code"] == "invalid_request"`, and the new test
  `test_a_command_refusal_is_a_different_422_from_a_malformed_body` makes both
  requests and asserts the two codes differ — `invalid_request` for the shape,
  `invalid_input` for the value.

#### 4. [Architecture] The cap was a literal that could drift from the column

- **File**: `backend/apps/identity/services/profile.py`
- **Description**: `NAME_MAX_LENGTH = 120` duplicated the column's `max_length`. Two
  literals are two numbers that can drift: widen the column to 200 and the command
  would still truncate at 120, with **no error raised and no test failing**.
- **Rationale**: The module's own docstring says *"The cap is the column's own limit"* —
  so the code should read it *from* the column rather than restate it.
- **Risk Level**: Low — the value is unchanged (120), and the change is a derivation
  rather than an edit.
- **Decision**: **Applied.**
  `NAME_MAX_LENGTH = User._meta.get_field("name").max_length`, with a comment saying
  why it is read rather than written, and the new test
  `test_the_cap_agrees_with_the_column` — which the mutation probe confirms fails when
  the derivation is replaced by a literal.

---

### Skipped Suggestions

No suggestions were skipped.

One finding was **raised, checked, and found to be wrong** — it is recorded here
because a reviewer's claim that does not survive a check is worth recording too.

#### Not a defect: U+2028 and U+2029 are collapsed, not stored

- **Claim**: A reviewer reported that `Maya\u2028Ahmed` is *"accepted and stored"*.
- **Check**: It is not. `str.split()` treats U+2028 and U+2029 as whitespace, so the
  collapse rule turns them into the space it would give a tab — and a tab *is*
  collapsed. The stored name is `"Maya Ahmed"`, not `"Maya\u2028Ahmed"`.
- **Outcome**: The behaviour is correct, but it was **undocumented** — the module's
  docstring explained why a tab is not refused and said nothing about the line
  separators, which look like line breaks but are not control characters. Two tests
  were added (`…_collapses_a_line_separator_into_a_space` and
  `…_collapses_a_paragraph_separator_into_a_space`) and the docstring now says why:
  the characters refused are the ones that are **not** whitespace and would therefore
  survive the collapse into the stored name.

---

### Notes on What Was Checked and Found Correct

- **`current_user`'s internal CSRF check is a second, idempotent pass** —
  `apps/identity/api_auth.py` resolves the user first and only then calls
  `require_csrf`. The endpoint's own explicit `require_csrf(request)` is what puts the
  check first; the one inside the resolver is then a redundant pass over the same
  token. The endpoint's comment says so, and the order is right for it: a `401` says
  *"you are not signed in"* and a `403` says *"you are signed in, but this request
  could not be shown to come from this site"*.
- **`PUT`, not `PATCH`** — the frontend has no `api.PATCH` call site anywhere, and
  `/api/settings/notifications` is already a `PUT` with patch semantics. One verb for
  the product's settings writes.
- **`me` is the right read, and no new one was added** — the frontend already makes
  `GET /api/auth/me` on every page, and it is the only place the name is needed.
- **The endpoint's module imports no model** — it never touches
  `apps.identity.models` (import contract `models-identity`) and never writes directly
  (AD-5); `tests/architecture/test_no_direct_writes.py` scans it for exactly that.
- **The audit row carries no name** (AD-13) — `row.details == {}`, and the test asserts
  that neither *"Maya"* nor *"Ahmed"* appears in it rather than only asserting the
  shape.
- **The refusal writes nothing** — the refusal happens before the write, so the row
  keeps its old name, and no audit row is written either.
- **The endpoint returns the name the account holds** — the command returns the stored
  value, so the answer reports what the account now holds rather than what was asked
  for. The mutation probe confirms it.
- **The operation ids were read from the regenerated file**, not assumed —
  `apps_identity_api_me` and `apps_identity_api_put_profile`, both confirmed in
  `frontend/lib/api/openapi.json`.
- **The `DECLARED_UNCALLED` entry is a debt with a deadline** —
  `frontend/tests/endpoint-coverage.test.ts` lists `PUT /api/auth/profile` with the
  reason it has no caller yet, and the file's own stale-entry check fails the day the
  editor lands. It must be removed by the next work item.
- **The frontend fixture** — `frontend/lib/session.test.ts`'s `USER` gained `name: ""`.
  The type is `components["schemas"]["CurrentUserOut"]`, so `tsc` flagged the fixture
  as soon as the schema was regenerated.

---

## Work Item: profile-screen-and-editor

**Run**: run-eventpulse24-032
**Intent**: account-profile-name
**Work Item**: profile-screen-and-editor
**Reviewed**: 2026-11-13T12:10:00Z
**Files Reviewed**: 8

---

### Summary

| Category | Auto-Fixed | Applied | Raised |
|----------|------------|---------|--------|
| Code Quality | 1 | 3 | 0 |
| Architecture | 0 | 3 | 0 |
| Testing | 0 | 3 | 0 |
| **Total** | **1** | **9** | **0** |

**Tests Status**: Passing — 2439/2439 across the whole frontend suite, 20/20 mutation
probes caught, `pnpm typecheck` clean, `pnpm lint` with one **pre-existing** error
(`e2e/digest-opt-out.spec.ts:102`, committed in `5cffe04`, untouched by this run).

**Twelve findings came back. Eleven were applied, one was raised and checked and found
to be wrong.** They are listed below in the order they were found.

---

### Files Reviewed

- `frontend/app/settings/profile/page.tsx` (created, then rewritten)
- `frontend/app/settings/profile/loading.tsx` (created)
- `frontend/app/settings/profile/page.test.tsx` (created, then rewritten)
- `frontend/components/settings/profile-name.tsx` (created, then hardened)
- `frontend/components/settings/profile-name.test.tsx` (created)
- `frontend/lib/settings-sections.ts` (modified)
- `frontend/lib/profile-read.ts` (created, then **deleted**)
- `frontend/tests/settings-routes.test.ts` (modified)
- `frontend/tests/ad19-endpoint-coverage.test.ts` (modified)

---

### Applied Issues

#### 1. [Architecture] `lib/profile-read.ts` is a redundant second `GET /api/auth/me`

- **File**: `frontend/lib/profile-read.ts`
- **Description**: The module existed to read the profile separately from the session.
  **Every other settings route reads its own data because it has to — but this one's
  data is the name, and the session already carries it.** `CurrentUserOut` gained a
  `name` field for exactly this. A second read of the same endpoint, microseconds
  later, would answer the same question twice and double the route's API traffic for
  nothing.
- **Resolution**: **The module was deleted**, and the page now reads
  `session.user.name`. **The work item's own acceptance criteria settled it**: *"the
  `me` entry names `lib/session.ts` as its caller"* — so the intended design has no
  separate read, and the AD-19 entry was corrected to match.

#### 2. [Architecture] The AD-19 entry named a caller that does not exist

- **File**: `frontend/tests/ad19-endpoint-coverage.test.ts`
- **Description**: The `GET /api/auth/me` entry named `lib/profile-read.ts` as its
  caller. After the deletion that file was gone, so the entry pointed at nothing.
- **Resolution**: The caller is now `["lib/session.ts"]`, and the entry's docstring
  says why there is no second read. **A probe that names a caller which does not exist
  now fails the file** — so this cannot drift back.

#### 3. [Testing] The page test mocked a module that no longer exists

- **File**: `frontend/app/settings/profile/page.test.tsx`
- **Description**: The test mocked `@/lib/profile-read` and asserted an `unavailable`
  branch the page no longer has. The tree was inconsistent: the module was deleted but
  the test still imported it.
- **Resolution**: The mock and the `unavailable` test are gone. **The signed-out test
  was rewritten to say what it now covers** — `homeRoute` redirects an anonymous
  visitor to `/preview` before the branch runs, so the branch that is actually
  reachable is the one for a session that could not be *read*.

#### 4. [Testing] The `redirect` mock did not throw

- **File**: `frontend/app/settings/profile/page.test.tsx`
- **Description**: `redirect` in Next.js **never returns** — it throws a special error
  the framework catches. A mock that returned `undefined` would let the page fall
  through to the signed-out branch and render a screen for a visitor who was
  redirected away. **The test was asserting on a state the product never produces.**
- **Resolution**: The mock throws. **This immediately made the old signed-out test
  fail**, which is how the truth surfaced: that test was covering an unreachable
  branch, and it is now two honest tests — an anonymous visitor is redirected, and an
  unreadable session gets an empty shell.

#### 5. [Code Quality] A stale response could overwrite the name the user has typed

- **File**: `frontend/components/settings/profile-name.tsx`
- **Description**: **The editor saves on every keystroke**, so a second save can be
  started before the first comes back — and the first to *return* is not necessarily
  the newest request. A slow first response would replace the name the user had typed
  since with the server's answer to the *older* name. The user would watch their
  typing disappear.
- **Resolution**: A counter, and the rule *"only the newest save may write to the
  field"*. The counter is a **ref, not state** — it must not trigger a render of its
  own. **Two tests pin it**: a stale response arriving last must not overwrite the
  field, and a stale save's failure must not put a failure line on screen. **Both are
  mutations now.**

#### 6. [Code Quality] The field was not marked invalid when the API refused it

- **File**: `frontend/components/settings/profile-name.tsx`
- **Description**: The failure line says what went wrong, but the field itself did
  not. A person tabbing back to it had no reason to know it held a value the server
  will not take.
- **Resolution**: `aria-invalid` is set when there is a failure. **Only a refusal
  marks it invalid** — an offline failure is not the field's fault, and an invalid
  empty field with no error on it would be a form demanding something.
- **A note on what was *not* added**: no `aria-describedby` pointing at the failure
  line. `SaveFeedback` is shared by four islands and renders **no id of its own**, so
  a reference to an id that does not exist would be a description of nothing. The
  `role="alert"` on the line already announces it.

#### 7. [Code Quality] The page reported a failure it did not have

- **File**: `frontend/app/settings/profile/page.tsx`
- **Description**: The signed-out branch rendered `SettingsStates`, whose copy is
  *"Couldn't load your settings."* — but **nothing failed to load here.** There was
  nothing to load: the visitor is not here for the settings, and there is no read to
  fail.
- **Resolution**: The branch renders an empty shell, as the settings index already does
  for the same reason. The page's docstring says so.

#### 8. [Code Quality] The island's docstring described a fallback that is not its job

- **File**: `frontend/components/settings/profile-name.tsx`
- **Description**: The docstring described the email-derived fallback as though the
  island applied it. **The island is handed the *stored* name — `""` when none is set
  — and shows exactly that.** The display fallback is applied by the *server page*,
  which has the email; the island has no email to derive anything from.
- **Resolution**: The docstring now says the island shows the stored name exactly, and
  that the fallback is the page's rule — **two rules to keep in sync otherwise**.

#### 9. [Testing] Stale docstring counts

- **Files**: `frontend/components/settings/settings-nav.tsx`,
  `frontend/app/settings/page.tsx`
- **Description**: The counts *"six times over"*, *"the same six links"* and *"Six rows
  in a `<ul>`"* were all written when there were six sections. **There are seven.**
- **Resolution**: The live counts were made count-free — *"once per settings section"*,
  *"one row per section"* — so they cannot go stale again. **The historical "four of
  six" was left alone**, because it is a statement about the six screens that shipped
  before the index existed, and it is still true.

#### 10. [Code Quality] The section's `aria-label` collided with the field's label

- **File**: `frontend/components/settings/profile-name.tsx`
- **Description**: The `<section aria-label="Your name">` and the field's own
  `<span>Your name</span>` were **two elements answering the same question** — and the
  island's tests failed with *"Found multiple elements with the text of: Your name"*.
- **Resolution**: The section is labelled *"Profile"*, and the field keeps *"Your
  name"*. The section's own docstring says why the two must differ.

#### 11. [Testing] The rail assertions matched on text, and found two elements

- **File**: `frontend/app/settings/profile/page.test.tsx`
- **Description**: The name is on screen in **two** places — the rail's account row and
  the editor's field — so a text query found both.
- **Resolution**: The rail's row is found by its **accessible name** (`Account: Maya
  Ahmed`), which is the thing the screen reader announces anyway.

---

### Raised, Checked, and Found to Be Wrong

#### 12. [Testing] The settings-route rule requires two signed-in branches

- **File**: `frontend/tests/settings-routes.test.ts`
- **Description**: The finding was that the rule *"requires at least two signed-in
  `<AppShell>` branches per settings page, but `/settings/profile` has only one"* —
  and that the fix was to give the page a second branch.
- **Why it is wrong**: **The finding was right about the symptom and wrong about the
  cause.** The rule's floor of two exists because most settings pages read their own
  data, and that read can fail — so they have two branches: an `unavailable` shell and
  the page itself. **This page reads nothing of its own**, so it has one, and
  manufacturing a second would mean **adding a redundant read to satisfy a test** —
  which is the thing finding 1 removed.
- **Resolution**: **The floor was lowered to one, and the test's docstring now records
  why.** The floor's purpose is to guard against the loop finding nothing and passing
  vacuously — and **one branch is walked once, not vacuously**. The loop walks *every*
  branch it finds and demands the sub-nav after each.

---

### Summary of the Review

**The review's most valuable finding was the one that removed a module.** The
implementation had built `lib/profile-read.ts` to satisfy a test assertion — a second
`GET /api/auth/me` whose only purpose was to give the page the second branch that
`tests/settings-routes.test.ts` asked for. **A test asserting a shape can be met by
adding the shape, and the shape was wrong.** The work item's own acceptance criteria
gave the answer — *"the `me` entry names `lib/session.ts` as its caller"* — and
following them removed both the module and the assertion's over-specification.

**Two of the applied findings were bugs no test could have found.** The stale-response
race in the island is invisible to a unit test that saves once; it exists because a
free-text field is typed a character at a time, so two saves overlap. And the
`redirect` mock that did not throw was making the page test assert on a state the
product never produces — **the mock was wrong in the same direction as the code it
mocked**, which is the most dangerous kind of test bug, because the test would keep
passing after the code changed in exactly the way it should not have.

**The item closes with no net diff to `frontend/tests/endpoint-coverage.test.ts`.**
Item 2 had added the `PUT /api/auth/profile` entry to `DECLARED_UNCALLED` and said it
must be removed by the next item that calls the endpoint. This is that item, the entry
is gone, and the file is byte-identical to `HEAD`.

---

## Work Item: reduced-account-sheet

**Run**: run-eventpulse24-032
**Intent**: account-profile-name
**Work Item**: reduced-account-sheet
**Reviewed**: 2026-11-13T12:25:00Z
**Files Reviewed**: 2

---

### Summary

| Category | Auto-Fixed | Applied | Flagged, Out of Scope |
|----------|------------|---------|----------------------|
| Code Quality | 0 | 2 | 1 |
| Architecture | 0 | 1 | 0 |
| Testing | 0 | 4 | 0 |
| Accessibility | 0 | 0 | 1 |
| **Total** | **0** | **7** | **2** |

**Tests Status**: Passing — 2449/2449 across the whole frontend suite, 11/11 mutation
probes caught, `pnpm typecheck` clean, `pnpm lint` with one **pre-existing** error
(`e2e/digest-opt-out.spec.ts:102`, committed in `5cffe04`, untouched by this run).

**Eight findings came back. Seven were applied, one was flagged as out of scope, and
one was checked and consciously left.**

---

### Files Reviewed

- `frontend/components/shell/account-menu.tsx` (modified)
- `frontend/components/shell/account-menu.test.tsx` (created)

---

### Applied Issues

#### 1. [Testing] The "Sign out is last" assertion could not fail

- **File**: `frontend/components/shell/account-menu.test.tsx`
- **Description**: The assertion was built on `signOut.closest("div")`, **which is
  `SignOutButton`'s own wrapper** — a div with exactly one child. So *"the last child
  contains the button"* is true by construction, **wherever the button sits.** The
  review proved it with two mutations: Sign out moved to the top of the panel, and
  Sign out moved into the middle of it. **Both left the suite 9/9 green.**
- **The docstring claimed *"The order is the rule"* while the rule was unpinned.**
- **Resolution**: The panel root now carries a `data-account-panel` hook, and the
  assertion is made against the panel's **own children**. A floor assertion — *"at
  least three children"* — was added alongside it, **so a refactor that flattened the
  markup fails loudly instead of passing vacuously.** That floor is the guard the repo
  uses elsewhere for exactly this reason: *"the loop would find nothing and pass
  vacuously, which is the failure mode of every source-text assertion."*

#### 2. [Testing] The "no Settings row" and "no Pricing row" assertions pinned the label, not the route

- **File**: `frontend/components/shell/account-menu.test.tsx`
- **Description**: Testing Library's `name` option is an **exact string** match, so
  the two assertions only caught a re-added link whose visible text was literally
  "Settings" or "Pricing". **The review proved the gap with a mutation**: re-adding
  both links as `<Link href="/settings">Account settings</Link>` and
  `<Link href="/pricing">Upgrade</Link>` — **which re-opens exactly the two doors this
  item closed** — left the suite **9/9 green.**
- **Resolution**: A new test asserts the panel's **whole set of destinations**:
  `expect(hrefs).toEqual(["/settings/profile"])`. **The label checks were kept** — they
  pin the wording, which the work item specifies — **but the href assertion is the real
  one.** This is how the repo pins link destinations elsewhere:
  `tests/settings-routes.test.ts` asserts `code.match(/href="\/settings/g)` is empty,
  not that a label is absent.

#### 3. [Code Quality] The `email` prop's docstring said the session carries nothing but the email

- **File**: `frontend/components/shell/account-menu.tsx`
- **Description**: The prop's docstring claimed *"the only account fact the session
  carries — `CurrentUserOut` sends the id, the email and the onboarding status, and
  nothing else — so it is the only one shown."* **That is now false**: the schema
  carries `name` too, and the panel shows it. **The sentence sat on the `email` prop,
  one screen away from the panel that displays the name.**
- **Resolution**: The docstring now says the session carries **four** things — the id,
  the email, the name and the onboarding status — and that **the panel shows two of
  them**. The id is the account's key rather than something to show, and the onboarding
  status is a fact about a flow rather than about the person.

#### 4. [Testing] The More-sheet test rendered `MoreMenu`, not the bottom bar

- **File**: `frontend/components/shell/account-menu.test.tsx`
- **Description**: The work item says *"the bottom bar's More sheet"*, and the file's
  own docstring said *"the bottom bar"*. **But the test imported `MoreMenu` directly**
  — which tests the component without the bar that mounts it.
- **Resolution**: The test renders `BottomTabNav` and opens the More sheet through it,
  **the way `nav-routes.test.tsx` does**, and asserts the panel's link is inside the
  More dialog. The dynamic `await import` became a static one.

#### 5. [Code Quality] The dynamic import was unnecessary

- **File**: `frontend/components/shell/account-menu.test.tsx`
- **Description**: There is no circular-import problem and no mock that required
  laziness. `nav-routes.test.tsx` imports statically.
- **Resolution**: Static import.

#### 6. [Testing] The panel's hook was needed before the ordering assertion could work

- **File**: `frontend/components/shell/account-menu.tsx`
- **Description**: The `data-account-panel` hook is what finding 1's fix finds the
  panel by, and its own docstring says why: **without it, the nearest `<div>` to the
  Sign out button is the button's own wrapper**, and an assertion built on that is
  true whatever the panel's order is.

#### 7. [Testing] The panel's *whole* destination set is now asserted

- **File**: `frontend/components/shell/account-menu.test.tsx`
- **Description**: Finding 2's fix. Stated separately because **it is the assertion
  that would catch a future door** — not the two this item closed, but any new one.
  A panel about the account that grows a link to anywhere is a change somebody chose,
  and this test says so.

---

### Flagged and Confirmed as Out of Scope

#### 8. [Architecture] The `name` prop means two different things across the shells

- **File**: `frontend/app/settings/profile/page.tsx`
- **Description**: The profile page passes the **stored** name (falling back to the
  email-derived one) to `AppShell`; **every other page passes the email-derived name.**
  So the sheet's `name` prop means two different things depending on which page opened
  it, and the destination of the new "Edit your name" link is **the one page whose rail
  disagrees with all the others.**
- **Why it is out of scope**: **This is the next work item** (`display-name-everywhere`),
  and the profile page's own docstring says so — *"That is a separate change, and it is
  a display rule."* **Fixing it here would have meant doing the next item's work in
  this one**, which is how a run's diffs stop being reviewable.
- **Resolution**: Recorded, not fixed. **The sequencing is intended**: the profile
  screen shows the stored name first, and the next item carries it to every other page.

---

### Checked and Left Alone

#### 9. [Accessibility] The link's accessible name does not match its destination's heading

- **File**: `frontend/components/shell/account-menu.tsx`
- **Description**: The link reads **"Edit your name"**; the destination's `<h1>` is
  **"Profile"**. A screen reader user activating the link lands on a page whose heading
  does not carry the name they were given — though the page's subtitle does
  (*"Your name, and how we address you."*).
- **Why it is left**: **This is the work item's explicit decision.** *"The link's copy
  is 'Edit your name', not 'Profile'. The section in the settings nav is 'Profile'; the
  link says what it does."* The counter-rule in `settings-sections.ts` is about **nav
  labels** — a label that renamed the screen on the way to it — and **an action link is
  an action, not a location.** Changing it would break the item's specification, not
  fix a defect.
- **Resolution**: Left as specified, with the reasoning already written in the code.

---

### Summary of the Review

**The two findings that mattered were both tests that could not fail** — and both were
proven, not asserted. The reviewer ran the mutations and showed the suite staying
**9/9 green** for: a Sign out button moved to the top of the panel, a Sign out button
moved into the middle, a `/settings` link relabelled "Account settings", and a
`/pricing` link relabelled "Upgrade".

**Every one of those four mutations re-opens exactly what this item closed.** The
panel's two removed doors were asserted *by label*, and a label is the thing that
drifts; the ordering was asserted against *the wrong element*, and the wrapper it
found made the claim true by construction. **The mutation probes that existed before
the review did not catch either** — and that is the point of writing them against the
assertion rather than against the intent.

**The fixes are the ones the repo already uses elsewhere**: assert on the **href**
(`settings-routes.test.ts` does), and add a **floor** so the assertion cannot pass
vacuously (`settings-routes.test.ts` does that too, for the same reason).

**The review also caught a docstring that had become false in the opposite direction
from the one the work item predicted.** The work item said the *"no endpoints yet"*
sentence would become *half* false — because the name gained an endpoint. It was the
**other** sentence, on the `email` prop, that went fully false, and it went false
because the session gained a field. **A docstring that argues for a position the code
has left is the same defect these docstrings exist to prevent** — and that one had
quietly started arguing for a position the code had *left behind*.

---

## Project Tooling Used

The following project linters were detected and used:

- **Ruff** (`backend/pyproject.toml`) — `ruff check` and `ruff format`
- **import-linter** (`backend/pyproject.toml`) — `lint-imports`, 19 contracts
- **pytest** — the backend suite
- **Django system checks** — `manage.py check`, `makemigrations --check --dry-run`
- **ESLint / Prettier** (`frontend/package.json`) — `pnpm lint`
- **TypeScript** — `pnpm typecheck` (`next typegen && tsc --noEmit`)
- **Vitest** — `pnpm test`
- **openapi-typescript** — `make client`, the contract regeneration

---

## Standards Referenced

- `.specs-fire/standards/constitution.md`
- `.specs-fire/standards/coding-standards.md`
- `.specs-fire/standards/testing-standards.md`
- `.specs-fire/standards/system-architecture.md`
- `.specs-fire/standards/tech-stack.md`
- `ARCHITECTURE-SPINE.md` (AD-2, AD-3, AD-5, AD-13, AD-19, D13)

## Work Item: display-name-everywhere

**Run**: run-eventpulse24-032
**Intent**: account-profile-name
**Work Item**: display-name-everywhere
**Reviewed**: 2026-11-13T18:29:00Z
**Files Reviewed**: 20

---

### Summary

| Category | Auto-Fixed | Applied | Flagged, Out of Scope |
|----------|------------|---------|----------------------|
| Code Quality | 0 | 2 | 0 |
| Architecture | 0 | 0 | 0 |
| Testing | 0 | 3 | 0 |
| Accessibility | 0 | 0 | 0 |
| **Total** | **0** | **5** | **0** |

**Tests Status**: Passing — 2476/2476 across the whole frontend suite, 30/30 mutation
probes caught, `pnpm typecheck` clean, `pnpm lint` with one **pre-existing** error
(`e2e/digest-opt-out.spec.ts:102`, committed in `5cffe04`, untouched by this run).

**Five findings came back. All five were applied.** The review was given the changed
files and asked specifically to *try to make the assertions fail* — and the first
finding it returned was exactly that: **a page can hand-build the name and every
assertion in the file stays green.**

---

### Files Reviewed

**Created**

- `frontend/lib/display-name.ts`
- `frontend/lib/display-name.test.ts`
- `frontend/tests/display-name.test.ts`
- `frontend/tests/stored-name-in-shell.test.tsx`

**Modified (the fifteen pages)**

- `frontend/app/page.tsx`, `frontend/app/browse/page.tsx`, `frontend/app/conflicts/page.tsx`,
  `frontend/app/timeline/page.tsx`, `frontend/app/settings/page.tsx`,
  `frontend/app/settings/{account,calendars,collections,digest,profile,quiet-hours,reminders}/page.tsx`,
  `frontend/app/events/[id]/page.tsx`, `frontend/app/events/[id]/reminders/page.tsx`,
  `frontend/app/personal-events/[id]/reminders/page.tsx`

---

### Applied Issues

#### 1. [Testing] The "no hand-built name" assertion could not fail

- **File**: `frontend/tests/display-name.test.ts`
- **Description**: The assertion allow-listed the bare identifier `name` — **and six
  pages bind the name to a local `const name` and pass that**, so the shape was the
  established one, not a hypothetical. The review proved the gap with a mutation:
  `app/settings/account/page.tsx` rewritten to
  `const name = "Maya " + session.user.email.split("@")[0];` with the import deleted —
  **which left all 7 tests in the file green.**
- **The file's own docstring claims the property** — *"no page carries a copy of its own"* —
  **while a page could hand-build the name and pass every assertion.**
- **Resolution**: The rule is now **traceability**, not shape. A prop is legal if it is
  the helper's call, the empty string, or a local binding whose definition is *exactly*
  the helper's call (a ternary of the helper and `""` counts — three pages use that
  form). **Anything else is a hand-built name**, and the failure message names the
  binding and its definition so the fix is obvious.
- **Both review mutations now fail**: the local binding and the inline prop.

#### 2. [Testing] The "no local copy" assertion matched a name, not a rule

- **File**: `frontend/tests/display-name.test.ts`
- **Description**: The assertion matched `/function\s+displayName\s*\(/` — so a copy
  called `localName` or `greetingName` is **the same copy under another hat**, and it
  passed. The review proved it with a mutation that added a `localName` function
  deriving the name from the email: **all 7 tests stayed green.**
- **Resolution**: The rule is now about **the rule**, not the identifier. A page that
  derives a name from an email — by splitting it on `@` or on the separator set — is
  carrying a copy, whatever the function is called.

#### 3. [Testing] The docstring promised "not trimmed" and nothing pinned it

- **File**: `frontend/lib/display-name.test.ts`
- **Description**: The module's docstring says a stored name is shown *"not trimmed, not
  re-cased"*. **The "not re-cased" half was pinned; the "not trimmed" half was not** —
  a helper that trimmed left every test green. The review also noted the **absence** of
  a whitespace-only case, which is the one input that would make the rail blank.
- **Resolution**: Two tests added — `is not trimmed either` (the name keeps its
  surrounding spaces) and `is shown even when it is only whitespace` (a name of spaces
  is shown as spaces). **The second one records the reasoning**: the emptiness check is
  `name === ""`, not a trim, and **the backend owns the question of what counts as
  empty** — it trims on write, so `""` is the only empty state the account can hold.

#### 4. [Code Quality] A dangling docstring described a deleted function

- **File**: `frontend/app/settings/calendars/page.tsx`
- **Description**: The local `displayName` was deleted, but its docstring stayed:
  *"The greeting name, from the email's local part. Matches the other settings
  routes."* **It described a function that no longer existed, and it described the old
  rule** — the very thing this item replaced.
- **Resolution**: Removed. **A grep across `app/` for "local part" now returns nothing**,
  which is the check that would have caught it.

#### 5. [Code Quality] A second dangling docstring, on the personal-events route

- **File**: `frontend/app/personal-events/[id]/reminders/page.tsx`
- **Description**: The same defect as finding 4 — *"A name for the sidenav's account
  row — the same rule every authed route uses."* — left behind by the same deletion.
  **It was found by grepping for trailing docstrings in the changed pages**, after
  finding 4 had shown the pattern existed.
- **Resolution**: Removed.

---

### Checked and Left Alone

#### 6. [Testing] The two regexes' limits are acceptable, and they fail loudly

- **File**: `frontend/tests/display-name.test.ts`
- **Description**: The review checked both source-text regexes for the failure modes
  this repo cares about:
- **The shell regex `/<AppShell\s+name=\{([^}]*)\}/g`** stops at the first `}`. For
  `name={displayName(session.user)}` the capture ends at the shell's own closing
  brace, because `session.user` contains none — so it works. **A prop containing a
  nested `}` would be truncated and flagged as an offender** — a *false positive*, which
  fails loudly rather than silently. **Accepted.**
- **The call regex `/\bdisplayName\s*\(([^)]*)\)/g`** truncates at the first `)` — so a
  multi-line call or a nested argument would be captured incompletely and **would not
  match the allow-list, so it would be flagged as wrong**. **That is the safe
  direction.** The review verified both by mutation: a multi-line call fails the test.
- **Multiple calls in one page are handled correctly** — `match()` with `/g` returns
  every call, and the loop checks each independently. Verified across all fifteen
  pages; `app/browse/page.tsx` has two calls and both are `session.user`.

#### 7. [Code Quality] `frontend/lib/display-name.ts` is genuinely server-safe

- **File**: `frontend/lib/display-name.ts`
- **Description**: The review confirmed by mutation that the module has **zero imports**
  and **no `"use client"` or `"use server"` banner**, and that the comment-stripping
  convention is applied correctly — **the module's own docstring names `"use client"` in
  prose, and the assertion reads the comment-stripped source, not the raw file.**
- **One note, for the record**: the `code()` helper's comment stripper corrupts string
  literals containing `//` or `/*`. **No page has such a string in code** — the only
  hits are `` `/api/*` `` inside JSDoc prose, which is stripped as a comment anyway.

---

### Summary of the Review

**The first finding is the one that mattered, and it is the repo's own lesson applied to
new code.** The file asserted *"no page carries a copy of its own"* and *"no page passes
a hand-built name"* — and **a page could do exactly the second thing while passing
every assertion in the file**, because the allow-list named a shape without asking
where the shape came from.

**The fix is the same one the repo uses for every other assertion of this kind: assert
the property, not the shape.** The name must be *traceable* to the helper — and a copy
is a copy of the *rule*, whatever it is called.

**Five findings, five applied, none flagged.** The two code-quality findings were the
same defect twice — a docstring left behind by a deletion — and the second was found
only because the first one had shown the pattern existed.

---

## Work Item: contract-and-e2e-proof

### Summary

**Two work items, reviewed together**, because the second was found by the first.

| | |
|---|---|
| **Contract** | Already committed and true. `make client` leaves the tree clean; `tests/api/test_contract.py` passes. **Verification, not work.** |
| **E2E proof** | The new `profile-name.spec.ts` (7 tests) and the updated `settings-navigation.spec.ts` (5 tests) — **12 passing against the real stack**. |
| **Live name** | Found by the e2e proof, fixed, and proved again in a browser. **9 mutation probes, 9 caught.** |

### Files Reviewed

- `frontend/e2e/profile-name.spec.ts` (new)
- `frontend/e2e/helpers.ts`
- `frontend/e2e/settings-navigation.spec.ts`
- `frontend/lib/session-name.ts` (new)
- `frontend/tests/live-display-name.test.tsx` (new)
- `frontend/components/shell/account-menu.tsx`
- `frontend/components/settings/profile-name.tsx`
- `frontend/app/settings/profile/page.tsx`
- `frontend/components/settings/profile-name.test.tsx`

### Applied Issues

**1 — The e2e suite was silently proving a stale product.** *(found by running the spec,
not by reading it)*

The first run of the new spec failed 4 of 7 tests. **Three of the four were the
product's fault, not the test's.** The rail showed the old name after a save, because
the shell's name is a server render and nothing in the design made it live.

**The product's own docstring had recorded this as a limitation** — *"So the rail is
stale until the next load … it is said here rather than left to be discovered"* — and
**a documented limitation is still a limitation** when the requirement was that the
stored name replaces the email-derived one in the rail, the bottom bar and every page.

Fixed by the `live-name-in-the-shell` work item below.

**2 — The `beforeEach` cleared the account after the page had been rendered.** *(found
by the second run)*

The sign-in landed on a page the server drew with whatever name the account held
*then*; clearing the account afterwards did not redraw the rail. **The account said "no
name" and the screen said "Maya Ahmed", and the screen was the one out of date.** The
fix is a reload after the clear, and the reason is written down in the spec.

**3 — The line-break test could never have failed.** *(found by the test not passing)*

The test filled the field with `"Maya\nAhmed"` and waited for a refusal. **The HTML
value sanitization algorithm strips `\r` and `\n` from a single-line input's value**, so
the newline never reached the field, let alone the API — **the API had been asked to
save a legal name.**

Rewritten to use BEL (`\u0007`), which the browser does not strip and the backend does
refuse, and the reason is written down so the next reader does not "fix" it back to a
newline.

**4 — A control character written as a literal is invisible.** *(found by reading the
file back)*

The first version of the rewrite put a literal BEL in the source. **A reader cannot
see it, a formatter may strip it, and a diff shows nothing where the character was.**
Replaced with a named constant, `BEL = "\u0007"`, written once.

**5 — The e2e helper was duplicated.** *(found by reading the two specs side by side)*

`resetSignInThrottle` had a copy inside `settings-navigation.spec.ts`. **Two copies of
a throttle reset is two things to keep in sync**, and `helpers.ts` is where the other
shared helpers already live — so it moved there, and both specs import it.

**6 — The `useCallback` dependency was a real bug, not a style note.** *(found by
ESLint)*

The island's `save` callback closed over `email` and listed no dependencies. **A
changed address would have been published with the old one** — and the address is
exactly what the fallback is derived from. The dependency is now `[email]`.

**7 — The shell's live name was never asserted on the sheet.** *(found by the mutation
probe)*

The first version of `live-display-name.test.tsx` asserted only on the rail row, so
the account sheet could show the stale name and the suite stayed green. **A test that
never fails proves nothing** — and this one had never failed, because it had never
been asked the question. The sheet assertion was added, and the mutation was caught.

### Checked and Left Alone

**8 — The store is a module, and not a React context.** A context provider would have
to sit *above* the rail, and the rail is rendered by `AppShell`, which every page
mounts by hand — **a provider means fifteen pages each wrapping their own
`<AppShell>`**, which is the exact thing the display-name work just finished
consolidating. `useSyncExternalStore` is React's own answer to "a value outside React
that React must re-render for", and it needs no provider.

**9 — Only the two leaves read the store.** `Sidenav` and `BottomTabNav` only forward
the name, so **neither file changed at all**. The read is in `AccountMenu` (the row)
and `AccountPanel` (the sheet) — the two components that actually *display* the name.

**10 — The store holds the display name, not the stored name.** The two are different
questions and the shell asks the display one. **So the island holds the address too**,
and derives the display name with the *same* shared helper the pages use — one rule,
one implementation. Publishing the stored name instead would blank the rail for anyone
who clears their name, and the mutation probe for exactly that mistake is caught.

**11 — The store survives a navigation, and that is correct.** A soft navigation
re-renders the server components, which read the name the account now holds — the same
name the store holds, because the save went through the API first. **The two agree.**
A hard reload empties the store and the seed takes over, which is the right direction:
the server is the source of truth, and a reload asks it.

**12 — The five failing e2e tests are pre-existing.** `digest-opt-out.spec.ts` (3) and
`unwired-surfaces.spec.ts` (2) fail **identically on the baseline** — verified by
stashing this work and re-running. The `unwired-surfaces` failures are a browse card
linking to `/pricing` instead of `/events/…`; the `digest-opt-out` failures are a
missing "What's in your Pulse Digest" link. **Neither has anything to do with the
account's name**, and both were left alone.

**13 — The one lint error is pre-existing.** `e2e/digest-opt-out.spec.ts:102` — the
file is unmodified by this work and was left alone rather than fixed as unrelated
churn.

### Summary of the Review

**The important thing this review found is that the e2e proof found the product's
defect.** The unit tests were green, the page tests were green, the contract was
committed and true, and the product still **contradicted itself**: the account sheet
said "here is who you are" while the row it was opened from said something else, on
every page, for every user who changed their name.

**That is exactly the class of defect an e2e suite exists to catch** — and it was
caught only because the walk-through was written to ask the questions a person would
ask, and then actually run.

**A second finding was the test that had never failed.** The live-name suite's first
version asserted only on the rail row, and mutation 9 — the sheet showing the stale
name — left it green. **The mutation probe is what surfaced it**, and the sheet
assertion is now in place.

**Nothing was flagged and left unresolved.**
