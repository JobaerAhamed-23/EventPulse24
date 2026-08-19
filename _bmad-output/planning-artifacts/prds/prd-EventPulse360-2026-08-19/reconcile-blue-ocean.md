# Reconciliation: Blue Ocean Strategy vs PRD (EventPulse24)

**Date:** 2026-08-19
**Source:** `_bmad-output/blue-ocean-strategy-2026-08-19.md`
**PRD:** `prd-EventPulse360-2026-08-19/prd.md` (+ `addendum.md`)

---

## 1. Gaps — Blue Ocean insights NOT in PRD or Addendum

The PRD absorbs most Blue Ocean material, but the following strategic framing is missing or under-developed:

### G1. The explicit "Six Paths to Blue Ocean" framing is absent
Blue Ocean enumerates six paths (look across alternative industries, strategic groups, buyer chain, complementary offerings, functional-emotional, time) and ties each to a borrowable pattern (Headspace, Notion/Reclaim, Siri). The PRD inherits the *outputs* (calm, intelligence layer) but never names the *method*. A reader can't see why calm app patterns were borrowed. Recommendation: add a short paragraph to §1 Vision or §12 Why Now.

### G2. The "Two Ways to Create Blue Oceans" core principle is missing
Blue Ocean opens with: *"Blue Ocean is not about being better at the same game. It's about changing the game… simultaneously pursue differentiation AND low cost."* The PRD's §1 Vision lands on differentiation/calm but never states the **simultaneous low-cost claim**. This is the most quotable strategic insight from Blue Ocean and it does not appear in PRD prose.

### G3. The "Three Blue Ocean Options" decision (A/B/C) and the "Hybrid A" verdict
Blue Ocean presents Option A (Calm Consumer), Option B (Group Concierge), and Option C (B2B Intelligence) with pros/cons and recommends Hybrid A. The PRD's §4.9 names FR-42/43 for B2B and FR-34 for group — i.e., the *outputs* — but the **strategic rationale for rejecting C as primary and B as primary** is preserved only in the Addendum (B section), not in the main PRD. A future reader without the Addendum loses the "why we said no" rationale.

### G4. The "Calm App Adjacency" / "Headspace of Events" positioning is not named
Blue Ocean repeatedly anchors positioning against Headspace, Calm, Notion, Reclaim — the *visual references* that legitimize the brand. The PRD's §13.1 lists "Headspace (calm illustration), Notion (decision-friendly minimalism), Apple Calendar" as aesthetic references but never claims the **brand-positioning parallel** ("Headspace of events" is Blue Ocean's own language, line 130). The PRD inherits aesthetic alignment but loses the strategic positioning claim.

### G5. "Confidence Pulse" is misclassified in source vs PRD
Blue Ocean's CREATE table lists "Confidence Pulse" as a created factor (line 131). The Addendum A.7 traces it to "Design Thinking," not Blue Ocean. The PRD's FR-22 implements it as-is. **This is a sourcing discrepancy, not a strategic gap** — but the Addendum should reconcile the source attribution.

### G6. The "Pulse Streak (calm gamification)" and "Year in Pulse" creations are missing from PRD
Blue Ocean lists two CREATE factors with explicit retention/brand value:
- **Pulse Streak** (line 142): "Daily check-in streak; gentle, not punitive — Retention without FOMO"
- **Year in Pulse** (line 144): "Spotify-Wrapped-style annual event recap — Brand love + viral moment"

Neither appears in the PRD. FR-33 (Phase 2) mentions "I want more of this" controls, but retention mechanics like streaks and annual recaps are absent. If intended for MVP/Phase 2 they belong as FRs; if deferred they should be acknowledged.

### G7. The "Anti-Eventbrite" framing is implicit, not explicit
Blue Ocean's "Single Strategic Bet" (line 361): *"Be the anti-Eventbrite — the calm intelligence layer above all event sources."* The PRD positions against Eventbrite in §1 and §2.2 (non-users) but never uses the **"anti-Eventbrite"** formulation. This is the sharpest single-line brand position in Blue Ocean.

### G8. The "competitive set after EventPulse24 enters: None" claim
Blue Ocean line 376: *"The competitive set after EventPulse24 enters: None. By the time incumbents notice, we've built a data moat…"* The PRD's §17 Risk #5 (Incumbent copycat) **acknowledges this is contested** — Very High likelihood, Medium impact. The PRD is *more honest* than the Blue Ocean source. This is a deliberate softening, not a conflict.

---

## 2. Conflicts

No hard factual conflicts. Strategic tone differences:

### C1. Confidence in "uncontested market space"
- **Blue Ocean:** "Pure uncontested space" (line 179), "competitive set after EventPulse24 enters: None" (line 376)
- **PRD §17:** Lists incumbent copycat as "Very High likelihood" and Luma expansion as "Medium likelihood, High impact." PRD explicitly names Luma as the closest functional neighbor (Addendum D).

The PRD is **more honest about competition** than the Blue Ocean source. The PRD downgrades "no competition" claims to "brand + data moat to slow copycats." This is appropriate for a PRD but should be flagged as a tonal downgrade from the strategy doc.

### C2. "Calm apps" competitive adjacency understated in Blue Ocean
Blue Ocean treats Headspace, Calm, Notion as **borrowed patterns**, not competitors. The PRD §12 Why Now #3 acknowledges Apple Intelligence and Gemini in Calendar as competitors for the "smart calendar" lane. **The PRD correctly broadens the competitive set** beyond Blue Ocean's framing. No conflict — but Blue Ocean could be read as under-acknowledging platform-owner threat.

### C3. Blue Ocean lists "Pulse Streak" as CREATE; PRD never references
Not a contradiction — PRD may have consciously de-scoped — but the absence should be acknowledged in §6.2 Out of Scope for MVP.

---

## 3. Honest Assessment — Blue Ocean "Honest Moat" Table vs PRD §17 Risks

Blue Ocean's risk table (lines 336–344):

| Blue Ocean Risk | Likelihood | Impact | PRD §17 Coverage |
|---|---|---|---|
| Apple/Google add AI to native calendar | Medium | Critical | **Risk #1** — Medium / Critical — ✅ Match |
| AI inference costs explode | Medium | High | **Risk #2** — Medium / High — ✅ Match |
| Web crawling legally blocked | High | High | **Risk #3** — High / High — ✅ Match |
| Cold start unsolved | High | Critical | **Risk #4** — High / Critical — ✅ Match |
| Incumbent copycat | Very High | Medium | **Risk #5** — Very High / Medium — ✅ Match |
| User trust collapse | Medium | High | **NOT EXPLICITLY NAMED in §17** |

### Finding: Risk #6 (User trust collapse) is **missing** from PRD §17
Blue Ocean names "User trust collapse" with mitigation "Explainable AI, source transparency, kill-switch." The PRD's §17 omits this as a discrete risk row, though:
- FR-21–24 (Why-this Tags, Confidence Pulse, Source Badge, Why-this Breakdown) implement explainability
- §10.1 Compliance guardrails address trust via auditability
- §11.5 Accessibility is in place

The PRD **covers the mitigation** but doesn't name the risk. Add as Risk #11 (Medium likelihood, High impact) with mitigations: explainability FRs (21–24), Source Badge (FR-23), audited Source Registry (FR-13), Source Reliability Score (FR-16), kill-switch via Source ranking demotion (FR-16).

### Additional risks in Blue Ocean §"De-risk" section that PRD doesn't surface as discrete risks:
- **Moat erosion timeline** (12–18 months before platform copy) — absorbed into §12 Why Now, not §17
- **Unit economics failure** — covered by FR-29, SM-C5, but not §17
- **Brand/positioning being mis-claimed by incumbent** — implicit in Risk #5

### Verdict
PRD §17 is **substantially equivalent** to Blue Ocean's risk table, with one omission (user trust collapse as a discrete row) and one divergence (Luma Risk #6 added that Blue Ocean doesn't have — appropriate).

---

## Summary

**Strategic gaps the PRD should consider acknowledging:**
1. Two Ways to Create Blue Oceans principle (simultaneous differentiation + low cost)
2. Six Paths framing (method, not just outputs)
3. "Anti-Eventbrite" brand-positioning formulation
4. Pulse Streak + Year in Pulse (CREATEs that disappeared between docs)
5. User trust collapse as discrete risk (mitigations exist; risk unnamed)

**Conflicts:** None blocking. PRD is appropriately more honest than Blue Ocean on competition.

**Honest assessment:** §17 substantially mirrors Blue Ocean's risk table. Trust-collapse row should be added.