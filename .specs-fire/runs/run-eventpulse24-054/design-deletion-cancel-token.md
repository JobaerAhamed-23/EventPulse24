---
run: run-eventpulse24-054
work_item: account-deletion-confirmation-email
intent: account-profile-expansion
decision: cancel-token-on-deletion-request
status: settled
decided_at: 2026-11-20
---

# Design: The Cancel Link in the Account-Deletion Notice

## The Decision

**The account-deletion notice carries a single-use token that lives for the whole grace
period, stored as a salted digest on the `DeletionRequest` row itself.**

The link in the mail points at the frontend route `/cancel-account-deletion?token=…`.
Spending the token cancels the pending deletion and nothing else.

## The Three Options, and Why This One

The work item named three mechanisms. All three keep A-16's sentence true; they differ in
what they cost and what they promise.

### Option 1 — a token valid for the whole grace period *(chosen)*

Two columns on `DeletionRequest`: `token_hash` and `token_salt`.

**Why the token's lifetime can be long without being alarming.** Compare what the two
long-lived bearer credentials in this product actually authorise:

- A **password-reset** token lives 30 minutes and, when spent, grants **full account
  access**. Its window is short precisely because the capability is large.
- A **deletion-cancel** token lives 30 days and, when spent, **deletes the pending
  destruction**. It grants no access, reads nothing, exposes no data, and leaves the
  account byte-for-byte as it was.

**A token that can only prevent destruction is a categorically weaker bearer than one
that grants access.** The worst outcome of a leaked cancel link is that the account
*survives* — the safe direction. The upside is bounded by "the account was going to be
destroyed", because that is the only thing that can be prevented. That bounded upside is
what makes a 30-day window defensible here in a way it would not be for a reset token.

**Why `DeletionRequest` and not a new model.** The row already exists for exactly the
grace window, and `cancel_account_deletion` already deletes that row as the entire act of
cancelling. **The token's lifetime is therefore the row's lifetime by construction.**
There is no second expiry field that could disagree with `scheduled_for`, and no window
in which the row exists but the token has expired — or worse, in which the token is
expired but the row is not, which would be a silent failure to honour the promise.

**The properties, and where each comes from.** `PasswordResetToken`'s docstring
(`backend/apps/identity/models.py:118`) records why each property exists; this token
needs the same five, and gets them differently:

| Property | How this token has it |
|---|---|
| No token at rest (AD-18) | `sha256(salt + token)`; the raw token exists only in the mail body and its link |
| Single-use | Spending the token **deletes the row**, so it cannot be replayed — consumption *is* the row's deletion |
| Revocable | A new deletion request replaces the row; `cancel_account_deletion` removes it; `destroy_account` removes it |
| Not expiring early | The row's own lifetime is the token's lifetime; there is no separate expiry |
| User by value (OQ-8) | The token is on the account's own `DeletionRequest` row; there is no relation to `User` |

### Option 2 — a short-lived token that mints a fresh one *(rejected)*

**It is the strongest cryptography and it is overbuilt for this threat.** Its
short-lived-then-minted shape is the right shape for a credential that grants access. A
cancel token grants the *opposite* of access, so the minting machinery is defending
against an attacker whose best outcome is keeping an account alive.

**The real cost is a second source of truth.** Option 2 needs a new model with its own
`expires_at`, its own mint path, and its own consumption path — and a token whose expiry
is 24 hours while the thing it cancels runs for 30 days is a token that can be expired
while the promise it serves is still live. That is the same class of bug this project
keeps writing docstrings about: a number in one place and a different number in another.

### Option 3 — no token; the mail sends the user to a signed-in page *(rejected)*

**It is the safest, and it hollows out the promise.** Under this option the mail's link
is a redirect to a page the user must sign in to. The mail carries no capability of its
own.

**The work item's own framing of the mail's purpose is what decides it.** The mail
exists *"for a user who asked to leave and then got cold feet"* — a user who **closed
the tab**. Under option 3 that user must authenticate again before they can act, which
means the grace period only helps people who could already come back. The grace period's
purpose is to give a cold-feet user a way back **without** requiring them to prove who
they are a second time.

**And it changes A-16's sentence.** *"you can cancel anytime during the 30-day grace from
this page or from the email we send"* would become true only in the weaker sense "by
going somewhere else and doing the thing yourself". This intent was reopened precisely
because a surface promised something the product did not do; a mail that redirects
without acting is the same shape of promise, smaller.

## Consequences

### A-16's wording is unchanged

*"You can cancel anytime during the 30-day grace from this page or from the email we
send"* — **both halves stay true.** The page (the cancel-surface item) and the mail's
link each cancel on their own, without a sign-in. **The modal's third paragraph needs no
change**, and this decision does not force a copy change on any other item.

### The route the link points at

`/cancel-account-deletion?token=…` — the **frontend** route, not the API, matching
`reset_password_link` and `confirm_email_change_link`. The frontend is a different origin
from the API runtime, so the base URL comes from `settings.FRONTEND_BASE_URL`.

**The page that consumes the token is not this item's work.** This item mints, stores,
emails, and makes the token spendable; the HTTP surface that accepts it belongs to
`account-deletion-cancel-surface`, and the UI belongs to
`account-delete-confirmation-surface`. This design records the route so those items can
be written against it.

### The spend path

**Spending the token deletes the pending `DeletionRequest` row** — the same act
`cancel_account_deletion` already performs. The token is matched against the candidate
row's own salt with `secrets.compare_digest`, and the row's deletion is the consumption.

**The shared `token_service.find_outstanding` scan is not reusable here**, and the reason
is worth recording: it narrows by `used_at`/`revoked_at` and scans blindly for a
matching digest, whereas this token's row *is deleted* when spent (so there is no
`used_at` to set) and the candidate row is known in advance from the account the caller
claims. The digest comparison primitive is shared; the scan is not.

### The address is deliberately not captured

**Message B — "your account has been gone" — is not built by this item and cannot be
without capturing the address.** When `destroy_account` runs the account row is gone
(`backend/apps/identity/services/deletion.py:574`), so there is no address left to write
to. If B is ever to exist, the address must be captured onto `DeletionRequest` at request
time and survive the account's death — a PII consideration (AD-13) and an AD-15 retention
question.

**This item therefore does not add an address column**, and the model's docstring says
so, so a later reader does not mistake the absence for an oversight.

### What this decision does *not* settle

- **Other live sessions when a cancellation happens** — cancelling destroys nothing, so
  no session is ended. Out of scope, and correct: nothing about the account changed.
- **Whether the destroyed-account mail (B) exists at all** — a separate decision, with a
  PII cost, in a later item.
