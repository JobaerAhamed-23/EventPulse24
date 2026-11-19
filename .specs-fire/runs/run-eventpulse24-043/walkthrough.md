---
run: run-eventpulse24-043
work_item: email-change-mails
intent: account-profile-expansion
date: 2026-11-19
---

# Walkthrough: the letter that had to be true

## The small half

`services/emails.py` already rendered and streamed auth mail, and `request_email_change`
already returned the token, both addresses, the row id and the expiry. So the confirmation
mail was a link, a renderer, a template and a stream choice — the shape
`render_reset_password_email` set, followed rather than reinvented.

The expiry in all three templates now renders from the constant that enforces it, through
`domain.sources.humanise_duration` — which already existed, and which was found by looking
before writing a second formatter.

## The half that stopped the item

The warning mail is supposed to be the security control: a credential that moves silently
is an account takeover, and the only person who can stop it is the one reading the
warning. So the draft told them what to do — *"change your password now. That ends the
other sessions on your account, which stops the change from being confirmed."*

**It was false.** `confirm_email_change` takes a token and nothing else: no session, no
password. And `reset_password` had zero references to `PendingEmailChange`. An attacker
holding the confirmation link kept it through a password change and the login moved
anyway. Ending sessions would not have helped either — the link is in their mailbox, not
their session.

**The design from run-042 reasoned correctly about who to reach and never checked what to
tell them.** It called the warning the real defence while there was no action the warning
could offer. That is the kind of gap that survives a green suite, because nothing in the
code was broken: the hole was in what the code could *promise*.

So `reset_password` now revokes the account's outstanding email changes in the same
transaction, and the advice is true. `test_password_reset_revokes_a_pending_email_change`
holds it there: it issues a change, resets the password, and asserts the attacker's link
no longer moves the login.

## What the probes said about the probes

Four mutations, each failing the right tests — including removing the new revocation,
which fails exactly the test that proves the remedy.

One probe's *restore* misfired: `git checkout` cannot restore an untracked new template,
and on a tracked one it restored the **committed** version, quietly undoing this item's
own fix to `password_reset.txt`. The suite caught it in the next run, through the test
written for exactly that failure mode — asserting that *changing the constant changes the
copy*, which hard-coded text that merely matches would not survive.

## What this item does not do

It sends nothing. Wiring the two sends into the request path belongs to
`email-change-endpoints-and-contract`, which owns the edge.
