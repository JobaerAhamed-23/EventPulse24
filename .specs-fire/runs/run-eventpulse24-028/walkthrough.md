---
run: run-eventpulse24-028
intent: traceability-reconciliation
scope: wide
items: 6
---

# Walkthrough: Traceability Reconciliation

## What this run was for

Eleven intents shipped against a traceability matrix nobody regenerated. It was produced
**2026-09-08**, seven weeks before the first FIRE intent ran, and by November it was wrong in
both directions: it reported a gap that had been closed, and it reported four gaps that were
real but had inverted — the *software* existed and the *design* describing it did not.

A stale check is worse than no check, because people stop reading it. This run restored it.

## What changed

| | |
|---|---|
| Files created | 5 — 4 mockups + `.memlog.md` |
| Files modified | 10 |
| Files deleted | **1,328** |
| Tests added | 5 |
| Backend/frontend source changed | **none** |

**The last row is the headline.** Four requirements were flagged as undesigned; none needed a
line of application code. The code was right and the documents were wrong.

### Mockups created

| File | FR | Closes |
|---|---|---|
| `personal-event-reminders-desktop.html` | FR-20 | PARTIAL (inferred only) |
| `share-affordance-desktop.html` | FR-28 | PARTIAL (inferred only) |
| `collections-desktop.html` | FR-49 | **MISSING** |
| `event-state-conflict-desktop.html` | FR-55 | PARTIAL (inferred only) |

Plus two existing FR-58 mockups re-tagged with `FR-55`, which was the "documented
acknowledgment" the matrix found missing.

### Tests added

| Test | What it pins |
|---|---|
| `test_a_personal_events_plan_emptied_cancels_every_send` | Removing a **personal** event's reminders stops the email, not just the plan |
| `test_a_muted_event_still_reports_its_notice` | The mute and the notice are independent — an invariant two docstrings defended and nothing proved |
| 3 × Open Graph tests | The `description` field, its **no-description fallback**, and truncation |

## What the run actually found

**1. Four requirements had code but no design — and one of them said so.**
`collection-manager.tsx` opens: *"This surface has no approved design, and that is a fact
about the build rather than an oversight… If it ever grows past a modest management UI, that
is the signal to stop and get a design pass."* `attach_default_plan`'s docstring cites the
traceability gap by name. The build knew. The documents did not.

**2. Most "missing" verification already existed.** Of the eleven tests the work items
specified, **six were already written and passing**. The FR-49 reorder regression existed in
a *better* form than specified — pinning the route-ordering trap behaviourally rather than by
asserting registration order. Tests were cited by name and **run**, not merely cited.

**3. The gaps that were real were small, specific and the kind that ship silently.** An
Open Graph `description` nobody asserted. A mute-and-notice pair nobody put on the same
event. A personal event whose reminders could be emptied without proving the emails stopped.

**4. Three errors in a hand-maintained table — one of which had never been checked.**
Row 10 claimed a design that did not exist (`collection` ×0 in the named file). Row 11 read
as FR-28 but was tagged `UJ-5`. Row 9 named **a mockup file that has never existed**; only a
filename-by-filename check against `ls` found it.

**5. The matrix's own headline finding was false.** Its "single highest-value finding" — that
Architecture never accounted for FR-32/FR-33 — is contradicted by `AD-21`, two Capability-Map
rows, and the word "Amendment" at three places in a spine it claimed never used it.

**6. The suite has been quietly rotting on a timer.** 17 backend tests fail on `main`, all
from hardcoded absolute datetimes that have passed. The count rose **16 → 17 during this
run**: `test_reminder_plan_api.py`'s `AFTERNOON_START` is 2026-11-12 02:00 UTC, and run 027's
suite finished at 02:19. Run 027 recommended a defect item for this; it was never created.

## The result

| | September | Now |
|---|---|---|
| Section A | 32 FULL · 3 PARTIAL · 1 MISSING · 9 N/A | **35 FULL · 1 PARTIAL · 0 MISSING · 9 N/A** |
| Section B | FR-32/FR-33 MISSING | **45 FULL · 0 gaps** |
| Mockups scanned | 32 | 50 |

**The target was 36 FULL and the run reports 35.** The one short is FR-16, which was *always*
PARTIAL — September rated it FULL on exactly the adjacency evidence it called PARTIAL for
three other FRs. Its own counts were not internally consistent.

Closing FR-16 is one line. It was deliberately not done, because the pass that measures
coverage must not edit what it measures.

## What is still open

Five items, all recorded in the matrix's own closing section:

1. **FR-16** — one tag or one citation moves it to FULL.
2. **The postponed-into-conflict e2e test** — waits on the time-bomb fix so it lands green.
3. **17 time-bombed tests** — a defect class, not a bug; fix is a clock port or `freezegun`.
4. **The A-11–A-20 convention question** — whether UX-originated amendments should flow back
   into the PRD. Decide once, rather than re-flagging it every regeneration.
5. **`DESIGN.md`'s frontmatter does not parse** — unescaped quotes from Amendment A-22,
   predating this run. Found here, deliberately left for its own change.

## How this is kept from happening again

The matrix is now **regenerated rather than hand-maintained**, and `.memlog.md` records each
scan. The next reader can measure drift from the gap between its dates instead of
rediscovering it seven weeks and eleven intents later.
