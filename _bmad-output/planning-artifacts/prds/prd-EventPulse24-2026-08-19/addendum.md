# Addendum: EventPulse24 PRD

This addendum preserves depth from the discovery conversation and source documents that belongs in downstream artifacts (Architecture, Solution Design, UX Spec, Marketing Plan) or earned a place in the discussion but does not fit in the PRD itself. It does **not** contain audit or override information — see `.memlog.md` for that.

---

## A. Synthesis Notes — How the Inputs Shaped the PRD

### From Product Brief

| Element | Source | Where in PRD |
|---|---|---|
| 30-second onboarding → FR-1 | Brief "Core experience #1" | §4.1 |
| Pulse Digest (3 cards/day) → FR-5, FR-6 | Brief "Core experience #2" | §4.2 |
| Multi-tier reminders → FR-9 | Scope doc core + Brief "Core experience #5" | §4.3 |
| "Why this?" micro-tag → FR-21 | Brief "Core experience #6" | §4.6 |
| Confidence Pulse → FR-22 | Design Thinking | §4.6 |
| Source Badge → FR-23 | Blue Ocean | §4.6 |
| Pulse Ping → FR-10 | Brief "Core experience #5" | §4.3 |
| Public event SEO → FR-26, FR-27 | Innovation Strategy Phase 1 | §4.7 |
| Pulse Preview → FR-2 | Design Thinking Onboarding | §4.1 |
| Personal event manual → FR-18 | Scope doc | §4.5 |
| AI event extraction → FR-14 | Innovation Strategy Phase 1 | §4.4 |
| AI cost dashboard → FR-29 | Innovation Strategy | §4.8 |
| MVP-deep + Phase 2/3 named FRs | User confirmation | §4.9 |
| Explicit guardrails, light compliance detail | User confirmation | §10.1 |

### From 2025-2026 Landscape Research

| Finding | Source | PRD impact |
|---|---|---|
| Apple Intelligence + Gemini in Calendar cover "smart calendar" lane | Subagent 1 | §1 Vision reframing; §12 Why Now; Risk #1 mitigation |
| Luma is closest functional neighbor | Subagent 1 | Risk #6 added; positioning emphasizes cadence + explainability as differentiators |
| HiQ v. LinkedIn (2023) — public scraping defensible but ToS matters | Subagent 1 | §10.1 Compliance; FR-17 acquisition hierarchy |
| LLM extraction: Pydantic + Instructor + constrained decoding is production standard | Subagent 2 | FR-14 default architecture |
| Dedup: hybrid canonical URL + normalized time + embedding sim (cosine 0.85-0.95) | Subagent 2 | FR-15 algorithm |
| Cost benchmarks: <$0.005/event blended | Subagent 2 | FR-14 cost target; §7.2 SM-C5; §10.3 |
| `apns-priority: 10` + `collapse-id` for multi-tier reminders | Subagent 3 | Phase 2 FR (mobile) behavioral note |
| Email digest = transactional stream, RFC 8058 unsubscribe | Subagent 3 | FR-11 consequences; §10.1 |
| `interruption-level` quiet-me for 1hr ping | Subagent 3 | FR-9 Phase 2 mobile behavior |
| Research subagent search gap (2 of 4 returned no live results) | Subagent 1 + 3 | Open Q #11 |

---

## B. Rejected Alternatives (Options-considered Matrix)

### Option B — "The Group Concierge" (Group-First Pivot)

**Why not chosen as primary for MVP:**
- Cold-start is brutal (groups need other users)
- Coordination UX is hard to get right
- Solo value proposition is weaker; users need group context to commit

**Why kept as embedded feature (Phase 2 — FR-34):**
- Group features create the network effect that solo use lacks
- Viral potential is the unlock for compounding growth
- Once solo use is excellent, group features are the *amplifier*, not the foundation

### Option C — "The B2B Intelligence" (White-Label for Organizations)

**Why not chosen for Year 1:**
- Slower scale; sales-heavy org required
- Less viral; less brand differentiation
- Pivots away from the original consumer vision (and the consumer-data moat)

**Why kept for Year 2+ (FR-42, FR-43):**
- Faster revenue when ready
- Defensible per-client lock-in
- Uses same AI infrastructure built for consumer

**Pivot path:** Consumer traction fails by Month 9 → pivot to B2B2C for universities/tourism boards.

### Option D — "Ad-Supported Free"

**Why rejected:** Direct conflict with "calm" positioning. Ad-driven metrics optimize for engagement, which is the *opposite* of what we're selling.

### Option E — "Ticketing Platform"

**Why rejected:** Capital-heavy infrastructure play. Distracts from the intelligence layer that is our actual differentiator. Affiliate to Eventbrite/Ticketmaster instead.

### Option F — "Native Mobile First"

**Why rejected for MVP:** Web-first is faster to ship, lower-cost, and avoids app-store friction. Mobile is Phase 2 — but the codebase is responsive-first so the mobile app is a thin native shell.

### Option G — "Always-On Push"

**Why rejected:** The "calm" bet. Single daily Pulse Ping is the product's differentiation. Push cascades would recreate the engagement-trap.

### Option H — "Multi-Model LLM Routing from Day 1"

**Why deferred:** Multi-model routing adds complexity. Start with single vendor (recommendation: Anthropic Claude for extraction, OpenAI embeddings for similarity, decision Open Q #3). Add multi-model when cost pressure justifies it.

---

## C. Persona Depth — Maya (Beyond the PRD)

**Demographics:** 32, female, senior product designer at mid-size SaaS company in Brooklyn. Married, 2 young kids (4 and 7). Household income ~$180K. Tech-savvy but not developer. Uses iPhone primarily; laptop for work.

**Daily tech stack:** Google Calendar (work), Apple Calendar (family), Gmail, Notion, Slack, Figma, Instagram, WhatsApp. Has tried and abandoned: Facebook Events, Meetup app, Eventbrite local, Bandsintown, Songkick.

**Quote:** *"I don't want MORE things to do. I want someone to tell me the 3 things actually worth doing this week."*

**Behavioral data:**
- Checks Google Calendar 5x/day
- Skims Facebook Events tab weekly
- Has 47 unread event newsletters
- Has missed 2+ close friend birthdays/year
- Disables push notifications on most apps within 1 week of install
- Manually copies dates from Eventbrite confirmation emails
- Asks spouse "what's this weekend?" instead of using any app

**Success moment with EventPulse24:** Opens Pulse in the morning → sees 3 relevant events → saves one → sets 2-day reminder → closes app. Total time: 30 seconds. **Doesn't open the app again until tomorrow's Pulse Digest.**

**Secondary personas (PRD §2.1):**

- **The Group Coordinator** — Plans weekends, dinners, activities for friend groups. Needs "Pulse the Group" (FR-34, Phase 2).
- **The Traveler** — Visits new cities monthly; needs hyperlocal event discovery without setting up a new profile each time. Travel Mode (FR-40, Phase 3).
- **The Parent** — Manages kids' events (school, sports, birthday parties) alongside personal/professional commitments. Needs unified family calendar (Phase 2).

---

## D. Competitive Teardown — Detailed

### Eventbrite

**What they do well:** Massive event catalog; trusted ticketing; organizer tools; payments.
**Where they fail users:** Pushes promoted listings; UX optimized for transactions; no personal event handling; no global intelligence layer.
**Why we don't compete:** They're a ticketing infrastructure company. We don't sell tickets.
**Our play:** Affiliate to them. They win on transactions; we win on discovery intelligence.

### Meetup

**What they do well:** Strong community feel; group-based discovery; local in major US cities.
**Where they fail users:** Narrow scope (only Meetup groups); no global coverage; declining relevance post-pandemic; no AI curation.
**Why we don't compete:** They're a community company. We don't build tribes.
**Our play:** Show Meetup events in our Pulse Digest alongside everything else.

### Facebook Events

**What they do well:** Massive distribution; social graph integration.
**Where they fail users:** Engagement-driven; FOMO-reinforcing; declining trust; opaque ranking; declining event quality.
**Why we don't compete:** They're a social engagement company. We don't sell engagement.
**Our play:** Avoid social entirely. Compete on calm + intelligence.

### Google Calendar

**What they do well:** OS-level distribution (Android); strong APIs; trusted brand; calendar sync standard.
**Where they fail users:** No public event awareness; no recommendations; passive storage; no curation.
**Why we don't compete:** They're a storage company. We don't store time.
**Our play:** Sync INTO Google Calendar. Be the intelligence layer above it.

### Apple Calendar

**What they do well:** OS-level distribution (iOS); privacy positioning; tight hardware integration.
**Where they fail users:** Same as Google — passive; no public events; no recommendations.
**Why we don't compete:** Same as Google.
**Our play:** Same as Google. **Risk:** Apple could add AI features to native Calendar. Mitigation: web-first, cross-platform, brand moat.

### Luma (lu.ma)

**What they do well:** Professional+social event pages, RSVP/ticketing, growing into a default for tech/community events.
**Where they fail users:** Browse-heavy UX; not a calm digest; no aggregation across non-Luma sources.
**Why they're our closest competitor:** Same general lane (community/event aggregation).
**Our play:** Differentiate on cadence (3 cards/day vs. browse) + explainability (Why-this Tags) + breadth (everything, not just tech/community events).

### Bandsintown / Songkick

**What they do well:** Music-specific alerts; strong recommendation engine.
**Where they fail users:** Vertical (music only); notification-heavy; no personal events.
**Why we don't compete:** Vertical scope. We're general.
**Our play:** Show their events in Pulse Digest alongside everything else.

### Other notable players

- **Partiful** — viral party planning; strong network effects in NYC; interesting group-coordination play but narrow (parties only)
- **IRL** — attempted social event discovery, shut down 2023 (lesson: social doesn't monetize)
- **Posh** — premium event discovery; luxury niche; not mainstream
- **Shotgun** — electronic music events; niche

**Key insight:** Most "event app" failures share one pattern — they tried to compete on engagement/social and got crushed by Facebook Events, then died. The survivors (Eventbrite, Meetup) won on transactions or community. **Nobody has won on intelligence + calm yet.**

---

## E. Technical Constraints & Considerations (for Architecture Phase)

### LLM Strategy

- **Decision needed**: Single vendor (OpenAI/Anthropic) vs. multi-model routing (Open Q #3).
- **Recommendation** [ASSUMPTION]: Start with Anthropic Claude for extraction (cost + quality), use OpenAI embeddings for similarity, evaluate Mistral or Llama for cost optimization at scale.
- **Cost concern**: Per-event extraction is expensive. Caching + batching mandatory (FR-30).

### Event Extraction Pipeline

- **Crawl approach**: Hybrid — official site partnerships > RSS feeds > careful web scraping (legal review per source).
- **Sources for MVP**: Mix of venue sites, tourism boards, university calendars, niche blogs, aggregators (where ToS permits). 20 sources (Open Q #1).
- **Extraction**: LLM-based structured output (event name, date, location, category, source URL, confidence) with Pydantic + Instructor + constrained decoding.
- **Deduplication**: Hybrid — canonical URL + normalized time + venue + embedding similarity (cosine 0.85–0.95).

### Data Storage

- **Event records:** PostgreSQL primary with pgvector for embeddings.
- **User preference graph:** PostgreSQL tables for MVP; graph DB (Neo4j/Memgraph) for Phase 2+ when group features land.
- **Source registry:** PostgreSQL with audit log.
- **Cold-start:** SEO-derived interests (location + first event interactions).
- **Privacy:** Personal calendar data isolated from public event data; encryption at rest.

### Notification Infrastructure

- **Delivery:** Multi-channel — email (primary for digest), push (mobile in Phase 2), SMS (critical reminders only — likely never), in-app.
- **Email stream:** Transactional (Postmark Message Streams or SendGrid).
- **iOS/Android throttling risk:** Use email + in-app as fallback; don't depend on push. APNs `apns-priority: 10` for time-sensitive only; `collapse-id` for memoization.
- **Time-of-day targeting:** User timezone + historical open times.

### SEO & Content Flywheel

- **Strategy:** Every event has a public URL with Schema.org Event JSON-LD.
- **Target keywords:** "events in [city]", "tech meetups in [city]", "things to do in [city] this weekend"
- **Content:** Auto-generated city guides, weekly event roundups.

### Data Moat Building

- **Event corpus:** Every event crawled = proprietary data.
- **User preferences:** Every swipe/save/dismiss = signal.
- **Source reliability scores:** Each source has a track record; informs future ranking.
- **Network effects:** Solo use → group use → community intelligence → better recommendations.

---

## F. Funding & Team Considerations [ASSUMPTION]

### Capital Requirements (rough order of magnitude)

- **MVP build:** $50–150K (3-person team for 6 months: 1 full-stack eng, 1 AI eng, 1 designer/PM)
- **12-month runway:** $300–600K (5–7 people + infrastructure costs)
- **AI inference at scale:** Variable; design discipline required (FR-29, FR-30)

### Team Gaps to Fill Pre-Launch

- Technical co-founder OR senior full-stack engineer (Next.js + PostgreSQL)
- AI/ML engineer (LLM prompt engineering, event extraction, vector search)
- Designer (UX-heavy product; calm aesthetic)
- Marketing/growth (SEO + Product Hunt + community)
- **Optional:** Senior advisor from event tech (Eventbrite alumni ideal)

### Funding Path Options

- **Bootstrap:** $0–$50K personal → revenue-funded growth (conservative, slower)
- **Pre-seed:** $250K–$500K angel round (faster MVP, more runway)
- **Seed:** $1M–$3M institutional (faster scale, more pressure)

**Recommendation** [ASSUMPTION]: Pre-seed angel round to fund 12-month MVP + initial growth, then Series A at 100K MAU + $1M ARR.

---

## G. Marketing & Launch Plan (high-level)

### Pre-Launch (Months 1–3)

- Landing page + waitlist
- "Pulse Preview" interactive demo (no signup) — FR-2
- SEO foundation: city event pages with structured data (FR-27)
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

## H. Compliance & Legal — Detailed

### GDPR / CCPA

- Right to access (user data export — JSON + ICS)
- Right to deletion (within 30 days of request)
- Right to portability (JSON + ICS export)
- Data minimization (Personal vs. Public separation)
- Privacy policy + Terms of Service (required at sign-up)

### CAN-SPAM + Email

- Transactional email for Pulse Digest + Reminders (separate from any marketing)
- One-click unsubscribe per RFC 8058 (per event, not per category by default)
- Physical address in email footer
- Honest subject lines (no deceptive marketing)

### Web Scraping

- HiQ v. LinkedIn (2023) — public scraping defensible under CFAA
- ToS/anti-bot measures still carry contract-law exposure
- Acquisition hierarchy (FR-17) — official APIs > partnerships > RSS/JSON-LD > email/ICS > crawling (last resort)
- Source Registry audit log (FR-13) for every source's ToS review

### Accessibility

- WCAG 2.1 AA target (PRD §11.5)
- Screen-reader audit on Pulse Digest, Detail Screen, Onboarding
- Keyboard navigation verified
- Color contrast on warm/cool Pulse Card variants

---

## I. Open Questions — Detailed

(See PRD §8 for the full table. The following is rationale for the most important questions.)

### Open Q #1: Which 20 event sources for MVP?

**Why it matters:** The corpus is the product. Wrong sources = wrong MVP.

**Recommendation:** Mix of:
- 5 official sites (e.g., NYC Tourism, SXSW, CES, Sundance, Aspen Ideas)
- 5 aggregators (e.g., Eventbrite public listing, Meetup GraphQL, Bandsintown music)
- 3 community platforms (e.g., Luma tech events, Partiful public listings)
- 3 niche blogs (e.g., BrooklynVegan, TechMeme events)
- 2 university calendars (e.g., MIT, Stanford)
- 2 city/tourism boards (geo-targeted)

**Decision criteria:** Source must have structured data (JSON-LD or API) preferred; crawl-to-extract only when no alternative.

### Open Q #3: LLM provider strategy

**Recommendation:** Start single-vendor (Anthropic Claude for extraction, OpenAI for embeddings). Multi-model routing adds complexity without proven benefit at MVP scale. Re-evaluate at 100K MAU.

### Open Q #6: Geographic beachhead

**Recommendation:** 3 cities at launch (NYC, SF, Austin) — not 1 city deep. 3 cities prove the model cross-region; 1 city doesn't validate the product nationally. Expansion to LA, Chicago, Boston at Month 6.

### Open Q #11: Live research validation gap

**Context:** 2 of 4 research subagents reported web search returned no live results (knowledge-cutoff synthesis only). Pre-launch re-validation needed for:
- Luma's 2025-2026 product moves
- Apple Intelligence calendar features
- Gemini in Calendar consumer rollout
- Partiful's geographic expansion
- Any new "calm event" entrant

---

## J. Phase 2/3 Features — Behavioral Notes

(These augment the named FRs in PRD §4.9 with architectural/brief hints.)

### FR-31 Calendar Sync (Phase 2)

- **OAuth flow:** Google + Outlook in Phase 2; CalDAV for Apple.
- **Sync interval:** 15 min pull + push on write.
- **Conflict resolution:** Server-side wins on field-level merge with user-visible conflict log.
- **Recurring events:** Handle RRULE expansion; show instance as separate row.
- **Two-way or one-way:** One-way read in MVP calendar sync; write-back in Phase 3.

### FR-32 Unified Timeline (Phase 2)

- **View modes:** Week / Month / Day.
- **Color differentiation:** Warm tones (personal) vs. cool tones (public).
- **Conflict markers:** Subtle (no red, no sound). Typological (work vs. social) not just temporal.
- **Empty state:** "Your week is quiet — Pulse Digest is the place to discover."

### FR-34 Pulse the Group (Phase 2)

- **Group size cap:** 10 people.
- **Privacy:** No event titles shown to group; only free/busy.
- **AI suggestions:** 3 event options matching composite preferences.
- **Opt-in:** Per group.
- **Free tier limit:** 1 group; Pro unlimited.

### FR-36 Voice Quick-Add (Phase 3)

- **Surface:** Mobile app (Phase 2+).
- **Recognition scope:** Event name + time + location.
- **Adoption:** Expected niche; treated as showcase.

### FR-37 Email-to-Event Forwarding (Phase 3)

- **Address:** personal @pulse.email address.
- **Extraction:** Same LLM extraction as public sources.
- **Confidence:** User-visible; user can correct.
- **Adoption:** Expected niche; power-user feature.

### FR-39 On-Device Personal AI (Phase 3)

- **Scope:** Personal events only (public events still server-side).
- **Privacy:** Personal data never leaves device.
- **Federated learning:** Optional; aggregates to server-side preference graph.
- **Cost benefit:** Eliminates per-user personal-event inference cost.

### FR-40 Travel Mode (Phase 3)

- **Trip detection:** Calendar/email parsing (Phase 2 calendar sync dependency).
- **Auto-suggest only:** Never assume — ask before changing default city.
- **Persistence:** Auto-set 7 days before trip; auto-revert 3 days after.

---

## K. References to Source Documents

- **Product Brief:** `_bmad-output/planning-artifacts/briefs/brief-EventPulse24-2026-08-19/brief.md`
- **Product Brief Addendum:** `_bmad-output/planning-artifacts/briefs/brief-EventPulse24-2026-08-19/addendum.md`
- **Innovation Strategy:** `_bmad-output/innovation-strategy-2026-08-19.md`
- **Design Thinking:** `_bmad-output/design-thinking-2026-08-19.md`
- **Blue Ocean Strategy:** `_bmad-output/blue-ocean-strategy-2026-08-19.md`
- **Original scope:** `docs/scope.txt`
- **PRD (this run):** `prd-EventPulse24-2026-08-19/prd.md`
- **Memlog (this run):** `.memlog.md`

---

_This addendum captures content from the PRD creation session that belongs in downstream artifacts (Architecture, Solution Design, UX Spec, Marketing Plan) or was discussed but did not earn a place in the PRD itself._
