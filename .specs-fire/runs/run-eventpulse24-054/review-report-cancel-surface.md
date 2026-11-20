---
run: run-eventpulse24-054
work_item: account-deletion-cancel-surface
intent: account-profile-expansion
reviewed_at: 2026-11-20
status: complete
---

# Code Review: The Cancellation Surface — the Way Back

## Files Reviewed

| File | Status |
|---|---|
| `backend/apps/identity/services/deletion_read.py` | created |
| `backend/apps/identity/services/__init__.py` | modified |
| `backend/apps/identity/api.py` | modified |
| `backend/apps/identity/schemas.py` | modified |
| `backend/tests/identity/test_deletion_read.py` | created |
| `backend/tests/identity/test_account_deletion_api.py` | modified |
| `backend/tests/identity/test_auth_api.py` | modified |
| `backend/tests/identity/test_profile_api.py` | modified |
| `frontend/components/settings/danger-zone-pending.tsx` | created |
| `frontend/components/settings/danger-zone-pending.test.tsx` | created |
| `frontend/components/settings/danger-zone.tsx` | modified (server → client) |
| `frontend/components/settings/danger-zone.test.tsx` | modified |
| `frontend/app/settings/privacy/page.tsx` | modified |
| `frontend/tests/privacy-danger-zone-pending.test.tsx` | created |
| `frontend/tests/endpoint-coverage.test.ts` | modified (exemption deleted) |
| `frontend/lib/api/openapi.json`, `frontend/lib/api/schema.ts` | regenerated |

## Summary

| Category | Auto-fixed | Suggested | Skipped |
|----------|-----------|-----------|---------|
| Code quality | 1 | 0 | 0 |
| Accessibility | 0 | 0 | 0 |
| Architecture | 0 | 0 | 0 |
| Testing | 0 | 0 | 0 |
| **Total** | **1** | **0** | **0** |

**No finding required confirmation.** Every change was a correction of this item's own
work, and the suite was re-run after it.

## Auto-Fixed

| # | Finding | File | Change |
|---|---|---|---|
| 1 | A line 106 characters long — over the project's 100-character limit — in a new test file | `backend/tests/identity/test_deletion_read.py:32` | Wrapped. `make lint-backend` is clean |

**Tests re-run after the auto-fix:** 7651 backend passed, 2798 frontend passed (174
files), `make lint-backend` clean (21 import contracts kept), `tsc --noEmit` clean,
`eslint` clean on every changed file, `prettier --check` clean.

## Findings Reviewed and Accepted as Correct

These were found by reading the diff and are **not** defects — they are recorded because
a reviewer who did not know the reasoning would reasonably ask about them.

### 1. The danger zone became a client component, and that is a real cost

The previous item's section was a server component. **This item made it `"use client"`.**

**It had to.** The section decides between two states, and the decision changes *after* a
cancellation — a server component renders once per request and cannot know that a button
was pressed. The alternative (a client island that owns the whole section) was rejected
because the section also has to host the modal that item 4 builds, and the modal and
the cancel are two mutually-referencing pieces of one section.

**The cost is that the whole section is now on the client.** It is one heading and one
row, so the cost is small. The section's own docstring says what the cost buys and
where the state lives. Not changed.

### 2. `useState` seeds from the prop and does not follow it afterwards

`useState(deletionScheduledFor !== "")` reads the server's answer once, at mount.

**This is correct for this surface.** The prop changes only when the server's answer
changes, and the server's answer changes only when the pending state is cleared — which
is exactly what the container's own `onCancelled` handler does. **A `useEffect` that
re-synced the state from the prop would fight the cancellation**: the prop would still
say "pending" until the next `me` read, and the effect would put the pending row back
after the person cancelled. The seeded state is the right shape.

### 3. The read lives in the service layer, and `api.py` reads `DeletionRequest` directly for `pending_email`

The `pending_email` read in `api.py` goes straight to the model. **This item's read does
not, and deliberately did not copy that precedent.**

`DeletionRequest` carries `token_hash` and `token_salt` — the digest of a bearer
credential that cancels the account's destruction. **A read that handed the API layer the
row would hand it that digest**, and `me` is readable by anyone holding the account's
session. So the read returns a frozen dataclass with exactly two datetime fields, and
the token has no path to the wire through it.

**The two tests that hold this** are `test_the_read_carries_no_cancel_token`
(`assert not hasattr(pending, "token_hash")`) and `test_me_carries_no_cancel_token`
(the raw response body contains neither `token_hash` nor `token_salt`). The second is at
the wire, which is where the claim actually is. Not changed.

### 4. The section's "renders unconditionally" paragraph now describes a different rule

The docstring says the section is not conditional on a read succeeding, and that a failed
read shows the request row — because *"no pending deletion I can see"* and *"no pending
deletion"* are different things.

**That paragraph is still true**, but it is now describing the *frontend's* fallback
rather than the backend's, and the read that can fail is `me` itself. The rule as written
still holds: the section renders whichever state it can prove. Not changed — it is
correct, and it describes a rule that survives this item.

### 5. The island re-implements date formatting rather than sharing a helper

`destructionDate()` and `requestedOn()` are two functions with the same body.

**They are not the same function.** One reads the destruction date and the other reads
the request date, and they are named for what they read — a future reader changing the
destruction date's format should not silently change the request date's. The shared body
is four lines. Merging them would need a third name for a thing that has two callers
with two distinct meanings. Not changed.

### 6. The failure alert lives inside the row, and the reassurance lives outside it

The `role="alert"` for a failed cancel is inside the island, so it is inside the
`SettingRow` and cannot be separated from the control it belongs to. The success
reassurance is in the container, outside the row.

**That asymmetry is deliberate and necessary.** The failure belongs to the *control* —
the person pressed it and it did not work, so the message sits with the button. The
success belongs to the *section* — the pending row is gone, and the message must outlive
the row it replaced. `SettingRow` has a `footer` prop for exactly the first case; the
island uses the control slot because the message has to be near the button, and the
container uses the row-below slot because the reassurance has to survive.

**This was caught during implementation.** The first version put both states in the
island, which meant the reassurance vanished along with the pending row it was
reassuring about. Not changed — the fix is in place and tested.

### 7. The endpoint coverage exemption for `DELETE` was deleted, not rewritten

The work item says the exemption is deleted, not rewritten. **It was deleted**, and the
`POST /api/auth/profile/deletion` exemption stays — that is item 4's modal, which does
not exist yet.

**The deletion is proven by the coverage test itself**: the moment the `DELETE` call site
went in, `DELETE /api/auth/profile/deletion` would have become an orphan and the test
would have failed. A mutation probe confirmed the reverse direction — a wrong path
re-orphaned it, and the test noticed in the same run as the island's own test. Not
changed.

### 8. The `POST` exemption's reason text still says "a modal in front of promises the engine does not keep"

That reason is about the *modal*, not the cancel endpoint, and it is still true. Not
changed.

## Accessibility Review

| Check | Result |
|---|---|
| The pending state has a **real button** with an accessible name | ✅ `aria-label="Keep my account. The pending deletion is cancelled."` — the name says what it does, not just what it is called |
| The button is **keyboard reachable** | ✅ A real `<button type="button">`, with a 44px minimum height |
| The in-flight state is announced | ✅ `aria-busy={busy}` on the control, and the label changes to "Keeping it…" |
| The failure is announced **without stealing focus** | ✅ `role="alert"` — assertive, but the focus does not move |
| The success is announced **politely** | ✅ `role="status" aria-live="polite"` in the container, matching `SaveFeedback`'s pattern exactly |
| The live region is **always present** | ✅ An empty live region is what makes the *arrival* of text announceable at all — the reasoning `SaveFeedback` records |
| The colour is not the only signal | ✅ "Deletion scheduled", the date, and "Keep my account" all carry the meaning; terracotta is absent by design |
| The destructive colour is not on the way back | ✅ Asserted in three places, mutation-probed |
| One instruction at a time | ✅ The pending row *replaces* the request row; asserted from both directions |
| Serious/critical axe violations | ✅ Zero, in **both** states |
| `color-contrast` | ⚠️ Disabled in the axe gate — measured separately by `tests/contrast.test.ts` |

## Architecture Review

| Check | Result |
|---|---|
| **AD-16 — write ownership** | ✅ The frontend writes nothing directly. The island calls `DELETE`, which the API layer turns into the named command `cancel_account_deletion`. `tests/architecture/test_no_direct_writes.py` is green |
| **AD-5 — named commands own writes** | ✅ `api.py` calls the service; the service owns the transaction and the audit entry |
| **AD-2 — no cross-app model imports** | ✅ `read_pending_deletion` imports `apps.identity.models` from within `apps.identity` — allowed by the `models-identity` contract, and `make lint-imports` is green (21 contracts kept) |
| **AD-3 — schema routing** | ✅ `.using(PERSONAL)` on the query, `PERSONAL` imported from `shared.db`. No bare alias |
| **AD-6 — no naive datetimes** | ✅ Both moments are aware, from the model's `timestamptz` columns |
| **AD-13 — no PII in the payload** | ✅ The two moments are dates. No email, no name, no token |
| **AD-19 — OpenAPI is the contract** | ✅ The client was regenerated with `make client`; `backend/tests/api/test_contract.py` is green. The endpoint path is written out **literally** in the call site, because the coverage test's matcher needs the method and the path adjacent |
| **The generated client is never hand-edited** | ✅ `openapi.json` and `schema.ts` were regenerated, not written |
| **The `models-<app>` contract** | ✅ `read_pending_deletion` is the *only* new place that touches `DeletionRequest`, and it lives inside `apps.identity` |

## Testing Review

| Check | Result |
|---|---|
| Tests can fail | ✅ **Four mutation probes, all detected** |
| Naming convention | ✅ `test_<unit>_<condition>_<expected>` on the backend; `it("…")` in a `describe` naming the unit on the frontend |
| Fakes at the port boundary | ✅ `getSession` and `readRankingTransparency` are the page's two reads, both replaced at the port. `api.DELETE` is replaced at the client boundary — the same way `email-change.tsx`'s tests do it |
| **Never mock the ORM** | ✅ The backend tests use a real Postgres and the real model |
| Coverage of the changed files | ✅ `deletion_read.py` — every line. `danger-zone-pending.tsx` — every branch. `danger-zone.tsx` — both states. `privacy/page.tsx` — both branches, both with and without a pending deletion |
| Edge cases | ✅ Nothing pending; pending with a parseable date; pending with an **unparseable** date (the surface says nothing rather than inventing one); the API refusing; the request never reaching the API; a second press while one is in flight; a failed cancel |
| The failure that keeps the pending state | ✅ Asserted three ways: the button stays, the date stays, and the container is **not** told |
| The full suite | ✅ 7651 backend, 2798 frontend, 0 failures |

## The One Thing I Would Raise, and Did Not Change

**The reassurance's live region is outside the row, and the row's contents unmount on
success.** The button the person just pressed is removed from the DOM at the moment of
success — so a keyboard user's focus lands on nothing, and the announcement comes from a
sibling region rather than from the control they were on.

**This is how `email-change.tsx` behaves too** (the sent confirmation replaces the form),
and `SaveFeedback` puts its success region in a sibling as well. So it is the project's
established pattern, not a departure.

**It is not perfect, and the fix is not free.** Moving the live region inside the row
would mean the region unmounts too — and a live region that is added to the DOM at the
same time as its text is not reliably announced. The accessible fix is to move focus to
the reassurance, which is a real behavioural decision about where focus lands after a
destructive action is undone. **That decision is worth making deliberately, and it is not
this item's to make silently.** It is recorded here so the next reader knows it was seen
and not missed.

## Conclusion

**No changes require confirmation.** The one auto-fix was a line-length correction, and
the suite is green after it.

The item is ready for completion.
