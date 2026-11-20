# Test Report: prd-section-10-2-reconciliation

**Run:** run-eventpulse24-056 · **Date:** 2026-11-20 · **Result:** PASS

## Nature of this item

**Document-only.** Verified: `git diff --name-only` shows no `.py`, `.tsx` or `.ts` file
touched by this item. The acceptance criterion *"if this item touches a code file, its
scope has slipped"* holds.

| Check | Result |
|---|---|
| `backend/tests/shared/test_retention_published.py` | 6 pass |
| `frontend/tests/legal-pages.test.tsx` | 15 pass |
| Files changed | `prd.md`, `TRACEABILITY.md` only |

## Why the tests matter here even though no code changed

The two amendments assert facts about the code. **Both are already under test**, which is
what makes them amendments rather than opinions:

- **A-27's claim** that `EMAIL_DELIVERY_EVENTS` and `ANALYTICS_AGGREGATES` have no models
  is asserted by `test_the_unimplemented_categories_are_still_unimplemented`, parametrised
  over both. If the amendment were wrong — if either had a model — that test would already
  be failing.
- **A-28's claim** that no opt-out is configured is negative and cannot be tested directly,
  but its consequence is: `legal-pages.test.tsx` asserts the rendered `/privacy` never
  matches `/opt(ed)?[ -]out/i`, so the withdrawn promise cannot return to the public page.

## Amendments written

### A-27 — two retention categories withdrawn

Both bullets in §10.2's retention list are struck through in place with a pointer to the
amendment, rather than deleted. **A reader comparing an old copy needs to see what moved**,
and a silently shorter list is how a document loses its own history.

Evidence recorded in the amendment: no model declares either; `apps/delivery/email_api.py`
states the open-and-click storage "is not" built; no analytics vendor exists in the
repository.

The amendment states explicitly that **the enum members stay**, with the reason
(`deletion.py` classifies both and the walk test requires every category to be classified),
so a later reader does not "finish the job" by deleting them.

### A-28 — the training-opt-out sentence corrected

Struck through in place, with the verified position in its stead: **no personal data
reaches the provider at all**, which is a stronger claim than the one withdrawn, plus the
condition under which a real opt-out becomes a prerequisite (FR-25's preference graph, if
it ever embeds user signals).

## Numbering

A-26 was the highest in use. Verified free across `prd.md`, `EXPERIENCE.md` — including
the `updated_note` block, where numbers are easiest to miss — and `DESIGN.md`, all three
returning zero matches for A-27 and A-28 before writing.

## Acceptance criteria

| Criterion | Status |
|---|---|
| A-27 at §10.2 with evidence and the enum-retention note | ✔ |
| A-28 at §10.2 with the verified position and the revisit condition | ✔ |
| Both follow A-25/A-26's inline form, dated, with reasoning | ✔ |
| A-26 verified highest before writing | ✔ three documents checked |
| `TRACEABILITY.md` F-6 and F-7 marked closed, naming the amendments | ✔ |
| No code changes | ✔ verified by `git diff --name-only` |
