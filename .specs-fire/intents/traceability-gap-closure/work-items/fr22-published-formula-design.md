---
work_item: fr22-published-formula
intent: traceability-gap-closure
created: 2026-11-19
mode: validate
checkpoint_1: approved
---

# Design: FR-22 publishes a formula the product does not compute

## Summary

The work item's central premise is **false**, and the real defect is different.

The PRD **does** carry an amendment publishing the five-term as-built formula — `prd.md:751`,
inside FR-22, dated 2026-11-11, citing `docs/adr/ADR-0025.md`, which exists and is Accepted.
It landed in commit `59df1a9`, **before** the 2026-11-17 doc-trace pass that wrote this work
item. It was missed, not absent.

What is actually wrong is that **the amendment reuses an ID that already belongs to a
different amendment** (A-10, the Browse surface, 2026-09-06), that **FR-22 now contradicts
itself** about whether the weights changed, and that **two cross-references are stale**.

This design ratifies the five-term formula, re-mints the ranking amendment as **A-25**,
reconciles FR-22 internally, and fixes the ledger. No production code changes.

## Scope

**In Scope:**

- Re-minting the ranking amendment from the colliding A-10 to **A-25**
- Reconciling FR-22's weights table with its own amendment block
- Updating `[ASSUMPTION-11]` and the PRD frontmatter amendment list
- Updating `ADR-0025.md`'s `Amends:` citation
- Tagging EXPERIENCE.md's as-built formula note with A-25
- Correcting the Amendment Ledger: A-3 superseded, A-10 scoped to Browse, A-25 added
- Verifying the bucket boundaries still partition the five-term range
- *(Optional)* extending `test_constants.py` to pin the PRD's weights alongside the ADR's

**Out of Scope:**

- Changing `domain/ranking.py`, `shared/constants.py`, or any weight value
- Browse's A-10 and its propagation across DESIGN.md, EXPERIENCE.md and 3 mockups
- Building `/settings/privacy` — split to its own work item (`settings-privacy-ranking-transparency`)
- `timeline-why-this-tag`, which holds **A-24**

## What the documents actually say

### The amendment exists

`prd.md:751`, within FR-22:

> **Amendment A-10 (2026-11-11):** The **MVP weights are unchanged** — `w1` 0.40 / `w2` 0.25 /
> `w3` 0.20 / `w4` 0.15 still stand as published above. What this amendment records is
> **which term the implementation evaluates for each published component** …

followed by the five-term expression verbatim, a per-term rationale, and a pointer to
ADR-0025. `docs/adr/ADR-0025.md` is Accepted, dated 2026-11-11, and its `Amends:` line names
FR-22 "via PRD **Amendment A-10**".

There is also an existing guardrail: `backend/tests/shared/test_constants.py:166`
(`test_the_ranking_weights_have_an_amendment_that_says_so`) opens the ADR named by
`RANKING_WEIGHTS_AMENDMENT` and asserts every weight constant appears in it — so "bump the
weight and update the string" does not get past CI.

### Defect 1 — the amendment ID collides

| ID | What it is | Where it appears | Date |
|---|---|---|---|
| **A-10** | Browse surface, 6th authed route | EXPERIENCE.md (§4 Sidenav, Browse glyph, `g b` shortcut), DESIGN.md, 3 mockups, Amendment Ledger | 2026-09-06 |
| **A-10** | The ranking formula amendment | `prd.md:751`; ADR-0025's `Amends:` line | 2026-11-11 |

Two different amendments, one ID, two months apart.

The Amendment Ledger scores `A-10 (Browse, 6th authed route) | PRD, DESIGN, EXPERIENCE,
3 mockups | Consistent` — it is scoring the **Browse** amendment and reading clean straight
over the collision. For a convention whose entire purpose is that an ID appears in every
document a change touches, a **reused** ID is worse than a missing tag: a missing tag reads
as a gap, while a reused one makes the ledger confidently wrong.

**This is the defect this work item should be remembered for.**

### Defect 2 — FR-22 contradicts itself

`prd.md:717-723` still publishes the locked weights table:

| Weight | Component | Value |
|---|---|---|
| `w1` | preference_graph_match | 0.40 |
| `w2` | source_reliability | 0.25 |
| `w3` | recency_fit | 0.20 |
| `w4` | novelty_vs_exploration | 0.15 |

The amendment block two paragraphs below asserts "**MVP weights are unchanged** … w1 0.40
… still stand as published above", and then implements `interest_overlap` at **0.35**,
explaining the 0.05 as slack absorbed from the dropped `novelty_vs_exploration`.

Both claims live inside FR-22. A reader computing a score by hand from the table gets a
different number than one computing from the amendment — which is exactly the
"arithmetically checkable while producing a different number from the one on the card"
failure `domain/ranking.py`'s docstring argues against at length. The module is right; the
PRD's presentation is what has not caught up.

### Defect 3 — two stale cross-references

- `[ASSUMPTION-11]` (`prd.md:1308`) still reads "From Amendment **A-3** / FR-22 — Confidence
  Pulse formula weights (`w1=0.40, w2=0.25, w3=0.20, w4=0.15`) are locked at MVP launch."
  Never updated when the 2026-11-11 amendment landed.
- The PRD frontmatter's `amendments:` list names A-1…A-8 (merged), A-9 and A-23. The ranking
  amendment is absent from it entirely.

### Defect 4 — FR-22's transparency surface does not exist

`frontend/app/settings/` holds `account`, `calendars`, `collections`, `digest`, `general`,
`profile`, `quiet-hours`, `reminders`, `sources` and `taste`. **There is no `privacy`
route**, and a search across `frontend/` finds nothing that renders a formula, a weights
table or an amendment history.

Two consequences, and they pull in opposite directions:

- **Not urgent.** The work item named "a user is shown a formula they cannot reproduce" as
  the thing that would make this urgent rather than tidy. No user is shown any formula, so
  the urgent case does not apply.
- **A larger gap than this item can hold.** FR-22's own testable consequence — *"Settings →
  Privacy → 'Ranking algorithm version' shows the current weights and the last-amendment
  date"* — is entirely unbuilt, as are FR-21's privacy copy and A-13's amendment-history
  timeline. Acceptance criterion 4 cannot be met without building a route.

**Decision: split it.** A new work item,
`settings-privacy-ranking-transparency`, is created in the same intent. Folding a route
build into a documentation reconciliation would hide a surface-sized gap inside a docs fix.

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Which formula is canonical? | **The five-term as-built formula** | Already decided and documented in ADR-0025 and the PRD's amendment block. `domain/ranking.py`'s reasoning for refusing inert weights is sound and should be ratified, not reopened. |
| What is the primary defect? | **The A-10 ID collision** | Not the "missing amendment" the work item describes. The amendment is present; its ID is taken. |
| Which A-10 moves? | **The ranking one, to A-25** | Browse's A-10 is correctly propagated across PRD, DESIGN.md, EXPERIENCE.md and 3 mockups. The ranking amendment is newer and cited in exactly two places, so it is far cheaper and lower-risk to move. |
| Why A-25, not A-24? | **A-24 is allocated to `timeline-why-this-tag`** | Approved at its Checkpoint 1 on the same day. The two must not collide — which would be a poor outcome for the item that exists to fix a collision. |
| FR-22's weights table | **Reconciled: published component → implemented term → weight** | The table and the amendment cannot disagree inside one requirement. The published components stay visible so the lineage is legible; the implemented term and its actual weight sit beside them. |
| Bucket boundaries (AC 3) | **Verify; expect no change** | Five weights sum to `RANKING_WEIGHT_SUM == 1.00` and every term is normalised to [0,1], so the score range is still [0,1] and the published boundaries still partition it. The *distribution* shifted — see the note below — but a boundary re-cut is a product decision with no evidence behind it yet. |
| `/settings/privacy` | **Out of scope; new work item created** | A new authed route plus a read API is not a documentation fix. |
| Amendment Ledger A-3 | **Recorded as superseded by A-25** | AC 5's second branch. A-3 locked the four published weights; A-25 supersedes that lock. Tagging A-3 onto the as-built sections would assert a revision they do not implement — the exact thing the ledger's own note warns against. |
| Any production code change? | **None** | Optionally one test. No weight moves, no module changes. |

### A note on the launch-time distribution

Worth recording, because someone will ask whether 5 dots is reachable.

At launch every source sits at or near the 0.50 beta-binomial prior (`reliability_score(0, 0)`),
since FR-16's recompute needs 30 observations. A maximally favourable card — full interest
overlap, same city, start within the day, high extraction confidence — scores:

```
0.35 × 1.00  +  0.20 × 1.00  +  0.10 × 1.00  +  0.10 × 0.90  +  0.25 × 0.50
   = 0.35    +     0.20      +     0.10      +     0.09      +     0.125
   ≈ 0.865
```

against `RANKING_BUCKET_5 = 0.85`. **Five dots is reachable, but only just**, and only
while reliability sits at the prior. As sources differentiate the ceiling rises. This is a
consequence of the published boundaries meeting the implemented weights, not a defect, and
it is recorded rather than acted on.

## Technical Approach

### Architecture

```
  The amendment chain, as it should read after this work item:

    PRD FR-22 §705
      ├─ Formula (published, 4 named components) ....... unchanged
      ├─ Weights table ................................. RECONCILED
      │     published component → implemented term → weight
      ├─ Bucket boundaries ............................. unchanged, verified
      └─ Amendment A-25 (was A-10) ..................... RE-MINTED
            │  publishes the 5-term implemented expression
            └─> docs/adr/ADR-0025.md
                   Amends: FR-22 via PRD Amendment A-25   ← citation fixed
                   │
                   └─> pinned by backend/tests/shared/test_constants.py
                         RANKING_WEIGHTS_AMENDMENT == "ADR-0025"
                         every RANKING_WEIGHT_* appears in the ADR
                         (optional: and in the PRD's FR-22)

    PRD [ASSUMPTION-11] ... cites A-25, not A-3          ← fixed
    PRD frontmatter ....... A-25 listed                  ← added
    EXPERIENCE.md ......... as-built note tagged A-25    ← added
    TRACEABILITY.md ledger
      ├─ A-3  ... superseded by A-25                     ← fixed
      ├─ A-10 ... scoped to Browse only                  ← fixed
      └─ A-25 ... new row                                ← added

  Untouched, deliberately:
    Browse's A-10 across DESIGN.md, EXPERIENCE.md and 3 mockups
    shared/constants.py RANKING_WEIGHT_* — no value moves
    domain/ranking.py — its reasoning is being ratified, not revised
```

### API Changes

None.

### Database Changes

None.

## Affected Files

| File | Action | Purpose |
|------|--------|---------|
| `…/prds/prd-EventPulse24-2026-08-19/prd.md` (FR-22, §705-760) | Modify | Re-mint the amendment block as A-25; reconcile the weights table against it |
| `…/prd.md` `[ASSUMPTION-11]` (line ~1308) | Modify | Cite A-25 rather than A-3 |
| `…/prd.md` frontmatter `amendments:` | Modify | Add the A-25 line |
| `docs/adr/ADR-0025.md` | Modify | `Amends: … via PRD Amendment A-10` → A-25 |
| `…/ux-designs/…/EXPERIENCE.md` | Modify | Tag the as-built formula note (pinned to ADR-0025) with A-25 |
| `…/traceability/TRACEABILITY.md` | Modify | Ledger: A-3 superseded, A-10 scoped to Browse, A-25 added |
| `backend/tests/shared/test_constants.py` | Modify *(optional)* | Extend the existing ADR assertion to the PRD's FR-22 weights |
| `.specs-fire/intents/traceability-gap-closure/work-items/settings-privacy-ranking-transparency.md` | Create | FR-22's unbuilt transparency surface, tracked |

## Integration Points

| System | Type | Purpose |
|--------|------|---------|
| `prd.md` FR-22 | Spec amendment | The document FR-22 names as the source of the published formula |
| `docs/adr/ADR-0025.md` | ADR citation | The record the weights constant points at |
| `backend/tests/shared/test_constants.py` | CI guardrail | Already fails if a weight moves without the ADR moving with it |
| `TRACEABILITY.md` Amendment Ledger | Ledger correction | Where the collision currently reads as "Consistent" |

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Renumbering breaks a live reference to the ranking A-10 | Medium | Only two exist — `prd.md:751` and ADR-0025's `Amends:` line. Both are in the checklist, and a grep verifies no third. |
| A-25 collides with something not yet seen | Medium | An explicit grep for `A-24` and `A-25` across `_bmad-output/` and `docs/` runs **before** any edit. The highest ID found today is A-23. |
| Browse's A-10 is edited by mistake | **High** | Browse's A-10 is correct across five documents and three mockups. Edits are confined to FR-22, `[ASSUMPTION-11]`, the frontmatter, ADR-0025 and the ledger — and the ledger edit *scopes* the A-10 row rather than renaming it. |
| Reconciling the weights table reads as changing the weights | Medium | No weight value moves. The table gains a column; the amendment's "the weights are unchanged" claim is restated as "the published components are unchanged; here is the term each is evaluated as, and at what weight". |
| The optional test hard-codes a path that later moves | Low | It is optional, and the ADR assertion already covers weight drift. The PRD check is belt-and-braces. |
| `/settings/privacy` stays forgotten | Medium | A work item is **created**, not merely mentioned. |

## Implementation Checklist

- [ ] Grep `A-24` and `A-25` across `_bmad-output/` and `docs/` to confirm both are free before editing
- [ ] Re-mint `prd.md:751`'s amendment block as **Amendment A-25**, preserving its text and per-term rationale
- [ ] Reconcile FR-22's weights table: published component → implemented term → weight, so the table and the amendment agree
- [ ] Update `[ASSUMPTION-11]` to cite A-25 rather than A-3
- [ ] Add A-25 to the PRD frontmatter `amendments:` list
- [ ] Update `ADR-0025.md`'s `Amends:` line to name PRD Amendment A-25
- [ ] Tag EXPERIENCE.md's as-built formula note with A-25
- [ ] Amendment Ledger: A-3 recorded as **superseded by A-25**; the A-10 row scoped explicitly to Browse; a new A-25 row added
- [ ] Verify the bucket boundaries still partition [0,1]; record the ≈0.865 launch ceiling as a note, not a change
- [ ] Grep for any remaining reference to the ranking amendment as "A-10"
- [ ] *(Optional)* extend `test_constants.py` to assert the PRD's FR-22 carries the same five weights as the constants
- [ ] Confirm no diff under `frontend/`, and none under `backend/` beyond the optional test

---
*Generated by specs.md - fabriqa.ai FIRE Flow | Checkpoint 1 approved: 2026-11-19*
