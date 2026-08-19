# Addendum: EventPulse24 Product Brief

This addendum preserves depth that belongs in downstream documents (PRD, architecture, solution design) or earned a place in the conversation but does not fit the brief itself. It does not contain audit or override information — see `.memlog.md` for that.

---

## A. Synthesis Notes — How the 3 Strategy Documents Shaped This Brief

### From Innovation Strategy (JTBD + Force Field)

| Element | Source |
|---|---|
| 8 unmet jobs table → "the biggest unmet job" framing | JTBD analysis |
| Force Field Analysis → driving vs. restraining forces for opening positioning | Driving Forces: AI capability, notification fatigue backlash, personalization expectation |
| Strategic Options A/B/C → recommended "Hybrid A with B embedded, C deferred" | Innovation Strategy Step 7 |
| 6 hypotheses to validate → Open Questions + Success Criteria | H1–H6 mapped to leading indicators |
| 3-phase roadmap → Vision Year 1/2/3 | Execution Roadmap Phase 1/2/3 |
| Risks table (7 risks) → Top 5 risks selected for brief | Apple/Google, AI cost, web crawling, cold start, copycat |

### From Design Thinking

| Element | Source |
|---|---|
| Persona "Maya" → Primary Persona | Empathy Map primary persona |
| 8 affinity clusters → Problem framing | Cluster A (Trust) + B (Notifications) + D (Timeline) prioritized |
| Top 7 concepts → MVP feature IN list | Pulse Digest, 30-sec onboarding, reminder picker, unified timeline (Phase 2), group (Phase 2), Why this?, voice (Phase 3) |
| 7 ASCII wireframes → Solution narrative | All 7 concepts referenced in "Core experience" |
| Features to Test → Success Criteria leading indicators | 7 hypotheses mapped to measurable metrics |

### From Blue Ocean Strategy

| Element | Source |
|---|---|
| Tagline → brief subtitle | "The calm intelligence layer for the events that matter" |
| Four Actions → Scope IN/OUT structure | Eliminate: ticketing, social, creation UI, push spam, onboarding → OUT. Reduce: notifications, density → MVP constraints. Raise: AI quality, transparency → IN. Create: Pulse Digest, Why this?, conflict-aware scheduling, group, travel → Phase 2/3. |
| Strategy Canvas → "What Makes This Different" honest moat table | Brand + data + preference graph moats |
| Three Options A/B/C → Strategic direction | Hybrid A + B embedded, C deferred |
| 16 "create" factors → MVP scope | All 16 mapped to Phase 1/2/3 |

---

## B. Rejected Alternatives (Options-considered Matrix)

### Option B — "The Group Concierge" (Group-First Pivot)

**Why not chosen as primary**: 
- Cold-start is brutal (groups need other users)
- Coordination UX is hard to get right
- Solo value proposition is weaker; users need group context to commit

**Why kept as embedded feature (Phase 2)**:
- Group features create the network effect that solo use lacks
- Viral potential is the unlock for compounding growth
- Once solo use is excellent, group features are the *amplifier*, not the foundation

### Option C — "The B2B Intelligence" (White-Label for Organizations)

**Why not chosen for Year 1**:
- Slower scale; sales-heavy org required
- Less viral; less brand differentiation
- Pivots away from the original consumer vision (and the consumer-data moat)

**Why kept for Year 2+**:
- Faster revenue when ready
- Defensible per-client lock-in
- Uses same AI infrastructure built for consumer

### Option D (considered, rejected) — "Ad-Supported Free"

**Why rejected**: Direct conflict with "calm" positioning. Ad-driven metrics optimize for engagement, which is the *opposite* of what we're selling.

### Option E (considered, rejected) — "Ticketing Platform"

**Why rejected**: Capital-heavy infrastructure play. Distracts from the intelligence layer that is our actual differentiator. Affiliate to Eventbrite/Ticketmaster instead.

---

## C. Parked Roadmap Context

### Features intentionally deferred (with rationale)

| Feature | Deferred To | Rationale |
|---|---|---|
| Google/Apple/Outlook calendar sync | Phase 2 | OAuth + sync infra is complex; solo value can be proven without it |
| Conflict-aware scheduling | Phase 2 | Needs unified timeline as foundation |
| Pulse the Group | Phase 2 | Trust must be established first; solo must be excellent first |
| Travel Mode | Phase 3 | Requires trip detection logic (calendar/email parsing); nice-to-have |
| Voice Quick-Add | Phase 3 | Demo magnet, but adoption unlikely; showcase only |
| Email-to-Event | Phase 3 | Power-user feature; niche adoption expected |
| On-Device Personal AI | Phase 3 | Privacy + cost optimization; not core to MVP |
| Group availability heatmap | Phase 3 | Needs group features built first |
| White-label B2B2C | Year 2+ | Pivot option if consumer fails |
| B2B Insights API | Year 2+ | Revenue diversification; not core |

### Features explicitly NEVER building

| Feature | Why |
|---|---|
| Ticketing infrastructure | Capital-heavy; low-margin; distracts from intelligence |
| Social features / friend activity feeds | Engagement trap; reinforces FOMO |
| Event creation UI for organizers | Not our job |
| Ad-supported revenue | Conflicts with "calm" positioning |
| Real-time trending carousels | Manufactures FOMO |
| Account-required browsing | Reduces conversion; show value first |

---

## D. Persona Depth — Maya (Beyond What's in Brief)

**Demographics**: 32, female, senior product designer at mid-size SaaS company in Brooklyn. Married, 2 young kids (4 and 7). Household income ~$180K. Tech-savvy but not developer. Uses iPhone primarily; laptop for work.

**Daily tech stack**: Google Calendar (work), Apple Calendar (family), Gmail, Notion, Slack, Figma, Instagram, WhatsApp. Has tried and abandoned: Facebook Events, Meetup app, Eventbrite local, Bandsintown, Songkick.

**Quote**: *"I don't want MORE things to do. I want someone to tell me the 3 things actually worth doing this week."*

**Behavioral data**:
- Checks Google Calendar 5x/day
- Skims Facebook Events tab weekly
- Has 47 unread event newsletters
- Has missed 2+ close friend birthdays/year
- Disables push notifications on most apps within 1 week of install
- Manually copies dates from Eventbrite confirmation emails
- Asks spouse "what's this weekend?" instead of using any app

**Success moment with EventPulse24**: Opens Pulse in the morning → sees 3 relevant events → saves one → sets 2-day reminder → closes app. Total time: 30 seconds. **Doesn't open the app again until tomorrow's Pulse Digest.**

---

## E. Competitive Teardown — Detailed

### Eventbrite

**What they do well**: Massive event catalog; trusted ticketing; organizer tools; payments.
**Where they fail users**: Pushes promoted listings; UX optimized for transactions; no personal event handling; no global intelligence layer.
**Why we don't compete**: They're a ticketing infrastructure company. We don't sell tickets.
**Our play**: Affiliate to them. They win on transactions; we win on discovery intelligence.

### Meetup

**What they do well**: Strong community feel; group-based discovery; local in major US cities.
**Where they fail users**: Narrow scope (only Meetup groups); no global coverage; declining relevance post-pandemic; no AI curation.
**Why we don't compete**: They're a community company. We don't build tribes.
**Our play**: Show Meetup events in our Pulse Digest alongside everything else.

### Facebook Events

**What they do well**: Massive distribution; social graph integration.
**Where they fail users**: Engagement-driven; FOMO-reinforcing; declining trust; opaque ranking; declining event quality.
**Why we don't compete**: They're a social engagement company. We don't sell engagement.
**Our play**: Avoid social entirely. Compete on calm + intelligence.

### Google Calendar

**What they do well**: OS-level distribution (Android); strong APIs; trusted brand; calendar sync standard.
**Where they fail users**: No public event awareness; no recommendations; passive storage; no curation.
**Why we don't compete**: They're a storage company. We don't store time.
**Our play**: Sync INTO Google Calendar. Be the intelligence layer above it.

### Apple Calendar

**What they do well**: OS-level distribution (iOS); privacy positioning; tight hardware integration.
**Where they fail users**: Same as Google — passive; no public events; no recommendations.
**Why we don't compete**: Same as Google.
**Our play**: Same as Google. **Risk**: Apple could add AI features to native Calendar. Mitigation: web-first, cross-platform, brand moat.

### Other notable players

- **Bandsintown / Songkick** — music only; narrow scope; not a threat to general event intelligence
- **IRL** — attempted social event discovery, shut down 2023 (lesson: social doesn't monetize)
- **Posh** — premium event discovery; luxury niche; not mainstream
- **Partiful** — viral party planning; strong network effects in NYC; interesting group-coordination play but narrow (parties only)
- **Luma** — event hosting for tech community; growing; targets creators
- **Shotgun** — electronic music events; niche

**Key insight**: Most "event app" failures share one pattern — they tried to compete on engagement/social and got crushed by Facebook Events, then died. The survivors (Eventbrite, Meetup) won on transactions or community. **Nobody has won on intelligence + calm yet.**

---

## F. Technical Constraints & Considerations (for Architecture Phase)

### LLM Strategy
- **Decision needed**: Single vendor (OpenAI/Anthropic) vs. multi-model routing
- **Recommendation** [ASSUMPTION]: Start with Anthropic Claude for extraction (cost + quality), use OpenAI embeddings for similarity, evaluate Mistral or Llama for cost optimization at scale
- **Cost concern**: Per-event extraction is expensive. Aggressive caching + batching mandatory.

### Event Extraction Pipeline
- **Crawl approach**: Hybrid — official site partnerships > RSS feeds > careful web scraping (legal review per source)
- **Sources for MVP**: Mix of venue sites, tourism boards, university calendars, niche blogs, aggregators (where ToS permits)
- **Extraction**: LLM-based structured output (event name, date, location, category, source URL, confidence)
- **Deduplication**: Vector similarity + canonical URL matching

### User Preference Graph
- **Storage**: Graph DB (Neo4j or Memgraph) for user-event-source-category relationships
- **Cold-start**: SEO-derived interests (location + first event interactions)
- **Privacy**: On-device personal calendar parsing in Phase 3; server-side anonymized preference data only

### Notification Infrastructure
- **Delivery**: Multi-channel — email (primary for digest), push (mobile in Phase 2), SMS (critical reminders only), in-app
- **iOS/Android throttling risk**: Use email + in-app as fallback; don't depend on push
- **Time-of-day targeting**: User timezone + historical open times

### SEO & Content Flywheel
- **Strategy**: Every event has a public URL with structured data (Schema.org Event)
- **Target keywords**: "events near me [city]", "tech meetups [city]", "things to do [city] this weekend"
- **Content**: Auto-generated city guides, weekly event roundups

### Data Moat Building
- **Event corpus**: Every event crawled = proprietary data
- **User preferences**: Every swipe/save/dismiss = signal
- **Source reliability scores**: Each source has a track record; informs future ranking
- **Network effects**: Solo use → group use → community intelligence → better recommendations

---

## G. Funding & Team Considerations [ASSUMPTION]

### Capital Requirements (rough order of magnitude)
- **MVP build**: $50–150K (3-person team for 6 months: 1 full-stack eng, 1 AI eng, 1 designer/PM)
- **12-month runway**: $300–600K (5–7 people + infrastructure costs)
- **AI inference at scale**: Variable; design discipline required

### Team Gaps to Fill Pre-Launch
- Technical co-founder OR senior full-stack engineer (Rails/Next.js + PostgreSQL)
- AI/ML engineer (LLM prompt engineering, event extraction, vector search)
- Designer (UX-heavy product; calm aesthetic)
- Marketing/growth (SEO + Product Hunt + community)
- **Optional**: Senior advisor from event tech (Eventbrite alumni ideal)

### Funding Path Options
- Bootstrap: $0–$50K personal → revenue-funded growth (conservative, slower)
- Pre-seed: $250K–$500K angel round (faster MVP, more runway)
- Seed: $1M–$3M institutional (faster scale, more pressure)

**Recommendation** [ASSUMPTION]: Pre-seed angel round to fund 12-month MVP + initial growth, then Series A at 100K MAU + $1M ARR.

---

## H. Marketing & Launch Plan (high-level)

### Pre-Launch (Months 1–3)
- Landing page + waitlist
- "Pulse Preview" interactive demo (no signup)
- SEO foundation: city event pages with structured data
- Founder content: build-in-public on Twitter/LinkedIn, "calm event intelligence" thought leadership
- 10–20 beta users via personal network + targeted outreach

### Launch (Month 3–4)
- Product Hunt launch
- Reddit: r/productivity, r/nyc, r/sanfrancisco, r/brooklyn
- Hacker News (Show HN)
- Indie Hackers community
- Tech blog coverage (TechCrunch, The Verge, Wired productivity coverage)
- SEO: "events in [city]" pages rank for organic discovery

### Post-Launch (Months 4–12)
- Content marketing: weekly "Pulse Picks" city roundups
- Partnership outreach: event platforms, productivity tools, voice assistants
- Referral program (invite-based viral loop, in preparation for Phase 2)
- A/B testing every surface for retention

---

## I. References to Source Documents

- Innovation Strategy: `_bmad-output/innovation-strategy-2026-08-19.md`
- Design Thinking: `_bmad-output/design-thinking-2026-08-19.md`
- Blue Ocean Strategy: `_bmad-output/blue-ocean-strategy-2026-08-19.md`
- Original scope: `docs/scope.txt`

---

_This addendum captures content from the brief creation session that belongs in downstream artifacts (PRD, architecture, solution design, marketing plan) or was discussed but did not earn a place in the brief itself._