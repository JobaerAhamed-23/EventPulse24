---
run: run-eventpulse24-045
work_item: email-change-on-the-profile-screen
intent: account-profile-expansion
date: 2026-11-19
---

# Report: Asking to Move Your Address

## The gap, and how much of it was real

The decomposition owed this item a resend and a cancel and provided neither. **Half of it
was never a gap**, and the code said so:

- The raw token is **never stored** — only its digest (AD-18) — so a resend *cannot*
  re-send the original link. It must mint a new one.
- `request_email_change` **already revokes** the outstanding row before creating the next.

**So resend is the request endpoint called again with the pending address.** No endpoint,
and the existing per-account throttle limits it for free. Pinned by
`test_asking_again_mints_a_new_link_and_kills_the_old_one` and its API-level twin.

**The real gap was cancel**, now `cancel_email_change` + `DELETE /api/auth/profile/email`.

## Tests

| Suite | Result |
|---|---|
| `components/settings/email-change.test.tsx` | **13 passed** |
| `app/confirm-email/page.test.tsx` | **5 passed** |
| `app/settings/profile/page.test.tsx` | **18 passed** |
| `tests/identity/test_email_change.py` | **26 passed** |
| `tests/identity/test_email_change_api.py` | **21 passed** |
| Full frontend suite | **2690 passed**, 164 files |
| `tsc` / `make lint-web` | clean; back to the two pre-existing findings |

## The test that had to be thrown away

**The "a taken address looks like a free one" test was vacuous, and a mutation proved it.**
Changing the island to say *"That address is already in use."* left all 12 tests green.

The island **cannot** tell the two apart — the API answers both with the same 202, which
is the whole design — so rendering the same thing twice from identical inputs asserted
nothing. The oracle risk lives at the API and is pinned there by
`test_a_taken_address_is_answered_identically`.

Rewritten, the island is held to what it *can* be held to: the success line is a template
with the address substituted and **nothing else** — no branch on the address, no reading
of the response body. Two different addresses must yield two lines differing only where
the address sits. **The same mutation now fails.**

The first version looked entirely reasonable, which is why the reasoning is written into
the test's docstring rather than left to be rediscovered.

## Mutation probes

| Mutation | Result |
|---|---|
| The success line branches on the address | 1 failed *(after the rewrite; passed before it)* |
| The island saves on keystroke | 1 failed |
| A failed cancel clears the pending state anyway | 1 failed |
| The confirm route drops `no-referrer` | 1 failed |
| The reset stops revoking pending changes | 1 failed *(run-043)* |

## Two repo guards, again catching what the item's tests could not

**`mt-10` is off the project's spacing scale.** `styles/tokens.css` declares only the
scale's steps, so an off-scale class generates **no CSS at all** — the margin would
silently not exist. The guard's own docstring records that seventy-nine such classes had
shipped before it was written. Changed to `mt-12`, which the page already uses.

**An unescaped apostrophe in JSX copy** — `react/no-unescaped-entities`.

## A missed acceptance criterion, found by re-reading the work item

**The pending state was built without the expiry**, and the first draft of this report
ticked the criterion off as satisfied — listing *"address, resend, cancel"*, which is the
subset that had been built rather than the four the work item asks for. **That is a review
failure as much as an implementation one**: the summary was written from the code instead
of from the criterion.

It could not be fixed with copy. *"Valid for 24 hours"* in the frontend is the same
mistake `password_reset.txt` carried and run-043 fixed: a number that keeps claiming 24
hours after the constant says otherwise. So the **server sends the moment**:
`CurrentUserOut.pending_email_expires_at`, ISO-8601, `""` when nothing is pending.

The island formats it, and three branches are pinned: a live link says roughly how long it
has, a dead one says *"That link has expired — send a new one"* rather than counting past
zero, and an absent value prints nothing — an unparseable expiry is not a reason to invent
a deadline. After a resend the line is **cleared**, because the previous link's deadline
is no longer true and the new one is not known at that point.

**The two `me` field-set guards fired a second time**, which is exactly what they are for:
a field on `me` costs a deliberate edit every time.

## Acceptance criteria

| Criterion | State |
|---|---|
| Current address and an explicit control | ✅ |
| **Does not fire on change**; copy says what the action does first | ✅ asserted |
| Pending state: address, **expiry**, resend, cancel | ✅ *after the miss above* |
| Cancel clears it; old address keeps working | ✅ |
| API refusal verbatim; offline line only when nothing was reached | ✅ both |
| A taken address produces the same screen state | ✅ **after the rewrite** |
| The confirmation route works **signed out** | ✅ its own test |
| A bad/expired/reused token gives one undramatic explanation | ✅ one message for all five cases |
| No "you'll be signed out" warning, because sessions do not end | ✅ asserted negatively |
| `DELETE` endpoint, idempotent, audited, no address in details | ✅ |
| Every test can fail | ✅ four probes, one of which forced a rewrite |

## Not done here

The e2e spec and the screen's final composition belong to `profile-screen-and-e2e`, the
intent's last item.
