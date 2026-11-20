---
run: run-eventpulse24-048
work_item: settings-privacy-ranking-transparency
intent: traceability-gap-closure
generated: 2026-11-19
status: passed
---

# Test Report: FR-22's transparency promise has no surface

## Summary

| Category | Passed | Failed | Skipped |
|----------|--------|--------|---------|
| Backend | 7492 | 3 (pre-existing) | 7 |
| Frontend | 2698 | 0 | 0 |
| **Total** | **10190** | **3 (pre-existing)** | 7 |

Backend rose from 7477 to 7492 — the 8 new endpoint tests, the new constants test, and the
architecture guards re-counting the new surface file. Frontend rose by the 8 new component
tests.

## Acceptance Criteria Validation

- ✅ **`/settings/privacy` exists as an authed route and is reachable from the Settings navigation** — `frontend/app/settings/privacy/page.tsx`, with a `Privacy` row in `SETTINGS_SECTIONS`. `tests/settings-routes.test.ts` already asserts that every section resolves to a real `page.tsx` and that every route under `app/settings` is listed or is a redirect; it passes.
- ✅ **It shows the five-term implemented formula with each term's weight** — served by `GET /api/settings/ranking`, rendered by `RankingFormula`.
- ✅ **It shows FR-22's bucket boundaries and states that an exact boundary falls to the lower bucket** — all five steps including the 1-dot floor, plus *"A score that lands exactly on a boundary takes the lower band."*
- ✅ **It shows the ranking algorithm version: the amendment ID and date** — `A-25`, record `ADR-0025`, last changed `2026-11-19`, from the two new constants.
- ✅ **The weights are served by the backend from `shared.constants`, never hard-coded in the frontend** — enforced by a test that reads the component's own source (below).
- ✅ **A contract test covers the new read endpoint, and `make client` regenerates the client** — `test_ranking_transparency_api.py` (8 tests); `make client` run, producing **249 insertions and 0 deletions** in the generated files; `tests/api/test_contract.py` passes.
- ✅ **The amendment ID shown matches the one `fr22-published-formula` minted (A-25), not the colliding A-10** — `RANKING_WEIGHTS_AMENDMENT_ID == "A-25"`, pinned, and asserted to appear in **both** ADR-0025 and the PRD's FR-22 section.

## Tests Written

### Backend — `tests/personalization/test_ranking_transparency_api.py` (8)

The five published terms are the constants themselves (not literals restated in the test —
that would be a third copy free to drift); each label is the server's vocabulary; every
weight crosses the wire as a **string**; the weights sum to 1.00; the scale has all five
steps including its floor; the boundary rule is published; the amendment is the PRD's with
the ADR beside it and a date; **an anonymous caller is refused**.

### Backend — `tests/shared/test_constants.py` (+1, and two assertions extended)

`test_the_amendment_id_and_date_are_pinned` pins the two new constants. The existing ADR
check and the PRD check added in run 047 both now also assert the **amendment ID** appears
in their document — so moving the id in the docs without the constant, or the reverse,
fails CI. The page cannot show a stale amendment silently.

### Frontend — `components/settings/ranking-formula.test.tsx` (8)

Renders every served term, label and weight; shows the server's total rather than summing;
all five scale steps; the boundary sentence; per-band screen-reader names (the dots are
decorative glyphs); the amendment block.

**The fixture deliberately does not use the real weights.** It uses 0.41 / 0.23 / 0.19 /
0.11 / 0.06 — arbitrary values summing to 1.00 — because a component that ignored its props
and printed the real constants would pass a fixture that used them.

**And the assertion the file exists for:** `contains no weight literal — every number is
served` reads the component's own source, strips doc comments, and fails if any `0.<digits>`
remains. A hard-coded weights table would be exactly FR-22's failure mode, and every render
test above would still pass.

### Both new guards were probed by mutation

| Mutation | Result |
|---|---|
| `const FALLBACK_WEIGHT = 0.35;` added to `ranking-formula.tsx` | **FAILED** — `expected [ '0.35' ] to deeply equal []` |
| Component restored | 8 passed |
| `0.35` → `0.99` in the PRD's FR-22 section (run 047's test) | **FAILED** |

## Verification performed

| Check | Result |
|---|---|
| Backend suite | **7492 passed**, 3 pre-existing failures, 7 skipped |
| Frontend suite | **2698 passed**, 165 files |
| `make client` | regenerated; **249 insertions, 0 deletions** — purely additive |
| `tests/api/test_contract.py` | passes — committed schema matches the live API |
| `ruff format --check .` | 691 files already formatted |
| `lint-imports` | **20 contracts kept, 0 broken** |
| ESLint on the six changed/added frontend files | clean |
| `tests/settings-routes.test.ts` | passes — the route is reachable |

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| `gap-10` on the new component generated **no CSS at all** | **Medium** | **Fixed** — `tests/spacing-scale.test.ts` caught it. `styles/tokens.css` declares only 0/1/2/3/4/6/8/12/16/20/30, so an off-scale step fails silently: no warning, no error, just a layout with no gap. Changed to `gap-12`. The project's own guard worked exactly as its docstring promises. |
| Two architecture guards failed on the new `*_api.py` | **By design** | **Fixed** — `test_no_direct_writes.py` counts surface files (25 → 26) and `test_digest_composition_separation.py` keeps a `REQUEST_MODULES` tuple. Both are deliberate registries: *"a surface file missing from this list is exempt from AD-5, and nothing else would catch it."* The new module is registered in both, with a comment on why a query-less read still belongs under AD-5. |
| `make client` is blocked by the MinIO config error | **Environment** | **Worked around** — `make client` fails with `eventpulse.E008` because the blob store is unconfigured. Ran as `BLOB_ADAPTER=memory make client`, which the error's own hint suggests and which is correct for a schema export that touches no blob. **Worth knowing: the MinIO block now stops schema regeneration, not just `make up`.** |
| `ruff check .` fails on `tests/identity/test_email_change_mails.py` — `F401 pytest imported but unused` | **Pre-existing, and CI is red** | **NOT fixed — needs your call.** Verified unmodified by this run and present at HEAD, introduced by commit `d181391` (run 043). `make lint-backend` runs `ruff check .`, so **the backend lint gate is currently failing on committed code**. It is a one-line fix in another work item's file. |
| 3 `tests/delivery/test_preferences_api.py` failures | Pre-existing | **Not caused by this run.** Fourth consecutive run (041, 046, 047, 048). Still owned by no work item. |

## Ready for Completion

- [x] All tests passing (3 failures pre-existing and verified unrelated)
- [x] Coverage target met — every new surface has a test; both new guards probed by mutation
- [x] All acceptance criteria validated (7 of 7)
- [ ] No critical issues open — **one open:** the repo's backend lint gate is red on pre-existing code

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-048*
