---
title: "EventPulse24 — Pre-PRD Gap Fill: Intent for bmad-prd"
project: EventPulse24
date: 2026-08-19
source_session: brain-pre-prd-gaps-2026-08-19
mode: autonomous (Ideate for me)
handoff_target: bmad-prd
---

# EventPulse24 — Pre-PRD Gap Fill: Intent Document

> **Purpose:** Capture the 3 critical pre-PRD gaps the brief missed, plus the few connections that turn those gaps into PRD-ready decisions. Drop into `bmad-prd` as additive context to the existing brief.

This document was generated from a divergent session covering ~119 logged ideas across 8 techniques (First Principles, Reverse Brainstorming, Cross-Pollination, SCAMPER, Constraint Mapping, Worst Possible Idea + inversion, Analogical Thinking, Question Storming, Decision Tree, Failure Analysis). It is meant to be read alongside `brief-EventPulse360-2026-08-19/brief.md` and `addendum.md`.

---

## 1. Gap #1 — Legal & Compliance (HIGHEST PRIORITY)

### The hidden cliff

The brief mentions web crawling as a *risk* (high likelihood, high impact) but does not treat it as a **scope decision**. This is a gap. Crawling is not just risky — it is *optional*. Official event APIs cover the majority of urban events for MVP.

### 4 new additions to brief (or to a pre-PRD legal addendum)

| # | Item | Why it matters | PRD placement |
|---|---|---|---|
| L1 | **Data Sourcing Strategy (APIs first, crawling second)** | De-risks legal exposure; doesn't compromise product. Order: (a) official APIs — Eventbrite, Meetup, PredictHQ, Bandsintown, Songkick, Ticketmaster; (b) RSS feeds from tourism boards, universities, city gov; (c) careful crawling with robots.txt respect and ToS review (Phase 2); (d) partnership deals where venues send us data (Year 2). | Non-functional requirements → "Data Sources" section |
| L2 | **GDPR/CCPA stance** | Personal calendar data = GDPR Art 4.1 personal data → lawful basis needed (Art 6); consent is the safe default. Right-to-explanation (Art 22) maps directly to "Why this?" feature. Ship with privacy policy + consent flow from day 1; do not crawl EU sites for MVP. | Non-functional → "Compliance" section |
| L3 | **Copyright / data-minimization stance** | Event *facts* (date, place, name) are not copyrightable in US/EU; only creative expression is. LLM-paraphrase creative copy at extraction; keep canonical facts only. Drop raw HTML after extraction. Storage minimization by design. | Functional → "Event Extraction Pipeline" section |
| L4 | **Calendar sync legal posture (Phase 2 prep)** | Google/Apple ToS govern user calendar reads. Vendor choice (Nylas vs. SyncGene vs. build) is a legal + cost decision. Defer to Phase 2; flag now so architecture can plan for OAuth + ToS review. | Out of MVP; flagged in Open Questions |

### Legal risk reduction roadmap

- **MVP (0–6mo)**: APIs only. Zero crawling. Privacy policy + consent flow. US-only launch.
- **Phase 2 (6–12mo)**: Add RSS + careful crawling with per-source legal review.
- **Year 2**: Partnership deals + international expansion (post-EU legal review).

---

## 2. Gap #2 — Monetization & Pricing Validation

### What's missing in the brief

The brief mentions "Pro paid conversion rate >5%" and "$4.99/mo vs $7.99/mo vs annual-only" but does not model unit economics or validate willingness-to-pay for *calm*. This is a **medium-priority gap** — solvable by a 1-week validation sprint.

### 3 new additions

| # | Item | Why it matters | PRD placement |
|---|---|---|---|
| M1 | **Pricing Validation Sprint (1 week)** | Run Van Westendorp price-sensitivity survey (n≥50) + 5 user interviews to confirm $5–$8/mo is the WTP sweet spot. Cost: ~$200. Outputs a single number + confidence interval. | Out of scope for PRD *build*; prerequisite for *business case*. Block PRD start until complete. |
| M2 | **Free tier constraints (the lever)** | Decide before build: free = 3 digests/day, no calendar sync, no Pulse-the-Group, no "why this?" detail (only micro-tag). Pro = unlimited digests + calendar sync + group + deep "why" + voice quick-add. The lever must be visible and repeated, not buried. | Functional → "Subscription Tiers" section |
| M3 | **No-ads policy as a feature** | Codify "no ads, ever" as a product principle. If anyone in the company suggests ads, the answer is "calm." Anti-Eventbrite positioning. Brief already says it; add to PRD as a hard constraint. | Principles → "Business Model" section |

### Monetization decision tree (use this to pick path)

| Path | Free | Pro | Tip jar | Risk |
|---|---|---|---|---|
| A | 3 digests/day | $4.99/mo | no | Lowest revenue |
| B | 3 digests/day | $7.99/mo or $49/yr | no | Recommended after survey |
| C | 3 digests/day | $9.99/mo only | no | Maximizes per-user, lowest conversion |
| D | full free | $9.99/mo | yes | Subscription + donation hybrid |

**Recommendation:** Run validation sprint first (Path B as default until proven otherwise).

### Cross-industry inspiration (logged, not prescriptive)

Headspace/Calm (scarcity on the hook), Spotify (family plan = virality), Patreon (true-believer tier), Wikipedia (donation-funded mission), Mozilla (privacy positioning as funding hook). EventPulse24 should pick 2 of these patterns, not all.

---

## 3. Gap #3 — User Validation of Core Bets

### What's missing in the brief

The brief assumes the persona ("Maya") and the core hypothesis ("users prefer fewer, smarter notifications") but does not validate them. **Medium-priority gap**, but cheap to close.

### Core bets to validate (in priority order)

| # | Bet | How to test | Sample | Cost | Time |
|---|---|---|---|---|---|
| V1 | Users prefer 3 events to 10 | Fake-door A/B mockup, measure "save" rate | 30 | $0 | 1 day |
| V2 | "Why this?" reduces distrust | Same event, with vs without explanation, trust 1–5 | 30 | $0 | 1 day |
| V3 | Notification fatigue is acute | Survey "how many event/newsletter notifications do you ignore/day?" | 50 | $50 | 2 days |
| V4 | Maya persona is real | 5 user interviews with 30–40yo knowledge workers; ask them to walk through their week of events | 5 | $200 | 1 week |
| V5 | Users will pay for "calm" | Van Westendorp + 5 follow-up interviews | 50 | $50 | 1 week |

### Minimum viable validation sprint (1 week, ~$300)

- 5 user interviews (30–40yo NYC knowledge workers, $25 gift card each)
- 1 Typeform survey (V3 + V5 combined, 50 respondents via personal network)
- 1 fake-door mockup test (Figma + landing page, V1 + V2)

### If validation fails — pivot paths

- **V4 fails (Maya not real)**: revisit persona, possibly shift to parents or group coordinators
- **V1 fails (people want 10 not 3)**: revisit positioning, possibly add a "power user" tier
- **V5 fails (no WTP for calm)**: pivot monetization to B2B2C faster (university + tourism boards)

---

## 4. Decisions Made (Locked for PRD)

| Decision | Choice | Source |
|---|---|---|
| **Data sourcing for MVP** | Official APIs only; defer crawling to Phase 2 | INS-2, INS-6, L1 |
| **Geographic launch** | **BD-primary** (Dhaka focus) for MVP; US as secondary post-MVP expansion; EU deferred until legal review | User decision 2026-08-19 |
| **Bangla language support** | Required from day 1 (UI, notifications, event descriptions) | User decision 2026-08-19 |
| **BD payment methods** | bKash + Nagad required for Pro tier (international cards low penetration in BD) | User decision 2026-08-19 |
| **BD event sources** | events.com.bd, FB groups, university calendars (different ecosystem than US/Eventbrite) | User decision 2026-08-19 |
| **Personalization onboarding** | 30 sec + location auto-detect + 2 interest pills (BD: Bangla defaults; US: English defaults) | INS-7 |
| **Default notification behavior** | Pulse Ping (1 daily) is the default at signup; more notifications require explicit opt-in | INS-8 |
| **No-ads policy** | Hard constraint, codified as principle | INS-4, M3 |
| **Validation gate** | 1-week user interviews + survey before PRD feature freeze (2-3 BD + 2-3 US participants) | INS-5, INS-11, User decision 2026-08-19 |
| **"Why this?" dual purpose** | UX feature + GDPR Art 22 compliance mechanism | INS-3 |
| **Dual persona validation** | Maya (US 30-40yo) + Rumi (BD 25-35yo Dhaka professional) — validate both in sprint | User decision 2026-08-19 |
| **BD WTP sweet spot** | Likely $1-3 USD/mo (৳150-300), not US $5-8 — confirm in sprint | User inference 2026-08-19 |

---

## 5. Decisions Left Open (for PRD to resolve)

| Question | Owner | Priority |
|---|---|---|
| Which 3–5 official APIs for MVP launch? | Eng + Product | Pre-build |
| LLM provider strategy (Anthropic vs OpenAI vs multi-model)? | Eng | Pre-build |
| Free tier specifics — exact feature gates | Product | Pre-build |
| Pro pricing exact point ($5 vs $7.99 vs $9.99) | Product (after validation) | Pre-launch |
| Founder team gaps (who is AI/ML lead?) | Founder | Pre-build |
| Funding path (bootstrap vs angel vs seed) | Founder (after validation) | Pre-launch |

---

## 6. New Risks Discovered in This Session

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **AI hallucination produces wrong/cancelled/ghost events → trust collapse** | High | Critical | "Last verified at [time]" badges; easy user-report; revert to trusted source within 24h |
| **"Maya" persona is one demographic — what about Gen Z and Boomers?** | Medium | High | Validate in user interviews; ship with broader personalization signals |
| **Phase 2 calendar sync adds data privacy surface** | Medium | High | Vendor (Nylas/SyncGene) handles OAuth; never store raw calendar events on our servers, only structured facts |
| **Apple/Google ship AI Calendar in WWDC 2027** | Medium | Critical | Web-first + cross-platform + brand moat; already in brief |
| **Crawling blocked mid-Phase-2** | Medium | Medium | APIs cover the core; crawling is enrichment, not foundation |

---

## 7. Open Questions Raised by This Session (for PRD intake)

1. Will users set per-event reminders, or pick "smart defaults" and trust the system?
2. What happens when the AI gets an event wrong — what's the trust recovery flow?
3. How do we onboard *without* calendar connect — what personalization signals are available?
4. Does the 3-card limit feel liberating or limiting? (Test in validation sprint.)
5. What does "cancel anytime, your data goes with you" mean operationally? (Export calendar + preferences JSON.)

---

## 8. Recommended Next Step

**Run the validation sprint (1 week, ~$300) before starting `bmad-prd`.**

Why: Validation results will materially change the brief (persona, features, pricing). Building the PRD before validation risks 2 months of rework.

**Alternative (if time-constrained):** Document all of the above as **assumptions** in the PRD and validate after MVP ships. Higher risk; faster start.

---

## Source

Generated from `_bmad-output/brainstorming/brain-pre-prd-gaps-2026-08-19/.memlog.md` (119 entries). Hand off to `bmad-prd` together with the existing brief.md and addendum.md.