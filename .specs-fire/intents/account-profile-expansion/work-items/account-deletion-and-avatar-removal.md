---
id: account-deletion-and-avatar-removal
title: Deleting an Account — and the Picture That Must Not Outlive It
intent: account-profile-expansion
complexity: high
mode: validate
status: completed
depends_on:
  - avatar-model-and-command
created: 2026-11-19
run_id: run-eventpulse24-053
completed_at: 2026-11-20T04:56:48.491Z
---

# Work Item: Deleting an Account — and the Picture That Must Not Outlive It

## Description

**Split out of `avatar-model-and-command` on 2026-11-19, at its Checkpoint 1.**

That item carried the acceptance criterion *"Account deletion removes the stored
object"*, and its description made the stakes plain:

> A picture that survives account deletion is the single worst outcome available here.

It is right, and it could not be met — **because nothing deletes an account.** `grep`
over `apps/identity/services/` finds no `delete_account` and no deletion command of any
name; no endpoint exposes one; `frontend/components/settings/` has no delete or
danger-zone component. Amendment **A-16** designed the confirmation modal — 480px,
three paragraphs on what is deleted, what survives as anonymised aggregates, the 30-day
grace period, and a type-to-confirm input gating the primary — and it was never built.

**The criterion was split rather than dropped**, because a checkbox that passes silently
because the feature it guards does not exist is worse than an honest gap. It is now this
item's reason to exist.

**This is not only about the picture.** Deletion touches every model carrying a
`retention_category`, the billing records that must survive for their own legal window,
the audit log that AD-13 keeps PII out of precisely so it *can* survive, and the
anonymised aggregates A-16 promises the user are kept. The avatar is one object among
those, and the easiest to forget, because it is the only one that does not live in
Postgres.

## Acceptance Criteria

- [x] A named command in `apps/identity/services/` deletes an account (AD-5) — never a write in the API layer
- [x] **The stored avatar object is removed**, and a probe asserts the key is gone from the bucket, not merely blanked on the row
- [x] An account with **no** avatar deletes cleanly — the removal is not conditional on a key being present in a way that breaks on `""`
- [x] The 30-day grace period A-16 specifies is honoured, and the picture's removal happens at the point the account is actually destroyed rather than when deletion is requested — **a user who cancels within the grace period gets their picture back**
- [x] Billing records survive per their own retention category (AD-15); the audit log survives
- [x] Every model carrying a `retention_category` is accounted for — enumerated and asserted, so a model added later cannot be silently missed
- [x] The deletion is driven from a surface the user can reach (A-16's modal), or that surface is explicitly scoped to a follow-up item
- [x] Every test can fail — verified by a mutation probe per test

## Scope Note: A-16's Modal Is Not Built Here

**The AC above is satisfied by the second half of it: the surface is explicitly scoped to
a follow-up item.** This is recorded rather than hidden.

**A-16's third paragraph promises two things this item does not keep:** that the user can
cancel "from a page", and that they are **sent an email** when their account is deleted.
Neither is in this item — there is no mail here, and there is no page.

**Why the modal is not built anyway.** A type-to-confirm modal is a promise made in the
product's voice, in three paragraphs, describing what the user is agreeing to. Two of
those paragraphs would be describing behaviour that does not exist. **Building it would
be worse than not building it** — a modal that says "you will be emailed when this
completes" when no email is sent is a lie told at the exact moment the user is deciding
whether to trust the product with their account.

**What this item does instead.** It ships the engine the modal will sit on: the three
commands, the two endpoints (`POST` and `DELETE /api/auth/profile/deletion`), the
thirty-day grace period, and the worker that destroys an account when the grace expires.
**The API the modal needs exists in this pass** — a modal can be built against it
without touching the engine.

**The follow-up item's job**, when it is written:

1. The modal itself — 480px, three paragraphs, a type-to-confirm input gating the
   primary action.
2. The **email** A-16 promises, sent when the account is destroyed.
3. A place to cancel — A-16's "from a page".

**The anonymised aggregates A-16 mentions** are produced by the analytics pipeline, not
by this command, and no aggregate row carries a user id to begin with — so they survive
by having nothing to link them to. That is a fact about the pipeline, not an omission
here.

## What the code review found

**Four defects, all confirmed against the live database and all fixed.** They are
recorded here rather than in the run's `review-report.md` alone, because two of them
changed what this item *claims*.

**1. `admin.logentry` cannot survive the account, so it is purged by name.** Its
category is `AUDIT_LOG` — which survives — but its `user_id` is `NOT NULL` with a
foreign key to `User`, so the row is structurally impossible to keep. The classification
is now honest: the model is named in `PURGED_MODEL_OVERRIDES` **with its reason**, and
the override table carries reasons the way `SURVIVING_MODELS` does. **The audit log
that matters is untouched** — `identity.identityauditentry` is append-only, carries no
PII, and survives by name.

**2. The account row is deleted last, by hand.** The walk sorts by label, and
`identity.user` sorts into the middle — before the audit row for the deletion was even
written. The module's docstring promised "the account last"; the code did the opposite.
`User` is now excluded from the walk and deleted at the end.

**3. The purge is now actually tested.** The test file's docstring claimed "every
categorised row is gone" and the only row any test asserted was gone was the
`DeletionRequest`. A purge that deleted *nothing* failed one test. There is now a test
for the awkward cases — a model reached by a join, and a model reached by value — and it
asserts the other side too: another account's rows survive.

**4. A store failure no longer reports a successful deletion as failed.** The object's
removal runs after the commit, so a failure there is a leak and not an error — but the
exception escaped, and the worker logged "Account not destroyed" for an account that
*was* destroyed. The callback is now registered with `robust=True`, and the cleanup
catches broadly.

## Technical Notes

**Read `avatar-model-and-command-design.md` first.** It records why the avatar's key is
opaque, why the object is deleted in `transaction.on_commit` rather than inside the
transaction, and that the key's lifetime is bounded by *this* item.

**The grace period and the object are in tension, and the AC above resolves it
deliberately.** Deleting the object when deletion is *requested* makes the grace period a
lie — the user cancels and their picture is gone. Deleting it when the account is
*destroyed* means the bucket holds a picture for thirty days after the person asked the
product to stop holding it. The second is chosen because the grace period is a promise
the product made, and a cancelled deletion must restore the account whole.

**The audit row for deletion must carry no PII** (AD-13), which is the same rule that
makes the audit log safe to keep after the account is gone.

**`tests/architecture/test_no_direct_writes.py` must stay green** — deletion is a write,
and the API layer does not write.

## Dependencies

- `avatar-model-and-command` — there is no `avatar_key` to clear until it lands
