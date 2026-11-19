---
run: run-eventpulse24-048
work_item: settings-privacy-ranking-transparency
intent: traceability-gap-closure
generated: 2026-11-19
status: reviewed
---

# Review Report: FR-22's transparency promise has no surface

## Scope of review

The first code-bearing run of this sequence. Six files created, ten modified, across
backend and frontend.

| File | Change |
|---|---|
| `apps/personalization/ranking_transparency_api.py` | new — `GET /api/settings/ranking` |
| `apps/personalization/schemas.py` | +4 schemas |
| `shared/constants.py` | +2 amendment constants, +`RANKING_TERM_LABELS` |
| `config/api.py` | router registration |
| `tests/personalization/test_ranking_transparency_api.py` | new — 8 tests |
| `tests/shared/test_constants.py` | +1 test, 2 assertions extended |
| `tests/architecture/{test_no_direct_writes,test_digest_composition_separation}.py` | surface registries |
| `app/settings/privacy/page.tsx` | new route |
| `components/settings/ranking-formula.tsx` | new component |
| `components/settings/ranking-formula.test.tsx` | new — 8 tests |
| `lib/ranking-transparency-read.ts` | new read helper |
| `lib/settings-sections.ts` | Privacy row + docstring correction |
| `lib/api/{openapi.json,schema.ts}` | regenerated — never hand-edited |

## Checks

| Check | Result |
|---|---|
| Backend suite | 7492 passed, 3 pre-existing failures |
| Frontend suite | 2698 passed |
| `ruff format --check .` | 691 files formatted |
| `lint-imports` | 20 contracts kept, 0 broken |
| ESLint on changed frontend files | clean |
| Generated client is additive only | 249 insertions, 0 deletions |
| Endpoint touches the ORM | **no** — projects module constants only |
| Secrets / PII in the new surface | none — the response is identical for every caller |
| Next.js 16 conventions verified against `node_modules/next/dist/docs/` | ✅ see below |

### The Next.js check the project asks for

`frontend/AGENTS.md` requires reading the bundled docs before writing code, because this
version differs from training data. The page uses `export const dynamic = "force-dynamic"`,
and **Next 16 removes `dynamic` when Cache Components is enabled**
(`route-segment-config/index.md`: *"v16.0.0 — `dynamic`, `dynamicParams`, `revalidate` and
`fetchCache` removed when Cache Components is enabled"*). `next.config.ts` does **not**
enable `cacheComponents`, and 5+ existing routes use the same export, so the convention is
correct here. Checked rather than assumed.

## Auto-fixed

### 1. `gap-10` generated no CSS at all

**Found by the project's own `tests/spacing-scale.test.ts`**, which failed with
`components/settings/ranking-formula.tsx:49 gap-10`.

`styles/tokens.css` resets Tailwind's spacing multiplier and declares only 0, 1, 2, 3, 4,
6, 8, 12, 16, 20 and 30. There is no 10 — so `gap-10` emits **nothing**: no warning, no
error, just sections with no gap between them. The test's own docstring says seventy-nine
such classes had shipped before it existed.

**Fixed:** `gap-12`. A good reminder that this repo's guards catch things a reviewer would
not see in a diff.

### 2. Two architecture guards rejected the new surface file — correctly

`test_no_direct_writes.py` asserts an exact count of surface files, and
`test_digest_composition_separation.py` keeps a `REQUEST_MODULES` tuple. Both failed on the
new `*_api.py`. **This is the intended behaviour**, not an obstacle: *"a surface file that
is missing from this list is exempt from AD-5, and nothing else would catch it."*

**Fixed:** registered in both, count 25 → 26, each with a comment explaining why a
query-less, write-less read still belongs under AD-5 — *a read that is exempt today is a
write that is exempt tomorrow.*

### 3. A comment in my own code made a claim that was false

`_WEIGHTS`'s docstring said a key present in one table and not the other would be
*"a `KeyError` at import-adjacent time"*. **It would not.** The lookup happens inside the
view, so a mismatch would have been a **500 at request time** — on the page whose job is to
inspire confidence — and a weight with no label would have been worse still: silently
omitted, leaving a formula showing four terms that do not sum to the total printed beside
them.

**Fixed, and made true:** an explicit set-comparison now runs at **import time** and raises
with both offending keys named. The process does not start if the two tables disagree. The
comment now describes what the code does.

### 4. The component hard-coded the scale's size

`"○".repeat(5 - bucket.dots)` — not a weight, so the no-literal guard did not catch it, but
the same mistake in miniature: `5` is `RANKING_BUCKET_MAX`, a server fact, written into the
client.

**Fixed:** `buckets.length - bucket.dots`, derived from the served data.

## Judgment calls worth recording

| Decision | Why |
|---|---|
| The endpoint is behind `auth=current_user` though the formula is not personal | The surface is an authed settings screen (EXPERIENCE.md §2 row 9). An anonymous route to it would be a second, quieter way to reach settings. |
| Weights cross the wire as **strings** | `Decimal("0.85")` is not the float `0.85`, and `domain/ranking.py` turns on that throughout. A JSON number would be a double in the browser, on the page that exists to let a reader check the arithmetic. |
| The component never sums the weights | A floating-point total rendered as `1.0000000000000002` would discredit the page it appears on. The total is the server's. |
| No worked example | An example score computed in JS floats could land on the wrong side of a boundary, on the one page that exists to prove the arithmetic. |
| The test fixture uses fake weights (0.41 / 0.23 / …) | A component that ignored its props and printed the real constants would pass a fixture that used the real ones. |
| The nav row says "Privacy" with the description "How your Pulse is ranked." | Your call at the checkpoint. The route matches the spec'd IA; the description is honest about the one section that exists. |

## Open after this run — needs your call

### The backend lint gate is red on pre-existing code

`ruff check .` fails:

```
F401 `pytest` imported but unused
  --> tests/identity/test_email_change_mails.py:12:8
```

**Verified pre-existing**: the file is unmodified by this run and the error is present at
HEAD, introduced by commit `d181391` (run 043, "the two letters an email change owes").
`make lint-backend` runs `ruff check .`, so **the repo's backend lint gate is currently
failing on committed code**.

**Not fixed**, because it is a one-line change in another work item's file and this run had
no mandate over it — the same reasoning that left `fr22-published-formula`'s bullet alone in
run 046. But it means neither this run nor any other can honestly report `make lint-backend`
green until it is dealt with. It is a one-line deletion.

### Still unowned

| Item | Note |
|---|---|
| 3 `test_preferences_api.py` failures | Fourth consecutive run observing them (041, 046, 047, 048). No work item owns them. |
| The rest of `/settings/privacy` | Data inventory, deletion, training opt-out, A-14 geo-IP toggle, A-13 amendment-history timeline, sources mirror. Export already exists on `/settings/account`, so this starts as a reconciliation. |
| MinIO | Now blocks `make client`, not just `make up`. Worked around with `BLOB_ADAPTER=memory`. |

## Findings Summary

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | `gap-10` emitted no CSS — silent layout bug | Medium | **Auto-fixed** |
| 2 | New surface file absent from two AD-5 registries | By design | **Auto-fixed** |
| 3 | `_WEIGHTS` comment claimed an import-time check that did not exist | Medium | **Auto-fixed** — the check now exists |
| 4 | Component hard-coded the scale size `5` | Low | **Auto-fixed** |
| 5 | Backend lint gate red at HEAD (`F401`, another item's file) | Medium | **Awaiting your call** |

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-048*
