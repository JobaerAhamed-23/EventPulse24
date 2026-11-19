---
run: run-eventpulse24-042
work_item: pending-email-model-and-commands
intent: account-profile-expansion
date: 2026-11-19
---

# Walkthrough: the login learns to move

## Most of this was already written

The design's job here was mostly to notice that `password_reset.py` had already solved
this problem. Issue a proof to an address, consume it once, safely — and its docstrings
record *why* each property is there, including that Django's own
`PasswordResetTokenGenerator` was probed against the pinned Django and rejected for being
replayable and unrevocable. None of that was re-decided.

So `PendingEmailChange` is `PasswordResetToken`'s shape almost field for field, and the
scan that finds a row moved into `services/tokens.py` to be written once.

**The extraction went first, deliberately.** While password-reset was still its only
caller, that suite was the proof it had not changed — 23 tests, passing **unedited**. Done
last, a regression in the shared scan would have surfaced mixed in with new failures from
new code, and the suite that proves it is the one I would have just finished editing
around. A security helper is the wrong place to find out later.

## Three things that are genuinely new

**The race is lost at the constraint.** Between the request and the confirmation, someone
else can claim the address. Checking again at confirm time narrows the window and does not
close it: two confirmations can both pass the check and both write. `user_email_uq` is the
only thing that actually arbitrates, so the write is attempted and the `IntegrityError` is
the answer. The test runs the race for real rather than asserting the branch exists.

**A taken address is answered with silence.** `request_password_reset` is enumeration-safe,
and the mirror of that rule here is that an address another account holds must return
exactly what a free one returns — otherwise this endpoint answers *"does an account exist
at this address?"* for anyone who asks. Nothing is written and **nothing is sent**: a mail
to the taken address would be the oracle in another form, and a way to send mail to a
stranger by typing their address.

**Other sessions are not ended, and that reverses the obvious answer.** `reset_password`
ends them, so copying looks prudent. Django's session auth hash is an HMAC over the
**password** field — a password change invalidates every session by itself, which is why
`reset_password` has to pass `keep_session_key` and re-stamp, *rescuing* one session from a
logout the framework already imposed. An email change touches no password, so nothing is
invalidated and ending sessions would be a new, deliberate logout. And it does not defend
the case it appears to: an attacker holding a live session requests a change to **their
own** address, so a logout at confirm time signs out the victim. What defends that case is
the warning to the old address — the next item's job — and the throttle here.

## The test that did not exist until a probe asked for it

The suite was 19 for 19. Then the fourth mutation removed the conditional
`UPDATE ... WHERE used_at IS NULL` — the guard that makes the **database** the arbiter of
single-use rather than the row lock — and **every test still passed**.

`test_a_token_works_once` never touched it. The scan already filters
`used_at__isnull=True`, so a sequential second attempt finds no row and is refused for an
entirely different reason. The guard exists for two confirmations in flight at once, which
no sequential test can reach.

The new test consumes the row *after* the scan returns it and *before* the update — the
exact interleaving, and the only way to reach it deterministically. **A suite that is green
is not the same as a suite that is evidence.**

## And one the item's own tests could not have caught

`tests/architecture/test_write_ownership.py` failed on the new table: AD-16 wants every
table claimed in `TABLE_OWNERS`, enforced from both directions. A migration is not the end
of adding a table — somebody has to be responsible for it. `identity_pendingemailchange`
is identity's, for the reason the reset token is: the app that owns the credential owns
the unproven claim on it.

## What this item deliberately does not do

It sends nothing. `request_email_change` returns the raw token and **both** addresses, and
`email-change-mails` owns the two messages — including the warning to the old address that
this design leans on as its real defence.
