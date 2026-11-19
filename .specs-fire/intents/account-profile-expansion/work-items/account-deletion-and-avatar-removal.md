---
id: account-deletion-and-avatar-removal
title: Deleting an Account — and the Picture That Must Not Outlive It
intent: account-profile-expansion
complexity: high
mode: validate
status: pending
depends_on:
  - avatar-model-and-command
created: 2026-11-19
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

- [ ] A named command in `apps/identity/services/` deletes an account (AD-5) — never a write in the API layer
- [ ] **The stored avatar object is removed**, and a probe asserts the key is gone from the bucket, not merely blanked on the row
- [ ] An account with **no** avatar deletes cleanly — the removal is not conditional on a key being present in a way that breaks on `""`
- [ ] The 30-day grace period A-16 specifies is honoured, and the picture's removal happens at the point the account is actually destroyed rather than when deletion is requested — **a user who cancels within the grace period gets their picture back**
- [ ] Billing records survive per their own retention category (AD-15); the audit log survives
- [ ] Every model carrying a `retention_category` is accounted for — enumerated and asserted, so a model added later cannot be silently missed
- [ ] The deletion is driven from a surface the user can reach (A-16's modal), or that surface is explicitly scoped to a follow-up item
- [ ] Every test can fail — verified by a mutation probe per test

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
