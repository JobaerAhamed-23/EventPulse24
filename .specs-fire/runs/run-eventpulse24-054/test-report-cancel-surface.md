---
run: run-eventpulse24-054
work_item: account-deletion-cancel-surface
intent: account-profile-expansion
mode: confirm
tested_at: 2026-11-20
---

# Test Report: The Cancellation Surface — the Way Back

## What Was Tested

| File | Tests | Covers |
|------|-------|--------|
| `backend/tests/identity/test_deletion_read.py` | 9 | The read — both moments, `None` when nothing is pending, another account's absence, **no cancel token**, no writes, a cancelled deletion, the grace-period gap |
| `backend/tests/identity/test_account_deletion_api.py` (`TestTheSurfaceCanTell`) | 5 | `me` carries the two moments, they are the ones the request computed, `""` when none is pending, empty again after a cancel, **`me` carries no cancel token** |
| `frontend/components/settings/danger-zone-pending.test.tsx` | 15 | The island — the server's dates, no countdown of its own, the truth that nothing is deleted yet, the literal cancel path, the failure that keeps the pending state, the offline line, one request per press, axe-core |
| `frontend/components/settings/danger-zone.test.tsx` | 14 (9 new) | The section's two states — the pending state replaces the delete row, **never both, asserted from both ends**, no terracotta on the way back, axe-core in both states |
| `frontend/tests/privacy-danger-zone-pending.test.tsx` | 4 | The **page** — the pending state reaches the screen in both branches, and the server's date survives the trip |
| `frontend/tests/privacy-danger-zone.test.tsx` | 6 | The page with nothing pending — unchanged, and the nav/subheading agreement still holds |

**Forty-three tests across four files, and they run on both sides of the wire.** The
backend file proves the read is *correct and safe*; the frontend files prove the surface
is *reached and truthful*.

## Results

| Suite | Result |
|-------|--------|
| `backend/tests/identity/test_deletion_read.py` | 9 passed |
| `backend/tests/identity/test_account_deletion_api.py` | 22 passed (17 pre-existing + 5 new) |
| `backend/tests/identity/test_auth_api.py` | 12 passed |
| `backend/tests/identity/test_profile_api.py` | 10 passed |
| `danger-zone-pending.test.tsx` | 15 passed |
| `danger-zone.test.tsx` | 14 passed |
| `privacy-danger-zone-pending.test.tsx` | 4 passed |
| `privacy-danger-zone.test.tsx` | 6 passed |
| `tests/endpoint-coverage.test.ts` | 4 passed — the `DELETE` exemption is gone and no orphan appeared |
| **Full frontend suite** | **2798 passed, 0 failed** (174 files) |
| **Full backend suite** | **7651 passed, 0 failed** (15m53s) |
| `make lint-backend` (ruff + ruff format + import-linter) | clean — **21 contracts kept, 0 broken** |
| `pnpm tsc --noEmit` | clean |
| `pnpm eslint` on the changed files | clean |
| `pnpm prettier --check` on the changed files | clean |

## Mutation Probes — four, all detected

**A test that cannot fail is not a test.** Every load-bearing claim in this item was
contradicted deliberately, and the suite was asked to notice.

| # | Mutation | Detected by | Result |
|---|----------|-------------|--------|
| 1 | The cancel path changed to `"/api/auth/profile/deletion-cancel"` | `calls the cancel endpoint, literally` **and** `tests/endpoint-coverage.test.ts`'s orphan check | **Detected (2 files)** |
| 2 | The pending state cleared *and* `onCancelled` fired on a failed cancel | `does not tell the container anything when the cancel fails` | **Detected** |
| 3 | The page passed `""` for both moments (both branches) | All 4 tests in `privacy-danger-zone-pending.test.tsx` | **Detected (4 tests)** |
| 4 | The read's dataclass gained a `token_hash` field | `test_the_read_carries_no_cancel_token` | **Detected** |

### Probe 1 — why the path is written out literally

`tests/endpoint-coverage.test.ts` matches `\.${method}\s*\(\s*"${route}"` — the method
and the path have to be **adjacent**. A path held in a variable would not be found, and
the exemption this call site replaces would then be hiding a real one. **Probe 1 proved
that**: a wrong path did not merely break the island's own test — it re-orphaned
`DELETE /api/auth/profile/deletion` in the contract test, in the same run. Two
independent files caught the same mutation.

### Probe 2 — the failure this surface exists to prevent

The mutation was to clear the pending state on a **failed** cancel. It was caught by the
test that asserts the container is not told. **The companion assertion — that the date
and the button stay on screen — is what makes the claim legible to a person**; the
container assertion is what makes it structural. A surface that shows "Keep my account"
while telling a person their account is safe is the exact failure this item exists to
prevent, and it is now unreachable by construction.

### Probe 4 — the token cannot leak

The mutation added `token_hash` to `PendingDeletion`. The read's test failed on
`assert not hasattr(pending, "token_hash")`. **The token leak is now structurally
impossible rather than merely absent:** the dataclass has exactly two datetime fields,
and `DeletionRequest`'s `token_hash`/`token_salt` have no path to the wire through it.
The API-level test asserts the same thing one layer up — the raw `me` response does not
contain either string.

## The axe-core gate

Both `danger-zone.test.tsx` and `danger-zone-pending.test.tsx` run axe over the rendered
section and assert **zero serious or critical violations** — the pending state included.
`color-contrast` is disabled, for the same reason as everywhere else in this repo: jsdom
computes no layout, so axe cannot measure contrast. The project's separate gate
(`tests/contrast.test.ts`) measures contrast against the tokens.

## What Is Not Tested, and Why

- **The email's cancellation link** was item 1's surface and is tested there
  (`backend/tests/identity/test_account_deletion_mails.py`, and
  `test_account_deletion_token_concurrency.py`). **This item is the in-app twin**, and
  the two share one endpoint.
- **The `DELETE` endpoint's own request-side behaviour** — the token check, the
  idempotency key, the concurrency guard — was item 1's work. This item does not touch
  it; it *calls* it.
- **The delete confirmation modal** is item 4, and the `POST /api/auth/profile/deletion`
  exemption in `tests/endpoint-coverage.test.ts` stays until then. **This item removed
  only the `DELETE` exemption**, which is the one this call site replaces.

## Notes on the Design

**The read rides `me` as two moments, not a boolean.** `CurrentUserOut` gains
`deletion_scheduled_for` and `deletion_requested_at`. A `"pending": true` cannot answer
*"when does my account die?"*, and a duration cannot either — the grace period is
computed once, at request time, and a duration typed into a frontend is the mistake the
mail templates already made.

**The two moments ride every page's payload, and that is the cost.** It is recorded in
`CurrentUserOut`'s own docstring, next to the same note about `pending_email`.

**The surface computes no countdown of its own.** `danger-zone-pending.test.tsx` asserts
the absence of "30 days" and "30-day" outright. The island renders the server's date and
never re-derives a deadline.

**The section became a client component, and the island stayed an island.** The
container owns `pending` and `kept`, because it is the container that decides which row
shows — and because the reassurance outlives the row it replaced. The island calls
`onCancelled()` and nothing more. **This was caught during implementation**: the first
version put both states in the island, which would have made the reassurance vanish
along with the pending row.

---
*Test report for `account-deletion-cancel-surface`. The item is ready for review.*
