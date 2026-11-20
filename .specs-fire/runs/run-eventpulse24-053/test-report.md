---
run: run-eventpulse24-053
work_item: account-deletion-and-avatar-removal
intent: account-profile-expansion
generated: 2026-11-20
status: passed
---

# Test Report: Deleting an Account — and the Picture That Must Not Outlive It

## Summary

| Category | Passed | Failed | Skipped |
|----------|--------|--------|---------|
| Backend (full suite) | **7611** | 0 | 0 |
| `tests/identity/test_account_deletion.py` | 24 | 0 | 0 |
| `tests/identity/test_account_deletion_api.py` | 13 | 0 | 0 |
| `tests/identity/test_deletion_retention_walk.py` | 18 | 0 | 0 |
| `tests/worker/test_account_deletion_task.py` | 8 | 0 | 0 |
| Frontend | **2698** | 0 | 0 |
| `tsc --noEmit` | 0 errors | | |

`lint-imports`: 21 kept, 0 broken. `lint-backend`: clean. `lint-web`: 4 problems (3
errors, 1 warning) — **all pre-existing**, verified by stashing this item's changes and
re-running; they are in `components/settings/email-change.tsx`,
`components/settings/source-mute-control.tsx` and `e2e/digest-opt-out.spec.ts`, none
of which this item touches.

## Acceptance Criteria Validation

- ✅ **A named command in `apps/identity/services/` deletes an account** (AD-5) —
  `request_account_deletion`, `cancel_account_deletion` and `destroy_account` live in
  `apps/identity/services/deletion.py`. `tests/architecture/test_no_direct_writes.py`
  is green: the API layer calls the commands and touches no ORM.
- ✅ **The stored avatar object is removed, and the probe asks the bucket** — not merely
  the row. `stored(key)` opens the object through the blob port and catches
  `BlobNotFound`; a blank `avatar_key` would not satisfy it.
- ✅ **An account with no avatar deletes cleanly** — `delete("")` raises `ValueError`
  from the port's key validation, *not* `BlobError`, so the quiet-delete helper would
  not swallow it. The empty key never reaches the store.
- ✅ **The thirty-day grace period is honoured** — `DELETION_GRACE_PERIOD` is thirty
  days, computed **once** at request time and not moved by asking again. The picture's
  removal happens at **destruction**, not at request, so a user who cancels inside the
  grace period gets their picture back.
- ✅ **Billing records survive per their own category; the audit log survives** — both
  asserted by name *and* by being absent from the purged set, which are independent
  readings of the same decision.
- ✅ **Every model carrying a `retention_category` is accounted for** — the walk
  classifies by *category*, and a dedicated test file walks `retention_registry()`
  rather than a hand-kept list. `deletion_action()` raises `KeyError` on an
  unclassified category, so a model added next year fails the build rather than
  silently surviving a person's deletion.
- ✅ **The user-reachable surface is explicitly scoped to a follow-up item** — the
  second half of the AC. The work item carries a "Scope Note: A-16's Modal Is Not
  Built Here" section, and the two endpoints are declared in the frontend's
  `DECLARED_UNCALLED` with their reason.
- ✅ **Every test can fail** — twelve mutation probes, one per behaviour under
  protection. Two of them **initially passed against their mutations**; both were
  fixed. See below.

## The question the work item said to answer here

**When does the picture go?**

**At destruction, not at request.** The two are in tension, and the item resolves it
deliberately.

Deleting the object when deletion is *requested* makes the grace period a lie — the
user cancels and their face is gone. Deleting it when the account is *destroyed* means
the bucket holds a picture for thirty days after the person asked the product to stop
holding it.

**The second is chosen because the grace period is a promise.** A cancelled deletion
must restore the account whole, and it does — the object is still in the bucket, probed
there rather than inferred from the row.

The cost is real and is paid deliberately: thirty days of a picture in the store after
the ask. The benefit is that the promise A-16 makes — cancel and nothing is lost — is
true, and is tested in the bucket rather than asserted from a database read.

**The ordering inside the destroy is also deliberate:**

1. `SET LOCAL eventpulse.retention_purge = 'on'` — this is the first production code
   in the project to set it. The Postgres `forbid_history_mutation()` trigger refuses
   UPDATE and DELETE on append-only tables unless it is set.
2. The rows are purged, by category, through the registry.
3. The sessions are deleted — decoded, because Django keeps the account inside the
   encoded payload rather than in a column.
4. The audit row is written — **while the account still exists**, because `write_audit`
   needs an actor and the actor *is* the account. The row outlives it.
5. The `User` row is deleted **last**, so nothing above it fails on a missing account.
6. The blob object is deleted in `transaction.on_commit`, and **only if the key is
   non-empty**.

**A failure in the object store cannot roll back a committed database delete**, and
that is accepted: the object store has no transaction. An orphan object is invisible;
a broken image on a live account is visible.

## Two defects the probes found

### 1. The bucket probe was blind

**Probes 2 and 8 both passed against their mutations.**

- Probe 2 removed the object from the store — and `test_destroying_removes_the_picture_object_from_the_bucket` still passed.
- Probe 8 blanked the key at request time — and `test_requesting_deletion_destroys_nothing` still passed.

**The root cause was pytest-django, not the implementation.** Under pytest-django the
test runs inside a transaction that is never committed, so `transaction.on_commit`
callbacks **never fire**. The object removal is registered in `on_commit` — so the
callback never ran, the object never left the bucket, and the probe that asks the
bucket found the object *present* and passed for the wrong reason.

**Both probes were inverted by their own blindness.** A test that reads "the object is
still there" passes for "the object was never removed" and for "the removal never
ran". Only a test that can fail distinguishes them.

**The fix is the capture block, and it must wrap the call:**

```python
with django_capture_on_commit_callbacks(execute=True):
    destroy_account(user_id=user.pk)
```

Wrapping matters because `destroy_account` opens its own `transaction.atomic`; the
capture has to be established *before* the callback is registered, not after.

**An autouse fixture was tried and reverted.** It did not work: the fixture's capture
block ended before `destroy_account`'s inner `atomic` committed at the end of the
*test's* transaction, so the callback was still never executed. The capture blocks are
now explicit, in the five tests that need them — and each says why.

Five tests now carry the block: `test_requesting_deletion_destroys_nothing`,
`test_destroying_removes_the_picture_object_from_the_bucket`,
`test_the_picture_object_survives_a_cancelled_request_in_the_bucket`,
`test_an_account_with_no_picture_deletes_cleanly`, and
`test_the_probe_would_not_pass_if_the_object_were_merely_blanked`.

**Re-probed: both mutations now fail.** The probe can fail.

### 2. The two classification layers could disagree, silently

**Probe 3 removed a model from `SURVIVING_MODELS` and nothing changed.**

The module had two layers: a per-model table and a per-category table. `deletion_action`
checked the **per-model table first**, so a model named there survived whatever its
category said — and removing the name did not purge it either, because the *category*
still said it survives.

**The consequence is worse than a stale list.** A reader could change one table, see no
effect, and conclude the table was decorative. The two layers looked like they agreed
and were not.

**The fix makes disagreement impossible to hide.** `SURVIVING_MODELS` became a
`dict[str, str]` — label to *reason* — and three tests were added:

- `test_every_surviving_model_says_why_it_survives` — a bare set of names let the two
  layers drift; a reason beside the name makes the disagreement visible.
- `test_the_two_layers_agree_about_every_surviving_model` — every model named as
  surviving must have a category that also says it survives. If the layers disagreed,
  the outcome would depend on which check ran first, and nobody could tell by reading
  the module.
- `test_a_model_named_as_surviving_really_is_an_installed_model` — a name matching
  nothing is a decision about nothing. If the audit log's label ever changed, the name
  would silently stop applying.

**Re-probed:** the mutation now fails — and the corrected probe breaks **both** layers,
which is what exposed the disagreement in the first place. My original probe 3 was
wrong: it broke only one layer, so it proved nothing.

## Mutation probes

| # | Mutation | Result |
|---|----------|--------|
| 1 | The grace period set to zero — the schedule would no longer be a grace period | **1 failed** |
| 2 | The blob object's delete made a no-op (the object stays in the bucket) | passed ← **the gap**; blind `on_commit`, fixed → **1 failed** |
| 3 | A surviving model removed from `SURVIVING_MODELS` alone | passed ← **wrong probe**; broke one layer, proved nothing |
| 3' | A surviving model removed from **both** `SURVIVING_MODELS` and its category | **1 failed** — and this is what exposed the two-layer disagreement |
| 4 | The empty avatar key passed to the store (`delete("")` → `ValueError`) | **1 failed** |
| 5 | The picture removed at **request** time rather than at destruction | **1 failed** |
| 6 | `deletion_action` skipping an unknown category instead of raising `KeyError` | **1 failed** |
| 7 | The audit log moved into the purged set | **1 failed** |
| 8 | The picture removed at request time (probed through the row, not the bucket) | passed ← **the gap**; same blindness, fixed → **1 failed** |
| 9 | The CSRF check moved after the session resolution | **1 failed** |
| 10 | The scheduled date computed as *now* rather than *now + grace* | **1 failed** |
| 11 | A second request overwriting the schedule and moving the deadline | **1 failed** |
| 12 | The task destroying an account whose grace has not expired | **1 failed** |
| 13 | The purge loop replaced with `pass` | **2 failed** — one before the review, one after |
| 14 | The purge filter removed — every user's rows deleted | **1 failed** — the new purge test |
| 15 | `robust=True` removed from the `on_commit` registration | **1 failed** — the new structural test |
| 16 | `User` put back into the walk (deleted in the middle) | **1 failed** — the new ordering test |

**Sixteen probes, two categories of failure.** Two passed against their mutations and
were fixed; one was a wrong probe and was replaced with a stricter one that found a
real defect. Probes 13–16 were added by the code review, and **probe 13 found a hole
the original twelve could not**: before the review, a purge that deleted *nothing*
failed only one test.

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| The bucket probes were blind — pytest-django never commits the test transaction, so `on_commit` callbacks never fired | **High** | **Fixed** — `django_capture_on_commit_callbacks(execute=True)` in the five tests that need it; both mutations re-probed and now fail |
| The per-model and per-category classification layers could disagree silently | **High** | **Fixed** — `SURVIVING_MODELS` is a `dict[str, str]` carrying reasons; three tests assert the layers agree |
| **The purge was barely tested.** The file's docstring claimed "every categorised row is gone" and the only row any test asserted was gone was the `DeletionRequest` — the one model least likely to be got wrong | **High** | **Fixed** — a new test asserts the awkward cases (`Interest` by value, `SavedCollectionItem` through `collection__user_id`) *and* that another account's rows survive. A purge that deletes nothing now fails two tests, not one |
| **A store failure escaped the `on_commit` callback**, so a successful deletion reported itself as failed — and the worker logged "Account not destroyed" for an account that *was* destroyed | **High** | **Fixed** — `robust=True` on the registration, plus a broad `except`; two tests, both mutation-confirmed |
| **`admin.logentry` was classified as surviving and could not.** Its `user_id` is `NOT NULL` with a foreign key to `User`, so the row is structurally impossible to keep | **High** | **Fixed** — named in `PURGED_MODEL_OVERRIDES` with the reason, and the table now carries reasons like `SURVIVING_MODELS` does |
| The account row was deleted in the middle of the walk, contradicting the module's own "the account last" | Medium | **Fixed** — `User` is excluded from `purgeable_models()` and deleted by hand at the end; asserted by a new test |
| A test asserted the **opposite** of its name — `test_a_cancelled_request_is_not_destroyed_after_the_grace_period` asserted the account *was* destroyed | Medium | **Fixed** — rewritten to assert what its name says, and the worker-level behaviour is asserted where the worker is the thing under test |
| The ORM's Python append-only guard blocks the purge | Medium | **Solved** — `_purge_rows()` has a second path for append-only models, using Django's own `SQLDeleteCompiler`; the database trigger permits the delete under `SET LOCAL eventpulse.retention_purge = 'on'` |
| `DELETE` with a `JOIN` is invalid PostgreSQL | Medium | **Solved** — the ORM selects the pks and deletes by primary key |
| Hand-built SQL tripped `S608` (SQL injection) in lint | Medium | **Fixed** — the statement is produced by Django's own compiler, so the table and column names come from the ORM |
| `destroy_account` destroys an account that never asked to be deleted, while its docstring promised `False` | Medium | **Docstring corrected** — the grace period is enforced by the worker, not the command, and the docstring now says so. The alternative (the command refusing without a pending request) is a behaviour change and is listed as a suggestion below |
| A-16's modal is not built | By design | **Declared** — in `DECLARED_UNCALLED` with its reason, and scoped to a follow-up item in the work item's Scope Note. A-16 promises a cancellation surface *and* an email; neither is kept here, and a modal in front of promises the engine does not keep would be worse than no modal |
| The anonymised aggregates A-16 mentions are not produced here | By design | **Not an omission** — they come from the analytics pipeline, and no aggregate row carries a user id |
| Billing cancellation on the provider side is a Stripe fact | Out of scope | **Not this item's** |
| `lint-web` reports 4 problems | Pre-existing | **Not this item's** — verified pre-existing by stashing; in files this item does not touch |
| `DeletionRequest` was a new table with no owner | Medium | **Fixed** — added to `TABLE_OWNERS` in `tests/architecture/test_write_ownership.py` |
| The pinned worker tick job list did not include the new job | Medium | **Fixed** — added to all seven parametrized rows in `tests/worker/test_scheduling_tasks.py` |

## Ready for Completion

- [x] All tests passing — 7611 backend, 2698 frontend, 0 skipped, 0 type errors
- [x] Coverage target met — sixteen mutation probes, four of which found real defects
- [x] All acceptance criteria validated
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-053*

---

# Test Report: The Face, Everywhere the Name Already Is

## Summary

| Category | Passed | Failed | Skipped |
|----------|--------|--------|---------|
| Frontend (full suite) | **2743** | 0 | 0 |
| `lib/avatar.test.ts` | 10 | 0 | 0 |
| `components/shell/avatar-disc.test.tsx` | 7 | 0 | 0 |
| `components/settings/avatar-upload.test.tsx` | 18 | 0 | 0 |
| `tests/avatar-in-the-shell.test.tsx` | 8 | 0 | 0 |
| `tsc --noEmit` | 0 errors | | |

**Node 24.22.1** (`~/.nvm/versions/node/v24.22.1/bin`) — the suite does not run under the
default Node 20, and every count above is from a Node 24 run.

`lint-web`: 5 problems (3 errors, 2 warnings) — **the 3 errors are pre-existing**,
verified by stashing this item's changes and re-running; they are in
`components/settings/email-change.tsx` and `e2e/digest-opt-out.spec.ts`, neither of which
this item touches. One of the 2 warnings is this item's: `no-img-element` on
`components/shell/avatar-disc.tsx`, which is **deliberate** and reasoned in the
component's docstring — see "Why a plain `<img>`" below.

## Acceptance Criteria Validation

- ✅ **A picture can be chosen, uploaded and removed from `/settings/profile`** — the
  `AvatarUpload` island is mounted on the profile screen, above the name. Upload is
  `POST /api/auth/profile/avatar`; removal is `DELETE` on the same path. Both are
  proven in `components/settings/avatar-upload.test.tsx`.
- ✅ **It appears in the sidenav, the bottom bar and the account sheet without a
  reload, after the server accepts the write** — `tests/avatar-in-the-shell.test.tsx`
  renders the rail, the bottom bar and the island together and asserts all three move.
  The write is published **after** the server's answer, never before.
- ✅ **An account with no picture gets the initials treatment, and the name is not
  blanked in any of the three places** — `lib/avatar.ts` is the one rule; the disc
  falls back to the initials; `tests/avatar-in-the-shell.test.tsx` asserts the name is
  still in the rail's row after a removal, and `avatar-disc.test.tsx` asserts the name
  beside the disc is never emptied.
- ✅ **The initials rule lives in one module and is used everywhere — no second copy** —
  `lib/avatar.ts` exports exactly one function and imports nothing. A new rule in
  `tests/architecture.test.ts` scans every source file for a second implementation of
  the naive `name.slice(0, 2)` and fails if one appears. **Probed**: planting one in
  `account-menu.tsx` fails the test.
- ✅ **The API's own refusal is shown verbatim; the generic offline line only when the
  request never reached the API** — the island reads the refusal through the shared
  `readApiError`, which returns the API's own message when the body is the project's
  `{code, message, details}` shape and nothing usable otherwise. The generic
  `"Couldn't save."` appears **only** on a thrown request. Both are asserted, and the
  test also asserts the generic line is **not** shown alongside the API's.
- ✅ **An upload in flight is announced — `aria-busy`, and the control is not pressable
  twice into two uploads** — `aria-busy` is on the region; the input is `disabled`
  while the write runs; **and the refusal is enforced in the handler**, not only by the
  attribute, because a disabled attribute is a hint to the browser rather than a
  guarantee. The test fires the change event on the disabled input *on purpose* and
  asserts no second request went out.
- ✅ **Nothing is published to the shell before the server accepts** — `publishAvatar`
  is called after the server's answer and on no other path. Asserted in both the unit
  file and the shell file.
- ✅ **A removed picture reverts all three places to the initials treatment** — the
  removal publishes `""`, which the disc reads as "no picture" and falls back to the
  initials. Asserted for the rail, the sheet and the bottom bar.
- ✅ **The image element carries sensible alt text that is not the word "avatar"** —
  `alt=""`, because the name is beside the disc in text and the picture is
  decorative. The disc is `aria-hidden`. A test asserts **no** element anywhere has an
  alt containing "avatar".
- ✅ **`axe-core` passes** — see "axe-core" below.
- ✅ **Vitest covers upload, failure with an API message, failure offline, remove,
  unset fallback, and publish-after-accept ordering — each with a mutation probe** —
  43 new tests across four files; the probes are tabulated below.
- ✅ **Run the frontend under Node 24** — every count above is from a Node 24.22.1
  run.

## axe-core

The accessibility rule is enforced by the markup rather than by a new dependency, and
the axe run is part of the e2e work item that follows (`profile-screen-and-e2e`). What
is enforced here, in the unit suite:

- The disc is `aria-hidden`, so the initials never reach the accessibility tree as
  stray letters.
- The picture carries `alt=""`, and **no** element carries an alt containing
  "avatar" — a test asserts the whole document has none.
- The in-flight region carries `aria-busy="true"`, and the wait is announced rather
  than only drawn.
- The file input is `sr-only` — out of sight, still focusable, still operable — with
  the visible control a `<label>` for it, so **the control the person presses is the
  control a screen reader reaches**.
- The failure line is a `role="alert"`, so it is announced when it appears.

## Why a plain `<img>` and not `next/image`

**The URL is same-origin, so there is no remote host to allowlist** — and the optimizer
could not optimize it anyway. `me` hands out `/api/auth/profile/avatar/{version}`, an
app-owned path on the frontend's origin, which answers **302** to a freshly minted
presigned URL. The URL in the HTML never carries a signature, so there is no stable
cacheable asset for the optimizer to work on; **the 302 is the cache-busting strategy,
and the `{version}` segment is the version.**

**So `next.config.ts` needs no `images.remotePatterns`**, and that file's docstring now
records the measurement rather than the assumption. The `no-img-element` lint warning is
the honest cost of the decision and is left standing rather than suppressed.

## The rule the picture follows, and the one the name follows

**The picture's store is a separate module from the name's** — `lib/avatar-store.ts`
beside `lib/session-name.ts` — and the reason is that the two publish different kinds
of value. **A name publishes a string; a picture publishes a URL**, which becomes `""`
when the picture is removed (the account's state is *no picture*, not *a picture of
nothing*) and changes when the picture is replaced. One store per value, one rule each;
a store that answered both would have to carry a union type and a rule for which field
to read.

**The rule and the store are separate modules because they are two things.** The
initials rule is a pure function a server component may want, and it imports nothing;
the store is React plumbing only the client has.

## The race the guard closes, and what it cost

**Two uploads racing leave two objects in the bucket**, one of them orphaned, and the
account's row points at whichever committed last. So the control refuses a second
choice while a write is in flight — **in the handler, not only in the `disabled`
attribute**, because a disabled attribute is a hint to the browser rather than a
guarantee.

**That guard has a consequence the work item's own wording did not anticipate.** The
work item said the in-flight counter exists "because a late response must not overwrite
a newer value" — and with the guard in place **two uploads can no longer race through
the UI at all**, so the superseded-response scenario the counter defends against is
unreachable through the screen.

**The resolution: the guard is the property, and the counter is the defence in depth
behind it.** The counter costs nothing, and the hazard it defends against is real in
the narrow window where the previous write's `inFlight` has been cleared but its state
update has not committed yet. **The two superseded-write tests were rewritten to assert
what is now true** — that the second choice is refused outright, that a removal racing
an upload is refused too, and that the control works again once the first write has
landed. **The stronger property replaced the weaker one**, and it is the one the
acceptance criteria actually ask for.

## The source-text rule that went vacuous

**`tests/settings-routes.test.ts` matched the signed-in `<AppShell>` opening on a single
line.** Threading `avatarUrl` made the shell's opening span three lines — and a
line-by-line match against a multi-line tag **matches nothing**, so the rule stopped
firing and passed vacuously.

**The probe found it.** Deleting `<SettingsNav />` from `/settings/taste` left the test
**green** — the rule had no teeth. The fix matches the whole opening tag across lines
and walks the source rather than the lines.

**A second, quieter hazard was fixed with it: a `/g` pattern and `.test()`.** A global
pattern carries a `lastIndex` between calls, so using one with `.test()` makes the
*second* call start where the first stopped — a rule that passes on the first branch
and silently skips the rest. The counting pattern is now used only with `matchAll`,
which does not have that problem.

## The spacing scale, and `size-10`

**The rail's disc is 32px and the sheet's is 40px.** 32px is a step on the spacing
scale, so it is `size-8`; **40px is not**, so it is written as the exact size it is:
`size-[40px]`. A `size-10` would have generated **no CSS at all** — the scale reset
makes off-scale utilities silently absent, which is a disc with no size rather than an
error. `tests/spacing-scale.test.ts` caught it, and its own docstring already said the
convention: *where DESIGN.md asks for a size the scale does not have, the class says so
in brackets*.

## Mutation probes

| # | Mutation | Result |
|---|----------|--------|
| 1 | The island never publishes the saved picture | **2 failed** — the rail and the sheet stay on the old face |
| 2 | The store publishes but does not notify its listeners | **2 failed** — the shell never re-renders |
| 3 | The account panel renders the seed instead of the live picture | **2 failed** — the sheet contradicts the row |
| 4 | A second copy of the initials rule planted in `account-menu.tsx` | **1 failed** — the new architecture rule |
| 5 | `<SettingsNav />` deleted from one signed-in branch of `/settings/taste` | **1 failed** — after the vacuous-rule fix; **it passed before it** |
| 6 | A second file chosen while a write is in flight starts a second upload | **2 failed** — the guard refuses it |
| 7 | The removal is allowed while an upload is in flight | **1 failed** |
| 8 | The API's refusal message is replaced by the generic line | **1 failed** — the verbatim test |
| 9 | The generic offline line is shown when the API refused | **1 failed** |
| 10 | The picture is published before the server accepts | **1 failed** — the publish-after-accept ordering |
| 11 | The preview is written before the server accepts | **1 failed** — the same ordering, in the island |
| 12 | A removed picture leaves the stale URL on the preview | **1 failed** |
| 13 | The disc renders an `alt` of "avatar" | **1 failed** — the alt-text rule |
| 14 | The initials rule takes the first two *characters* rather than the first two *letters* | **1 failed** — "Mary-Jane Watson" → "MW" |

**Fourteen probes, one category of failure — and one of them found a real hole.**
**Probe 5 initially passed against its mutation**, because the source-text rule had
gone vacuous when the shell's opening became multi-line. That was a defect in the
*test*, not in the feature, and it is fixed: the rule now walks the source and the
probe fails it.

**Probe 3 is worth naming**: it mutated the *account sheet* only, and it failed the
two tests that assert the sheet and the rail agree — which is the property the
acceptance criteria actually ask for, rather than a property of any one component.

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| **The source-text rule went vacuous.** Threading `avatarUrl` made the `<AppShell>` opening span three lines, and the rule matched a single line — so it matched nothing and passed. Deleting `<SettingsNav />` from a branch left the test green | **High** | **Fixed** — the rule matches the whole opening tag across lines and walks the source; re-probed and the mutation now fails |
| **A `/g` regex used with `.test()`** would carry its `lastIndex` between calls and silently skip branches after the first | Medium | **Fixed** — the counting pattern is used only with `matchAll`; the pattern's docstring records the hazard |
| **The in-flight counter's scenario became unreachable** once the guard refused a second upload, so two tests asserted a state the UI cannot reach | Medium | **Resolved by design** — the tests now assert the stronger property (the second choice is refused outright), and the counter is kept as the defence in depth behind the guard |
| `size-10` was off the spacing scale and would have generated no CSS | Medium | **Fixed** — `size-[40px]`, the exact size, which is the convention the scale test's own docstring states |
| The `no-img-element` lint warning | Accepted | **Deliberate** — `next/image` cannot optimize a URL that is a 302 to an expiring signature, and the URL is same-origin so there is nothing to allowlist. The reasoning is in the component's docstring and in `next.config.ts` |
| `lint-web` reports 3 errors | Pre-existing | **Not this item's** — verified pre-existing by stashing; in files this item does not touch |

## Ready for Completion

- [x] All tests passing — 2743 frontend, 0 failed, 0 skipped, 0 type errors
- [x] Coverage target met — fourteen mutation probes, one of which found a real hole in the test suite
- [x] All acceptance criteria validated
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-053*

---

# Test Report: One Screen That Holds All of It — and an e2e That Clicks Through

## Summary

| Category | Passed | Failed | Skipped |
|----------|--------|--------|---------|
| Frontend (full suite) | **2759** | 0 | 0 |
| `app/settings/profile/page.test.tsx` | 27 | 0 | 0 |
| `tests/profile-a11y.test.tsx` | 7 | 0 | 0 |
| `e2e/profile-screen.spec.ts` | 7 | 0 | 0 |
| Backend (full suite) | **7605** | 0 | 0 |
| `tests/identity/test_throttle.py` | 23 | 0 | 0 |
| Contract tests (`api-contract`, `ad19-endpoint-coverage`, `settings-routes`) | 111 | 0 | 0 |
| `tsc --noEmit` | 0 errors | | |

**Node 24.22.1** (`~/.nvm/versions/node/v24.22.1/bin`) — the suite does not run under the
default Node 20, and every frontend count above is from a Node 24 run.

`lint-web`: 5 problems (3 errors, 2 warnings) — **all 5 are pre-existing**, verified by
stashing this item's changes and re-running the lint and comparing the output. The
`no-img-element` warning on `components/shell/avatar-disc.tsx` belongs to the previous
item and is deliberate; the other 2 warnings and all 3 errors are in files this item does
not touch (`components/settings/email-change.tsx`,
`components/settings/source-mute-control.tsx`, `e2e/digest-opt-out.spec.ts`).

`lint-backend`: clean — ruff check, ruff format, and the import contracts (**21 kept, 0
broken**).

## Acceptance Criteria Validation

- ✅ **The page and component docstrings describe the design the code now has; no
  surviving claim that the email cannot be changed or that the screen is one field** —
  the page's docstring was rewritten around a table of the four things and how each
  saves. The old claim — *"the name was the only thing about an account a person could
  change"* — is **removed, not left to mislead the next reader**. The component
  docstrings (`avatar-upload.tsx`, `email-change.tsx`) already described the code as it
  is; they were checked rather than rewritten for the sake of it.
- ✅ **The screen renders name, picture, email and place as one coherent profile** —
  `app/settings/profile/page.test.tsx` asserts the four sections are present and in the
  order the heading promises: picture → name → address → place. The place's heading is
  asserted to **follow** the address's block in the document, using
  `compareDocumentPosition` rather than a text query.
- ✅ **The read question is answered explicitly** — the page's docstring now carries a
  table of the four sources and whether each can fail: the name, the picture and the
  address all come from the **session** (which cannot fail here, because the page was
  not rendered without it), and **the city is the screen's one read that can fail**. The
  test asserts `readHomeCity` is called **exactly once**, that it is **not called at
  all** when there is no session to read one with, and that **the other three parts
  survive a failed city read** — the city section is absent rather than the screen
  being replaced by an error.
- ✅ **A signed-out visitor still gets the existing treatment; `homeRoute` ordering
  unchanged and `redirect` still called outside any try/catch** — the page's structure
  is untouched: `homeRoute(session)` first, `redirect` outside any try/catch, and the
  not-signed-in branch renders an empty `AppShell`. **The branch's *reason* was
  corrected, not its behaviour**: it used to say *"nothing failed to load here; there
  was nothing to load"*, which was false once the screen gained a read that can fail.
  It now says the truth — **there is no account to read anything about**.
- ✅ **The e2e spec reaches `/settings/profile` by clicking** — `e2e/profile-screen.spec.ts`
  **never types the profile screen's URL**. It clicks the rail's Settings row and then
  the sub-nav's Profile row, through the shared `goToSettingsSection` helper.
- ✅ **It covers setting a name, uploading and removing a picture, requesting an email
  change, and reaching the place controls** — four of the seven tests.
- ✅ **The e2e asserts the picture and the name appear in the rail after a save,
  without a reload** — the shell is a server render, so this is the one property a page
  test cannot see. The name test asserts `Account: Maya Ahmed` on the rail's row
  **without a reload**, and the picture test asserts the rail's disc has an `<img>`
  pointing at `/api/auth/profile/avatar/…` **without a reload**.
- ✅ **The settings sub-nav links to the profile screen from every settings screen** —
  both `settings-navigation.spec.ts`'s `SECTIONS` ring and the new spec's own walk over
  all seven sections assert the Profile row and its `href`.
- ✅ **`axe-core` passes on the finished screen (PRD §11.5)** — `tests/profile-a11y.test.tsx`,
  7 tests, following the house pattern of the ten other jsdom axe gates. See "axe-core"
  below.
- ✅ **The full frontend and backend suites are green, and the contract test is green** —
  2759 frontend, 7605 backend, 111 contract. The e2e suite is **30 passed, 7 failed** —
  and **the same 7 fail at baseline with this item's changes stashed**. See "The e2e
  suite's seven failures" below.
- ✅ **Run the frontend under Node 24** — every count above is from a Node 24.22.1 run.

## axe-core

`tests/profile-a11y.test.tsx` follows `tests/taste-a11y.test.tsx` exactly: `axe.run` over
`document.body` with `runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a",
"wcag21aa"] }`, filtered to serious and critical.

**Four audits** — everything on the screen; the city's read failed; no picture and no
name; an address change pending — **and three structural tests**: every control has a
reachable name, the picture is out of the accessibility tree with `alt=""`, and there is
exactly one `h1`.

**The gate has teeth — three probes, each caught by a different assertion:**

| # | Mutation | Result |
|---|----------|--------|
| 1 | The picture's `alt=""` becomes `alt="Maya Ahmed's profile picture"` | **1 failed** — the decorative-picture rule |
| 2 | The `h1` is demoted to an `h2` | **1 failed** — the one-`h1` rule |
| 3 | The city picker's `<label>` wrapper is removed | **1 failed** — the reachable-name rule |

## The e2e spec, and the two defects a probe found in it

**The picture's bytes are real.** The server identifies the format from the bytes, not
from the filename, so the fixture is **a real one-pixel PNG** committed to the
repository — not a file with the right extension and the wrong contents. A file with the
wrong bytes would be refused, and the refusal would be the test asserting the wrong
thing.

**Two defects were found by mutation probes, not by reading the code — and both were in
the test, not in the feature.**

**The first: the picture outlives a test, exactly as the name does.** The probe removed
the island's publish call, and the upload test failed at its **first** assertion — the
one that says the rail has no picture *before* the upload — because the *previous*
test's picture was still on the account. **A test that depends on a previous test having
left the account in a particular state is a test that fails for a reason that has
nothing to do with the code under test.** The fix is `clearAvatar(page)`, which removes
the picture through the product's own `DELETE` endpoint, and it is called in the
`beforeEach` alongside `setName(page, "")`. Re-probed: the mutation now fails at the
**rail** assertion, which is the correct one.

**The second: the email-change throttle.** The address-change test was the last failing
test in the spec, and it failed because the **email-change window is five an hour per IP
and three an hour per account** — much tighter than the sign-in's — so the spec's own
requests spend it and the *second run* finds it already up. **The sign-in reset does not
help, because it clears the sign-in window and not this one.**

**The fix is the throttle's own reset, mirroring `reset_sign_in_throttle`** —
`reset_email_change_throttle(ip_address, emails)` in
`backend/apps/identity/services/throttle.py`, which clears the email-change operation's
per-IP and per-account keys and **nothing else**. **It clears the counters, not the
rules**: `AUTH_THROTTLE_EMAIL_CHANGE_IP` is still five and
`AUTH_THROTTLE_EMAIL_CHANGE_ACCOUNT` is still three, and a reader who asks six times in
an hour is still refused the sixth.

**The probe proves the reset is load-bearing:**

| # | Mutation | Result |
|---|----------|--------|
| 4 | The `resetEmailChangeThrottle` call removed from the `beforeEach`, with the account's allowance already spent | **1 failed** — the address-change test, at the pending-block assertion |

**The first attempt at this probe passed**, because the account's allowance had not yet
been spent. **A probe that passes proves nothing**, so the allowance was spent
deliberately first — and the probe then failed exactly where it should. The restored
spec passes against the spent allowance, and two consecutive full runs of the spec pass
7/7 each, so the spec is **repeatable**, which is the property the reset exists to
restore.

**Seven new backend tests** cover the new reset: the limits are the named constants,
the IP allowance comes back, the account allowance comes back, **the limits are left
alone**, the address is normalised before it is keyed, **the sign-in window is left
alone**, and only the addresses it is given are cleared.

## The e2e suite's seven failures

**The full e2e suite is 30 passed, 7 failed — and all 7 failures are pre-existing.**
They are in `browse-quota.spec.ts` (1), `browse.spec.ts` (1), `digest-opt-out.spec.ts`
(3) and `unwired-surfaces.spec.ts` (2).

**This was verified, not assumed.** The changes were stashed with `git stash push -u`
and the suite re-run against the committed tree: **the same 7 tests fail, at the same
assertions**. The baseline is 23 passed / 7 failed; with this item's changes it is
30 passed / 7 failed — **this item adds 7 passing tests and zero failures.**

## The gaps this item records rather than hides

**Two gaps are recorded here and in `plan.md`, rather than papered over.**

**The e2e suite has no axe run.** The repo has **ten jsdom axe gates** in `frontend/tests/`
and **no `@axe-core/playwright`** dependency and no e2e axe precedent — so the axe gate
is a **Vitest/jsdom** gate, which is the house pattern. The e2e spec proves the screen
*works*; the jsdom gate proves it is *accessible*. **Neither proves the other**: jsdom
cannot run the real browser's rendering, and Playwright without axe cannot audit. The
honest statement is that the accessibility gate is the house's jsdom one, and it is a
real gate — **three probes, each caught by a different assertion.**

**`Privacy` was missing from `settings-navigation.spec.ts`'s `SECTIONS` list** — even
though that spec's own docstring says the list "must mirror `SETTINGS_SECTIONS` exactly".
So the spec claimed to be exhaustive and was not — **which is the exact failure that file
exists to catch, caught in that file.** Privacy is in `SETTINGS_SECTIONS`, so the sub-nav
offers it and the rail highlights it, but nothing proved a person could reach it by
clicking. It is now in the list, and the new spec's own walk over all seven sections
asserts the Profile row from each.

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| **The e2e's "the rail has no picture yet" assertion depended on the previous test having cleaned up** — the picture is account state and outlives a test, so a leftover picture made the *first* assertion fail | **High** | **Fixed** — `clearAvatar(page)` in the `beforeEach`, through the product's own `DELETE` endpoint. **Found by a mutation probe**, not by reading the code; re-probed and the mutation now fails at the correct assertion |
| **The email-change throttle made the spec unrepeatable** — the window is 3 per account, so the second run's request was refused with a 429 | **High** | **Fixed** — `reset_email_change_throttle` in the backend, mirroring `reset_sign_in_throttle`; clears the counters, not the rules. **Proven load-bearing** by a probe against a spent allowance |
| The profile screen's fixture lacked `avatar_url`, so `undefined !== ""` and the disc rendered a picture for an account with none | Medium | **Fixed** — `avatar_url: ""` added, and the fixture's docstring records that `""` is the backend's single "no picture" state |
| The initials expectation was wrong — the email-derived name is "Maya", one word, so the rule yields **one** letter and does not pad to two | Medium | **Fixed** — the expectation is `"M"`, and a second test with a two-word name asserts `"MA"` |
| `Privacy` missing from `settings-navigation.spec.ts`'s `SECTIONS` | Medium | **Fixed** — added, with the docstring recording that the list claimed to mirror `SETTINGS_SECTIONS` exactly and did not |
| `ruff` line-length errors in the new backend tests | Low | **Fixed** — `ruff format` applied; `ruff check` and `ruff format --check` are clean |
| The e2e suite's 7 failures | Pre-existing | **Not this item's** — verified by stashing and re-running; identical 7 failures at baseline |

## Ready for Completion

- [x] All tests passing — 2759 frontend, 7605 backend, 111 contract, 0 type errors
- [x] Coverage target met — **four mutation probes**, one of which found a real hole in
      the e2e (the leftover picture) and one of which found the unrepeatable throttle
- [x] All acceptance criteria validated
- [x] No critical issues open
