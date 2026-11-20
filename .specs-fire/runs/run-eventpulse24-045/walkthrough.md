---
run: run-eventpulse24-045
work_item: email-change-on-the-profile-screen
intent: account-profile-expansion
date: 2026-11-19
---

# Walkthrough: the screen that waits

## The gap shrank when it was checked

The decomposition owed this item a resend and a cancel. **Resend was never a gap.** The
raw token is never stored — only its digest — so a resend cannot re-send the original
link; it has to mint a new one. And the request command already revokes the outstanding
row before creating the next. So pressing *"Send the link again"* posts the same address
again, and the previous link stops working. The button is honest about what it does,
because what it does is the only thing it could do.

That left one real gap: **cancel**, which matters more than it looks. The warning mail
tells somebody who did not ask for the change to reset their password. Cancel is the
gentler route for the commoner case — a mistyped address, or a change of mind — and the
account holder should not have to reset a credential to stop something they started.

## The one control on this screen that waits

Every other settings island saves on keystroke; the name directly above this one does.
This one cannot: an address typed a character at a time would mail `m@`, then `ma@`, then
`may@`, to strangers, from an endpoint that sends real mail.

So it has an explicit action, and the copy says what that action does *before* it is
pressed. A reader who notices this control behaves differently from its neighbours is
noticing something true: it is the only setting here that changes a credential, and the
only one that cannot take effect immediately.

## The test that was thrown away

The island must not reveal whether an address is already taken. The first test rendered
the flow twice and asserted the same sentence came back — and **a mutation that made the
island say *"That address is already in use."* still passed every test.**

The test was vacuous, and for a structural reason: the island cannot tell the two cases
apart. The API answers both with the same 202, which is the entire point, so there is no
input that differs and nothing for the test to distinguish. The oracle risk lives at the
API, and it is pinned there.

What this layer *can* be held to is that the success line is a template with the address
substituted and nothing else — no branch, no reading of the answer. Rewritten that way,
the same mutation fails. **The first version looked perfectly reasonable**, which is why
the reasoning now lives in the test's docstring.

## The route the link lands on

`/confirm-email` is a pre-auth route, like `/reset-password`, and for a specific reason:
`homeRoute(session)` sends anonymous visitors to `/preview`, and a confirmation link that
gets redirected is a link that does not work. The link is opened from a mailbox, in a
browser that may never have signed in. That is the single most likely bug in this item, so
it has a test of its own.

It carries `referrer: "no-referrer"` because the token is a bearer credential in the URL,
and the form strips the query string once it holds it — both copied from the reset route,
which had already solved this.

**It spends the token with a POST, never by loading.** A `GET` that moves a login is
performed by every mail scanner and link prefetcher that touches the message; the account
would change address because software followed a link.

## Two guards that caught what the tests did not

`mt-10` is off the project's spacing scale — and `tokens.css` declares only the scale's
steps, so an off-scale class generates **no CSS at all**. The margin would silently not
exist. That guard's docstring records that seventy-nine such classes shipped before it was
written.

And an unescaped apostrophe in JSX copy.

Neither is the kind of thing an item's own tests look for, and both were caught in the
seconds it takes to run the suite.
