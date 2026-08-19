# PRD Structure Review — EventPulse24 (prd-EventPulse360-2026-08-19)

**Reviewer:** BMad PRD structure reviewer
**Date:** 2026-08-19
**Scope:** prd.md + addendum.md
**Files reviewed:**
- `/home/bs1346/Documents/P-project/EventPulse24/_bmad-output/planning-artifacts/prds/prd-EventPulse360-2026-08-19/prd.md`
- `/home/bs1346/Documents/P-project/EventPulse24/_bmad-output/planning-artifacts/prds/prd-EventPulse360-2026-08-19/addendum.md`

---

## 1. Glossary Consistency (§3 vs. §4 / §14)

The §3 Glossary is internally consistent and the discipline rule is declared up-front ("Introducing a synonym is a discipline violation"). The terms are used verbatim in most cases. However, several near-synonyms and minor drifts exist:

- **"Personal Calendar"** is defined in §3 as the home of Personal Events, but in §4.5 the term drifts to "personal calendar" (lowercase, generic). §14 also uses "Add Personal Event" as a surface without explicit alignment to the glossary's "Personal Event" term. Minor.
- **"Pulse the Group"** is glossary-defined; §4.9 FR-34 uses the term verbatim. ✓
- **"Why-this Tags"** — glossary says up to 3 keywords. §4.6 FR-21 uses "Why-this Tags" verbatim. ✓ However, §4.6 FR-21 talks about "Why-this Tags are human-readable, not raw model output" while FR-38 introduces "Why Now?" (Phase 3) with the distinction "*vs. Why-this Tags which explain why surfaced*". The capitalization here is `Why Now?` (with capital N) — this is glossary-consistent. ✓
- **"Neighbor count"** is referenced in §4.6 FR-24 ("`👥 X neighbors`") but is **not** defined in §3. Discipline violation — new domain noun introduced outside §3.
- **"Source Reliability Score"** is glossary-defined. §4.4 FR-16 uses it verbatim. ✓
- **"Confidence Pulse"** — glossary defines it as "1–5 dot indicator." §4.6 FR-22 uses it consistently. ✓ But §13.1 "Principles" references "warm-tone (Personal) and cool-tone (Public) variants" without a glossary pointer. The warm/cool color discipline is declared in §3 (Personal Event / Public Event bullets) and §4.9 FR-32 but is not formally a glossary term.
- **"Reminder Plan"** — glossary defines it ("up to N reminder slots (default: 5d, 2d, 1d, 1hr)"). §4.3 FR-9 uses "Reminder Plan" verbatim. ✓ §15.2 lists "Multi-tier reminders (email)" — the term drifts slightly from "Reminder Plan" but stays consistent with the §3 description.
- **"Pulse Preview"** — glossary term not explicitly defined (only mentioned indirectly via FR-2 description). §3 lists "Free Tier" but not "Pulse Preview" as a glossary entry. This is a minor gap — the term is used 8+ times in §4 and §6 but never formally defined.
- **"Pulse Digest"** — glossary-defined; used verbatim throughout. ✓
- **"Pulse Card"** — glossary-defined; used verbatim throughout. ✓
- **"Pulse Ping"** — glossary-defined; used verbatim throughout. ✓
- **"Source Badge"** — glossary-defined; used verbatim. ✓
- **"Detail Screen"** — glossary-defined; used verbatim. ✓
- **"Timeline"** — glossary-defined; used verbatim. ✓
- **"Preference Graph"** — glossary-defined; used verbatim. ✓
- **"Travel Mode"** — glossary-defined; used verbatim. ✓
- **"Voice Quick-Add"** — glossary-defined; used verbatim. ✓
- **"On-Device Personal AI"** — glossary-defined; used verbatim. ✓
- **"Why Now?"** — glossary-defined; used verbatim. ✓
- **"Pro Tier" / "Free Tier"** — glossary-defined; §15 uses verbatim. ✓
- **"AI Cost Dashboard"** — glossary-defined; §4.8 / §10.3 / §17 Risk #2 use verbatim. ✓

**Net:** Glossary discipline is largely intact. Two minor leaks: "Neighbor count" (introduced in §4.6) and "Pulse Preview" (used heavily but not formally in §3). Both should be added to the glossary for full discipline compliance.

---

## 2. FR Numbering (FR-1 through FR-47)

- **MVP FRs (FR-1 to FR-30):** All 30 numbered and defined in §4.1–§4.8. ✓
- **Phase 2/3 FRs (FR-31 to FR-47):** All 17 named in §4.9.
  - FR-31 Calendar Sync (Phase 2) ✓
  - FR-32 Unified Timeline (Phase 2) ✓
  - FR-33 Conflict-Aware Scheduling (Phase 2) ✓
  - FR-34 Pulse the Group (Phase 2) ✓
  - FR-35 Pro Tier (Phase 2) ✓
  - FR-36 Voice Quick-Add (Phase 3) ✓
  - FR-37 Email-to-Event Forwarding (Phase 3) ✓
  - FR-38 Why Now? (Phase 3) ✓
  - FR-39 On-Device Personal AI (Phase 3) ✓
  - FR-40 Travel Mode (Phase 3) ✓
  - FR-41 Group Availability Heatmap (Phase 3) ✓
  - FR-42 White-Label B2B2C (Year 2+) ✓
  - FR-43 B2B Insights API (Year 2+) ✓
  - FR-44 Already-Handled Reminder Suppression (Phase 2) ✓
  - FR-45 Adaptive Pulse Digest Card Count (Phase 3) ✓
  - FR-46 Pulse Streak (Year 2+) ✓
  - FR-47 Year in Pulse Recap (Year 2+) ✓

- **No gaps** in the numbering. **No duplicate FR definitions.** ✓
- **Total FRs:** 47 (30 MVP + 17 deferred), consistent with §6.1 summary line. ✓
- **Numbering stability:** FR numbers are stable across downstream references (addendum, §6.1, §6.2, §7 metrics, §10, §11, §17 risks, §15). ✓

---

## 3. Cross-Reference Integrity

### FR-N references — all anchor-resolvable
Spot-checked references across §4, §5, §6, §7, §9, §10, §11, §15, §17. Every FR referenced (e.g., "FR-17", "FR-29", "FR-39") maps to a defined FR. **No orphan FR references found.** ✓

### UJ-N references — UJ-1 through UJ-6
- UJ-1 defined in §2.3 ✓ referenced in FR-1, FR-5, FR-7, FR-9, FR-10, FR-11, FR-19, FR-20, FR-21, FR-22, FR-23, FR-24, FR-25, FR-36 (Phase 3+), FR-39 (Phase 3+), FR-40 (Phase 3+), FR-44.
- UJ-2 defined in §2.3 ✓ referenced in FR-3 (Phase 2), FR-19, FR-31, FR-32, FR-33, FR-37.
- UJ-3 defined in §2.3 ✓ referenced in FR-1, FR-2, FR-4, FR-10, FR-27.
- UJ-4 defined in §2.3 ✓ referenced in FR-21, FR-22, FR-23, FR-24, FR-25, FR-38.
- UJ-5 defined in §2.3 ✓ referenced in FR-26, FR-28.
- UJ-6 defined in §2.3 ✓ referenced in FR-34, FR-41.

**All UJ references resolve. ✓**

### SM-N references — SM-1 through SM-16, SM-C1 through SM-C5
- §7.1 Leading Indicators: SM-1 to SM-9, SM-16. (SM-10 to SM-15 are lagging indicators per §7.3.)
- §7.2 Counter-Metrics: SM-C1 to SM-C5.
- §7.3 Lagging Indicators: SM-10, SM-11, SM-12, SM-13, SM-14, SM-15.
- **Notable:** SM-16 appears under "Leading Indicators" (§7.1) but the numbering jumps from SM-9 to SM-16 — a numbering anomaly. The §6.1 summary line says "9 Success Metrics + 5 Counter-metrics" but actual count is 10 primary (SM-1 to SM-9 + SM-16) + 5 counter (SM-C1 to SM-5) = 15, not 14. **Numbering skip (SM-10 through SM-15 are reserved for lagging but appear after SM-9 in numeric order rather than after SM-5).** This is a minor structural anomaly.
- **All SM references resolve.** ✓

### Open Q #N references — #1 through #13
- §8 lists Open Q #1 to #13. ✓
- References in §2.2 (#6 implied), §4.9 FR-35 (Open Q #4), §10.3, §11.6, §12 (Open Q #11), §17 risks (Open Q #11, Open Q #7, Open Q #12) all resolve. ✓
- Addendum §I references Open Q #1, #3, #6, #11 — all resolve. ✓

### Minor cross-reference gaps:
- §5 Non-Goals says "Pulse the Group (Phase 2) is coordination, not a feed." No FR cross-reference; should be `FR-34`.
- §11.5 Accessibility references "Pulse Card, Detail Screen, and onboarding flow" but does not anchor to specific FRs (e.g., FR-6, FR-24, FR-1).

**Overall cross-reference integrity: strong, with minor skip in SM numbering.** ✓

---

## 4. Section Ordering

Expected order (per reviewer prompt): Vision → Target User → Glossary → Features → Non-Goals → MVP Scope → Success Metrics → Open Questions → Assumptions.

**Actual order in prd.md:**
1. §0 Document Purpose
2. §1 Vision
3. §2 Target User
4. §3 Glossary
5. §4 Features
6. §5 Non-Goals (Explicit)
7. §6 MVP Scope
8. §7 Success Metrics
9. §8 Open Questions
10. §9 Assumptions Index
11. §10 Constraints & Guardrails
12. §11 Cross-Cutting NFRs
13. §12 Why Now
14. §13 Aesthetic & Tone
15. §14 Information Architecture
16. §15 Monetization
17. §16 Platform
18. §17 Risks & Mitigations
19. §18 References

**Verdict:** The core flow (Vision → Target User → Glossary → Features → Non-Goals → MVP Scope → Success Metrics → Open Questions) is correctly ordered. **However, §9 Assumptions appears AFTER §8 Open Questions**, while the reviewer prompt expected Assumptions before Open Questions (or at minimum, Assumptions adjacent to Open Questions). The PRD instead places Assumptions *after* Open Questions. This is a **deviation from the expected order.**

Additional observations:
- §10 Constraints & Guardrails comes after §9 Assumptions — appropriate.
- §11 NFRs after §10 — appropriate.
- §12 Why Now appears after NFRs (rather than as part of Vision context); structurally late.
- §15 Monetization appears *after* §13 Aesthetic and §14 IA — unusual but defensible.
- §16 Platform appears after Monetization — order is unusual (Platform is typically an earlier constraint).
- §17 Risks at the end is conventional.

**Net:** Core flow intact. Two ordering concerns: (a) §9 Assumptions after §8 Open Questions (expected the reverse), (b) §16 Platform late in doc rather than as a §4.x or §11-adjacent constraint.

---

## 5. Out-of-Scope Discipline (§6.2 ↔ §4.9 FR-31 through FR-47)

§6.2 lists deferred features with cross-references to Phase 2/3 FRs. Mapping check:

| §6.2 row | FR cross-ref | §4.9 FR exists? |
|---|---|---|
| FR-31 Calendar Sync | FR-31 | ✓ |
| FR-32 Unified Timeline | FR-32 | ✓ |
| FR-33 Conflict-Aware Scheduling | FR-33 | ✓ |
| FR-34 Pulse the Group | FR-34 | ✓ |
| FR-35 Pro Tier | FR-35 | ✓ |
| FR-36 Voice Quick-Add | FR-36 | ✓ |
| FR-37 Email-to-Event Forwarding | FR-37 | ✓ |
| FR-38 Why Now? | FR-38 | ✓ |
| FR-39 On-Device Personal AI | FR-39 | ✓ |
| FR-40 Travel Mode | FR-40 | ✓ |
| FR-41 Group Availability Heatmap | FR-41 | ✓ |
| FR-42 White-Label B2B2C | FR-42 | ✓ |
| FR-43 B2B Insights API | FR-43 | ✓ |
| FR-44 Already-Handled Reminder Suppression | FR-44 | ✓ |
| FR-45 Adaptive Pulse Digest Card Count | FR-45 | ✓ |
| FR-46 Pulse Streak | FR-46 | ✓ |
| FR-47 Year in Pulse Recap | FR-47 | ✓ |

**All 17 deferred FRs (FR-31 through FR-47) are cross-referenced in §6.2.** ✓

§6.2 also includes non-FR deferred items:
- Native mobile apps (iOS, Android) — covered by §16 Platform (Phase 2+).
- Real-time push notifications to mobile — covered by FR-9 Out of Scope + §10 / §16.
- Event reviews / ratings on Detail Screen — explicitly excluded in §14.3.

**Discipline is intact.** ✓

---

## 6. Counter-Metric Pairing

§7.2 lists 5 counter-metrics (SM-C1 through SM-C5). Pairing check vs. §7.1 / §7.3 primary metrics:

| Counter | Paired primary | Pairing stated? |
|---|---|---|
| **SM-C1** Notification suppression rate | SM-2 (Pulse Digest daily open rate) | ✓ "Counterbalances SM-2 (open rate)." |
| **SM-C2** Pulse Digest bounce rate | SM-2 (Pulse Digest daily open rate) | ✓ "Counterbalances SM-2." |
| **SM-C3** Per-user reminder opt-out rate | SM-5 (Per-event reminder setup rate) | ✓ "Counterbalances SM-5." |
| **SM-C4** Free-tier signup cap conversion | SM-? — "Counterbalances growth-vs-monetization trade." Implicitly pairs with SM-11 (Pro paid conversion). **Pairing target not explicitly named.** |
| **SM-C5** AI cost per MAU | "Counterbalances any 'more personalization' push." Implicitly pairs with engagement/quality push but **no specific primary is named.** |

**Findings:**
- SM-C1, SM-C2, SM-C3 are explicitly paired.
- SM-C4 and SM-C5 are *unpaired* (no named primary). The discipline of "every primary has a paired counter-metric" is therefore not symmetrically enforced.
- Conversely, **SM-11 (Pro paid conversion)** and **SM-15 (North Star)** do not have explicit counter-metrics in §7.2. If the rule is "every primary needs a counter," these two laggards are unpaired.

**Net:** Counter-metric pairing is partial. Three of five are paired; two are unpaired in §7.2. Two lagging indicators (SM-11, SM-15) lack counter-metrics. **Discipline is incomplete.**

---

## 7. Scope Discipline (Capability vs. Implementation)

The PRD predominantly describes capabilities (UX behaviors, system responsibilities, FRs). However, several implementation leaks exist outside §11 / §14 / §16:

- **§6.1 "Architectural:" subsection** appears TWICE (lines 744 and 748 — duplicate paragraph). This block leaks: "PostgreSQL + pgvector, RDBMS for transactional data, transactional email stream (Postmark or SendGrid), server-side AI cost tracking." — these are implementation choices in an MVP Scope section (not §11/§14/§16).
- **§6.1 "Operational:" subsection** mentions "AI Cost Dashboard, Source Registry, ToS review log" — these are operational capabilities; mostly fine, but "Source Registry" is an FR (FR-13) reference rather than an implementation detail.
- **§7.1 SM-4** says "% of users who answer 'I trust Pulse's recommendations' YES in a weekly pulse survey" — this is a measurement mechanism, fine.
- **§10.2 Privacy** says "stored encrypted at rest" — implementation hint (acceptable in §10 Constraints).
- **§11.4 Observability** — implementation details ("Structured JSON logs; sampled at 100% for errors, 10% for info") — but §11 is an NFR section, so this is appropriate. ✓
- **§16 Platform** explicitly mentions "Tailwind + responsive layouts" — this is a framework leak but it IS in §16 Platform, so it's allowed per the reviewer prompt. ✓
- **§11.2 Security** — "OAuth credentials ... stored encrypted at rest. No PII in event logs; structured logs only. HTTPS-only; HSTS preload. CSP and SRI on all public assets. Rate limiting on all public endpoints." — implementation details in §11, which is the appropriate location per reviewer prompt. ✓
- **§11.3 Reliability** — "exponential backoff (3 retries, max 8h backoff)" — implementation hint in §11, acceptable.

**Findings:**
- **Duplicate paragraph** in §6.1 (lines 744 and 748 contain identical "Architectural:" blocks).
- **Tech-stack leak in §6.1** — PostgreSQL + pgvector, Postmark, SendGrid names appear in §6.1 (MVP Scope), not §11/§14/§16. This violates the "describe capabilities, not implementation" discipline.
- The PRD otherwise maintains capability-first framing. The §16 Platform mention of "Tailwind + responsive layouts" is the most visible framework leak but is in the right section.

---

## 8. Summary of Findings by Severity

### CRITICAL (must-fix)
1. **Duplicate paragraph in §6.1** — the "Architectural:" subsection is repeated verbatim (lines 744 and 748). One copy must be deleted; if both are intentional (one for MVP FRs, one for Phase 2/3), this is undocumented.
2. **Tech-stack leak in §6.1** — "PostgreSQL + pgvector", "Postmark or SendGrid" appear in MVP Scope, not §11/§14/§16. These should be moved to §11 (Cross-Cutting NFRs) or §16 (Platform) where the discipline permits.

### HIGH (should-fix)
3. **§9 Assumptions ordering** — appears after §8 Open Questions, but the reviewer prompt expected Assumptions before or adjacent to Open Questions. The PRD's Document Purpose (§0) implies Assumptions are inline-tagged with cross-reference to §9. Moving §9 to immediately after §6 would improve discoverability for downstream artifact authors.
4. **"Neighbor count" missing from §3 Glossary** — domain noun introduced in §4.6 FR-24 (`👥 X neighbors`) is not in §3.
5. **"Pulse Preview" not formally in §3 Glossary** — used 8+ times but only described via FR-2 in §4.1. Should be added.
6. **Counter-metric pairing incomplete** — SM-C4 and SM-C5 have no named primary target; SM-11 and SM-15 have no counter-metric. The discipline of pair-per-primary is not symmetrically enforced.
7. **§16 Platform appears too late** — Platform form-factor constraints are usually declared earlier. Placing §16 after §15 Monetization is unusual; consider moving before §13 Aesthetic or to the front of the doc as a top-level constraint.

### MEDIUM (nice-to-fix)
8. **SM numbering skip (SM-9 → SM-16)** — §7.1 jumps from SM-9 to SM-16. If SM-16 is meant to be the 10th leading indicator, the numbering should be SM-10 or the skipped numbers (SM-10 to SM-15) should be re-sequenced to come after SM-9. Currently the §6.1 summary counts "9 Success Metrics" but the actual count is 10 (SM-1 through SM-9 + SM-16).
9. **§12 "Why Now" placement** — appears after NFRs (§11) and before Aesthetic (§13). Conventional placement is in §1 (Vision) or §6 (Scope). Consider moving.
10. **§11.5 Accessibility** — references "Pulse Card, Detail Screen, and onboarding flow" without anchoring to FRs (FR-6, FR-24, FR-1). Cross-references would strengthen traceability.
11. **§5 Non-Goals** — references "Pulse the Group" without FR-34 anchor. Minor cross-reference discipline.
12. **§15.2 Pro Tier** lists "Why Now? (Phase 3)" and "On-Device Personal AI (Phase 3)" as Pro benefits, but §4.9 FR-35 describes Pro as "Calendar Sync (FR-31), Unified Timeline (FR-32), and Pulse the Group (FR-34)" only. The Pro Tier scope has drifted between §4.9 and §15.2 — should be reconciled.

### LOW (cosmetic)
13. Glossary term capitalization: "personal calendar" (lowercase) in §4.5 FR-18 should be "Personal Calendar" (capitalized per §3).
14. "Personal Event" vs. "personal event" inconsistency — §3 capitalized; §4.5 mostly lowercase. Minor.
15. SM-C5 references "more personalization" without FR anchor (FR-29 / FR-30 implied but unstated).

---

## 9. Compact Verdict

**Top-line:** The PRD is structurally sound. FR numbering (1–47) is gap-free and stable; cross-references (FR-N, UJ-N, Open Q #N) all resolve; glossary discipline is largely intact with two leaks (Neighbor count, Pulse Preview); §6.2 ↔ §4.9 cross-referencing is complete; counter-metric pairing is partial (3 of 5 paired explicitly); section ordering deviates from the reviewer prompt's expected sequence (Assumptions after Open Questions, Platform late). One **duplicate paragraph** and one **tech-stack leak** in §6.1 are the only critical structural issues.

**Critical findings:** 2 (duplicate paragraph in §6.1; tech-stack leak PostgreSQL/pgvector/Postmark in §6.1).
**High findings:** 4 (Assumptions ordering; "Neighbor count" missing from glossary; "Pulse Preview" missing from glossary; counter-metric pairing incomplete; §16 Platform too late — **5 in practice**).
**Medium findings:** 5.
**Low findings:** 3.
**Total:** ~15 structural issues; 2 must-fix before Finalize.

---

**File path:** `/home/bs1346/Documents/P-project/EventPulse24/_bmad-output/planning-artifacts/prds/prd-EventPulse360-2026-08-19/review-structure.md`
