---
run: run-eventpulse24-031
intent: unwired-surfaces
scope: wide
generated: 2026-11-13
---

# Walkthrough: run-eventpulse24-031

Ten work items planned, **eight implemented, two split into intents of their own.**

## What a user can now do that they could not before

| FR | Before | Now |
|---|---|---|
| FR-49 | A Pro subscriber could create, rename, reorder and delete a collection — and never put anything in one | "Add a save" inside the opened collection |
| FR-50 | Onboarding promised "disconnect any time in Settings"; there was no such screen | `/settings/calendars`, with Disconnect and Reconnect |
| FR-24 | The neighbour count counted savers only; the "opened" half never fired | Opening a Detail Screen records the open |
| FR-20 | `ReminderPicker` was hard-coded to `saved_event` | `/personal-events/:id/reminders`, linked from the edit sheet |
| FR-18 | *(closed just before this run, commit `2ba0073`)* | Delete, in the edit sheet's danger zone |

## What will not happen again

- **`tests/endpoint-coverage.test.ts`** — every endpoint is called or declared uncalled with
  a reason. Run against the pre-intent codebase it names **exactly** the four gaps the
  manual audit found.
- **`TRACEABILITY.md` Section C** — the first section that asks whether a user can reach a
  requirement. The rules are Step 4b of the `doc-trace` skill, so a regeneration reproduces
  it.
- **Two dead surfaces deleted** — `PersonalEventsPanel`'s list branch and
  `SavedEventsSection`: 16 passing tests for code nothing rendered.

## The two splits

Both were authorised by the brief at exactly the checkpoint that made them.

- **FR-25 → `relevance-feedback-loop`.** No dismissal model, no persisted embedding
  anywhere, no migration enabling pgvector, and `EmbeddingPort` has **no production caller
  at all**. AD-4 also forbids the use as written, so it needs a spine amendment first.
- **Settings → Sources → `source-transparency-and-mute`.** No endpoints at all, and the
  mockup's four groups (Official / Community / Aggregator / Crawled) exist in none of the
  model's three taxonomies.

Both were listed here because the audit found them; neither is a wiring gap. Keeping one
and splitting the other would have made the intent's scope mean two different things.

## Verification

- **Frontend unit suite: 2378 passed, 137 files.** Up from 2348 at the run's start, after
  deleting 16 tests for dead code.
- **E2E: 5 passed, twice, with no reseed between runs**, against the real stack.
- **`make client`: no diff.** No item in this intent changed the contract.
- `tsc`, `eslint` and `pnpm build` clean.

## What the probes caught

Mutation probes were run against every item. **Six found tests that could not fail**, and
each was fixed and re-probed:

1. Two probes reported green against files `sed` had never modified — the harness now
   checks `git diff --stat` before trusting a result.
2. The credential test passed against a build that never cleared the address: the refresh
   returned an *active* connection, so the form unmounted for the wrong reason.
3. "Fires once" re-rendered with the same id, which never re-runs an effect keyed on it —
   true with or without the guard. Now rendered in `StrictMode`.
4. The endpoint-coverage matcher counted an endpoint called when the method and path merely
   appeared in the same file — and one module calls `PATCH` and `DELETE` on the same path,
   so it could not see the gap it exists to find.
5. The detail-open e2e asserted a row **count** against an endpoint that is idempotent per
   `(user, event)`.

## Carried out, not fixed

- **`unassign` closes the collection it just modified** — `open(collectionId === opened?.id ? collectionId : collectionId)`,
  a ternary whose branches are identical. Pre-existing.
- **The `.catch` in `record-detail-open.tsx` has no failing unit test** — Vitest installs
  its own `unhandledRejection` handler. Covered in the browser instead.
- **33 MVP FRs are `UNASSESSED` in Section C.** A full pass is a `doc-trace` run of its own.
- **The Free-user collections tier gate is not covered end to end** — a Free user cannot
  reach the manager, so there is no control to assert on.
