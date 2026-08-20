# Reconciliation: Design Thinking → PRD

**Date:** 2026-08-19
**Purpose:** Extract the gaps and conflicts between the Design Thinking source and the PRD + addendum. Surface empathy insights, prototype concepts, and hypotheses the PRD's FR structure did not absorb.

---

## 1. Gaps (Design Thinking content NOT in PRD or Addendum)

### 1.1 Empathy Map — 7 Patterns (Observation Table)

The PRD retained Maya's persona and behavioral data points but dropped the **7 Patterns table** that links each observation to a UX implication. Specifically missing from PRD:

| # | Design Thinking Pattern | PRD Coverage | Gap |
|---|---|---|---|
| 1 | "Users abandon apps after the first wrong notification" | Partially in §1 vision (counter-metric) | Implication ("first impression matters more than feature breadth") is not in §6.1 MVP scope or success metrics. SM-1 measures time, not first-notification quality. |
| 2 | "Calendars are already a primary touchpoint" | FR-3, FR-31 | Design Thinking's insight "Don't build a new calendar — extend existing ones" is implicit in §1 but never stated as a constraint on §6 In-Scope. |
| 3 | "People browse events when bored, not when planning" | Implicit in §4.7 (sharing) | "Discovery should be ambient, not pushy" is the *thesis* behind Pulse Digest but not surfaced as a design principle in §13. |
| 4 | "Save for later is the most underused pattern" | UJ-1 (Save action) | No explicit FR for a low-pressure "maybe lane" / saved-collection beyond save. Design Thinking names this as a distinct concept; PRD only has Save vs. Dismiss. |
| 5 | "Travel breaks the local-event loop" | FR-40 (Phase 3) | "Trip detection is a UX unlock" — explicit rationale missing from Phase 3 narrative. |
| 6 | "Group chats are where event decisions happen" | FR-34 (Phase 2), UJ-6 | Design Thinking's framing "Coordination > discovery for viral loops" is the central thesis for Pulse the Group but only appears in §17 Risk #8, not in §1 Vision or §15 Monetization. |
| 7 | "'Why am I seeing this?' is the #1 uninstall reason" | FR-21, FR-24 | Rationale buried in §4.6; should be elevated to §1 vision or §13 principles. |

### 1.2 How-Might-We Questions (24 HMWs across 7 clusters)

The PRD retained **0 of 24 HMWs**. Most actionable HMWs not represented as testable requirements:

- **HMW #6** "Automatically suppress reminders the user has already seen/acted on" → Implicit in §11.3 (Phase 2 mobile "device active" suppression) but no FR for web/email already-handled detection (UJ-1 explicitly mentions this for husband scenario).
- **HMW #10** "Skip the interests quiz entirely and infer from connected calendars" → FR-3 lists calendar connect as optional, not as the *primary* inference path. PRD doesn't bind calendar-connect as the canonical cold-start signal.
- **HMW #12** "Detect conflicts intelligently and suggest resolutions" → Captured in FR-33 (Phase 2) but with weaker behavioral notes than the Design Thinking wireframe (Screen 6: "Move dinner earlier / Skip concert / Keep both" actions).
- **HMW #14** "Present a daily '3 things worth your time' digest instead of infinite scroll" → Captured in FR-5. Good.
- **HMW #16** "Add serendipity through 'trending near you' without creating FOMO" → FR-5 mentions "serendipity" card slot but the anti-FOMO framing ("without creating FOMO") is not in §13 anti-patterns.
- **HMW #20** "Auto-detect travel via calendar/email without manual input" → FR-40 Phase 3 only; Design Thinking wanted trip detection as a "UX unlock" signal across the product.
- **HMW #23** "Add events by voice in one sentence" → FR-36 Phase 3 only; Design Thinking ranked this as a top-7 prototype concept (#7) and "demo magnet" — not surfaced as marketing asset in §16 Platform / Phase 3+.

### 1.3 Solution Narratives & Wireframe Concepts (The 7 Screens)

Design Thinking contains 7 explicit low-fi wireframes. The PRD absorbed some but dropped the **solution narratives**:

| Screen | PRD Coverage | Lost Narrative |
|---|---|---|
| **Screen 1: Onboarding** | FR-1, FR-2 | "Time to first event: ~15 seconds" (not just 30). PRD target is 30s (SM-1); wireframe demonstrates 15s. |
| **Screen 2: Pulse Digest** | FR-5, FR-6 | The 3-card composition formula "1 must-know + 1 nearby + 1 surprise" is the **prototype hypothesis** (Design Thinking §"Generated Ideas #7" and Open Q #5). PRD §8 Q5 asks the question but doesn't ship a default. |
| **Screen 3: Timeline** | FR-32 (Phase 2) | "Quiet — no public" placeholder for empty days is a wireframe pattern; PRD §4.9 FR-32 mentions "no alarm" but not "show empty-state day labels." |
| **Screen 4: Per-Event Reminder Picker** | FR-9 | The visual-clock-with-chips (5d/2d/1d/1hr/At) concept is a wireframe; PRD lists slots as text. Also: "Quiet hours: 10pm–8am" is in FR-12 but the wireframe shows it on the reminder screen itself, not in settings. |
| **Screen 5: Group Pulse the Group** | FR-34 | Wireframe shows "👥 Weekend Crew (5) — Best time for all: Sat 7–9pm — Suggested: Comedy night @ The Stand — Sat 8pm • 3 love it — [Vote] [See details]." PRD §4.9 FR-34 is one sentence; addendum §J has behavioral notes but no vote mechanic. |
| **Screen 6: Conflict Detection** | FR-33 | Wireframe shows three explicit actions: "Move dinner earlier / Skip concert / Keep both — I'll manage." PRD FR-33 is "no auto-rebook; surface alternatives; user decides" — weaker than the wireframe's three-action interaction. |
| **Screen 7: "Why this?" Detail** | FR-24 | Wireframe's breakdown ("0.6mi from your location · Comedy is in your top 3 · 12 of your neighbors going · 4.7 (213 reviews)") includes **neighbor count** and **reviews**. PRD FR-24 lists neighbor count but NOT reviews. **Reviews is dropped.** |

### 1.4 Hypotheses (Design Thinking §"Features to Test")

The PRD retained **SMs but not the hypothesis structure**. Design Thinking pairs each feature with a hypothesis and a target metric. Mapping:

| # | DT Hypothesis | PRD SM | Mismatch |
|---|---|---|---|
| 1 | "<30s = >60% activation" | SM-1 (time), SM-3 (completion) | PRD does not bind activation-rate-to-onboarding-time as a coupled hypothesis. |
| 2 | ">60% open = strong retention signal" | SM-2 (60% target) | Match. |
| 3 | ">70% trust score" | SM-4 (70% target) | Match. |
| 4 | ">80% complete at least 1" reminder setup | SM-5 (80% target) | Match. |
| 5 | ">2min avg = stickiness" for timeline | None | **Timeline time-on-view not measured.** PRD §7 has no SM for Timeline stickiness even though it's FR-32. |
| 6 | ">0.5 invites/user = viral signal" | SM-14 (>0.5 viral coefficient) | Match (Phase 2). |
| 7 | ">20% try = productivity hit" for Voice Quick-Add | None | **Voice Quick-Add has no SM.** Even though it's Phase 3, the demo-magnet framing is dropped. |

### 1.5 Key Insights (Design Thinking §"Top 5")

The PRD absorbed most as FR-21 (trust), FR-12 (quiet hours), FR-3 (calendar canvas), FR-1 (30s), FR-34 (group). Two insights are missing as named principles:

- **"Inline trust beats click-to-reveal"** (Design Thinking §Next Steps #7) → PRD §13.1 has anti-patterns but no principle stating that explainability must be *visible on the card*, not behind a tap. The wireframe Screen 2 shows Why-this Tags on the card; PRD FR-21 says "on the Pulse Card" but §13 doesn't elevate it as a principle.
- **"Pulse Digest's 3 cards may need to be dynamic"** (Design Testing §Surprises + §Next Steps #1) → PRD FR-5 hard-codes "exactly 3 cards." Open Q #5 is the only acknowledgment; the "adaptive 3→5→7" hypothesis is not surfaced as a known unknown with a default plan.

### 1.6 Aesthetic Principles (Design Thinking §Ideate)

Design Thinking's Analogous Inspiration patterns (§"38–42") added a Headspace-style calm animation loading state, Spotify-Wrapped-for-events annual recap, Duolingo streak, Apple Wallet integration, Notion-style block customization. **All five are missing from PRD.**

Specifically:
- **Pulse Streak** (calm gamification, not FOMO) — not in PRD. SM-15 measures "Pulse made your week better" but no streak mechanic.
- **"Your Year in Pulse" annual recap** — absent from §15 Monetization or any future-feature list.
- **Apple Wallet integration** — absent. Listed in Design Thinking as analogous inspiration but no PRD candidate. Worth flagging for Phase 2/3 architecture.

### 1.7 Decision Gates Mismatch

Design Thinking decision gates (Week 4 / Week 8 / Week 12) operate on usability-test scale (7 users/concept). PRD §7.4 decision gates operate on launch scale (Month 3 / 9 / 18). The **usability validation gate** (Gate 1: SUS >75 + onboarding completion >85% → ship MVP) is implicitly covered by SM-3 + SM-4 but not stated as a *pre-launch gate*.

---

## 2. Conflicts (Where Design Thinking and PRD Disagree)

### 2.1 "Time to first event"
- **Design Thinking wireframe Screen 1:** "~15 seconds"
- **PRD SM-1:** "<30 seconds" target
- **Resolution:** PRD is the binding target; wireframe is a stretch. SM-1 should be updated to reflect the wireframe demonstrated value, OR PRD target should be tightened.

### 2.2 Pulse Digest card count
- **Design Testing §Surprises:** "Users may want more than 3 cards in Pulse Digest (counter to our hypothesis)."
- **Design Testing §Next Steps #1:** "Refine Pulse Digest to be adaptive — Default 3 cards for new users; expand to 5–7 for engaged users."
- **PRD FR-5:** "exactly 3 cards on a standard day. Exception: a 'No pulse for today' empty state." — no adaptability clause.
- **Resolution:** PRD hard-codes 3; Design Thinking identified adaptability as a known-need. Open Q #5 partially captures it but PRD doesn't ship a default-flex behavior.

### 2.3 "Why this?" density
- **Design Testing §Key Learnings #2:** "works best as 3 keywords, not paragraphs — 'nearby, tonight, music' beats full explanations."
- **Design Testing §Surprises:** "may feel patronizing if too detailed."
- **PRD FR-21:** "up to 3 keywords" (matches).
- **PRD FR-38 (Phase 3, "Why Now?"):** natural-language per-event explanation.
- **Resolution:** No conflict, but PRD doesn't state the *anti-pattern* ("don't write paragraphs here"). Design Thinking's "patronizing if too detailed" lesson is absent from §13 anti-patterns.

### 2.4 Notification suppression (already-handled detection)
- **Design Testing HMW #6:** "automatically suppress reminders the user has already seen/acted on."
- **PRD FR-9:** "A reminder is suppressed if the device is active (Phase 2 mobile) or the user is in a user-configured quiet window."
- **PRD addendum §J FR-31 (Phase 2):** One-way read sync, write-back Phase 3.
- **Gap:** Web/email-channel "already handled" suppression (e.g., user added the event to their own calendar outside EventPulse24) is not covered. Design Thinking's HMW #6 has no PRD binding. **This is the single biggest design-thinking-idea-without-PRD-coverage.**

### 2.5 Conflict-detection actions
- **Design Thinking wireframe Screen 6:** Three explicit actions — "Move dinner earlier / Skip concert / Keep both."
- **PRD FR-33:** "No auto-rebook. Surface alternatives; user decides." Behavioral notes are thinner than the wireframe.
- **Resolution:** PRD should adopt the three-action pattern from the wireframe in Phase 2 FR-33 behavioral notes.

### 2.6 Calendar connect as primary inference
- **Design Thinking HMW #10:** "Skip the interests quiz entirely and infer from connected calendars."
- **PRD FR-1:** calendar connect is Step 1 but optional; interest chips (Step 2) also optional and present.
- **Resolution:** No direct conflict, but PRD offers two parallel inference paths (calendar connect OR interest chips). Design Thinking's stronger claim is calendar-connect is THE inference path. PRD's parallel structure dilutes the insight.

### 2.7 Pulse Preview vs. anonymous value
- **Design Thinking Idea #4:** "'Pulse Preview' — Before signup, show a live 3-card digest of *their city's* events today. No signup wall."
- **PRD FR-2:** Pulse Preview exists, but §15.1 Free Tier caps unauthenticated to "1 card / day."
- **Conflict:** Design Thinking explicitly shows 3 cards pre-signup. PRD soft-walls at the 3rd card (FR-2 consequence). The conversion intent is captured (Open Q #9) but the wireframe's "no signup wall" framing is weakened.

### 2.8 Solo use before group
- **Design Testing §Key Learnings #3:** "Group features drive viral loops only after trust is established — solo use must be excellent first."
- **PRD §17 Risk #8:** "Pulse the Group in Phase 2 ... solo value must be excellent first."
- **Resolution:** Aligned. Design Thinking's key learning is in the Risk section but not elevated to a §6 MVP-in-scope principle or §1 Vision statement.

### 2.9 Onboarding "must produce visible value immediately"
- **Design Testing §Key Learnings #5:** "calendar connect + 3 relevant events in 30 seconds is the magic number."
- **PRD FR-1:** "≤30 seconds" — captures the time but loses the *content* requirement (3 relevant events must be visible immediately, not just a generic digest slot configured).
- **Resolution:** PRD §4.1 "glass-floor simple" prose captures the spirit but doesn't make the 3-events-immediately-visible a testable consequence.

---

## 3. Vision Preservation Check (Maya's Persona)

PRD §2.3 UJs vs. Design Thinking Empathy Map:

| Empathy Map Quote | PRD UJ | Status |
|---|---|---|
| "I keep missing things" | UJ-1 (morning Pulse Digest) | ✅ Preserved |
| "My phone buzzes too much" / disables notifs on most apps | FR-10 (single Pulse Ping) + FR-12 (Quiet Hours) | ✅ Preserved |
| "Why am I finding out about this concert AFTER?" | UJ-1 (multi-tier reminders 5d/2d/1d/1hr) | ✅ Preserved |
| "Is this app just going to spam me?" | UJ-1 climax: "Nothing else pushes itself" + FR-10 counter-metric | ✅ Preserved |
| "I wish my calendar just KNEW what I care about" | UJ-3 (inferred preferences from calendar) + FR-1 | ✅ Preserved (but see 2.6) |
| "I don't have time to browse events" | UJ-1 (3 cards/day, no browsing required) | ✅ Preserved |
| "Why is this showing me things I don't care about?" | UJ-4 (Why this? detail screen) + FR-25 (less-like-this) | ✅ Preserved |
| "Just remind me about stuff I actually care about" | UJ-1 step 4 (sets reminders) + FR-9 | ✅ Preserved |
| "There has to be a better way than Doodle" | UJ-6 (Pulse the Group Phase 2) | ✅ Preserved |
| "I don't want MORE things to do. I want someone to tell me the 3 things actually worth doing this week." | UJ-1 climax: "She knows what matters this week, in 30 seconds" | ✅ Preserved (PRD §2.3 UJ-1 climactic sentence aligns) |

**Behavioral data preservation check:**
- "47 unread event newsletters" → PRD UJ-1 contextualizes but doesn't echo the number. Acceptable.
- "Misses 2+ close friend birthdays/year" → UJ-1 step 3 card (a) is "A friend's birthday tonight." Aligned.
- "Asks spouse 'What's this weekend?'" → UJ-6 (Pulse the Group) addresses the spouse-coordination dimension.
- "Manually copies dates from Eventbrite emails" → UJ-5 (public share-link) addresses sharing inbound; not the manual copy. Acceptable (Phase 3 FR-37 Email-to-Event covers the source).
- "Disables push notifs on most apps after install" → UJ-1 entry state says "Has connected Google Calendar during yesterday's first-time onboarding" but does NOT establish that Maya has disabled Pulse Ping. PRD FR-10 consequence only suppresses when empty digest; doesn't model the disabled-ping behavior. **Minor gap.**
- Success moment ("Opens Pulse in the morning → sees 3 relevant events → saves one → sets 2-day reminder → closes app. Total time: 30 seconds") → PRD UJ-1 climax mirrors this. ✅ Preserved.

**Addendum §C persona depth** (extended Maya profile, secondary personas) is **fully preserved in the addendum, not absorbed into the PRD body.** This is acceptable per the PRD's "depth belongs in addendum" discipline, but the UJs in §2.3 do not surface the secondary personas (Group Coordinator, Traveler, Parent). They are Phase 2/3 FRs only. Acceptable.

**Overall verdict on Vision Preservation:** PRD UJs faithfully reflect the empathy-map insights. No empathy quote is contradicted by a UJ. Two minor non-conflicts: (a) PRD FR-10 doesn't model "Maya disabled Pulse Ping" as a behavioral mode (PRD assumes Maya keeps it on); (b) PRD doesn't make "3 events must be visible at minute 0" a testable consequence of FR-1.

---

## 4. Summary Table

| Category | Count | Severity |
|---|---|---|
| Empathy patterns dropped (7-pattern table) | 7 | Medium — mostly absorbed into FRs, but not all rationales preserved |
| HMWs not represented as FRs | 24 of 24 unreferenced; ~6 actionable gaps | Medium — most relevant is "already-handled detection" |
| Wireframe concepts not in PRD | 7 wireframes; ~5 narrative gaps | High — Conflict Detection three-action pattern and "Why this?" reviews are dropped |
| Hypotheses missing | 2 of 7 (Timeline stickiness, Voice Quick-Add) | Low |
| Insights missing as principles | 2 of 5 (inline trust, adaptive digest) | Medium |
| Aesthetic principles missing | 5 of 5 analogous-inspiration patterns (streak, annual recap, wallet, block customization, calm animation) | Low–Medium — these are nice-to-haves; "Pulse Streak" is the strongest candidate |
| Conflicts | 9 | 2 high (digest card count adaptability, already-handled detection), 7 medium/low |
| Vision preservation | 10 of 10 empathy quotes reflected in UJs | Aligned ✅ |

---

## 5. Top 5 Reconciliation Items (Recommended for Downstream Artifacts)

1. **Add "already-handled detection" suppression** as an MVP FR-9 consequence (or split into a new FR). Design Thinking HMW #6 is the strongest dropped insight.
2. **Adopt Conflict Detection three-action pattern** in FR-33 (Phase 2): "Move / Skip / Keep both" — matches wireframe Screen 6.
3. **Make "3 events visible at minute 0" a testable FR-1 consequence** alongside the 30-second timing target.
4. **Add adaptive Pulse Digest card count** as a deferred Phase 2 FR or a parameterized FR-5 (default 3, expand to 5–7 for engaged users). Open Q #5 partially captures; PRD should ship with a known-default-flex plan.
5. **Restore "Why this?" Detail Screen "reviews" element** OR explicitly drop it from §14.3 IA diagram with rationale.

---

_End of reconciliation. Generated for PRD input reconciliation only; no PRD text rewritten._
