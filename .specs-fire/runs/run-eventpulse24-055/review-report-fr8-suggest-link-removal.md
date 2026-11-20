# Review Report: fr8-suggest-link-removal

**Run:** run-eventpulse24-055 · **Date:** 2026-11-20 · **Verdict:** PASS, with one
pre-existing finding raised

## Scope

| File | Change |
|---|---|
| `prd.md` | Amendment A-26 inline at FR-8 |
| `EXPERIENCE.md` | §5 L517, §5 L522, §2 IA row, frontmatter `updated_note` |
| `TRACEABILITY.md` | FR-8 Sections A + C annotated; finding F-1 added |
| `frontend/components/digest/digest-empty.tsx` | link + import removed; header rewritten |
| `frontend/app/page.test.tsx` | presence assertion → absence |
| `frontend/tests/digest-home-boundary.test.ts` | `UNBUILT` exception removed; two assertions updated |
| `frontend/tests/internal-links.test.ts` | **new** |

## Checks

| Check | Result |
|---|---|
| Full frontend suite | 176 files / 2832 tests, pass |
| `tsc --noEmit` | clean |
| `pnpm lint` | 5 problems — **all pre-existing**, see finding below |
| Locked copy preserved | ✔ byte-identical |
| Standards | no `.specs-fire/standards/` rule engaged; this item adds no domain logic |
| Brownfield rules | read-before-write observed; the new test reuses the existing resolver's shape rather than inventing one |

## Auto-fixes applied

**None.** Nothing mechanical was found to fix.

## Findings

### F-1 (pre-existing, not introduced here) — three lint errors are committed on this branch

`pnpm lint` exits non-zero on `feature/broken-links-and-legal-pages` **before any change in
this run**. Verified by stashing the working tree and re-running: 5 problems both ways,
byte-identical.

| File | Line | Problem |
|---|---|---|
| `components/settings/email-change.tsx` | 186:34 | **error** — Cannot call impure function during render |
| `components/settings/email-change.tsx` | 191:38 | **error** — Cannot call impure function during render |
| `e2e/digest-opt-out.spec.ts` | 102:16 | **error** — `digest` is defined but never used |
| `components/settings/source-mute-control.tsx` | 147:5 | warning — `useCallback` missing dependency `state` |
| `components/shell/avatar-disc.tsx` | 92:9 | warning — `<img>` instead of `next/image` |

**The two `email-change.tsx` errors are the ones worth attention.** *"Cannot call impure
function during render"* is a React correctness rule, not style — it flags work that can
tear or double-fire under concurrent rendering. That file shipped in `run-eventpulse24-043`.

**Not fixed here.** It is outside this item's scope, unrelated to its subject, and touching
a settings component while removing a digest link would make the commit two things. Raised
so the next item or a follow-up run can take it with its own checkpoint.

**It also means CI lint is either red on this branch or not gating**, which is worth
knowing independently of the errors themselves.

### Observations, no action

- **The new test's exception is correct but must not outlive the run.** `UNBUILT` holds
  `/terms` and `/privacy` with a reverse assertion that fails the moment either route is
  built. `legal-page-routes` is forced to remove it. Verified the reverse assertion is live,
  not commented out.
- **`/suggest` still appears in `frontend/`** — six times, all inside comments explaining
  the withdrawal. Both link resolvers strip comments before matching, so this is inert, and
  the history is worth more than the grep-cleanliness.
- **The header comment on `digest-empty.tsx` was rewritten rather than deleted.** It
  previously argued *for* the link; leaving that above code that no longer renders one
  would have been the exact failure mode the file's own prose warns about elsewhere.

## Conclusion

The item is complete and green. The one finding is pre-existing, out of scope, and
recorded rather than silently absorbed.
