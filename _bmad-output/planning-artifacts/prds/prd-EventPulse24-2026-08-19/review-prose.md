# PRD Prose Review — EventPulse24

## Voice Consistency (§13.2 benchmark)

**Mostly coherent.** The PRD maintains the "calm, knowledgeable, restrained" voice in the bulk of the prose. Section 13.2 explicitly bans superlatives ("amazing," "incredible," "must-see"), exclamation points, and condescension; the document is largely free of these.

**Exceptions — places where the voice slips toward aspirational / brochure:**

- §1 Vision: "The aspiration is to be the **'Headspace of events'** — synonymous with calm event intelligence." This is aspirational marketing language, not testable PRD prose. It also recurs in FR-46 ("Realizes the brief's 'Headspace of events' ambition") and §13.1 ("Reference: Headspace"). The phrase is a tagline, not a requirement. If kept, it should be confined to §13.1 / §15 brand sections — not invoked inside FR behavioral notes.
- §1: "That misalignment is the moat." Repeats as a "Star principle" in §5.1 and again in §15.2. The metaphor itself is fine; the repetition across three sections adds no information.
- §1 "The contrarian bet — and the cost of the status quo" — heading style is more magazine-feature than PRD. "The cost of the status quo" is rhetorical framing, not engineering prose.
- §1: "47 unread event newsletters," "47 WhatsApp messages" — these numbers recur in §2.1 (Social JTBD) and UJ-1 / UJ-6 climax lines. They are memorable but borderline marketing-rhetoric; a PRD doesn't typically dramatize.
- §6.1: "**Total:** 30 MVP FRs ... 6 User Journeys, 13 Open Questions, 10 Assumptions, 9 Success Metrics + 5 Counter-metrics, 12 Risks." — This is a recap that's more "feature count brag" than PRD substance. Acceptable, but verges on a dashboard summary.
- §17 Risk #11: "Trust-eroding failure is the only failure mode that ends the company." — Slightly dramatic; "ends the company" is investor-deck prose.

**Hedging-language inconsistency:** §13.2 demands plain, direct language. The PRD mostly delivers this in FR definitions (where it is exemplary), but drifts in §1 (Vision), §12 (Why Now), and §13.1 (Reference brands). The drift is not catastrophic; it's a tonal unevenness — operational sections read like a PRD, strategic sections read like a positioning memo.

---

## Concision

**Generally strong.** FR sections are tight; each FR has Description, Consequences (testable), Out of Scope, optional Notes — this structure is exemplary and the prose within is disciplined.

**Issues:**

### Throat-clearing and filler

- §0 Document Purpose: "Sections build on those artifacts instead of duplicating them — depth and rationale that does not earn its place in the PRD-main narrative lives in `addendum.md`." — Meta-narrative about document structure that doesn't help the reader.
- §2.3 UJ-1: "**Persona + context:**" / "**Entry state:**" / "**Climax:**" / "**Resolution:**" / "**Edge case:**" — labels are fine; the **Climax** label is a storytelling artifact borrowed from screenwriting. "Climax" in a PRD is throat-clearing.
- §4 Features preamble: "Features grouped into coherent behavioral clusters. FRs globally numbered and stable. Each FR is testable." — Three sentences asserting qualities already evident from the document structure. Could collapse to one.
- §13.1 "**Principles:**" — list is fine, but "**No urgency badges.** No 'trending now,' no 'limited slots,' no countdown timers." reads as marketing-deck bullet; could be more declarative ("Urgency badges are excluded.")

### Redundancy across adjacent sections

- The "calm > engagement" principle is restated: §1 (twice), §5 Non-Goals (multiple bullets), §5.1 Locked Product Principles (table), §13.1 Anti-patterns, §15.2 ("That misalignment is the moat"). Five restatements. PRD discipline would consolidate to §5.1 and reference elsewhere.
- The "3 cards max" rule appears in: §1, §3 (Glossary — Pulse Digest), §4.2 (FR-5, FR-5 Notes), §5.1 (Locked Product Principles), §6.2 Out of Scope, §13.1 (Principles), §7.2 (Counter-metrics reference). Six restatements.
- "Why this?" appears as FR-21, FR-24, Glossary, Locked Principles, UJ-4, Counter-metric SM-4, Counter-metric SM-8 — seven restatements. Some are necessary cross-references; some duplicate.
- §6.1 has the **Architectural** bullet twice (lines 744 and 748). This is a clear duplication bug.
- §3 Glossary entry for Pulse Digest and §4.2 FR-5 Description both describe the same surface in nearly identical language. One could reference the other.
- §17 Risk #11 and §10.2 Privacy both describe "no PII in logs" / GDPR deletion. Could be cross-referenced.

### Over-long sentences

- §1 Vision, opening: "EventPulse24 is the calm intelligence layer above all event sources. In a world where users are drowning in events they didn't ask about, missing events they care about, and exhausted by notifications that don't respect their attention, EventPulse24 is the single, trustworthy surface that uses AI to surface the small number of events that actually matter to each user, and delivers them via context-aware, multi-tier reminders that *reduce* notification volume instead of adding to it." — 89 words. The clause "uses AI to surface the small number of events that actually matter" is hedged by "actually" — vague intensifier that doesn't earn its place. The sentence would be cleaner broken in two.
- §12 Why Now #2: "Consumers have disabled notifications on most event apps. The 'calm' positioning is a *demand* signal, not just a marketing choice. Industry-average 5–15 notifications/day is the problem EventPulse24 solves." — Fine, but "the problem EventPulse24 solves" is marketing-tagline syntax.
- §17 Risk #5 Mitigation: "Pulse Digest is a feature, calm is the brand" — aphoristic, but aphorisms in a risk register read as marketing.

---

## Specificity

**Excellent overall.** This is the PRD's strongest prose dimension. Concrete numbers, dates, thresholds, and p95 latency targets appear throughout:

- NFRs: "<500ms p95 (cached); <3s p95 (cold)" — §11.1
- Extraction cost: "<$0.005 per event blended" — FR-14
- AI cost per MAU: "<$0.50/month" — FR-29, SM-C5
- Dedup: "cosine ≥0.85" auto-merge ≥0.95 — FR-15
- Source freshness: "within 4 hours" — §10.4
- Email deliverability: "bounce rate <2%, spam complaint rate <0.1%" — §10.4
- MAU targets: "100K by Month 6, 1M by Month 18" — SM-10
- Pricing range: "$4.99–$7.99/mo" — §15.2 (tagged as illustrative)
- Decision gates: Month 3, Month 9, Month 18 — §7.4
- SM-1: "<30 seconds" — concrete
- SM-2: ">60%" — concrete

**Vague claims to flag (per the reviewer's brief):**

- §2.1 Emotional JTBD: "Reduce the anxiety of 'I'm missing something'" — not measurable, but acceptable in a JTBD context. The PRD correctly moves metrics into §7.
- §2.1 Contextual JTBD: "One calm surface, on any device, that respects my time. Default everywhere = 'fewer, better.'" — "respects my time" is vague; acceptable as JTBD, but the "fewer, better" formula is a slogan.
- §4.6 Description: "Every recommendation must show its reasoning. 'Why this?' is a feature, not a hidden cost. Source transparency is the moat against the engagement-trap incumbents." — "the moat against" is figurative, not testable. Acceptable in vision prose, but it's a moat-claim recurring in §1, §13.1, §15.2, §17.
- §6.1 "Operational": "AI Cost Dashboard, Source Registry, ToS review log." — bullets without descriptions. Fine, but no NFRs attached.
- §13.1 "Whitespace over density." A Pulse Card uses ~40% of viewport real estate; the rest is breath." — "~40%" is vague. Either specify the actual layout target (e.g., "max-height: 280px on mobile, leaving ≥60% whitespace above fold") or remove the number.
- §17 Risk #4 Mitigation: "Phase 2 unlocks personalization" — Phase 2 is a phase, not a personalization engine. Slightly hand-wavy.
- §17 Risk #5 Likelihood: "Very High" — only risk rated Very High; no rationale provided for why this is higher than Risk #1 (Apple/Google AI) which is rated Medium. This is an asymmetry that should be explained or harmonized.
- §1 "Why now" point 1: "The technology bet has been won." — rhetorical; would be stronger with a date or named milestone.
- §1 point 2: "Industry-average 5–15 notifications/day" — sourced from research per addendum §A but no citation here. Acceptable for a PRD (sources in addendum).

**No instances of "fast," "scalable," "easy" as bare adjectives.** The PRD is disciplined about avoiding these.

---

## Marketing / Instructional Split

**Mostly the right side of the line, with leakage.**

- **PRD-like (testable, specific):** §4 (FRs), §6 (Scope), §7 (Metrics), §8 (Open Questions), §9 (Assumptions), §10 (Constraints), §11 (NFRs). These read as engineering specifications.
- **Marketing-like (aspirational, slogan-y):** §1 (Vision — strong brand framing), §12 (Why Now — rhetorical), §13.1 / §13.2 / §13.3 (Aesthetic & Tone — necessarily so), §15 (Monetization — "No ads. No commissions. No data sales." reads as manifesto).
- **Borderline:** §5 Non-Goals (each bullet is short and declarative; the cumulative effect is brand-defining rather than PRD-style), §17 Risks (the "Mitigation" cells sometimes read like strategy statements rather than mitigations).

The Vision section (§1) is the most brochure-flavored. Compare:

- §1: "the cost of the status quo is real: missed close-friend birthdays, 47 unread event newsletters, signal-to-noise ratios below 5%, group coordination that takes 47 WhatsApp messages, FOMO-driven attendance at events that weren't worth going to." — This is narrative copywriting.
- §11.1: "Pulse Digest composition: <500ms p95 (cached); <3s p95 (cold)." — This is PRD.

The PRD's overall voice tilts toward the engineering-PRD side in operational sections (where it must be) and toward brand-strategy prose in vision/scope sections (where it can afford to be). This is acceptable genre-mixing; the issue is only when brand language bleeds into FR-level prose. The Headspace tagline is the clearest leak.

---

## Tone Discipline (§13.2 rules)

§13.2 explicitly bans:
- "amazing," "incredible," "must-see" — **none found anywhere.**
- Exclamation points — **none found.** (Verified by scan.)
- Superlatives and condescension — **mostly absent.** One borderline: §5 Non-Goals "The metric I'd be optimizing for (engagement) is the metric my user hates." — first-person singular is unusual in a PRD and slightly editorial.

**Tone-positive observations:**
- The PRD uses contractions sparingly, prefers declarative sentences, avoids rhetorical questions.
- The locked-principle table in §5.1 is well-disciplined.
- The anti-patterns list in §13.3 is consistent with §13.2 voice.

**Tone slips:**
- "synonymous with" (§1) — aspirational
- "the only failure mode that ends the company" (§17 R11) — hyperbolic
- "The technology bet has been won." (§12) — rhetorical
- "Realizes the brief's 'Headspace of events' ambition." (FR-46 Notes) — brand-ambition inside an FR Note

---

## Specific Recommendations (Not Rewrites)

1. **Consolidate "calm > engagement" principle.** Pick one canonical statement (§5.1 table is the natural home) and cross-reference from §1, §13.1, §15.2. Remove the third repetition of "That misalignment is the moat."
2. **Remove the duplicate "Architectural" bullet in §6.1** (literal copy-paste duplication at lines 744 and 748).
3. **Confine the "Headspace of events" tagline to §13.1 / §15 brand sections.** Do not invoke it inside FR Notes or behavioral notes.
4. **Replace "Climax" label in UJ-1 through UJ-6 with "Outcome" or "Result."** "Climax" is screenwriting vocabulary; PRDs use Result/Outcome.
5. **Tighten §0 Document Purpose.** The document-purposes paragraph is meta; the FR-numbering/Assumption-tagging rules can move to a one-line methodology note.
6. **Reconcile Risk #5 "Very High" with Risk #1 "Medium."** Either add a sentence explaining the asymmetry or harmonize the ratings.
7. **Drop "the cost of the status quo" framing in §1** or move it to §12 Why Now. It reads as magazine-feature heading in a PRD's opening.
8. **Replace "~40%" in §13.1** with an actual layout metric or remove the number.
9. **Cross-reference, don't restate.** Where §3 Glossary and §4.x describe the same concept, have one cite the other.
10. **Replace first-person in §5** ("The metric I'd be optimizing for...") with third-person ("Optimizing for engagement would directly conflict with the calm promise.")

---

## Summary

The PRD is generally well-disciplined in prose. Its FR sections are exemplary — specific, testable, well-structured. Its weaknesses are concentrated in §1 (Vision), §12 (Why Now), and the recurring "calm > engagement" / "Headspace" / "moat" repetitions that span the strategic sections. There is one literal copy-paste duplication (§6.1). The voice is mostly calm but has a brochure-tilt in vision/scope sections; this is acceptable genre-mixing provided it doesn't bleed into FR-level prose.

**No banned words found. No exclamation points. No "fast/scalable/easy" as bare adjectives.**

The PRD reads as a PRD — not a marketing brochure — in roughly 85% of its prose. The remaining 15% could be tightened.
