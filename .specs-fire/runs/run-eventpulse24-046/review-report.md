---
run: run-eventpulse24-046
work_item: timeline-why-this-tag
intent: traceability-gap-closure
generated: 2026-11-19
status: reviewed
---

# Review Report: The Timeline block's Why-this tag — deferred, with the reason

## Scope of review

No code was written, so the usual categories (naming, error handling, security, query
cost) have nothing to act on. The review instead covered what this run actually produced:
**three document edits**, judged on structural validity, internal consistency, and whether
a later reader is left with a correct and complete picture.

Files reviewed:

| File | Change |
|---|---|
| `EXPERIENCE.md` | §13 Density Modes row (line 1107); `updated:` date; A-24 entry prepended to `updated_note` |
| `TRACEABILITY.md` | FR-32 row (line 197); the "Open items that are decisions, not work" bullet |
| `work-items/timeline-why-this-tag.md` | frontmatter `status: pending` → `completed` |

## Structural checks

| Check | Result |
|---|---|
| EXPERIENCE.md frontmatter parses as YAML | ✅ `updated: 2026-11-19`; `updated_note` is a single double-quoted scalar |
| Inner quotes in `updated_note` escaped | ✅ 0 unescaped `"` in the scalar body |
| §13 Density Modes table still well-formed | ✅ every row 1099–1107 carries 4 pipes, matching the header |
| TRACEABILITY.md FR-32 row still well-formed | ✅ pipe count unchanged |
| Amendment ID A-24 unique | ✅ `grep -rno "A-24" _bmad-output docs` → no other occurrence |
| Work item frontmatter matches state.yaml | ✅ both `completed` |

## Auto-fixed

### 1. The FR-32 matrix row was disproportionately long and duplicated the Open-items bullet

**Found:** the first edit put the entire argument — the `nearby`/`saved` reasoning, the
cost correction and the AD-10 correction — into the FR-32 cell of the Section C matrix.
At ~1,100 characters it was roughly three times the longest neighbouring row, and it
repeated verbatim what the "Open items" section said forty lines below.

**Why it mattered:** Section C is a scannable matrix. A row that carries a full argument
stops the table being scannable, and two copies of the same reasoning in one document drift
apart the moment one is edited.

**Fixed:** the row now states the outcome (O-2 closed, withdrawn by A-24, location only,
now the spec's position) and points at *Open items* for the reasoning. 551 characters,
in line with FR-29's 382 and FR-49's 246. The argument lives in exactly one place.

**Re-verified after the fix:** pipe count unchanged, no test affected (none reads this file).

## Suggestions — raised for confirmation

### 1. §13's trust-signal anti-pattern sits two lines below the amended row and now reads as a contradiction

**Severity:** medium — correctness of the document, not of the decision.

Immediately after the amended Density Modes table, §13 says:

> **Anti-pattern: progressive disclosure that hides trust signals**
>
> Adaptive density must not hide the trust signals (Why-this Tags, Confidence Pulse,
> Source Badge) at any density mode. The mobile default exposes all three; hover/focus/
> long-press *add* detail but never *remove* the trust signals.

A reader who reaches the amended row and then this paragraph sees A-24 removing a Why-this
Tag from a density mode — apparently the exact thing the rule forbids.

**It is not a violation**, and the design doc settled why: the rule's own wording scopes it
to the **Pulse Card** ("the mobile default exposes all three"). The Timeline block's default
shows *none* of the three at any density, so A-24 removes nothing — it withdraws a promise
before it was ever kept.

**That explanation currently lives only in the `updated_note` frontmatter**, ~1,100 lines
above. A reader working through §13 will likely never see it.

**Suggested fix:** one scoping sentence appended to the anti-pattern paragraph, e.g.
*"This rule governs the Pulse Card, whose default exposes all three signals. The Timeline
event-block carries none of the three at any density; Amendment A-24's withdrawal of its
hover tag therefore removes no trust signal, and the full Why-this breakdown remains on the
Detail Screen."*

**Confirmed by the user and applied.** A `**Scope (Amendment A-24):**` paragraph now sits
directly beneath the rule, stating that it governs the Pulse Card (whose default exposes
all three signals), that the Timeline event-block carries none of the three at any density,
that A-24 therefore removes no trust signal, and that the rule is **unchanged and
undiminished** for every surface that does expose them. The rule itself is not edited — it
is scoped. EXPERIENCE.md's frontmatter was re-verified as parsing after the edit.

### 2. The `fr22-published-formula` bullet directly below now contains a claim known to be false

**Severity:** low for this run — it is the next work item's scope.

The bullet immediately after the one this run rewrote says:

> What is missing is the PRD, which still publishes the four-term version as *"immutable
> post-launch"* — the document FR-22 names as the source of the published formula is the
> one that does not know it changed.

The approved design for `fr22-published-formula` establishes this is **false**: the PRD
carries the amendment at `prd.md:751`, dated 2026-11-11, citing ADR-0025. The real defect
is that it reuses amendment ID A-10.

**Left untouched on purpose.** It belongs to `fr22-published-formula`, whose design doc and
checklist already cover it. Correcting another work item's finding from inside this run
would blur which run changed what. Flagged here so it is not mistaken for an oversight.

## Not changed, and why

| Candidate | Decision |
|---|---|
| `TRACEABILITY.md:19` — narrates the 2026-11-17 regeneration raising both items as "decisions for a human" | **Left.** Accurate as history. Rewriting past narration to match a later decision is how a ledger stops being trustworthy. |
| The work item's `source` line in `state.yaml` | **Left.** "AD-10 bars personalization from the Event Fit" is true and records why the 2026-11-17 split happened. The clarification lives in the design doc. |
| A Surface Coverage Map row for A-24 | **Left absent.** That map is for amendments adding a surface and mockup. A-24 adds neither. |
| `domain/ranking.py`, `why_this_tags`, `RANKING_TAG_ORDER` | **Left.** Correct as they stand; this was about one surface's use of them. |

## Findings Summary

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | FR-32 matrix row over-long, duplicated the Open-items reasoning | Medium | **Auto-fixed** |
| 2 | §13 trust-signal anti-pattern reads as contradicting A-24 inline | Medium | **Fixed** (confirmed by user) |
| 3 | `fr22-published-formula` bullet carries a now-disproved claim | Low | **Deferred to that work item** |

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-046*
