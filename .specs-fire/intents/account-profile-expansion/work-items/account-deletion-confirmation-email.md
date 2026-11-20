---
id: account-deletion-confirmation-email
title: The Mail That Says Your Account Is Going Away — and How to Stop It
intent: account-profile-expansion
complexity: medium
mode: confirm
status: completed
run_id: run-eventpulse24-054
completed_at: 2026-11-20T07:47:43.578Z
depends_on:
  - account-deletion-and-avatar-removal
created: 2026-11-20
---

# Work Item: The Mail That Says Your Account Is Going Away — and How to Stop It

## Description

**A-16's third paragraph promises a mail, and no mail exists.**

> You can cancel anytime during the 30-day grace from this page or from the email we
> send.

`account-deletion-and-avatar-removal` built the engine and recorded, deliberately, that
this promise was unkept: *"**A-16's third paragraph promises two things this item does
not keep:** that the user can cancel 'from a page', and that they are **sent an email**
when their account is deleted. Neither is in this item — there is no mail here, and there
is no page."*

**That was the right call then.** A modal and a mail both in one pass, where the mail
describes a cancellation the product cannot perform, is the same lie in a different
place. **Now the pieces can land separately, and this item is the mail.**

## The decision this item has to settle first: which email?

**There are two moments the product could write to, and they are different messages.**

| | Sent when | Purpose | Carries a cancel link? |
|---|---|---|---|
| **A — The notice** | The request is **made** | *"Your account will be destroyed on <date>. Here is how to stop it."* | **Yes** — it must, or "cancel from the email we send" is false |
| **B — The last call** | The account is **actually destroyed** | *"Your account has been deleted."* | **No** — it is too late; the account is gone |

**A-16's promise can only be kept by A.** The sentence is *"you can cancel during the
30-day grace ... from the email we send"* — the mail is the thing that arrives *during*
the grace, carrying the means to stop it. **A mail sent after the destruction cannot
carry a cancel link, because there is nothing left to cancel.**

**So this item builds A. And it is honest about the fact that B is a different message
with different content** — see the "Scope Note" below.

## What the notice must say, and what it must not

**The mail is the only channel that reaches a user who has closed the tab.** The page
surface (a sibling item) is there for a user who is looking at the site. The mail is
there for a user who asked to leave and then got cold feet — and if that user cannot
stop it from the mail, the 30-day grace period is a formality.

**Its contents, all of which the engine already knows:**

- **The date the account will be destroyed** — `scheduled_for`, which was computed once
  when the request was made and cannot be moved by asking again
- **How to cancel** — a link, and the route it lands on
- **What is deleted** and **what survives** — the same two facts the modal's body states,
  because the two surfaces must not drift
- **That the account keeps working until then** — nothing is destroyed at request time

**The one thing it must not say: "we will email you again when it is done."** That is
message B, and until B exists, promising it here would be the same unkept promise the
engine item refused to make.

## The cancel link, and the token it carries

**A cancel link that a stranger can click is a cancel link that cancels the wrong
account.** So the link carries a token that authenticates the holder as the account's
owner.

**The project already has the exact pattern to copy, and it is `PasswordResetToken`**
(`backend/apps/identity/models.py:92`): the digest at rest with a per-row salt, single-
use via `used_at`, short-lived via `expires_at`, revocable via `revoked_at`, and the user
held **by value** rather than by relation (OQ-8). `account-deletion-and-avatar-removal`
records the same reasoning when it rejected Django's own `PasswordResetTokenGenerator`:
*it is replayable and cannot be revoked*.

**So this item follows that row's shape rather than inventing a second token story.**

**The hard question is the lifetime.** A reset token is short-lived because the user is
at the password screen *right now*. **This token has to live as long as the grace period
— thirty days** — because the mail may sit unread in an inbox for a fortnight before
the person opens it and decides they want to come back.

**That is a real security decision and it belongs in the design checkpoint, not in a
guess.** Thirty days of bearer access to an account-cancellation is thirty days during
which a leaked mailbox link can cancel the deletion. The alternatives are worth weighing
in the design doc:

1. **A token valid for the whole grace period** — simplest, and matches the promise
   literally, but the window is 30 days
2. **A short-lived token that, on use, mints a fresh one** — the mail's link works once
   and the page it lands on issues a new one, so an old unread link is harmless
3. **No token in the mail at all** — the mail tells the user to visit a page and sign in
   normally, and the cancel action rides the session

**Option 3 is the safest and it is the one the product should probably take** — it
needs no new token, no new model and no new lifetime to reason about. **But it changes
the modal's sentence**, because A-16 says "cancel ... from the email we send", which
reads as cancelling *from the mail*. If the mail sends the user to a page, the copy has
to say so.

**This item's design checkpoint exists to settle this**, and the answer decides whether
it needs a model and a migration or not.

## Scope Note: The "your account is gone" Mail Is Not This Item

**Message B — the mail sent when the account is actually destroyed — is a separate
concern and is not built here.**

**The reason is technical, not a scoping dodge.** When `destroy_account` runs, the
account row is **gone** — deleted at `backend/apps/identity/services/deletion.py:574`,
with the picture removed from the bucket immediately after the commit. **There is no
email address left to send it to.** The mail has to be sent *before* the row dies, or
the address has to be captured onto the `DeletionRequest` row when the request is made.

**That choice has consequences and it belongs in the design doc.** If B is to exist at
all, the address must be captured at request time and survive the deletion — which
means a copy of the email on a row that outlives the account, which is a PII
consideration (AD-13) and arguably an AD-15 retention question.

**This item does not make that decision and does not build B.** It builds the mail the
modal's promise actually requires — the notice that arrives during the grace period,
carrying the means to stop it — and it records that B remains unbuilt so the gap is
visible rather than assumed.

## Acceptance Criteria

- [x] **The design checkpoint settles the cancel-link mechanism**, and the decision and
      its rationale are recorded in a design doc before any code is written
      — `design-deletion-cancel-token.md`, written and approved at the plan checkpoint
      before the first line of implementation
- [x] A mail is sent when the deletion is **requested**, on the **transactional** stream
      (`Stream.TRANSACTIONAL`), following the existing renderer-and-stream pattern in
      `backend/apps/identity/services/emails.py`
      — `render_account_deletion_email` + `account_deletion_stream`;
      `test_requesting_deletion_sends_the_notice`
- [x] The mail carries **the date the account will be destroyed**, rendered from
      `scheduled_for` — the value the server computed, not a hardcoded "30 days"
      — `test_it_carries_the_date_the_account_will_be_destroyed`
- [x] The mail carries **a working way to cancel**, and the way it works is the one the
      design checkpoint chose
      — the token, spent by `cancel_account_deletion_with_token`;
      `test_the_token_in_the_mail_cancels_the_deletion`
- [x] **The account's email address is the recipient** — and it is **not** written to a
      log line, not put in an audit detail, and not stored anywhere the AD-13 rules
      forbid (AD-13)
      — `test_the_send_failure_log_carries_no_address`,
      `test_the_audit_rows_carry_no_token`, `test_the_audit_rows_carry_no_personal_data`
- [x] If a token is used, it is **stored as a digest with a per-row salt**, is
      **single-use**, is **revocable**, and holds the user **by value** rather than by
      relation (OQ-8) — the `PasswordResetToken` shape, not a new story
      — `token_hash` + `token_salt` on `DeletionRequest`;
      `test_the_notice_carries_a_token_that_is_not_stored_in_the_clear`,
      `test_a_spent_token_cannot_be_replayed`,
      `test_two_concurrent_cancellations_of_one_token_only_one_succeeds`
- [x] The mail's template lives in `backend/apps/identity/templates/identity/`, beside
      the four that are already there
      — `account_deletion.txt`, fifth in the directory
- [x] **The mail says the same things the modal's body says** — what is deleted, what
      survives as anonymised aggregates, that the account keeps working during the
      grace — and the two are checked against each other rather than written twice
      — `DELETION_REMOVES` and `DELETION_SURVIVES` are one source for both surfaces;
      `test_it_uses_the_shared_words_the_modal_uses`
- [x] **The mail does not promise a follow-up mail**, because no such mail exists
      — `test_it_does_not_promise_a_follow_up_mail`
- [x] Every expiry in the copy is **rendered from the constant that enforces it**, per
      this module's own docstring — *"a number typed into a template is a number that
      keeps saying '30 minutes' after the constant says otherwise"*
      — `test_it_states_the_grace_period_from_its_constant` **and**
      `test_changing_the_constant_changes_the_copy`, which moves the constant and asks
      the copy to follow
- [x] The mail is sent **once**, not on every request — a second request is idempotent
      and must not produce a second mail
      — `test_asking_twice_sends_one_mail_not_two`; the idempotency key is derived from
      the request row (`account_deletion:<pk>`), never from the address
- [x] A send failure **does not fail the deletion request** — the request stands, and
      the failure is logged rather than raised, because the endpoint's contract says the
      request "cannot fail on its merits"
      — `test_a_mail_failure_does_not_fail_the_request`;
      `robust=True` on the `on_commit` registration
- [x] The new template and renderer are covered by **tests that can fail** — verified by
      a mutation probe
      — **four probes, all detected**: sending inside the transaction, an unconditional
      send, a hard-coded "30 days" in the template, and the row lock removed from the
      token spend. The last failed on 3 of 3 runs.
- [x] `backend/tests/api/test_contract.py` stays green, and the contract is
      **regenerated and committed** if the change reaches the schema (AD-19)
      — **the schema is byte-identical**: this item adds no endpoint and no field, so
      `export_openapi_schema` produces no diff and the generated client needs no
      regeneration. The contract test is green.
- [x] `tests/architecture/test_no_direct_writes.py` stays green
      — the send is in the command; the API layer writes nothing

## Technical Notes

- **Read `account-deletion-and-avatar-removal.md` first.** It records why the object is
  removed at destruction rather than at request, and why the audit row is written before
  the account dies.
- **The renderer pattern is `render_to_string` + `EmailMessage`, and the stream is a
  named function** — `reset_password_stream`, `email_change_stream`,
  `data_export_stream`. The stream choice lives in one place so a second auth mail
  cannot drift onto the wrong one.
- **The transactional stream is right.** This is a one-time answer to something the user
  did, not a list they subscribed to — the same reasoning `render_data_export_email`
  records, and it means no RFC 8058 unsubscribe URL.
- **The idempotency key (AD-7)** — every auth mail in this module carries one. The
  deletion notice's key must be derived from the request, so a second request sends
  nothing.
- **Where the send happens is a decision.** Inside `request_account_deletion`, after
  the transaction commits — so a rolled-back request sends no mail. This is the same
  ordering the avatar's bucket removal uses, and for the same reason: **the bucket and
  the mail are both outside the transaction, and both happen after it.**
- **Do not widen the logger allowlist** (AD-13). A send failure logs a type, not a
  recipient.

## Dependencies

- `account-deletion-and-avatar-removal` — the request command, the `DeletionRequest`
  row that holds `scheduled_for`, and the `cancel_account_deletion` command the link
  has to reach

## What Shipped, and What Is Still Missing

**Shipped in `run-eventpulse24-054`.** The notice mail, the cancel token it carries, and
the command that spends the token. The link in the mail names the frontend route
`/cancel-account-deletion?token=…`.

**Still missing, and it is the next item's work.** The route itself has no HTTP surface
yet — the command `cancel_account_deletion_with_token` exists and is tested, but nothing
exposes it over HTTP. **`account-deletion-cancel-surface` owns that**, and it also owns
the read that tells the danger zone a deletion is pending. The route name is recorded
here and in the design doc so it can be written against.

**Still missing, and deliberately out of scope.** Message B — the mail sent when the
account is actually destroyed — is not built. The account row is gone by then, so there
is no address to send it to, and capturing one onto a row that outlives the account is a
PII and retention decision this item does not get to make. **`DeletionRequest` does not
hold an address, and its docstring says so**, so a later reader does not mistake the
absence for an oversight.

**One thing the copy does not say, on purpose.** The notice says the link "works only
once" — and it does, because spending the token deletes the row the token lived on.
It does *not* promise a second mail when the account is destroyed, because that mail
does not exist.
