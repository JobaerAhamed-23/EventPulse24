---
title: "Product Brief: EventPulse24"
status: draft
created: 2026-08-19
updated: 2026-08-19
project: EventPulse24
author: Jobaer
sources:
  - _bmad-output/innovation-strategy-2026-08-19.md
  - _bmad-output/design-thinking-2026-08-19.md
  - _bmad-output/blue-ocean-strategy-2026-08-19.md
---

# Product Brief: EventPulse24

> **The calm intelligence layer for the events that matter.**

---

## Executive Summary

EventPulse24 is an AI-powered event discovery and notification platform built around a single, contrarian premise: **users are drowning in events they didn't ask about, missing events they care about, and exhausted by notifications that don't respect their attention.** Every existing player — Eventbrite (ticketing), Meetup (community), Facebook Events (social), Google/Apple Calendar (passive storage) — optimizes for *more engagement, more notifications, more transactions.* None optimizes for *calm, intelligence, or signal-to-noise.*

EventPulse24 takes the opposite bet. It will be the **calm intelligence layer above all event sources** — global, national, local, and personal — that uses AI to surface the small number of events that actually matter to each user, and delivers them via context-aware, multi-tier reminders (5d/2d/1d/1hr) that *reduce* notification volume instead of adding to it.

The product unifies **personal** calendar events (birthdays, meetings, weddings) with **public** events (concerts, tech meetups, government programs, sports) into a single timeline with intelligent conflict detection — a capability no incumbent owns. The MVP ships as a web-first product with calendar sync, AI-curated daily "Pulse Digests" (3 cards), per-event reminder pickers, and explainable AI ("Why this?" micro-tags). Growth comes through SEO ("events near me") for cold-start, then viral group coordination ("Pulse the Group") for compounding network effects.

**Why now**: AI cost curves have collapsed, attention fatigue is acute, and no incumbent has incentive to cannibalize their engagement business by building calm. The window is 12–18 months before Apple/Google ship native AI calendar features at OS-level distribution. **EventPulse24 must win the consumer brand for "calm event intelligence" before the platform owners notice.**

---

## The Problem

### Real scenarios

**Maya, 32 — Senior product designer, Brooklyn.** Keeps a Google Calendar that mostly tracks work meetings. Her husband uses Apple Calendar. Their kid's school sends event flyers by email. Friends text about concerts. Meetup.com emails about tech meetups. Facebook Events surfaces things she doesn't care about. Eventbrite shows local shows. She finds out about 80% of events she attends through friends or accidental discovery — *not* through any app.

She misses things she cares about (a friend's birthday party because it wasn't in her calendar). She attends things she doesn't (a marketing email made it sound good, but it wasn't). She has 47 unread event newsletters. She turned off notifications on every event app she tried because they showed her irrelevant things.

### What today's tools get wrong

| Tool | Optimizes for | User experience |
|---|---|---|
| **Eventbrite** | Ticket sales revenue | Pushes promoted listings; UX optimized for transactions, not discovery |
| **Meetup** | Community growth | Local but narrow (group-based); no global coverage |
| **Facebook Events** | Time-on-app engagement | Social feed injected; FOMO-driven; declining relevance |
| **Google/Apple Calendar** | Time-blocking storage | Passive — knows nothing about public events; no recommendations |
| **Email newsletters** | Open-rate metrics | Volume-based; not personalized; ignored or unsubscribed |

### The cost of the status quo

- **Missed meaningful events**: lost personal moments, missed professional opportunities, FOMO anxiety
- **Notification fatigue**: users disable alerts on every event app; signal-to-noise ~5%
- **Decision paralysis**: too many events, too little time, no intelligent curation
- **Calendar fragmentation**: personal, work, family, and public events live in 4+ separate places
- **Group coordination hell**: "find a Saturday night for 5 friends" = 47 WhatsApp messages

---

## The Solution

### What we're building

A **single, trustworthy surface** where every event — global, national, local, personal — meets intelligent, calm curation and adaptive notifications.

### The core experience

**1. 30-Second Onboarding** — User connects their existing calendar (Google, Apple, Outlook) OR skips it. Immediately sees 3 relevant events in their city. No quiz, no forms.

**2. Pulse Digest (Home)** — Each morning, the user receives a 3-card brief:
- 1 must-know event (high personal relevance)
- 1 nearby event (location + interest match)
- 1 surprise (serendipity, outside their bubble)
- Each card shows "Why this?" as 3 keywords (`nearby, tonight, music`) and a 1–5 confidence pulse

**4. Unified Timeline** — Personal events (warm tones) and public events (cool tones) coexist in one calm week-view. Conflicts highlighted, never alarmed.

**5. Per-Event Reminder Picker** — For any event, user drags chips on a visual timeline: 5d / 2d / 1d / 1hr / custom. Default = "Pulse Ping" (one daily reminder replaces per-event spam).

**6. "Why this?" Detail Screen** — Tap any card to see: source badge (verified venue / official site / community), confidence level, similar events you've attended, neighbor count attending.

**7. Pulse the Group** *(Phase 2)* — Tap group → AI finds the best time slot + an event everyone would enjoy. Privacy-respecting availability heatmap. One tap to coordinate.

### The product principles (locked)

| Principle | Meaning |
|---|---|
| **Calm > Engagement** | Optimize for *fewer*, *better* notifications. The business model is misaligned with the metric — and that's the moat. |
| **Explainable AI** | Every recommendation shows its reasoning. "Why this?" is a feature, not a hidden cost. |
| **Calendar-sync-in, not replace** | Extend Google/Apple/Outlook. Don't fight OS-level distribution. |
| **3 cards max** | Decision fatigue is the enemy. Pulse Digest is bounded by design. |
| **Trust through transparency** | Source badges, confidence pulses, no hidden ranking algorithms. |

---

## What Makes This Different

### Honest assessment of the moat

| Moat Type | Strength | Why |
|---|---|---|
| **Brand positioning ("calm intelligence layer")** | Strong | First-mover in a category no incumbent has incentive to enter. Incumbents monetize engagement; calm is anti-engagement. |
| **Proprietary event corpus** | Building | Web-scale AI aggregation creates a data corpus that improves daily. The longer we run, the harder to copy. |
| **User preference graph** | Building | Per-user behavior (swipes, saves, dismisses) trains a personalization model. Cold-start is the gap. |
| **Network effects** | None yet (Phase 2) | Solo use has no lock-in. Group coordination is the unlock. |
| **Technical moat (LLM capability)** | Weak | LLM is commoditizing. The moat is the *data*, not the model. |
| **Distribution** | Weak | No OS-level access. SEO + community is the path. |

### How we win

We **don't compete** with Eventbrite (ticketing), Meetup (community), Facebook Events (social), or Google Calendar (storage). We **change the question**:

| Red Ocean Question | Blue Ocean Question |
|---|---|
| "What events exist?" | "What events matter to me, calmly?" |
| "Get users to attend more events" | "Help users spend time well on events" |
| "Monetize transactions" | "Monetize calm" |
| "More notifications = better" | "Fewer, smarter notifications = better" |
| "Catalog size wins" | "Personalization quality wins" |

**What we eliminate** (the industry's red ink we refuse to take on): ticketing infrastructure, social features, creation UI, push notification volume, long onboarding.

**What we create** (the uncontested space): Pulse Digest, "Why this?" explainability, conflict-aware scheduling, unified personal+public timeline, group coordination AI, travel mode, voice quick-add.

---

## Who This Serves

### Primary persona — "The Overwhelmed Professional"

**Maya, 32** — Senior product designer at a mid-size SaaS company. Lives in Brooklyn. Married, two young kids. Active in local running club, casual tech meetup attendee, family birthday-tracker.

**Her job-to-be-done**: *"Help me spend my time on experiences that matter to me, without the noise."*

**Her pains**:
- Notification blindness (disables alerts on most apps)
- FOMO anxiety (misses things, attends things she shouldn't)
- Calendar fragmentation (work / personal / family / public = 4 surfaces)
- Trust gap with AI ("Why am I being shown this?")
- Group coordination is hidden hell

**Her success moment**: Opens Pulse in the morning, sees 3 relevant events in 15 seconds, sets a 2-day reminder for the one she likes, ignores the rest without guilt. Done.

### Secondary personas (Phase 2+)

- **The Group Coordinator** — Plans weekends, dinners, activities for friend groups. Needs "Pulse the Group."
- **The Traveler** — Visits new cities monthly; needs hyperlocal event discovery without setting up a new profile each time.
- **The Parent** — Manages kids' events (school, sports, birthday parties) alongside personal/professional commitments. Needs unified family calendar.

### Non-consumers we unlock

The 60% of adults who don't currently use event apps because they're "too noisy" or "too complicated." Our mobile-first, zero-setup, smart-by-default UX unlocks them.

---

## Success Criteria

### North star metric
**% of users who report Pulse made their week better** (weekly NPS-style survey). Target: >40% by Month 6.

### Leading indicators (early signals — Weeks 1–8)
| Metric | Target | Why |
|---|---|---|
| Time-to-first-relevant-event | <30 seconds | Validates onboarding speed hypothesis |
| Pulse Digest daily open rate | >60% | Validates the 3-card format hypothesis |
| Onboarding completion rate | >85% | Validates calendar-connect flow |
| "Why this?" trust score | >70% | Validates explainability hypothesis |
| Per-event reminder setup rate | >80% | Validates multi-tier reminder UI |
| D7 retention | >40% | Validates core value hypothesis |
| Notification suppression rate | >30% | Signal of intelligence working |

### Lagging indicators (business outcomes — Months 2–12)
| Metric | Target |
|---|---|
| Monthly Active Users (MAU) | 100K by Month 6, 1M by Month 18 |
| Pro paid conversion rate | >5% |
| Net Revenue Retention | >110% |
| LTV/CAC ratio | ≥3 |
| Viral coefficient (invites per user) | >0.5 |
| AI cost per user per month | Trend down (cache + batch + on-device) |

### Decision gates
- **Gate 1 (Month 3)**: SEO traction + D7 retention >40% → ship MVP + invest in growth
- **Gate 2 (Month 9)**: Freemium conversion + group feature adoption → continue vs. pivot to B2B
- **Gate 3 (Month 18)**: Unit economics + viral coefficient >0.5 → scale, else niche focus

---

## Scope

### ✅ IN for MVP (Months 0–6)

| Feature | Description | Source |
|---|---|---|
| **Pulse Digest (3 cards/day)** | Daily morning brief | Design Thinking #1, Blue Ocean Create |
| **Multi-tier reminders (5d/2d/1d/1hr)** | Per-event reminder picker | Scope doc core feature |
| **"Why this?" micro-tag** | 3-keyword reasoning on each card | Design Thinking, Blue Ocean Create |
| **Confidence Pulse** | 1–5 dots showing AI certainty | Design Thinking |
| **Source Badge** | Verified venue / official / community | Blue Ocean Create |
| **30-second onboarding** | Calendar connect OR skip | Design Thinking #2 |
| **Public event discovery (SEO)** | "Events near me [city]" pages | Innovation Strategy Phase 1 |
| **Pulse Preview** | 3 events before signup wall | Design Thinking Onboarding |
| **Personal calendar manual add** | Create personal events with voice quick-add | Scope doc |
| **Basic AI event extraction** | Crawl 20 sources, extract structured events | Innovation Strategy Phase 1 |
| **Pulse Ping** | Single daily notification replaces spam | Design Thinking |
| **AI cost dashboard** | Per-feature cost tracking from day 1 | Innovation Strategy |

### ❌ OUT for MVP (deferred to Phase 2+)

| Feature | Reason for deferral | Target Phase |
|---|---|---|
| Personal+Public unified timeline | Requires calendar sync; complex | Phase 2 |
| Conflict-aware scheduling | Needs unified timeline first | Phase 2 |
| Pulse the Group (viral loop) | Needs trust established first | Phase 2 |
| Google/Apple/Outlook calendar sync | Complex OAuth + sync infra | Phase 2 |
| Travel Mode | Requires trip detection logic | Phase 3 |
| Voice Quick-Add (full) | Showcase feature, not core | Phase 3 |
| Email-to-Event forwarding | Niche; power user only | Phase 3 |
| On-Device Personal AI | Privacy + cost optimization | Phase 3 |
| Group availability heatmap | Needs group features built | Phase 3 |
| White-label B2B2C | Year 2+ only | Phase 3 |
| B2B Insights API | Year 2+ only | Phase 3 |

### Explicitly OUT (will never build)

| Feature | Why |
|---|---|
| Ticketing infrastructure | Capital-heavy, low-margin, distracts from intelligence. Affiliate to Eventbrite/Ticketmaster. |
| Social features / friend activity feeds | Engagement trap; reinforces FOMO. |
| Event creation UI for organizers | Not our job. We're a consumer intelligence layer. |
| Ad-supported revenue | Direct conflict with "calm" positioning. |
| Real-time trending carousels | Manufactures FOMO. |

---

## Vision

### Year 1 (MVP → Growth)
The calm, AI-curated event discovery app for knowledge workers. 100K MAU across 25 cities. Pulse Digest + multi-tier reminders + explainable AI as the core. SEO-driven acquisition. Freemium monetization live.

### Year 2 (Network Effects)
Unified personal+public timeline ships. Group coordination "Pulse the Group" launches — the viral loop kicks in. 1M MAU. B2B2C pilots with 5 universities + 3 tourism boards. International expansion begins (South/Southeast Asia).

### Year 3 (Defensible Moat)
Travel Mode + Voice Quick-Add + On-Device Personal AI live. B2B Insights API generates 20% of revenue. 5M+ users. Proprietary event corpus + user preference graph create defensible moat. Considered the **"Headspace of events"** — synonymous with calm event intelligence.

### The 3-year ambition
> **EventPulse24 becomes the default intelligent surface for time and experience — the layer between humans and the chaos of scattered event information.**

Not an event app. An *AI time co-pilot* that happens to know every event in the world.

---

## Open Questions (for Product + Engineering to resolve)

| # | Question | Owner | Phase |
|---|---|---|---|
| 1 | Which 20 event sources to crawl for MVP? (Mix of official sites, aggregators, niche blogs?) | Eng + Product | Pre-launch |
| 2 | Calendar sync vendor — build vs. partner with Nylas/SyncGene? | Eng | Phase 2 prep |
| 3 | LLM provider strategy — single vendor (OpenAI/Anthropic) vs. multi-model? | Eng + CTO | Pre-launch |
| 4 | Pricing for Pro tier — $4.99/mo vs. $7.99/mo vs. annual-only? | Product | Pre-launch |
| 5 | Should we seed Pulse Digest with 1 must-know + 1 nearby + 1 surprise, or rank dynamically? | Product + Data | Post-MVP |
| 6 | Geographic beachhead — 3 US cities (NYC, SF, Austin) or 1 city deeply? | Product + Marketing | Pre-launch |
| 7 | Funding runway — bootstrap vs. seed round vs. angel? | Founder | Pre-launch |
| 8 | Founding team gaps — who's the technical co-founder, AI/ML lead, designer? | Founder | Pre-launch |

---

## Risks & Mitigations (top 5)

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Apple/Google add AI to native calendar** | Medium | Critical | Web-first, cross-platform, brand moat; move fast on consumer brand before OS-level copy |
| **AI inference costs spiral** | Medium | High | Aggressive caching, batching, on-device AI for personal data; per-feature cost targets from day 1 |
| **Web crawling legally blocked** | High | High | Pivot to partnerships with event platforms; legal review on every source |
| **Cold start unsolved (personalization requires data)** | High | Critical | SEO flywheel for public events first; personalization is Phase 2 unlock |
| **Incumbent copycat (Eventbrite ships Pulse Digest)** | Very High | Medium | Brand + data moat by then; Pulse Digest is a feature, calm is the brand |

**Backup plan**: If consumer traction fails by Month 9, pivot to B2B2C (white-label for universities/tourism boards) using same AI infrastructure.

---

_Generated using BMAD Product Brief Workflow. Synthesis sources: Innovation Strategy (JTBD + Force Field), Design Thinking, Blue Ocean Strategy documents._