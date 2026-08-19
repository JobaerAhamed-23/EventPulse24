# PRD Quality Review — EventPulse24 (prd-EventPulse360-2026-08-19)

**Reviewer:** BMad PRD validator
**Reviewer rubric:** `/home/bs1346/Documents/P-project/EventPulse24/.agents/skills/bmad-prd/assets/prd-validation-checklist.md`
**Stakes declared by PRD:** Seed-stage public launch (full quantitative rigor expected).

---

## Overall verdict

This is a noticeably above-average consumer PRD — it has a thesis, a coherent MVP arc, and almost zero persona theater. The Vision and the "why now" are earned, not generic. The PRD is mostly decision-ready but has a handful of must-fix gates (inconsistent technical claims, a duplicated paragraph, and a structural conflict about MAU targets) before it can be handed to architecture or story creation without producing downstream bugs. Scope honesty and counter-metrics are strong; the cost discipline thread is unusually well-articulated for an MVP PRD.

**Strongest dimensions:** Strategic coherence, Scope honesty, Substance over theater.
**Weakest dimensions:** Decision-readiness (some real tensions are buried), Mechanical notes (one duplicated block, a count inconsistency, and an unresolved target conflict).

---

## 1. Decision-readiness — **adequate**

The PRD surfaces many real trade-offs (web-first vs. native mobile, single LLM vendor vs. multi-model, 3 cards vs. adaptive, free-tier save caps) and the rejected-alternatives matrix in the addendum is unusually honest. Decisions are usually stated as decisions.

Where it falls short:

- **Real but soft-shoed tensions.** The "no reviews" decision in §14.3 is asserted with a long rationale. The bigger internal tension — that the Source-Badge transparency logic depends on having real "verified" sources, which depends on partnerships that may not land — is left to Open Q #1 without a `[NOTE FOR PM]`.
- **Phase 2/3 features present a known risk.** FR-32, FR-33, FR-44, FR-45 carry behavioral notes that double as architectural decisions, but they are not phrased as decisions. Downstream architecture will treat them as "FRs already decided" when they are really sketches.
- **Open Questions are mostly genuinely open**, but #11 (live research validation gap) is an honest research-failure admission — it should be elevated to a launch **blocker**, not a question.
- **The "MAU target conflict"** in Risk #12 is acknowledged but not resolved; the PRD says "Product owner reconciles" — for a seed-stage green-light PRD, this is hand-waving.

### Findings

- **[high]** **MAU target conflict unresolved** (Risk #12, §17) — PRD says 100K MAU by Month 18 (innovation strategy) but 1M MAU by Month 18 (SM-10). PRD defers reconciliation to a "revised marketing plan" after funding. *Fix:* Pick a single target and call the other a backup or sub-gate; tie Gate 2 / Gate 3 to that target.
- **[high]** **Open Q #11 research-validation gap is a launch blocker, not an open question** (§8) — 2 of 4 research subagents returned no live search results; PRD's "Why Now" thesis (Apple Intelligence, Gemini in Calendar, Luma) depends on exactly those findings. *Fix:* Elevate from "open question" to "pre-launch gate" with a named recon task and pass/fail criteria; if it fails, all of §12 collapses.
- **[medium]** **FR-32 / FR-33 / FR-40 / FR-44 / FR-45 behavioral notes are decisions in disguise** (§4.9) — e.g., "server-side wins on field-level merge" for FR-31 is a concrete architecture call, not a behavioral note. *Fix:* Mark each non-cosmetic note with `[DECISION: …]` or move to Open Questions if still genuinely open.
- **[medium]** **Phase 2/3 FRs read as decided specs but lack acceptance criteria** — unlike MVP FRs, they have no "Consequences (testable)" block. Downstream will be unable to validate them later without re-litigating. *Fix:* Either add minimal consequences blocks to all FRs, or explicitly tag Phase 2/3 FRs as "scoping outline, not decided spec."

---

## 2. Substance over theater — **strong**

This section is unusually clean. The Vision is specific (calm vs. engagement-trap, "Headspace of events," deliberate misalignment with the engagement metric). The personas are earned: Maya has a "success moment" in the addendum, drives every UJ, and several UJ edge cases follow from her behavior. Non-Users are stated as a section, not a footnote. NFRs are quantified (p95 numbers, RPO/RTO, bounce-rate targets, EMAU thresholds). The "lock-in principle" pattern (§5.1) is a real decision primitive.

Minor notes:

- **"Headspace of events"** is a strong positioning line but it is a competitor's brand name used as a category aspiration. The PRD does not acknowledge this as a risk; someone reading it literally could be confused.
- **The "47 WhatsApp messages" line** (UJ-6 climax) is an evocative anchor — but it has no source. Either cite the usage research or soften.
- **FR-7 "if AI personalization runtime causes >5 minutes of delay, the system logs it; user never sees a 'delayed' status"** is excellent — exactly the kind of bounds-vs-adjectives discipline the rubric asks for.

### Findings

- **[low]** **"Headspace of events" is a brand-name aspiration** (§1, §5.1) — used as a positioning metaphor without acknowledging the trademark/connotation risk. *Fix:* Qualify once ("an aspiration, not a partnership") or substitute a category phrase.
- **[low]** **"47 WhatsApp messages"** (UJ-6, §2.3) — the number is presented as evidence without a source. *Fix:* Cite the user interview or change to "dozens."

---

## 3. Strategic coherence — **strong**

The PRD has a clear thesis: **the moat is the calibration of the business model against engagement**, and the MVP is the smallest surface that proves it. Every MVP FR ties back to that thesis:

- Pulse Digest (3 cards) proves the "fewer, better" bet.
- Why-this Tags + Source Badge + Confidence Pulse prove the "explainability" bet.
- Multi-tier Reminder + Pulse Ping prove the "calm notification" bet.
- AI Cost Dashboard proves the "cost discipline" bet.
- Source-acquisition hierarchy + ToS review prove the "compliance-first" bet.

The success metrics map to the thesis (SM-C1 *notification suppression rate* is an especially sharp counter-metric). The "Why Now" is a real three-vector argument, not a generic "market timing" paragraph.

Phase 2/3 features are coherent extensions: group coordination → network effect, calendar sync → integration layer, on-device AI → cost optimization.

### Findings

- **[low]** **No explicit thesis sentence** in the PRD — the thesis is implied across §1 Vision, §5.1, and §12. *Fix:* Add a one-sentence "Thesis" line at the top of §1: "The moat is a business model misaligned with the engagement metric; the MVP is the smallest surface that proves users will pay for calm."
- **[low]** **SM-16 (digest novelty rate)** is named in §7.1 with a "Lower signals corpus is too narrow; higher signals the relevance filter is too loose" — this is a two-sided metric with no specific target band. *Fix:* Add a target band (e.g., 50–70%) so the metric is actually actionable.

---

## 4. Done-ness clarity — **adequate**

MVP FRs are unusually well-specified. Each FR has a "Consequences (testable)" block with concrete conditions (e.g., FR-15 dedup thresholds, FR-14 extraction latency, FR-7 delivery tolerance). NFRs carry numbers (p95, RPO, RTO, bounce rates). The architecture paragraph at §6.1 names the stack.

Where done-ness is thin:

- **Acceptance criteria are not first-class.** They are folded into "Consequences" blocks. This works for FR-1..FR-30 but is easy to lose when downstream stories start.
- **FR-22 (Confidence Pulse)** says "computed from the AI's certainty about relevance" — but never specifies how relevance is computed or what the numeric formula is. Engineers cannot test this without a model-design decision.
- **FR-29 (AI Cost Dashboard)** says "alert when blended cost per MAU exceeds a configurable threshold (default: $0.50/month)" — the alert is not specified (who gets paged? what channel?).
- **FR-44 behavioral notes** are excellent but not testable as written ("Phase 2 mobile dependency" is fine for a Phase 2 FR, but the suppression heuristic is not specified).
- **FR-15 dedup cosine thresholds (0.85–0.95 review, ≥0.95 merge)** are concrete; the **0.85–0.95 review queue** has no SLAs — who trims it, in what cadence?
- **Free-tier "1 card / day"** (§3 Glossary) and **Pulse Preview soft-walls at 3rd card** (FR-2) disagree about the cap (1 vs. 3). This is a real collision in the doc.

### Findings

- **[critical]** **Free-tier cap inconsistency** (§3 Glossary Free Tier vs. FR-2 consequence) — Glossary says "1 card / day in Pulse Digest. Forces signup at the third card." FR-2 says "soft-walls at the 3rd card (signup required at the save tap)." These are two different rules. *Fix:* Pick one and propagate to Glossary, FR-2, and §15.1.
- **[high]** **FR-22 Confidence Pulse lacks a formula or model contract** — engineers cannot test "1–5 dot pulse" without knowing how the dots are derived. *Fix:* Add a "Source of the score" clause (e.g., "computed as a learned ranker output, bucketed into 5 equally-populated bins per source after 1k impressions").
- **[high]** **FR-29 alert mechanism unspecified** — says "alerts when… exceeds threshold" but no owner, channel, or dwell time. *Fix:* Add "alert delivered via [PagerDuty/Slack/email] on >3 consecutive days over threshold."
- **[medium]** **FR-15 review queue (0.85–0.95 cosine) has no SLA** — without trim cadence, dedup backlog will grow. *Fix:* Add a cadence (e.g., "reviewed weekly by editorial; auto-discard after 30 days").
- **[medium]** **Acceptance criteria are not first-class** — folded into "Consequences" inside each FR. *Fix:* Repeat the testable conditions as an explicit acceptance checklist at the end of each FR, or add a global "Acceptance Criteria" cross-reference table.

---

## 5. Scope honesty — **strong**

This is one of the PRD's strongest sections. Non-Goals are explicit and adversarial (ticketing, social feeds, organizer tooling, ad revenue, real-time carousels, account-required browsing, push-notification spam, algorithmic leaderboards, multi-step quizzes, creator economy, group-feed features, native mobile MVP, B2B). The MVP-vs-deferred table in §6.2 is granular. The "[ASSUMPTION: …]" inline tags are indexed in §9 (roundtrip verified). Locked Principles in §5.1 are explicit constraints.

Open-items density is higher than a low-stakes PRD would carry, but appropriate for seed-stage stakes: 13 open questions, 10 assumptions, 12 risks. The risks table is ranked by likelihood × impact.

### Findings

- **[medium]** **SM-15 wording is a slight evasion** — "% of users who report Pulse made their week better" is the North Star but the mechanism (weekly NPS-style survey) is not specified. *Fix:* State the survey instrument (single-question vs. multi-question) and the response rate guardrail.
- **[low]** **No `[NON-GOAL for MVP]` callouts inline** (§5) — the doc has explicit Non-Goals but doesn't tag deferred items where they would feel load-bearing (e.g., inside FR-25, the "Per-category mute UI" deferral deserves a callout). *Fix:* Add `[NON-GOAL for MVP]` inline tags at the deferral points instead of only in §5/§6.2.

---

## 6. Downstream usability — **adequate**

The PRD is explicitly designed to feed UX, Architecture, and Epics workflows. The Glossary is dense and disciplined (every domain noun used in FRs/UJs appears here). FR IDs are globally numbered and used inline (`(realizes UJ-X)`). UJs have named protagonists (Maya; "Maya's husband" in UJ-2). The §11 NFRs have concrete numbers.

Where downstream usability is thin:

- **The glossary has 25+ definitions** but several are inconsistent across the doc: "Why-this Tags" vs. "Why this?" vs. "Why Now?" — the FR section uses both, and downstream UX will have to reconcile.
- **"Phase 2 / 3 Features"** section uses FR numbers (FR-31..FR-47) but their "behavioral notes" are not testable and the FRs are not in the Assumptions Index. Downstream architecture will pull them as if they were specs.
- **§6.1 lists "30 MVP FRs (FR-1 through FR-30)"** but the doc also has FR-44 and FR-45 in §4.9 (Already-Handled Reminder Suppression, Adaptive Pulse Digest Card Count) — both explicitly Phase 2/3. The count is correct, but the structure "all FRs in §4.1-§4.8 are MVP" is slightly broken by the §4.9 section.
- **"Pulse the Group"** is defined in Glossary, mentioned in UJ-6, and called out in §5 as a non-goal, but is FR-34 (Phase 2). The doc is consistent here, but the cross-reference chain is fragile.

### Findings

- **[high]** **FR-31..FR-47 are not in the Assumptions Index but are written as decisions** — downstream will treat them as committed when they're sketches. *Fix:* Either add minimal acceptance criteria to each Phase 2/3 FR, or add a single FR-level `[ASSUMPTION: Phase 2/3 scope sketch; commitment deferred to Phase 2 PRD]` to the §4.9 header.
- **[medium]** **Glossary drift: "Why this?" / "Why-this Tags" / "Why Now?"** — three related terms used across sections. *Fix:* Add a one-paragraph Glossary entry linking them and noting their scope difference.
- **[medium]** **Section 6.1 duplicate "Architectural" paragraph** (the same paragraph appears twice, separated by a paragraph break) — copy-paste artifact. *Fix:* Delete one occurrence.
- **[low]** **UJ-5 protagonist is "a friend," not a named character** — every other UJ has Maya's husband or Maya herself named. *Fix:* Name the friend (e.g., "Priya, a college friend of Maya's") for consistency.

---

## 7. Shape fit — **strong**

The PRD is the right shape for a seed-stage consumer product with a UX-heavy surface (Pulse Digest, Onboarding, Detail Screen) and a multi-stakeholder build (Product, Eng, Design, Marketing). UJs with named protagonists are load-bearing here, and the doc delivers six of them. Personas are deep (Maya survives in the addendum). Glossary is appropriate.

The §14 Information Architecture and §13 Aesthetic & Tone sections are unusual in a PRD but earned — without them, the "calm" thesis is unbuildable.

One shape concern: the §6.1 MVP scope list is essentially a FR index. Some of this duplicates the §4 feature descriptions. For a consumer launch at this stakes level, §6.1 is fine to be a recap; just note redundancy.

### Findings

- **[low]** **§6.1 reads as a recap of §4** — the "Architectural" paragraph is duplicated. *Fix:* Either trim §6.1 to "30 FRs, 6 UJs, 13 Open Questions, 10 Assumptions, 9 SMs + 5 Counter-metrics, 12 Risks" (a one-line manifest) and let §4 carry the spec, or keep §6.1 and trim the recap.

---

## Mechanical notes

- ✅ **Glossary present and used.** All major domain nouns defined once; minor drift noted above ("Why this?" / "Why-this Tags" / "Why Now?").
- ✅ **FR IDs contiguous and unique.** FR-1..FR-47. No gaps. §6.1 count is consistent with §4 (30 MVP FRs).
- ⚠️ **FR-44 / FR-45 are misclassified in the "Phase 2/3" section.** FR-44 says "Phase 2" but the doc classified it as a non-goal in §5. Internal consistency check passes; flag is only a naming quirk.
- ✅ **Assumptions Index roundtrip.** All 10 inline `[ASSUMPTION: …]` tags indexed in §9; index entries all appear inline.
- ✅ **Open Questions table.** 13 entries, owners and phases named.
- ✅ **UJs have named protagonists.** All 6 UJs anchor on Maya or her husband; UJ-5 is mildly weak (friend unnamed).
- ❌ **Free-tier cap inconsistency** (covered above as critical).
- ⚠️ **§6.1 duplicate paragraph** (covered above as medium).
- ⚠️ **MAU target inconsistency** (covered above as high).
- ✅ **Cross-references resolve.** All `(realizes UJ-X)` and `FR-X` references point to real entities.
- ✅ **Risks table.** 12 risks, ranked by likelihood × impact, mitigations tied to FRs/Decisions.

---

## Top-of-mind specific gaps that downstream will hit first

These are the items that will produce concrete downstream bugs if shipped as-is:

1. **Free-tier cap rule conflict** → UX/Architecture will implement two different rules.
2. **FR-22 Confidence Pulse lacks a formula** → Engineering cannot test.
3. **FR-29 alert mechanism unspecified** → On-call rotation can't be set up.
4. **MAU target conflict** → Marketing plan and Success Metrics will be misaligned.
5. **Open Q #11 elevated to launch blocker** → Pre-launch recon is the actual gate, not a question.

---

## Summary verdict

**Adequate-to-strong seed-stage consumer PRD.** Strong thesis, clear MVP arc, mostly decisive. The critical drops are concrete consistency bugs (free-tier cap, duplicate paragraph, MAU target) and a few over-lax acceptance criteria (Confidence Pulse, AI Cost alert). Fix the criticals and the two high-priority hits, and this is ready to feed UX, Architecture, and Epics without producing downstream rework.
