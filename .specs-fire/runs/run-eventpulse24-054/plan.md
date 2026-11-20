---
run: run-eventpulse24-054
work_item: account-deletion-confirmation-email
intent: account-profile-expansion
mode: confirm
checkpoint: plan
approved_at: 
---

# Implementation Plan: The Mail That Says Your Account Is Going Away — and How to Stop It

## The Design Decision This Checkpoint Exists to Settle

The work item asks the checkpoint to settle **the cancel-link mechanism**, and says *"the
answer decides whether it needs a model and a migration or not."* Here is the decision.

**Chosen: option 1 — a single-use token that lives for the whole grace period, held on the
`DeletionRequest` row itself.**

The three options the work item lays out, and what each costs:

| Option | Needs | Cost |
|---|---|---|
| **1. Token valid for the whole grace period** | two columns on `DeletionRequest` | a 30-day bearer window on a *cancel* |
| **2. Short-lived token that mints a fresh one** | a new model, a mint endpoint, a page | more machinery than the promise needs |
| **3. No token — the mail sends the user to a signed-in page** | nothing | changes A-16's wording; the mail is a redirect, not a mechanism |

**Why 1 and not 3.** The work item's own framing of the mail's purpose is decisive: it is
*"there for a user who asked to leave and then got cold feet"* — a user who **closed the
tab**. Under option 3 that user has to sign in again from the mail, and the mail's link
is a redirect to a page whose action the page itself already offers. The mail would then
carry no capability of its own, and the sentence A-16 promises — *"you can cancel anytime
during the 30-day grace ... from the email we send"* — would be true only in the weaker
sense "by going somewhere else and doing the thing yourself". **The grace period's whole
purpose is to let a cold-feet user come back; option 3 requires them to already be able
to come back.** That is the promise hollowed out, which is the exact failure this intent
was reopened for.

**Why 1 and not 2.** Option 2's "short-lived token mints a fresh one" is the strongest
cryptography, and it is *overbuilt for this threat*. Its threat model is a leaked mailbox
link being used by a stranger. But note what cancelling actually does: `cancel_account_deletion`
**deletes the `DeletionRequest` row** — it destroys the pending destruction. It grants no
access to the account, exposes no data, reads nothing, and leaves the account exactly as
it was. The worst outcome of a leaked cancel link is that **the account survives** — which
is the safe direction. The 30-day bearer window is not 30 days of account access; it is 30
days during which a stranger can *undo* a deletion. The upside of the cancellation is
bounded by "the account was going to be destroyed", and the downside is "the account was
not destroyed". **A token that can only prevent destruction is a much weaker bearer than
a token that can grant access**, so the long lifetime is defensible here in a way it would
not be for a password reset — where the same window grants full account access.

**And option 1 needs no new model and no migration.** The token goes on `DeletionRequest`,
which already exists for exactly the grace window, and `cancel_account_deletion` already
deletes that row as the whole of a cancellation. **The token's lifetime is the row's
lifetime by construction** — there is no second expiry field that could disagree with
`scheduled_for`, and no window in which the row exists but the token has expired (or the
reverse). Option 2's extra model would have introduced exactly that second source of
truth, which is the class of bug this project keeps writing docstrings about.

**What this costs, stated honestly:** the token is a bearer credential for the grace
window, and it is single-use — the moment it is used the row is gone, so the token
cannot be replayed. It is revocable — a new deletion request revokes any outstanding
token, and `cancel_account_deletion` removes it. It is stored as a salted digest with a
per-row salt, so a database dump yields no usable link. And it holds the user **by
value** (OQ-8), like every other table that reaches an account.

**The A-16 wording question.** Option 1 keeps A-16's sentence exactly as written —
*"cancel anytime during the 30-day grace from this page or from the email we send"* —
because the mail's link really does cancel the deletion, by itself, with no sign-in. **No
copy change is needed, and the modal's third paragraph stays true.**

### How the token is carried

The mail's link points at the **frontend route**, not at the API, and carries the raw
token as a query parameter — the same shape as `reset_password_link` and
`confirm_email_change_link` already use. The frontend route is rendered by
`account-delete-confirmation-surface`'s sibling work; **this item ships the mail and the
token, and the page that consumes the token is a separate item's work.** The link must
therefore point at a route that this item does not build, and **the plan records that
route as `/cancel-account-deletion?token=…`** so the consumer item can be written
against it.

**Consuming the token is out of this item's scope.** The token is minted, stored,
emailed, and revoked — and the command that *spends* it belongs to the cancel-surface
item, which owns the read and the action. What this item guarantees is that the token
**works**: it is minted, it is linked, it survives until used, and using it deletes the
row. So the plan adds the **spend** to the existing `cancel_account_deletion` command
(so that the "cancels it" claim is *tested*, not asserted) while the HTTP surface that
accepts the token stays with the cancel-surface item.

### The one thing this item deliberately does not build

**Message B — "your account has been gone"** — is still not built, and this item does not
build it. The work item's scope note records why it is technically impossible *now*: when
`destroy_account` runs, the account row is gone, so there is no address to send to. If B
is ever to exist, the address must be captured onto `DeletionRequest` at request time and
survive the account's death — a PII consideration (AD-13) and an AD-15 retention
question. **This item therefore does not capture the address onto the row**, and it says
so in the code, so a later reader does not mistake the absence for an oversight.

## Approach

1. **Settle and record the design decision** in a design doc at
   `.specs-fire/runs/run-eventpulse24-054/design-deletion-cancel-token.md`, carrying the
   reasoning above, the options weighed, and the consequences — before any code is
   written (the work item's first acceptance criterion demands the decision be *recorded*).
2. **Add the token to `DeletionRequest`** — two columns (`token_hash`, `token_salt`),
   nullable so the migration is forward-only and existing rows stay valid. The token is
   minted at request time, hashed with a per-row salt via the existing
   `services/tokens.py` helpers, and **never stored in the clear**.
3. **Add the renderer and the stream** to `backend/apps/identity/services/emails.py` —
   `render_account_deletion_email` and `account_deletion_stream`, following the
   existing renderer-and-stream pattern exactly. The stream is `Stream.TRANSACTIONAL`.
4. **Add the template** `backend/apps/identity/templates/identity/account_deletion.txt`,
   beside the four that are already there.
5. **Wire the send into `request_account_deletion`** — **after** the transaction commits,
   so a rolled-back request sends no mail, and the ordering the avatar's bucket removal
   already uses (both are outside the transaction, both happen after it). The send
   failure is **logged, not raised**: the endpoint's contract says the request "cannot
   fail on its merits", so a mail transport failure must not fail the request.
6. **Make the send idempotent** — the mail is sent **once**, not on every request. The
   idempotency key is derived from the request row's id (AD-7), so a second request sends
   nothing. This falls out of the command already returning the existing row on a second
   call: the second call returns the existing row, and the send is keyed to whether
   *this* call created the row.
7. **Add the spend path** — `cancel_account_deletion` gains a token-consuming sibling
   (or an optional-token variant) so that "the link cancels the deletion" is a tested
   fact rather than a claim in a docstring. The token is matched via the existing
   `token_service.find_outstanding` scan, which already locks, tolerates salt
   collisions, and refuses to let an expired row shadow a valid one.

## Files to Create

| File | Purpose |
|------|---------|
| `.specs-fire/runs/run-eventpulse24-054/design-deletion-cancel-token.md` | The design decision, its rationale, and its consequences — recorded before code (AC-1) |
| `backend/apps/identity/templates/identity/account_deletion.txt` | The notice mail's body (AC-8) |
| `backend/apps/identity/migrations/00XX_accountdeletionrequest_token.py` | The two nullable token columns on `DeletionRequest` |
| `backend/tests/identity/test_account_deletion_mails.py` | The renderer, the stream, the copy, and the expiry-from-constant assertions (AC-2, AC-3, AC-9, AC-10, AC-13) |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/apps/identity/models.py` | Two nullable columns on `DeletionRequest` (`token_hash`, `token_salt`), plus the docstring recording *why* the token's lifetime is the row's lifetime and why no address is captured (AD-15 retention category already declared) |
| `backend/apps/identity/services/emails.py` | `render_account_deletion_email` + `account_deletion_stream`, and the link helper — every expiry rendered from `DELETION_GRACE_PERIOD` |
| `backend/apps/identity/services/deletion.py` | Mint the token in `request_account_deletion`; send the mail after commit; add the token-consuming path to `cancel_account_deletion` |
| `backend/shared/constants.py` | No new lifetime constant — **the token's lifetime is the row's**, which is the point of the decision. (Recorded here as an explicit "no change" so its absence is not read as an oversight.) |

## Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/identity/test_account_deletion_mails.py` | The renderer: recipient is the account's own address; the body carries the date rendered from `scheduled_for`; the body carries a cancel link; the body says what is deleted / what survives / that the account keeps working; the body does **not** promise a follow-up mail; the grace period is rendered from `DELETION_GRACE_PERIOD` and changes when the constant changes; the stream is `Stream.TRANSACTIONAL` |
| `backend/tests/identity/test_account_deletion.py` (extend) | The token is minted on request and stored as a digest (the raw token is not in the DB); a second request sends **no** second mail; a send failure does **not** fail the request and is logged without the address; the token cancels the deletion when spent; a spent token is refused; a revoked token is refused; the address is never in the audit details or a log line |
| `backend/tests/architecture/test_no_direct_writes.py` (unchanged, must stay green) | The API layer writes nothing — the mail is sent from the command (AD-5) |

**Mutation probe (AC-13).** The tests must be shown to fail when the implementation is
wrong — specifically: change the template to say "30 days" as literal text and confirm the
constant-derived assertion fails; remove the `transaction.on_commit` and confirm the
"rolled-back request sends no mail" assertion fails; make the send unconditional and
confirm the "sent once" assertion fails.

## Technical Details

### The token's columns, and why they are nullable

`token_hash` (64 chars, hex) and `token_salt` (32 chars, hex) — **the same shape as
`PasswordResetToken`**, which stores `sha256(salt + token)`. Nullable, because:
- the migration is forward-only and existing rows have no token;
- a row can exist with no token in the window between creation and minting if the two
  ever need to be separated.

**`find_outstanding` cannot be reused as-is.** It scans `model.objects.filter(...)` with
no `user_id` narrowing and expects the model to carry `used_at` / `revoked_at`. The
deletion token is different: **the row it lives on is deleted when the token is spent**,
so there is no `used_at` to set — the deletion of the row *is* the consumption. And the
token is looked up by digest against a *single* known row (the `DeletionRequest` for the
account the caller claims), not by a blind scan.

So the spend path computes the digest against the candidate row's own salt and compares
in constant time — the same primitive `find_outstanding` uses, written once **here** for
this shape, and commented as to why it is not the shared scan.

### The idempotency key and "sent once"

The key is derived from the request row: `f"account_deletion{SEND_KEY_SEPARATOR}{row.pk}"`
— matching `password_reset.py`'s `f"auth_reset{SEND_KEY_SEPARATOR}{row.pk}"`. The row's
id is stable across a second request, so even if the second request *did* reach the
send, the port's idempotency would collapse it. **The command also does not reach the
send** on a second call — it returns the existing row — so the guarantee holds at two
independent layers.

### Where the send happens, and why it is not inside the transaction

**After the commit.** The mail is outside the transaction exactly as the bucket removal
is: `transaction.on_commit(lambda: _send(...), using=PERSONAL, robust=True)`. A rolled-back
request sends no mail, and a mail-transport failure cannot roll back a recorded
deletion request. The `robust=True` is what makes the failure **logged rather than
raised**, so the exception does not propagate out of the committed callback into the
caller. The endpoint's contract says the request "cannot fail on its merits" — a mail
transport is not a merit.

### AD-13 — the address never appears anywhere but the recipient field

The recipient is `user.email`, read from the row inside the command and passed to the
renderer. It appears in:
- the `EmailMessage.to` field (the only place it may appear),
- the `idempotency_key` — **never**: the key is derived from the row id, not the address.

It appears in **no** log line, **no** audit `details`, and **no** exception message. The
send-failure log records the **type** of failure, not the recipient. The logger allowlist
is **not widened**.

### AD-18 / AD-13 — the token is a digest at rest

The raw token exists in exactly two places: the mail body and the link. The row holds
`token_hash` and `token_salt` only. `hash_token(token, salt)` is the existing helper in
`services/tokens.py` and the comparison is `secrets.compare_digest` — the same constant
-time comparison `find_outstanding` uses.

### The copy — what it says, and what it must not say

The mail states the **same four facts** the modal's body states, because the two
surfaces must not drift:
1. the date the account will be destroyed, rendered from `scheduled_for`;
2. how to cancel — the link, and the route it lands on;
3. what is deleted, and what survives as anonymised aggregates;
4. that the account keeps working until then.

**It must not say "we will email you again when it is done."** Message B does not exist,
and promising it would be the same unkept promise the engine item refused to make.

**The date is the server's date.** `scheduled_for` is computed once, at request time, and
a later request returns the same date — so the mail renders the value the row holds,
never a recomputed "30 days from now". The grace period's *length* is rendered from
`DELETION_GRACE_PERIOD`; the *date* is rendered from the row.

**The mockup's false subtitle does not ship.** The A-16 mockup says "Permanent. Cannot
be undone." — which is false of a thirty-day grace period. The mail says the opposite,
and the *modal* (a later item) must too.

### The modal's third paragraph stays true

A-16: *"You can cancel anytime during the 30-day grace from this page or from the email
we send."* Under the chosen option, **both halves are true**: the page (the cancel-surface
item) and the mail's link, each of which cancels on its own. **No copy change is needed**,
and this item's output does not force a change to the modal's text.

## Based on Design Doc

`design-deletion-cancel-token.md` (created by this plan, in this run directory) — the
cancel-link mechanism decision, its rationale, and its consequences.

---
*Plan approved at checkpoint. Execution follows.*
