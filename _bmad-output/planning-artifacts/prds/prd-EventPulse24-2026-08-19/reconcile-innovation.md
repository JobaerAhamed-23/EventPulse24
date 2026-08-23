# Innovation Strategy → PRD Reconciliation

**Date:** 2026-08-19
**Source:** `_bmad-output/innovation-strategy-2026-08-19.md`
**Target:** `prd-EventPulse24-2026-08-19/prd.md` + `addendum.md`
**Author:** Input reconciliation pass

---

## 1. Gaps — Strategic Content Not Captured in PRD / Addendum

### 1.1 JTBD Analysis (Innovation §"Unmet Customer Jobs") — Partially Captured

Innovation Strategy enumerates **8 JTBD rows** plus a "biggest unmet job" thesis. The PRD §2.1 compresses these into 3 functional + 2 emotional + 2 social + 1 contextual bullets. Notable **un-captured or under-captured** JTBD:

- **JTBD #6** — *"Help me say yes to experiences without FOMO"* → maps to **"Saved for Later" + Trending-near-you social proof** (Innovation Initiative #8). PRD has no save-collection UX, no "trending near you" surface, and no explicit FOMO-relief feature beyond the bounded Pulse Digest. Addendum mentions "1 saved collection" as a free-tier cap (§F ASSUMPTION) but no save UX is named in §4.
- **JTBD #8** — *"Make event planning for groups not painful"* → folded into FR-34 (Phase 2), but the PRD drops the **coordination-hell** pain framing. The Innovation Initiative #5 (Group Coordination AI) viral-loop rationale never appears in PRD §17 risks or §6.2.
- **JTBD #1, #5** (hyperlocal + serendipity gaps) → the **"Catch the tech conference happening next door that nobody told me about"** framing is the seed of SEO positioning. PRD §1 captures it implicitly via "SEO-driven public-event discovery" but **does not name hyperlocal serendipity** as a JTBD anywhere in §2.1.

**Missing PRD anchor:** §2.1 should explicitly enumerate the 8 unmet jobs (or a defensible subset) so epics/stories can trace back to JTBD.

### 1.2 Force-Field Analysis (Innovation §"🌊 FORCE FIELD ANALYSIS") — Not Captured

The 8 driving + 8 restraining force table, the 3 strategic-leverage points, and the 2 strategic-risk points are **entirely absent** from PRD and addendum. Force-field reasoning is the **core lens of Innovation §Strategic Focus** but has no PRD home.

**Missing PRD anchor:** §12 "Why Now" partially captures driving forces (AI cost curves, attention fatigue) but **no restraining-force analysis** is articulated. The leverage-point conclusion ("enter through public-event SEO first, then expand to personal unification") IS the product strategy and IS captured in §6.1, but without the force-field reasoning that justifies it.

### 1.3 Six Hypotheses (H1–H6) — Missing From PRD §7

This is the largest single gap. Innovation Strategy §"Key Hypotheses to Validate" defines **6 hypotheses** with validation methods and failure thresholds:

| # | Hypothesis (Innovation) | Innovation Validation Method | Innovation Failure Threshold | PRD Coverage |
|---|---|---|---|---|
| **H1** | Users accept fewer notifications for higher relevance | A/B Pulse Digest vs. real-time alerts | <40% digest opt-in | **Indirect** — SM-2 (digest open rate ≥60%) is *behavioral*, not the same as *opt-in rate*. PRD never measures "opt-in to digest mode" specifically. |
| **H2** | Web-scale AI aggregation finds events users can't find elsewhere | Manual audit of 100 recommended events | <60% novelty rate | **MISSING.** No novelty-rate or audit metric in PRD §7. AI extraction precision (SM implicit in FR-14) ≠ novelty. |
| **H3** | Users will pay $4.99/mo for unified personal+public timeline | Paid waitlist conversion | <5% conversion in 30 days | **Phase-2 only** — SM-11 (Pro conversion >5%) is a lagging indicator gated on Phase 2. Innovation treats H3 as a Phase 1–2 bet; PRD treats it as Phase 2 only. |
| **H4** | Group coordination drives viral invites | Cohort invite-rate tracking | <0.3 invites/user/month | **Indirect** — SM-14 (viral coefficient >0.5) is the lagging equivalent, but Phase-2-locked. No invite-rate leading indicator in §7.1. |
| **H5** | Cold-start can be broken via public-event SEO | Organic traffic → signup conversion | <3% signup rate | **Indirect** — SM-7 (Pulse Preview conversion >20%) and Gate 1 (SEO traction) approximate this. But Innovation specifies **organic SEO → signup**, while PRD SM-7 measures **Pulse Preview → signup**. Different funnels. |
| **H6** | Trust score + explainable AI reduces notification skepticism | Survey + retention comparison | <70% trust in recommendations | **Captured** — SM-4 ("Why this?" trust score >70%) and FR-21/22/23/24 align. ✅ |

**Net: H6 mapped. H1, H2, H3, H4, H5 partially or weakly mapped.** H2 has no metric.

### 1.4 Sizing Data (Innovation §"Market Landscape")

TAM/SAM/SOM figures ($1.2T / $45B / $50–150M ARR) **do not appear** in PRD or addendum. The addendum §F ("Funding & Team") includes capital requirements ($50–150K MVP, $300–600K runway) which is consistent with but distinct from market sizing.

**Missing PRD anchor:** Vision/market context. PRD §1 is a vision statement without market sizing. Whether market sizing belongs in PRD is debatable, but the **SOM target (~5M MAU, $50–150M ARR)** should at least appear in §7.3 lagging indicators — SM-10 says "1M MAU by Month 18" which is **below** the Innovation SOM target.

### 1.5 Strategic-Option Rationale (Innovation §"🎲 STRATEGIC OPTIONS") — Addendum Captures Substantively

The 3-option analysis (Calm Consumer, Group Intelligence, B2B2C Vertical) + Recommended Strategy (Hybrid A-primary, B-embedded, C-deferred) is **well captured in Addendum §B** ("Rejected Alternatives"). PRD §6.2 and §15 (Monetization) reflect the recommended strategy. **No gap here.**

---

## 2. Conflicts — Innovation Strategy vs. PRD

### 2.1 MAU Target Conflict

- **Innovation §Phase 2:** "Scale to 100K MAU" by Month 18.
- **Innovation §Phase 3:** "Scale to 5M+ users" by Year 3+ (the SOM target).
- **PRD §7.3 SM-10:** 100K MAU by Month 6, **1M by Month 18**.
- **PRD Gate 3 (Month 18):** 1M MAU + positive unit economics.

**Conflict:** Innovation's Phase 2 (Months 6–18) target is 100K MAU; PRD's SM-10 for the same window is 1M MAU — **10× larger**. PRD is more aggressive than Innovation. Either PRD has absorbed a 10× growth multiplier or Innovation was conservative; this is a real disagreement worth flagging.

### 2.2 Hypothesis Validation Timing

- **Innovation §Phase 1:** Validate H1, H2, H5 in Months 0–6.
- **Innovation §Phase 2:** Validate H3, H4, H6 in Months 6–18.
- **PRD §7.4 Gate 1 (Month 3):** SEO traction + D7 retention — matches H5 proxy, **does not match H1 or H2 timing** (H1 is "A/B test Pulse Digest vs. real-time alerts" — a Phase 1 measurement PRD never operationalizes).

**Conflict:** H1 is a head-to-head A/B between digest and real-time, but PRD §1 commits to "Pulse Ping (one daily notification, not many)" as the *product*. The PRD has already decided H1 by making it the design — there's no A/B because Pulse Ping is the only path. Innovation treats H1 as falsifiable; PRD treats it as given.

### 2.3 Pricing Point

- **Innovation §Business Model Innovation:** Pro tier = **$4.99/mo** (specified, not assumed).
- **PRD §15.2:** Pro tier pricing is `[ASSUMPTION: $4.99–$7.99/mo range, open]` — ranges and explicitly defers decision to Phase 2 PRD.
- **PRD §8 Open Q #4:** Pricing for Pro tier — $4.99 vs. $7.99 vs. annual-only — listed as open.

**Soft conflict:** Innovation's $4.99 is a stated design choice (and is the basis for H3's failure threshold); PRD downgrades it to "open assumption." This widens H3's failure threshold from "5% conversion at $4.99" to "5% conversion at an unknown price."

### 2.4 Phase 1 City Count

- **Innovation §Phase 1:** "Crawl/aggregate 50K+ events from 20 sources in **3 cities**."
- **Addendum §I (Open Q #6):** Recommends 3 cities at launch (NYC, SF, Austin).
- **PRD §8 Open Q #6:** "Geographic beachhead — 3 US cities (NYC, SF, Austin) or 1 city deeply?"

**Soft conflict:** Innovation specifies 3 cities as the plan; PRD lists 3-vs-1 as an open question. Recommend resolving as "3 cities" per Innovation + Addendum, and closing Open Q #6.

### 2.5 Notification Tier Names

- **Innovation §Strategic Focus:** "multi-tier reminders (5d/2d/1d/1hr)."
- **PRD §4.3 FR-9:** "up to 4 reminder slots: 5d, 2d, 1d, 1hr before the event" — **matches.**

No conflict.

### 2.6 Cost per MAU Target

- **Innovation (implicit via "AI inference is the killer cost" + SOM economics):** Implied <$1/MAU for SOM viability.
- **PRD §7.2 SM-C5:** AI cost per MAU <$0.50/month, **trend must be down.**
- **PRD §10.3:** Default threshold $0.50/MAU.

**No conflict** but Innovation's SOM math ($50–150M ARR / 5M users ≈ $1–3 ARPU/month) implies a looser cost ceiling than PRD's $0.50. Not a conflict in PRD's favor, but worth noting.

---

## 3. Hypothesis Coverage Matrix

| Hypothesis | Innovation Stated Validation | PRD Metric(s) | Coverage |
|---|---|---|---|
| **H1** (digest over real-time) | A/B digest vs. real-time; failure <40% opt-in | SM-2 (digest open rate ≥60%), SM-C1 (suppression ≥30%) | **Partial** — measures digest *usage*, not *opt-in choice* between digest and real-time. PRD pre-commits to Pulse Ping, removing the A/B. |
| **H2** (web aggregation finds unique events) | 100-event novelty audit; failure <60% novelty | None | **MISSING** |
| **H3** ($4.99 paid conversion) | Waitlist conversion ≥5% in 30 days | SM-11 (>5% Pro conversion, Phase 2) | **Partial** — Phase-2-locked, no 30-day waitlist metric in MVP window |
| **H4** (group coordination virality) | Invite-rate ≥0.3/user/month | SM-14 (viral coefficient >0.5, Phase 2) | **Partial** — Phase-2-locked, no MVP proxy |
| **H5** (SEO breaks cold start) | Organic → signup ≥3% | SM-7 (Pulse Preview → signup ≥20%), Gate 1 (SEO traction) | **Partial** — Pulse Preview ≠ organic SEO traffic; different funnels |
| **H6** (explainable AI builds trust) | Survey ≥70% trust | SM-4 (trust score ≥70%) | **COVERED** ✅ |

**Coverage summary:** 1/6 fully covered (H6), 4/6 partially covered (H1, H3, H4, H5), **1/6 missing (H2)**.

---

## 4. Recommended PRD Updates (Advisory — Not Rewriting)

- **§7.1 (Leading Indicators):** Add novelty-rate audit metric for H2 (e.g., manual review of 50 weekly recommendations: ≥60% not findable on Google search for the same query).
- **§7.1:** Add digest *opt-in rate* (H1) as a leading indicator — separate from SM-2 (digest *open rate*).
- **§7.1:** Add H4 viral proxy at MVP — e.g., share-link click-through (FR-28) as a leading indicator for invite-rate once Phase 2 unlocks invites.
- **§7.3 SM-10:** Reconcile with Innovation Phase 3 SOM target. Either tighten Innovation to 1M (less ambitious SOM) or expand PRD to 5M (more aggressive scale story).
- **§8 Open Q #4 (Pricing):** Note Innovation's $4.99 as the source default; close or escalate to decision.
- **§8 Open Q #6 (Geography):** Recommend closing as "3 cities per Innovation §Phase 1."
- **§2.1 (JTBD):** Optionally enumerate the 8 unmet jobs (or a compressed 4–5) for traceability into stories/epics.
- **§12 Why Now / §17 Risks:** Add a 1-paragraph force-field summary noting the dominant restraining force (incumbent distribution + cold start) and the strategic response (web-first + SEO-first).

---

## 5. Summary Verdict

The PRD is **substantively faithful** to Innovation Strategy's strategic posture (Calm Consumer primary, Group Intelligence embedded, B2B2C deferred; pulse digest, multi-tier reminders, source transparency, explainable AI all present). However, **the explicit hypothesis-validation framework (H1–H6) is mostly absorbed rather than preserved** — only H6 has a clean leading-indicator mapping. **H2 (novelty/aggregation value) has no PRD metric**, and the MAU targets disagree by 10×. The force-field analysis and the 8-JTBD table have no PRD home.

**Severity:** Medium — the PRD will ship a coherent product, but the strategic-validation discipline that Innovation recommends is partially lost. For a seed-stage launch, the gaps in H1–H5 measurement are the most consequential.