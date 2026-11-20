---
run: run-eventpulse24-044
work_item: email-change-endpoints-and-contract
intent: account-profile-expansion
date: 2026-11-19
---

# Walkthrough: two endpoints, and the guards that met them

## The open question answered itself

The work item warned that `require_csrf` could not apply to a confirm endpoint opened from
a mailbox, and asked for some other protection. **It can.**
`password_reset_confirm` already calls `require_csrf` while serving callers with no
session, because `GET /api/auth/csrf` issues the token for exactly that case. So the
email-change confirm mirrors it, and nothing was invented.

Both halves are pinned: a session-less caller gets 200, and a caller without a CSRF token
gets 403. The second test is what stops "anonymous" quietly becoming "unprotected".

## The property the whole flow is shaped around

`POST /api/auth/profile/email` must answer a free address and a taken one **identically**
— status *and* body. The command returns `None` for taken; the handler sends nothing and
returns the same 202. One test compares the two responses field for field, and a mutation
that makes the taken case say `already_taken` fails it.

That test is the flow's reason for existing. Everything else here is plumbing.

## Three guards the repo fired that the item's own tests could not

**The email fixture.** Six tests failed with `'SmtpEmailAdapter' object has no attribute
'sent'`. `email_adapter` patches `get_email_port` in a *named list* of modules and listed
only the two services — but these sends happen at the **edge**, so `apps.identity.api` is
a third consumer. Without it, those tests were being answered by a real SMTP adapter. The
list now says so, with the reason, because the next module that sends mail will hit this
too.

**Two field-set guards on `me`.** One asserts the whole dict, one the key set.
`CurrentUserOut` claims it has no catch-all so nothing internal can ride along, and these
two are how that claim is enforced. Adding `pending_email` is meant to cost that edit, and
the reasoning now lives in the test's docstring rather than only the schema's.

**The pattern is worth naming.** The item's own tests keep proving the behaviour that was
being thought about. The repo's guards keep catching the things that were not.

## A divergence kept on purpose

`request_password_reset` sends from inside the service; `request_email_change` returns the
token and both addresses and lets the endpoint send. The command stays testable with no
email port at all — and the cost is precisely the fixture seam above. It is recorded in
the review report rather than smoothed over, because two auth flows that otherwise mirror
each other now differ in one structural way.
