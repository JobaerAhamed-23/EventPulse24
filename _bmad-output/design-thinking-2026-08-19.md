# Design Thinking Session: EventPulse24

**Date:** 2026-08-19
**Facilitator:** Jobaer
**Design Challenge:** Design a calm, trustworthy, AI-first user experience for EventPulse24 that unifies personal + public event discovery and multi-tier notifications without contributing to notification fatigue.

---

## 🎯 Design Challenge

### Challenge Statement
How might we design a UX that feels 10× simpler than Eventbrite/Meetup/Facebook Events while giving users genuine intelligence about the events that matter to them — across global, local, and personal contexts — through adaptive, non-intrusive reminders (5d/2d/1d/1hr) that respect attention rather than exploit it?

---

## 👥 EMPATHIZE: Understanding Users

### Methods Selected
- **Empathy Mapping** — Visual representation of what users say, think, do, and feel.
- **User Interviews (hypothesized)** — Deep conversations about event discovery pain points.
- **Journey Mapping** — Document complete experience across touchpoints.
- **Diary Studies** — Capture authentic moments over time.

### 🎭 Primary Persona: "The Overwhelmed Professional" — Maya, 32

**Bio:** Senior product designer at a mid-size SaaS company. Lives in Brooklyn. Married, two young kids. Active in local running club, casual tech meetup attendee, family birthday-tracker.

### Empathy Map

```
                          ┌─────────────────────────────┐
                          │        THINKS / FEELS         │
                          │                                │
                          │ • "I keep missing things."     │
                          │ • "My phone buzzes too much."  │
                          │ • "Why am I finding out about  │
                          │    this concert AFTER it      │
                          │    happened?"                  │
                          │ • "Is this app just going to  │
                          │    spam me?"                   │
                          │ • "I wish my calendar just     │
                          │    KNEW what I care about."    │
                          │ • Anxiety: FOMO + overwhelm    │
                          │ • Trust: low for AI tools     │
                          └─────────────────────────────┘
                                       │
SAYS                                    │                              DOES
──────────────────────                  │              ─────────────────────────
"I don't have time to browse           │              • Checks Google Calendar 5x/day
 events."                                │              • Skims Facebook Events tab
"Why is this showing me                 │              • Asks spouse "What's this
 things I don't care about?"              │                weekend?"
"Just remind me about stuff I           │              • Has 47 unread email
 actually care about."                   │                newsletters
"There has to be a better               │              • Misses friend birthdays
 way than Doodle."                       │              • Manually copies dates from
                                        │                Eventbrite emails
──────────────────────                  │              • Disables push notifs on
                                        │                most apps after install
                                        │              ─────────────────────────
                                       │
                          ┌─────────────────────────────┐
                          │       PAINS / FEARS            │
                          │                                  │
                          │ • Notification blindness         │
                          │ • FOMO anxiety                    │
                          │ • Calendar fragmentation          │
                          │   (work/personal/family)         │
                          │ • Trust gap with AI ("why this?")│
                          │ • Decision fatigue from too      │
                          │   many choices                   │
                          │ • Discovery is mostly accidental  │
                          └─────────────────────────────┘
```

### User Insights

**1. Trust Paradox**: Users say they want AI curation but disable notifications from AI-curated apps within a week. Why? Because they get shown things they don't care about. Trust is *withdrawn* in advance and must be *earned back* through transparent recommendations.

**2. Discovery Is Accidental**: Maya finds out about 80% of events she attends through friends, not apps. Apps fail because they're not where the social signal originates.

**3. Calendar As Control Surface**: Users want their *existing* calendar to be smarter, not a *new* calendar. Sync-in beats sync-out.

**4. Reminder Threshold Is Personal**: A 5-day reminder annoys one user and reassures another. Default reminders don't work; per-event, per-context reminders do.

**5. Group Coordination = Hidden Job**: Maya's biggest event-related pain isn't discovery — it's "find a Saturday night that works for 4 friends." This job is currently done via 47 WhatsApp messages.

**6. Calm Is the Differentiator**: When asked what they want from an event app, "calm" comes up more than "smart" or "personal."

### Key Observations (The 7 Patterns)

| # | Observation | Implication |
|---|---|---|
| 1 | Users abandon apps after the first "wrong" notification | First impression matters more than feature breadth |
| 2 | Calendars are already a primary touchpoint | Don't build a new calendar — extend existing ones |
| 3 | People browse events when bored, not when planning | Discovery should be ambient, not pushy |
| 4 | "Save for later" is the most underused pattern | Users want a low-pressure "maybe" lane |
| 5 | Travel breaks the local-event loop | Trip detection is a UX unlock |
| 6 | Group chats are where event decisions happen | Coordination > discovery for viral loops |
| 7 | "Why am I seeing this?" is the #1 uninstall reason | Explainability must be visible by default |

---

## 🎨 DEFINE: Frame the Problem

### Point of View Statement
**Maya** (a busy professional) needs **a single, trustworthy surface for the events that matter to her** — global, local, and personal — **because** she's overwhelmed by fragmented information sources, suffers FOMO from missed events, and has lost faith in apps that show her irrelevant notifications. She needs the *intelligence without the noise*.

### Affinity Clusters (Problem Themes)

| Cluster | Description |
|---|---|
| **A. Trust & Explainability** | "Why am I seeing this?" — the #1 friction |
| **B. Notification Intelligence** | Multi-tier reminders that adapt to context |
| **C. Onboarding Friction** | 30-second target; pick interests in <5 swipes |
| **D. Unified Timeline** | Personal + public events in one view |
| **E. Discovery Without Doom** | Browse mode without decision paralysis |
| **F. Group Coordination** | Solve the "find a time for all of us" pain |
| **G. Travel & Context** | Auto-switch when user is in a new city |

### How-Might-We Questions (24 HMWs across 7 clusters)

#### Cluster A — Trust & Explainability
1. **HMW** make every recommendation feel earned, not guessed?
2. **HMW** show users *why* without overwhelming them with data?
3. **HMW** let users correct the AI so trust compounds over time?

#### Cluster B — Notification Intelligence
4. **HMW** make reminders feel like a friend checking in, not an alert?
5. **HMW** let users set per-event reminder timing (5d/2d/1d/1hr) without UI clutter?
6. **HMW** automatically suppress reminders the user has already seen/acted on?
7. **HMW** use location + context to know *when* to ping (commute, lunch, evening)?

#### Cluster C — Onboarding Friction
8. **HMW** get users to their first "wow" event in under 30 seconds?
9. **HMW** learn preferences through actions (swipe, save, ignore) rather than forms?
10. **HMW** skip the "interests quiz" entirely and infer from connected calendars?

#### Cluster D — Unified Timeline
11. **HMW** show personal and public events in one calm timeline without visual clutter?
12. **HMW** detect conflicts intelligently and suggest resolutions?
13. **HMW** color-code by source (personal vs. public) without being noisy?

#### Cluster E — Discovery Without Doom
14. **HMW** present a daily "3 things worth your time" digest instead of infinite scroll?
15. **HMW** make browsing feel like flipping a magazine, not shopping a catalog?
16. **HMW** add serendipity through "trending near you" without creating FOMO?

#### Cluster F — Group Coordination
17. **HMW** make "find a time for all of us" feel like one tap, not 20 messages?
18. **HMW** suggest events the *group* would enjoy, not just events nearby?
19. **HMW** respect group privacy (no one sees everyone's full calendar)?

#### Cluster G — Travel & Context
20. **HMW** auto-detect travel via calendar/email without manual input?
21. **HMW** switch to hyperlocal discovery automatically when in a new city?
22. **HMW** bring "home" event patterns back when user returns?

#### Cluster H — Productivity Boosters
23. **HMW** add events by voice in one sentence ("dinner with Sarah Friday 8pm")?
24. **HMW** let users share an event with one tap that auto-formats for any platform?

### Key Insights (Top 5)

1. **Insight #1 — Trust is the gate**: No feature matters until users trust the recommendations. Build trust first, features second.
2. **Insight #2 — Calm is a feature**: The act of *not* notifying is itself a feature. Build "Quiet Hours" and "Suppression Intelligence" into MVP.
3. **Insight #3 — Calendar is the canvas**: Don't fight Google/Apple Calendar. Extend them. Sync-in > replace.
4. **Insight #4 — First 30 seconds decide retention**: Onboarding must produce a "wow" event within 30 seconds or users churn.
5. **Insight #5 — Group coordination is the viral loop**: Solo use has no network effect. Group features drive invites.

---

## 💡 IDEATE: Generate Solutions

### Selected Methods
1. **Crazy 8s** — 8 quick UX sketches per problem area to push past obvious solutions.
2. **SCAMPER** — Apply 7 lenses (Substitute/Combine/Adapt/Modify/Purposes/Eliminate/Reverse) to existing event app patterns.
3. **Analogous Inspiration** — Borrow UX patterns from non-event domains: meditation apps (calm), dating apps (swipe), news readers (digest), fitness apps (streaks).

### Generated Ideas (40+ Concepts)

#### Onboarding (Target: <30 seconds to first wow)
1. **Magic Calendar Connect** — One-tap Google/Apple/Outlook import; AI pre-fills interests in 5 seconds.
2. **Swipe-to-Train** — Tinder-style card stack of 10 events; swipes teach the AI (no quiz).
3. **Location Auto-Discover** — On launch, immediately surface 3 events near user right now.
4. **"Pulse Preview"** — Before signup, show a live 3-card digest of *their city's* events today. No signup wall.
5. **Voice Onboarding** — "Tell me what you love" → 5-second voice sample → inferred interests.
6. **Social Proof Onboarding** — "47 of your city neighbors are tracking X" → instant FOMO-relief.

#### Discovery & Pulse Digest
7. **Daily "Pulse" — 3 cards max** — Morning brief: 1 must-know, 1 nearby, 1 surprise.
8. **Mood Cards** — "I want to learn" / "I want to move" / "I want to chill" → curated list.
9. **Time-Travel Mode** — "Show me what's happening this Saturday" / "next month" / "tonight."
10. **Surprise Me Button** — One tap, one curated event outside your bubble.
11. **Pulse Streak** — Daily check-in streak; gamify calm (no FOMO mechanic).
12. **Trending Near You** — Top 5 events by neighbors; ambient signal, no ranking algorithm.

#### Personal + Public Unified Timeline
13. **Two-Lane View** — Personal on left, public on right, conflict-detected in middle.
14. **Color Calm** — Personal = warm tones, public = cool tones; never alarms red.
15. **"Pulse Merge"** — Toggle: show only conflicts / show everything / show only public.
16. **Conflict Cards** — When overlap detected: "You have dinner at 7 + a tech meetup at 7:30 nearby. Skip one?"
17. **Time Block Heatmap** — Week view showing personal commitments + public options as density map.
18. **"Quiet Day" Mode** — Hide public events entirely on busy personal days.

#### Notification Intelligence (5d/2d/1d/1hr)
19. **Per-Event Reminder Picker** — Visual clock with drag-to-set chips (5d, 2d, 1d, 1hr, custom).
20. **Context-Aware Delivery** — Reminders wait for natural break times (lunch, commute, evening).
21. **"Pulse Ping"** — Single daily ping replaces 10 separate notifications.
22. **Already-Handled Detection** — If user added event to calendar or RSVP'd elsewhere, suppress.
23. **Escalation Ladder** — Soft → firm → urgent based on user response history.
24. **"Snooze Cluster"** — Snooze all event reminders for 2 hours during focus mode.

#### Group Coordination (Viral Loop)
25. **"Pulse the Group"** — Tap group → AI finds free time + event everyone would enjoy.
26. **Group Availability Heatmap** — Visual grid of friend free/busy (privacy-respecting).
27. **Quick Vote** — 3 options, group votes, winner auto-schedules.
28. **Shared Wishlist** — Group saves events together; AI surfaces overlap.

#### Trust & Explainability
29. **"Why this?" micro-tag** — Every event card shows source + reason (3-word tag: "nearby, tonight, music").
30. **Confidence Pulse** — 1–5 dots showing AI confidence per recommendation.
31. **Thumbs Magic** — One-tap feedback ("not for me", "more like this", "show less") → AI adapts visibly.
32. **Source Badge** — "Verified by venue" / "From official site" / "Community-reported" on each card.

#### Productivity Boosters
33. **Voice Quick-Add** — "Add Sarah's birthday, March 15" — natural language parsing.
34. **Email-to-Event** — Forward a confirmation email → AI extracts event + adds to timeline.
35. **Quick-Share** — Tap event → choose platform → auto-formatted preview.
36. **Travel Auto-Switch** — Detects trip via email/calendar → switches to destination city.
37. **"Don't Forget" Card** — Pre-event morning card: 3 logistics (where, when, what to bring).

#### Analogous Inspiration Patterns
38. **Headspace-style Calm Animation** — Loading states use breathing animations, not spinners.
39. **Spotify-Wrapped for Events** — "Your Year in Pulse" — annual recap.
40. **Duolingo Streak** — Daily check-in streak (gentle, not punitive).
41. **Apple Wallet Integration** — Tickets + reminders + maps in one place.
42. **Notion-style Block Customization** — User customizes their home view.

### Top Concepts (Selected for Prototyping)

| Rank | Concept | Why Selected |
|---|---|---|
| **#1** | **Pulse Digest (3 cards/day)** | The single core differentiator; defines the brand |
| **#2** | **30-Second Onboarding (calendar connect + swipe)** | Retention-critical; validates hypothesis fast |
| **#3** | **Per-Event Reminder Picker (5d/2d/1d/1hr)** | Core feature from scope; needs UX care |
| **#4** | **Unified Two-Lane Timeline** | The defensible moat |
| **#5** | **Group "Pulse the Group"** | Viral loop; future engine |
| **#6** | **"Why this?" Micro-tag + Confidence Pulse** | Trust foundation |
| **#7** | **Voice Quick-Add** | Productivity showcase; demo magnet |

---

## 🛠️ PROTOTYPE: Make Ideas Tangible

### Prototype Approach
- **Fidelity**: Low-fi paper + Figma wireframes. NOT polished design.
- **Speed**: 1 week for MVP prototype covering all 7 concepts.
- **Tools**: Figma (wireframes), paper sketches (Crazy 8s), Wizard-of-Oz for AI features.
- **What's real**: Visual layout, navigation flow, content tone.
- **What's faked**: AI recommendations (curated manually), calendar sync (pre-populated data), notification timing (manual triggers).

### Prototype Description (The 7 Screens)

#### Screen 1: Onboarding (30-Second Flow)
```
┌─────────────────────────────────�
│   Welcome to Pulse              │
│                                 │
│   Connect your calendar         │
│   [Google] [Apple] [Outlook]    │
│                                 │
│   Or skip →                     │
│                                 │
│   ┌───────────────────────────┐ │
│   │ "Pulse Preview"           │ │
│   │ 3 events in your city     │ │
│   │ happening today           │ │
│   │ [See them now →]          │ │
│   └───────────────────────────┘ │
└─────────────────────────────────┘
```
**Time to first event:** ~15 seconds.

#### Screen 2: Pulse Digest (Home)
```
┌─────────────────────────────────┐
│ Good morning, Maya ☀️           │
│ 3 things worth your time today  │
│                                 │
│ ┌─────────────────────────────┐ │
│ │ 🎵 Brooklyn Steel — Live    │ │
│ │ Indie Night • 8pm • 0.8mi   │ │
│ │ Why: nearby, music, tonight │ │
│ │ ●●●●○  Confidence           │ │
│ │ [Save] [Skip] [Details]     │ │
│ └─────────────────────────────┘ │
│ ┌─────────────────────────────┐ │
│ │ 🏃 Brooklyn Run Club        │ │
│ │ 6:30am tomorrow • Prospect  │ │
│ │ Why: trending near you      │ │
│ │ ●●●○○                       │ │
│ └─────────────────────────────┘ │
│ �─────────────────────────────┐ │
│ │ 🎂 Sarah's Birthday Party   │ │
│ │ Sat 7pm • DUMBO (personal)  │ │
│ │ Why: from your calendar     │ │
│ │ ●●●●●                       │ │
│ └─────────────────────────────┘ │
└─────────────────────────────────┘
```

#### Screen 3: Timeline (Unified)
```
┌─────────────────────────────────┐
│  This Week                      │
│                                 │
│  Mon ● Lunch with Sam 12pm      │
│       ● Tech meetup 7pm         │
│  Tue ● (Quiet — no public)      │
│  Wed ● Concert 8pm              │
│       ⚠️ Conflicts with: dinner │
│  Thu ● Yoga 7am                 │
│  Fri ● Trivia night (trending)  │
│  Sat ● Sarah's birthday 7pm     │
│  Sun ● Open                     │
└─────────────────────────────────┘
```

#### Screen 4: Per-Event Reminder Picker
```
┌─────────────────────────────────┐
│  Remind me for:                 │
│                                 │
│  ●─────●─────●─────●─────●      │
│  5d    2d    1d    1hr   At     │
│                                 │
│  [Custom time]                  │
│                                 │
│  Delivery: [Pulse Ping ▾]       │
│  Quiet hours: 10pm–8am         │
│                                 │
│  [Save reminder]                │
└─────────────────────────────────┘
```

#### Screen 5: Group "Pulse the Group"
```
┌─────────────────────────────────┐
│  Pulse the Group                │
│  👥 Weekend Crew (5)            │
│                                 │
│  Best time for all: Sat 7–9pm   │
│                                 │
│  Suggested:                     │
│  ┌───────────────────────────┐ │
│  │ Comedy night @ The Stand  │ │
│  │ Sat 8pm • 3 love it       │ │
│  │ [Vote] [See details]      │ │
│  └───────────────────────────┘ │
└─────────────────────────────────┘
```

#### Screen 6: Conflict Detection
```
┌─────────────────────────────────┐
│  ⚠️ Heads up                    │
│                                 │
│  Wed 8pm Concert               │
│  vs.                            │
│  Wed 7pm Dinner (personal)     │
│                                 │
│  15-min gap, 2.4mi apart        │
│                                 │
│  [Move dinner earlier]          │
│  [Skip concert]                 │
│  [Keep both — I'll manage]      │
└─────────────────────────────────┘
```

#### Screen 7: "Why this?" Detail
```
┌─────────────────────────────────┐
│  Comedy Night @ The Stand       │
│                                 │
│  Why we're showing this:        │
│  � 0.6mi from your location    │
│  🎤 Comedy is in your top 3     │
│  👥 12 of your neighbors going  │
│  ⭐ 4.7 (213 reviews)          │
│                                 │
│  Source: Official venue site    │
│  Added 2 hours ago              │
│  Confidence: ●●●●○              │
└─────────────────────────────────�
```

### Features to Test (With Hypotheses)

| # | Feature | What We're Testing | Hypothesis |
|---|---|---|---|
| 1 | 30-second onboarding | Time to first "wow" event | <30s = >60% activation |
| 2 | Pulse Digest (3 cards) | Daily open rate | >60% open = strong retention signal |
| 3 | "Why this?" micro-tag | Trust score | >70% trust score |
| 4 | Per-event reminder picker | Set-up completion rate | >80% complete at least 1 |
| 5 | Unified timeline | Time spent in view | >2min avg = stickiness |
| 6 | Group coordination | Invite rate per user | >0.5 invites/user = viral signal |
| 7 | Voice quick-add | Adoption rate | >20% try = productivity hit |

---

## ✅ TEST: Validate with Users

### Testing Plan

#### Recruitment
- **Target**: 7 users per concept (industry standard for usability).
- **Segmentation**: 3 busy professionals (Maya persona), 2 students, 2 parents.
- **Channel**: Product Hunt waitlist, Reddit r/productivity, LinkedIn outreach.
- **Compensation**: $50 gift card + lifetime Pro.

#### Method
- **Moderated remote usability** (Zoom + screen share).
- **Tasks** (5 per user):
  1. "Set up your account and find an event for tonight."
  2. "Add a reminder 2 days before your favorite upcoming event."
  3. "Show me what's happening this weekend."
  4. "Plan a Saturday night for you and 2 friends."
  5. "Explain why you're showing me this event."
- **Post-test survey** + Feedback Capture Grid.

#### Metrics
- Time-on-task
- Error rate
- SUS (System Usability Scale) score — target >75
- Qualitative pain points
- Net Promoter Score (NPS) — target >40

### User Feedback (Anticipated Patterns)

#### What Will Likely Work
- ✅ **Pulse Digest (3 cards)**: Users consistently prefer bounded choices; this mirrors Headspace/Calm UX patterns.
- ✅ **"Why this?" tag**: Trust-building pattern proven in Spotify, TikTok; expected to score well.
- ✅ **30-second onboarding**: Calendar-connect flow is the fastest path to relevance; expected to beat interest-quiz competitors.
- ✅ **Voice Quick-Add**: Demo magnet; will likely be shared on social.

#### What Will Likely Struggle
- ⚠️ **Group coordination**: Privacy concerns may surface; users will want control over what's visible to others.
- ⚠️ **Per-event reminder picker**: Users may want fewer choices ("just default to 1 day + 1 hour").
- ⚠️ **Unified timeline**: Visual clutter if not carefully designed; needs testing for density.

#### Surprises to Watch For
- 🟡 Users may want **more than 3 cards** in Pulse Digest (counter to our hypothesis).
- 🟡 "Why this?" may feel patronizing if too detailed.
- 🟡 Travel Mode may be expected even without explicit trip detection (calendar heuristic).

### Key Learnings (Hypothesized)

1. **Pulse Digest's "3 cards" may need to be dynamic** — power users want 5–7; new users want 1–2.
2. **"Why this?" works best as 3 keywords, not paragraphs** — "nearby, tonight, music" beats full explanations.
3. **Group features drive viral loops only after trust is established** — solo use must be excellent first.
4. **Notification timing matters more than notification count** — one well-timed reminder beats ten poorly-timed.
5. **Onboarding must produce visible value immediately** — calendar connect + 3 relevant events in 30 seconds is the magic number.

---

## 🚀 Next Steps

### Refinements Needed

1. **Refine Pulse Digest to be adaptive** — Default 3 cards for new users; expand to 5–7 for engaged users.
2. **Simplify "Why this?" to 3 keywords** — Visual chips, not paragraphs.
3. **Pre-test Group features with solo value** — Lock group features behind solo-use quality threshold.
4. **Build notification intelligence from day 1** — Even basic time-of-day targeting beats current alternatives.
5. **Add "Skip for now" everywhere** — Users must never feel locked into recommendations.
6. **Test voice quick-add as a hidden demo feature** — Use it as marketing, not core onboarding.
7. **Build explainability into every recommendation, not a separate screen** — Inline trust beats click-to-reveal.

### Action Items

| Priority | Action | Owner | Sequence |
|---|---|---|---|
| P0 | Finalize Figma wireframes for 7 core screens | Designer | Week 1 |
| P0 | Recruit 7 usability testers per concept | PM | Week 1 |
| P1 | Run 5 moderated usability tests | UX Researcher | Week 2 |
| P1 | Synthesize Feedback Capture Grid | UX Researcher | Week 2 |
| P1 | Refine wireframes based on test insights | Designer | Week 3 |
| P2 | Build Wizard-of-Oz prototype for AI features | Engineer | Week 3 |
| P2 | Run A/B test on Pulse Digest card count (3 vs. 5) | PM + Data | Week 4 |
| P3 | Test group features with engaged users | UX Researcher | Week 6 |
| P3 | Iterate on "Why this?" content density | Designer | Week 6 |

### Success Metrics

#### Leading Indicators (Week 1–4)
- Onboarding completion rate: target >85%
- Time to first "wow" event: target <30 seconds
- SUS (System Usability Scale) score: target >75
- Pulse Digest daily open rate: target >60%
- Per-event reminder set-up rate: target >80%

#### Lagging Indicators (Month 1–6)
- D7 retention: target >40%
- D30 retention: target >25%
- Monthly active users (MAU)
- Viral coefficient (invites per user): target >0.5
- Notification suppression rate (reminders not delivered because user acted): target >30% (signal of intelligence)
- NPS: target >40

#### Decision Gates
- **Gate 1 (Week 4)**: SUS >75 + onboarding completion >85% → ship MVP.
- **Gate 2 (Week 8)**: D7 retention >40% + Pulse Digest open >60% → invest in group features.
- **Gate 3 (Week 12)**: Viral coefficient >0.3 → double down on group; else solo-first.

---

_Generated using BMAD Creative Intelligence Suite - Design Thinking Workflow_
