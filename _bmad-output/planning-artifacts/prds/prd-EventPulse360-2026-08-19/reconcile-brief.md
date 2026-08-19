# Brief → PRD Reconciliation

**Inputs compared:**
- **Brief:** `brief-EventPulse360-2026-08-19/brief.md`
- **PRD:** `prd-EventPulse360-2026-08-19/prd.md`
- **Addendum:** `prd-EventPulse360-2026-08-19/addendum.md`

---

## 1. Gaps (brief material absent from PRD + addendum)

### 1a. Product Principles as a *locked contract* (qualitative loss)

The brief's "Product Principles (locked)" table (Calm > Engagement, Explainable AI, Calendar-sync-in not replace, 3 cards max, Trust through transparency) is the brief's *moral core*. The PRD absorbs individual principles into FRs (3 cards → FR-5, explainability → FR-21/22/23) but **never restates them as a principle block in §13 or elsewhere in the PRD**. The PRD §13 (Aesthetic & Tone) is the only qualitative/voice section; principles would naturally live there but are missing.

→ **Move the locked principles into PRD §13.1/§13.2 or add a §13.4 "Operating Principles" block so they survive as a contract, not a feature.** Or, if intentionally deferred to UX Spec, flag here so they're not lost.

### 1b. Contrarian premise / "The Cost of the Status Quo" (narrative framing loss)

Brief lines 22, 36, 50–56 contain a powerful qualitative framing: *every incumbent optimizes for engagement; nobody optimizes for calm/signal-to-noise*. This is the brief's "why this must exist as a brand." The PRD §1 Vision paraphrases it but loses the **rhetorical force and the "industry optimizes for engagement, we optimize for calm" thesis line**. The "cost of status quo" table (missed events, notification fatigue ~5% signal-to-noise, calendar fragmentation, 47-WhatsApp hell) is fully absent from PRD §1.

→ **Add a 2–3-sentence "anti-thesis" paragraph to PRD §1, anchored in the cost-of-status-quo framing.** Risk #1 / Risk #5 touch on platform-owner risk but not the broader cultural argument.

### 1c. Maya's behavioral specificity

Brief gives Maya: Google Calendar + Apple Calendar split (husband), 47 unread newsletters, 2+ missed close-friend birthdays/year, disables notifications within 1 week, has *abandoned* Bandsintown/Songkick/etc. The PRD §2.3 UJ-1 mentions "47 unread newsletters" and "2+ close friend birthdays" but **drops the husband-uses-Apple-Calendar split** (appears briefly in UJ-2 path only) and the **abandoned-competitors list**, which is a qualitative texture loss about why the 60% non-consumer segment is reachable.

→ **Either preserve in addendum §C (already there in abbreviated form) or restore to PRD persona section as a one-liner.** The abandoned-competitors list is a defensible-moat insight.

### 1d. "Why this?" Detail Screen — neighbor-count and similar-events signal

Brief's "Core experience #6" lists: source badge, confidence level, similar events attended, neighbor count. PRD FR-24 captures all four. **However, the brief's *spirit* — "show me this is a real event, not marketing" — is collapsed into FR-24's consequences without a UX rationale.** No PRD section explains *why* these four signals together constitute the trust bundle. Brief line 89 says "Source badges, confidence pulses, no hidden ranking algorithms" — a phrase worth preserving verbatim somewhere.

### 1e. "Pulse the Group" Phase 2 emotional promise

Brief says "47 WhatsApp messages → 4 taps" (line 56, 179). PRD UJ-6 climax line preserves "47 WhatsApp messages replaced by 4 taps" verbatim. **But brief also includes "Be the planner app without being 'the planner app'" qualitative spirit.** PRD loses this anti-burden framing — only captures mechanic, not emotional.

### 1f. Year-3 ambition / brand aspiration

Brief line 248: *"EventPulse24 becomes the default intelligent surface for time and experience... the layer between humans and the chaos of scattered event information"* and the "Headspace of events" framing. PRD §1 Vision is close but does **not** preserve the "Headspace of events" reference or the 3-year ambition as a quoted block. This is a brand anchor loss.

→ **Add to PRD §1 or §13 a quoted 3-year ambition sentence and "Headspace of events" positioning reference.**

### 1g. Honest moat assessment

Brief's "Moat Type | Strength | Why" table (lines 100–107) is a candid self-assessment: brand strong, data building, network effects none yet, LLM technical moat weak, distribution weak. **The PRD has no equivalent self-critical section.** Risks §17 covers external threats but not internal moat honesty. This is a significant qualitative loss — the brief shows self-awareness; the PRD does not.

### 1h. Funding runway & team-gap Open Questions

Brief Open Questions #7 (funding: bootstrap/seed/angel) and #8 (founding team gaps: technical co-founder, AI/ML lead, designer) are operational concerns. **They appear in PRD §8 as Open Questions #7 and #8 verbatim — good.** But the *context* about them being existential founder-questions (not engineering questions) is lost. Worth a brief note that these are founder-blocking, not engineering-blocking.

### 1i. "Why Now" quantitative specifics

Brief says "12–18 months before Apple/Google ship native AI calendar features." PRD §12 captures "12–18 months" but loses the deeper point that **AI cost curves collapsed** (a specific trigger that wasn't true 18 months ago) and **attention fatigue is acute** (a cultural-not-technological trigger). The "Cost of Status Quo" ~5% signal-to-noise number from brief is absent.

### 1j. Maya's quote (qualitative richness)

Brief quotes Maya: *"I don't want MORE things to do. I want someone to tell me the 3 things actually worth doing this week."* Addendum §C preserves it. **PRD does not.** A single pull-quote in PRD §2 would do more for empathy than UJ-1's 9-step path.

---

## 2. Conflicts

### 2a. Pulse Digest fixed composition

- **Brief §"Open Questions #5"**: "Should we seed Pulse Digest with 1 must-know + 1 nearby + 1 surprise, or rank dynamically?" → **open, unresolved**.
- **PRD FR-5**: "The 3 cards cover at least 2 distinct categories (e.g., one `personal-near`, one `public-near`, one `serendipity`)" — **implies a fixed must-know + nearby + surprise composition**.
- **PRD §8 Open Q #5**: Still listed as open.

**Conflict:** FR-5 consequences presume fixed seeding while §8 keeps it open. Not catastrophic but inconsistent — FR-5 consequence prematurely constrains the open question.

### 2b. Geographic beachhead

- **Brief Open Q #6**: "3 US cities (NYC, SF, Austin) or 1 city deeply?" → open.
- **Addendum §I recommendation**: "3 cities at launch (NYC, SF, Austin) — not 1 city deep."
- **PRD §8 Open Q #6**: Still listed as open.

**Conflict:** Addendum commits to a recommendation; PRD leaves it open. The addendum's role is to capture rationale, not decide — but the recommendation is presented in decided tone. Either lift to PRD §8 as resolved or rephrase addendum to "for discussion: 3 cities."

### 2c. Personal Events in Pulse Digest default

- **Brief Scope**: "Personal calendar manual add" is IN for MVP.
- **PRD §8 Open Q #13**: "Personal Events in Pulse Digest: opt-in or opt-out default?" — open.
- **PRD FR-19 Consequences**: "A Personal Event with `start_time` within the next 48 hours is eligible for the Pulse Digest."
- **PRD ASSUMPTION-7**: Defaults to opt-out, pending Open Q #13 confirmation.

**Conflict is minimal but visible:** PRD tells the builder "opt-out" via assumption while §8 flags as open. Resolution note should be added.

### 2d. LLM provider strategy

- **Brief Open Q #3**: Single vendor (OpenAI/Anthropic) vs. multi-model — open.
- **Addendum §B Option H**: "Start single-vendor... Add multi-model when cost pressure justifies it."
- **PRD §8 Open Q #3**: Still listed as open.

Same addendum-vs-PRD-inconsistency as 2b. Addendum should be reframed as "for discussion" or PRD should resolve.

### 2e. Pulse the Group cap

- **Brief line 82** mentions "Tap group → AI finds the best time slot" — no cap stated.
- **Addendum §J FR-34**: "Group size cap: 10 people."
- **PRD FR-34**: "Small group (≤10 people)." → Consistent, no conflict.

(No conflict — just confirmed alignment.)

---

## 3. Captured Depth (addendum correctly preserves)

The addendum does well on these:

- **Rejected alternatives matrix (§B):** Options B–H from the implicit strategy discussion (Group-First Pivot, B2B Intelligence, Ad-Supported, Ticketing Platform, Native Mobile First, Always-On Push, Multi-Model LLM) — none of these appear in the brief explicitly, but the brief's "What we eliminate" and "What we create" lists imply them. The addendum gives them *rejection rationale*, which the PRD cannot carry. **Correctly placed.**
- **Competitive teardown (§D):** Eventbrite, Meetup, Facebook, Google/Apple Calendar, Luma, Bandsintown, Partiful, IRL — the brief names the first five; addendum adds Luma (from landscape research), Partiful, IRL, Posh, Shotgun. **Depth added**, not just preserved.
- **Maya persona depth (§C):** Demographics, daily tech stack, behavioral specifics preserved verbatim from brief. Brief material that PRD UJ-1 already absorbed is *re-stated with extra texture*. **Correctly placed.**
- **Phase 2/3 behavioral notes (§J):** FR-31 (RRULE handling, two-way vs. one-way), FR-32 (color differentiation, empty state copy "Your week is quiet — Pulse Digest is the place to discover"), FR-34 (free-tier limit: 1 group, Pro unlimited), FR-39 (federated learning optional), FR-40 (auto-suggest only, never assume). Brief gives fragments; addendum consolidates architectural hints the PRD §4.9 brevity cannot hold. **Correctly placed.**
- **Marketing & launch plan (§G):** Pre-launch / Launch / Post-launch phases with channel-specific tactics. Brief mentions "SEO-driven acquisition" + "viral group coordination" but no channel list. Addendum fills from input. **Correctly placed.**
- **Compliance & legal (§H):** GDPR/CCPA export, CAN-SPAM, HiQ v. LinkedIn accessibility. Brief mentions "AI extraction legal review" only. **Correctly placed.**
- **Open Questions rationale (§I):** Recommendations for Q1, Q3, Q6; rationale for Q11 research-validation gap. Brief has Q1–Q8 plain; addendum elaborates. **Correctly placed.**
- **Capital & team gaps (§F):** Build cost estimates, team archetypes, funding path options. Brief Open Qs #7/#8 are skeleton; addendum flesh. **Correctly placed.**
- **LLM/extraction/dedup/notifications technical constraints (§E):** Architecture hints the PRD §11 NFRs cannot hold. **Correctly placed.**

The addendum is acting as a *working-memory extension* for the PRD, capturing depth that's correctly out of PRD scope but needed downstream. This is its job and it's doing it.

---

## 4. Net Assessment

- **PRD is faithful to brief features** (FR-1 through FR-43 line up well).
- **PRD is structurally weaker on brief's *qualitative*** material: contrarian premise, locked principles, brand ambition, moat honesty, Maya's voice.
- **Addendum does its job well** as downstream-feed.
- **Three resolve-able conflicts** (digest composition, beachhead, personal-events default) need a tightening pass before Finalize.
- **Highest-value gap to fix in PRD itself** (not addendum): restore the *locked principles* and *brand ambition* so the PRD is a contract for tone, not only a contract for features.
