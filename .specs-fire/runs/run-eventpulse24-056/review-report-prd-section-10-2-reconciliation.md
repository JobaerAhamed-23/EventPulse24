# Review Report: prd-section-10-2-reconciliation

**Run:** run-eventpulse24-056 · **Verdict:** PASS

## Scope

`prd.md` (§10.2: two retention bullets struck, one sentence struck, A-27 and A-28 added),
`TRACEABILITY.md` (F-6 and F-7 closed).

## Checks

| Check | Result |
|---|---|
| Retention seam test | 6 pass |
| Legal page tests | 15 pass |
| Code files touched | **none** |

## Auto-fixes applied

**None.**

## Findings

### F-6 — closed by A-27
### F-7 — closed by A-28

Both now state the verified position with the evidence attached, and both corrections run
in the user's favour: the product collects **less** than the document claimed, and sends
the AI provider **nothing personal** rather than relying on an opt-out that was never
configured.

### F-9 (observation) — this class of error is only findable from outside the document

Neither divergence was discoverable by reading the PRD. §10.2 is internally consistent: it
lists nine categories and nine windows, and nothing in it is self-contradictory. **Both
errors surfaced only because `/privacy` was written from `shared/retention.py` instead of
from §10.2.**

The same is true of the traceability matrix's blind spot found in run-055 — FR-8 scored
`FULL` twice while its link 404'd, because Section C never followed an `href`.

**The pattern is worth naming:** a document checked only against itself cannot find the
places where it has drifted from the thing it describes. The two guards now in place —
`test_retention_published.py` and `internal-links.test.ts` — both work by resolving a
claim against the artefact it claims about, which is the only kind of check that catches
this.

## Observations, no action

- **Strike-through rather than deletion** keeps the original text legible beside its
  withdrawal, matching how A-24 and A-26 handled withdrawn promises.
- **A-27 explicitly protects the enum members** from a well-meaning future cleanup, naming
  `deletion.py` and the walk test. Without that sentence, the natural next step on reading
  "this category is unused" is to delete it, which would break the retention walk.
- **A-28's replacement claim is stronger than the one it withdraws**, and is testable
  today: no personal model is read into an embedding by any code path.

## Conclusion

Complete. The PRD and the code now agree on what is collected and on what reaches the
model provider.
