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
