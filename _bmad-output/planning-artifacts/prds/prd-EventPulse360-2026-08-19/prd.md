---
title: "PRD: EventPulse24"
status: final
created: 2026-08-19
updated: 2026-08-19
project: EventPulse24
author: Jobaer
sources:
  - _bmad-output/planning-artifacts/briefs/brief-EventPulse360-2026-08-19/brief.md
  - _bmad-output/planning-artifacts/briefs/brief-EventPulse360-2026-08-19/addendum.md
  - _bmad-output/innovation-strategy-2026-08-19.md
  - _bmad-output/design-thinking-2026-08-19.md
  - _bmad-output/blue-ocean-strategy-2026-08-19.md
  - docs/scope.txt
---

# PRD: EventPulse24

> **The calm intelligence layer above all event sources.**

## 0. Document Purpose

This PRD is the source of truth for Product, Engineering, Design, and the downstream BMad workflows (UX, Architecture, Epics) for the launch of EventPulse24. It is anchored in the **Product Brief** (`brief-EventPulse360-2026-08-19/brief.md`) and the three strategy documents it synthesizes (Innovation, Design Thinking, Blue Ocean). Sections build on those artifacts instead of duplicating them — depth and rationale that does not earn its place in the PRD-main narrative lives in `addendum.md`.

Vocabulary is Glossary-anchored; every domain noun is defined once in §3 and used verbatim from there. Functional Requirements (FRs) are numbered globally and stable across downstream references. Inferred items are tagged `[ASSUMPTION: ...]` inline and indexed in §9. Open Questions are tracked in §8 and re-checked at Finalize.

Stakes: **Seed-stage public launch.** Sections reflect full quantitative rigor (NFRs, metrics, risks, mitigations).

---

## 1. Vision

EventPulse24 is the **calm intelligence layer above all event sources.** Users are drowning in events they didn't ask about, missing events they care about, and exhausted by notifications that don't respect their attention. EventPulse24 is the single, trustworthy surface that uses AI to surface the small number of events that matter to each user, and delivers them via context-aware, multi-tier reminders that *reduce* notification volume instead of adding to it.

The product unifies **personal** calendar events (birthdays, meetings, weddings) with **public** events (concerts, tech meetups, government programs, sports) from across the open web into a single calm timeline with intelligent conflict detection — a capability no incumbent owns. Where Eventbrite monetizes transactions, Meetup monetizes community, Facebook Events monetizes engagement, and Google/Apple Calendar monetizes storage, EventPulse24 monetizes **calm** — a business model whose metric is *fewer, better* notifications, in deliberate misalignment with the engagement-optimized industry.

The MVP ships as a web-first product with AI-curated daily **Pulse Digest** (3 cards), **Pulse Ping** (one daily notification, not many), per-event **multi-tier reminder** picker (5d/2d/1d/1hr), explainable **"Why this?"** micro-tags, and a **Source Badge** for trust. Growth comes through SEO-driven public-event discovery, then viral group coordination ("Pulse the Group") as the compounding network effect in Phase 2.

**The contrarian bet — and the cost of the status quo.** Every incumbent (Eventbrite, Meetup, Facebook Events, Google/Apple Calendar) optimizes for *more* engagement, *more* notifications, *more* transactions. None optimizes for *calm*, *intelligence*, or *signal-to-noise*. The cost of the status quo is real: missed close-friend birthdays, 47 unread event newsletters, signal-to-noise ratios below 5%, group coordination that takes 47 WhatsApp messages, FOMO-driven attendance at events that weren't worth going to. EventPulse24 takes the opposite bet — a business model whose metric is *fewer, better* notifications, in deliberate misalignment with the engagement-optimized industry. That misalignment is the moat. The aspiration is to be the **"Headspace of events"** — synonymous with calm event intelligence.

**Why now:** AI cost curves have collapsed, attention fatigue is acute, and Apple/Google's native calendar AI features (Apple Intelligence, Gemini in Workspace) cover the "smart calendar" lane but not the **aggregation + curated calm digest** across sources Apple/Google don't index. The window is 12–18 months before platform owners notice the consumer layer EventPulse24 defends. EventPulse24 must win the consumer brand for "calm event intelligence" before the OS-level copy lands.

---

## 2. Target User

### 2.1 Jobs To Be Done

**Functional:**
- Help me see the 3 events this week that are actually worth my time — without searching 6 apps.
- Help me remember events I care about (birthdays, weddings, hard-to-tickets) with reminders that don't pile up.
- Help me reconcile my personal calendar with the public events that overlap with my life.

**Emotional:**
- Reduce the anxiety of "I'm missing something" — both for events I should attend and personal commitments I shouldn't forget.
- Make choosing what to do feel like a *decision*, not a *deluge*.

**Social:**
- Be the person who knows what's happening without being "the planner" — for friends, family, work.
- Coordinate small groups without 47 WhatsApp messages.

**Contextual:**
- One calm surface, on any device, that respects my time. Default everywhere = "fewer, better."

### 2.2 Non-Users (v1)

EventPulse24 is **not** for v1:

- **Event creators / organizers** — we do not host creation UIs, payment infrastructure, or organizer tooling. Organizers are pipeline inputs, not users.
- **Power users who want every event** — the product philosophy is *less*, not *more*. Power users prefer Eventbrite, Meetup, or Facebook Events.
- **Ticketing-driven users** — if the primary goal is to buy a ticket, EventPulse24 redirects to Eventbrite/Ticketmaster via affiliate.
- **Tightly coupled social-feed users** — if the value of events is the social graph (Facebook Events), this is the wrong product.
- **Consumers in regions where the source corpus is empty** at MVP. The geographic beachhead is the open question (see §8).

### 2.3 Key User Journeys

#### UJ-1. Maya gets the 3 events that matter this morning.

**Persona + context:** Maya, 32, senior product designer in Brooklyn. Wife, two kids. Disables notifications on most apps within a week of install. Has 47 unread event newsletters. Has missed 2+ close friend birthdays/year.

**Entry state:** Coming from email. Has connected Google Calendar during yesterday's first-time onboarding. Already authenticated.

**Path:**
1. Pulse Ping notification arrives at 8:00 AM local (her chosen digest slot).
2. Taps notification → land on Pulse Digest (home).
3. Sees 3 cards: (a) "A friend's birthday tonight — `close-friend, tonight` ⬤⬤⬤⬤○" (b) "Free tech meetup Thu, 2 blocks from work — `nearby, thursday, free` ⬤⬤⬤○○" (c) "Rooftop jazz in your neighborhood Sat — `nearby, weekend, novel` ⬤⬤⬤○○".
4. Taps card (a) → Detail screen: source badge ("Added by spouse via shared calendar"), confidence pulse, similar events she's attended. Sets 2-day reminder + Pulse Ping reminders.
5. Swipes card (b) down to dismiss (no penalty; signal recorded).
6. Saves card (c) and sets 1-hour reminder.

**Outcome:** She knows what matters this week, in 30 seconds, without opening 6 apps and without being marketed to.

**Resolution:** App closed. Comes back tomorrow at 8:00 AM. Nothing else pushes itself.

**Edge case:** If the digest is empty (no qualifying events), show a single "No pulse for today — your week is quiet" card with a "Suggest an event" link.

#### UJ-2. Maya's husband creates a personal event from his phone and Maya sees it instantly.

**Persona + context:** Maya's husband, who uses Apple Calendar. He creates a personal event ("Anniversary dinner — 7pm Friday @ Lilia") directly in Apple Calendar. The event is shared via the family iCloud calendar.

**Entry state:** Husband adds event in Apple Calendar. (He does not have EventPulse24 installed — he's a non-user, see §2.2.)

**Path:**
1. EventPulse24 (Phase 2 feature) syncs Maya's Apple Calendar in the background.
2. Friday's Pulse Digest or Timeline includes the anniversary dinner alongside any public events that night.
3. Maya sees it as a "personal event" card (warm-tone color) labeled "Anniversary dinner" with `family, friday, restaurant` micro-tags.
4. Default reminder: Pulse Ping includes the event without per-event override.

**Outcome:** Maya sees the personal event in the same calm surface as public events, without effort.

**Resolution:** No conflict highlighted (no other events). She never leaves EventPulse24 to remember.

**Edge case:** If the anniversary dinner conflicts with a public event Maya saved, the timeline shows both with a gentle conflict marker (no alarm).

#### UJ-3. A new user signs up and sees relevant events in 30 seconds, no quiz.

**Persona + context:** A new user who has never used EventPulse24. Heard about it from a friend. Lands on the home page.

**Entry state:** First visit. No auth. Browser cookie only.

**Path:**
1. Pulse Preview (home page) shows 3 events in her inferred city (geo-IP default), each with `Why this?` micro-tags.
2. She clicks "Sign up" → onboarding flow: 30 seconds, max 3 steps.
3. Step 1: optionally connect Google Calendar (1-click OAuth) or skip.
4. Step 2: optionally pick 3 interest chips (or skip).
5. Step 3: daily digest delivery time + timezone. Done.
6. Lands on Pulse Digest with a fresh 3-card brief keyed to her preferences.

**Outcome:** She has a useful, personalized, calm interface in under 30 seconds, with no quiz.

**Resolution:** Tomorrow's Pulse Ping arrives at the chosen time. She opens, sees 3 cards, closes app.

**Edge case:** If geo-IP is wrong, she can change city one-tap in onboarding (no address entry).

#### UJ-4. Maya wants to know why an event is in her digest.

**Persona + context:** Maya, in Pulse Digest. Suspects the algorithm is showing her events she doesn't care about.

**Entry state:** Authenticated. Looking at a card.

**Path:**
1. Taps "Why this?" micro-tag on the card.
2. Detail screen expands: source badge (verified venue / official site / community), confidence pulse (1–5 dots), similar events she's attended, neighbor count (👥 12 neighbors).
3. Reads the reasoning. Accepts or dismisses with a "less like this" swipe.

**Outcome:** She knows why the AI showed her this, and the system learned from her dismissal.

**Resolution:** Future digests deprioritize similar events (without erasing them — useful for "spice" events).

**Edge case:** If she's dismissing 3+ similar events in a row, the system proactively shows a calm prompt: "Less rooftop jazz in your next digest?" — one tap to mute.

#### UJ-5. A friend shares an event with Maya via Pulse share-card.

**Persona + context:** A friend of Maya's (eventually both Phase 2 users, but for v1 it's a public share-link).

**Entry state:** Friend is on EventPulse24 or uses the public share link.

**Path:**
1. Friend taps "Share" on a card → public URL with structured Schema.org Event data.
2. Maya opens link → sees the event detail with a "Save to Pulse" CTA.
3. Taps save → routed to onboarding (if not yet) or directly into her Pulse Digest/Timeline.

**Outcome:** EventPulse24 is a sharing surface, not a walled garden.

**Resolution:** Share-link events are clearly tagged as "shared by {friend}" in her timeline.

**Edge case:** If the event is far from Maya's city, share-link shows the event details but defers save to "Travel Mode" copy (Phase 3).

#### UJ-6. Maya coordinates a birthday weekend with 4 friends (Phase 2).

**Persona + context:** Maya plans her birthday weekend. Needs to find a Saturday-night slot 4 friends can attend.

**Entry state:** Maya has a small group of friends who use EventPulse24 (Phase 2 feature).

**Path:**
1. Opens "Pulse the Group" → picks group → picks date range.
2. System shows a privacy-respecting availability heatmap (no event titles, only free/busy).
3. The system suggests 3 event options that match the group's composite preferences.
4. Maya picks one, sends to the group, RSVPs collect in-app.

**Outcome:** 47 WhatsApp messages replaced by 4 taps.

**Resolution:** Group has a confirmed plan; Maya didn't have to be "the planner app."

**Edge case:** If no slot works, system surfaces "Suggest an alternative date" with 3 non-overlapping options.

---

## 3. Glossary

*Downstream artifacts (UX, Architecture, Epics, Stories) MUST use these terms exactly. Introducing a synonym is a discipline violation. New domain nouns introduced in §4 land here in the same pass.*

- **Event** — A single time-bounded happening with a name, start time, location, and source. May be public (sourced from a public source) or personal (created by the user). Cardinality: 1-to-many Sources, 1-to-1-or-0 ReminderPlan.
- **Source** — A provenance record for an Event. Types: `official_site` (verified venue/organizer), `community` (community-posted, e.g., Luma), `aggregator` (e.g., Eventbrite public listing), `user_imported` (user-forwarded email/ICS), `crawled_html` (last resort, ToS-reviewed). Each Source has a reliability score.
- **Pulse Digest** — The home surface. A daily, fixed-cadence, 3-card brief delivered to the user. Default delivery: 8:00 AM local. Each card is a Pulse Card.
- **Pulse Preview** — The no-auth public surface shown to first-time and unauthenticated visitors. 3 Pulse Cards in the user's inferred city (geo-IP default, one-tap city override). Soft-walls at the "Save to Pulse" CTA — signup is required to save, not to browse.
- **Pulse Card** — A single event in the Pulse Digest. Shows: event name, time, location, 3-keyword "Why this?" micro-tags, 1–5 Confidence Pulse, Source Badge. Tappable to Detail Screen.
- **Pulse Ping** — The single daily notification that brings the user back to the Pulse Digest. **Not** an event-specific reminder. Counter to industry's 5–15/day blast.
- **Why-this Tags** — Up to 3 keywords on a Pulse Card explaining *why* the AI surfaced this event (e.g., `nearby, tonight, music`). Same tags appear on the Detail Screen.
- **Confidence Pulse** — A 1–5 dot indicator on each Pulse Card showing AI certainty about relevance. 5 = very strong match; 1 = weak. Persisted on the Event record.
- **Source Badge** — A small visual label on each Pulse Card and Detail Screen indicating the Source type. `official_site` = ✅, `community` = 👥, `aggregator` = 🔗, `user_imported` = 📥, `crawled_html` = ⚠️.
- **Detail Screen** — The expanded view of a Pulse Card. Shows: full event description, location with map, reminder picker, share, save, dismiss, Why-this breakdown, similar events user has attended, neighbor count.
- **Neighbor Count** — A signal on the Detail Screen showing how many other EventPulse24 users are in the same area and tracking the same event (`👥 X neighbors`). Revealed only when at least 1 qualifying user exists; absence is silent, not a zero. Privacy-respecting — no identifying information.
- **Timeline** — A unified calendar view (Phase 2) showing Personal Events (warm tones) and Public Events (cool tones) in one week- or month-view. Conflicts highlighted, never alarmed.
- **Personal Event** — A user-created or calendar-synced event (birthday, meeting). Exists in the user's Personal Calendar. Phase 2 surfaces a Personal Event in the Timeline; MVP surfaces it only via manual add in the EventPulse24 UI.
- **Public Event** — A Source-sourced event not created by the user.
- **Reminder Plan** — A per-Event set of up to N reminder slots (default: 5d, 2d, 1d, 1hr before) plus Pulse Ping (which is a separate, global concept). User-editable per event.
- **Preference Graph** — Per-user behavior-derived data structure (dwell, swipes, dismissals, saves) that drives Pulse Digest composition. Built incrementally; cold-start is SEO/geo-derived.
- **Pulse the Group** — Phase 2 feature: AI-assisted small-group coordination (UJ-6). NOT a social feed.
- **Travel Mode** — Phase 3 feature: hyperlocal event discovery in visited cities without per-city setup.
- **Voice Quick-Add** — Phase 3 feature: voice-input personal event creation. Demo magnet, niche adoption.
- **On-Device Personal AI** — Phase 3 feature: local preference learning for personal events. Privacy + cost optimization.
- **Why Now?** — Phase 3 feature: per-event "why should I attend this in particular" natural-language explanation (vs. Why-this Tags which explain *why surfaced*).
- **Pro Tier** — The paid tier. Calendar sync (Phase 2), group coordination (Phase 2), unlimited Pulse the Group, On-Device Personal AI (Phase 3).
- **Free Tier** — Unauthenticated browsing via Pulse Preview. Authenticated users on the free tier see the full Pulse Digest (3 cards/day) and can save up to 1 event/day; the 2nd save action triggers a soft-wall CTA to sign up or upgrade. Feature caps apply (see §15.1).
- **Source Reliability Score** — Per-Source trust score (0.0–1.0) computed from extraction accuracy, user dismissal rate, and editorial review. Lowers ≠ removes a Source; changes its ranking.
- **AI Cost Dashboard** — Internal-facing per-feature telemetry (FR-29) tracking spend on extraction, embeddings, classification, and personalization.

---

## 4. Features

Features grouped into coherent behavioral clusters. FRs globally numbered and stable. Each FR is testable. References to UJs inline (`realizes UJ-X`). Inferred items tagged `[ASSUMPTION: ...]`.

### 4.1 Onboarding & Account

**Description:** A user from cold start to first personal Pulse Digest in ≤30 seconds. Realizes UJ-3. The flow is glass-floor simple: skip most steps, get immediate value, configure later. Onboarding never asks for things the system can infer (city from geo-IP, interest from first interactions).

#### FR-1: 30-Second Onboarding Flow

The system provides an onboarding flow with at most 3 user-visible steps: (1) optional calendar connect, (2) optional interest chips (3 picks), (3) digest delivery time + timezone. The user can skip any step. Realizes UJ-3.

**Consequences (testable):**
- An onboarding flow that exceeds 3 steps before the first Pulse Digest is shown violates FR-1.
- An onboarding step that *requires* user input (rather than allows skip) violates FR-1.
- A user who skips all steps still sees a geo-IP-inferred Pulse Digest on first login.

**Out of Scope:** Multi-step "interest quizzes" of more than 3 picks. Detailed profile completion. Account verification before Pulse Digest.

#### FR-2: Pulse Preview (No-Auth First Value)

The system surfaces a Pulse Preview (3 events in the user's inferred city) on the public home page and as the first surface for unauthenticated visitors. Realizes UJ-3.

**Consequences (testable):**
- A first-time visitor without an account sees at least 2 Pulse Cards without signup.
- A "Save to Pulse" CTA on a Pulse Card in Pulse Preview soft-walls at the 3rd card (signup required at the save tap).
- Geo-IP is the default city; one-tap change to override.

**Out of Scope:** Personal event surfacing in Pulse Preview. Personalization before signup.

#### FR-3: Calendar Connect (Optional OAuth)

The system supports optional OAuth-based connection of Google Calendar, Apple Calendar (via CalDAV), and Outlook Calendar. Skippable. Realizes UJ-2 (Phase 2 FR-31).

**Consequences (testable):**
- A user can complete OAuth and see personal events in the Calendar Connect step without leaving the onboarding flow.
- A user can skip Calendar Connect and still receive a Pulse Digest.
- Revoked OAuth credentials are detected on next sync and the user is prompted to reconnect, not silently denied.

**Out of Scope:** Calendar write-back (push events from EventPulse24 → calendar) in MVP. Two-way sync in Phase 2 (FR-31).

#### FR-4: Authenticated User State

The system persists authenticated user state across sessions (web cookie + server session). Realizes UJ-1, UJ-3.

**Consequences (testable):**
- An authenticated user reopening the app within 7 days is not prompted to re-authenticate.
- An unauthenticated user with a stale OAuth token is redirected to onboarding with state preserved.

**Notes:** `[ASSUMPTION: web cookies are sufficient for MVP; mobile/session tokens in Phase 2.]`

---

### 4.2 Pulse Digest (Home)

**Description:** The daily morning brief. The product's moment-of-truth surface. Realizes UJ-1. Bounded by design: 3 cards, max. Decision fatigue is the enemy.

#### FR-5: Pulse Digest Composition

The system composes a Pulse Digest of 3 Pulse Cards per user per day based on the user's Preference Graph, location, and Source Reliability Scores. Realizes UJ-1.

**Consequences (testable):**
- A Pulse Digest contains exactly 3 cards on a standard day. Exception: a "No pulse for today" empty state.
- A Pulse Card in the digest is not a duplicate (same Event) of another.
- The 3 cards cover at least 2 distinct categories (e.g., one `personal-near`, one `public-near`, one `serendipity`).
- The system can run an empty-state Pulse Digest when there are no qualifying public events. In this case, the digest shows one card: "No pulse for today."

**Out of Scope:** More than 3 cards. User-configurable digest size. Per-event "I want more of this" in MVP — Phase 2 (FR-33).

**Notes:** `[ASSUMPTION: digest composition algorithm is deterministic per user per day; rainbow-A/B testing done via shadow composition in the AI Cost Dashboard, not live user experience.]`

#### FR-6: Pulse Card Information Density

Each Pulse Card shows: event name, time, location, up to 3 Why-this Tags, a 1–5 Confidence Pulse, and a Source Badge. Realizes UJ-1.

**Consequences (testable):**
- A Pulse Card never shows more than 3 Why-this Tags.
- A Pulse Card always shows a Confidence Pulse between 1 and 5.
- A Pulse Card always shows a Source Badge.

**Out of Scope:** Promotional content (ads), promotional Source Boosts, "sponsored" placements.

#### FR-7: Pulse Digest Delivery Time

The system delivers the Pulse Digest at the user-configured time (default 8:00 AM local) plus a tolerance window of ±15 minutes. Realizes UJ-1.

**Consequences (testable):**
- A user can change the Pulse Digest delivery time in settings.
- A user in a new timezone gets a digest at the new local 8:00 AM, not the old-timezone 8:00 AM.
- If AI personalization runtime causes >5 minutes of delay, the system logs it; user never sees a "delayed" status.

#### FR-8: Empty-State Pulse Digest

If no qualifying public events exist for the user, the system presents a single "No pulse for today — your week is quiet" card with a "Suggest an event" link. Realizes UJ-1.

**Consequences (testable):**
- An empty Pulse Digest is never blank; it always shows the empty-state card.
- The empty-state card never promotes a "promoted event" or ad.

---

### 4.3 Reminders & Notification Discipline

**Description:** The product's most distinctive bet: fewer, better notifications. Multi-tier reminders per event plus a single daily Pulse Ping. Counter-metric to industry spam.

#### FR-9: Multi-Tier Reminder Picker

For any event, the user can set up to 4 reminder slots: 5d, 2d, 1d, 1hr before the event. The system also supports a custom slot. Realizes UJ-1.

**Consequences (testable):**
- A user can save a Reminder Plan with 0 to 4 slots. 0 slots = no reminders (still in feed).
- A user can edit a saved Reminder Plan.
- The default Reminder Plan for an event is 1d + 1hr.
- A reminder is suppressed if the device is active (Phase 2 mobile) or the user is in a user-configured quiet window.

**Out of Scope:** Push notifications to mobile in MVP (email digest only); see FR-11.

#### FR-10: Pulse Ping — Single Daily Notification

The system sends exactly one Pulse Ping notification per user per day, at the user's chosen delivery time, linking to the Pulse Digest. Realizes UJ-1, UJ-3.

**Consequences (testable):**
- A user with 0 qualifying events does NOT receive a Pulse Ping.
- A user with 3 qualifying events receives exactly 1 Pulse Ping, not 3.
- The Pulse Ping content is consistent across the user's devices (no double-pings if multi-device).

**Counter-metric:** Notification suppression rate target ≥30% (SM-C1) — *more* Pulse Pings suppressed = better intelligence, not worse.

**Out of Scope:** Per-event pushes outside an event's own Reminder Plan. "Trending now" push cascades.

#### FR-11: Email Multi-Tier Reminders

The system delivers Reminder Plan slots via email. Reminder content is transactional, not marketing. Realizes UJ-1.

**Consequences (testable):**
- A user with a 5d/2d/1d/1hr Reminder Plan receives 4 emails (one per slot) at the appropriate time.
- Reminder emails are sent via the transactional email stream (separate from any marketing); SPF/DKIM/DMARC configured.
- A reminder email contains 1-click unsubscribe for that event's reminders (does not unsubscribe from Pulse Ping).

#### FR-12: Quiet Hours

The user can configure a quiet window (e.g., 10:00 PM – 7:00 AM) during which no notifications or emails are sent. Realizes UJ-1.

**Consequences (testable):**
- A reminder slot that falls in the quiet window is sent at the quiet-window end, not during it.
- A Pulse Ping inside the quiet window is silently deferred (no notification stack, no next-day surprise).

**Out of Scope:** Per-day-of-week quiet windows in MVP. Per-category quiet windows in MVP.

---

### 4.4 Event Extraction & Source Pipeline

**Description:** The system that ingests events from public sources. Architecture is hybrid: official APIs > partnerships > RSS/JSON-LD > email/ICS import > web crawling (last resort, ToS-reviewed). Critical to product: the source registry is the corpus. Each event has a Source. Each Source has a reliability score.

#### FR-13: Source Registry

The system maintains a Source Registry, one record per event source. Each record includes: source name, source type, source URL, acquisition method (API / partnership / RSS / email-ICS / crawl), ToS review status, reliability score, ingestion cadence, last-ingestion timestamp. Realizes UJ-1.

**Consequences (testable):**
- A Source with `acquisition_method = crawl` and `tos_review_status != approved` is blocked from ingestion.
- A Source with no ingestion in the last 2× expected cadence is flagged for review.
- The Source Registry is internally auditable; every change is logged.

**Out of Scope:** Self-serve source registration by users (Phase 3 candidate).

#### FR-14: Hybrid Event Extraction Pipeline

The system extracts structured Events from sources using a hybrid pipeline: structured-API sources emit JSON-LD or direct API responses (preferred); HTML-only sources use LLM-based structured extraction with constrained decoding against a Schema.org Event schema. Realizes UJ-1.

**Consequences (testable):**
- A source emitting valid Schema.org Event JSON-LD is parsed without LLM call.
- An HTML-only source triggers LLM extraction with constrained decoding (Pydantic + Instructor + JSON Schema).
- Extraction latency target: <2 seconds per event at p95.
- Extraction cost target: <$0.005 per event blended (LLM extraction for HTML + free for structured).

**Out of Scope:** Real-time extraction from social posts (Phase 3+). User-facing extraction quality dashboard.

#### FR-15: Event Deduplication

The system deduplicates extracted events using a hybrid pass: canonical URL match, normalized time + venue match, and embedding similarity (cosine ≥0.85) on event summary vectors. Realizes UJ-1.

**Consequences (testable):**
- A new event matching an existing event on canonical URL is suppressed.
- A new event with cosine similarity ≥0.95 to an existing event is auto-merged.
- A new event with cosine similarity 0.85–0.95 is flagged for review (not merged).
- The dedup pass is idempotent: re-extracting the same source does not create duplicates.

**Out of Scope:** Cross-language dedup (Phase 3). Auto-merge across >2 ambiguous candidates.

#### FR-16: Source Reliability Score

The system maintains a per-Source reliability score (0.0–1.0) updated from extraction accuracy, user dismissal rate, and editorial review. A low score lowers ranking; it does not remove the source. Realizes UJ-1.

**Consequences (testable):**
- A Source with reliability score <0.3 is escalated to editorial review.
- A Source ranked low in the Source Reliability Score is ranked low in the Pulse Digest.
- The score is updated at least weekly.

**Out of Scope:** User-facing source blocking.

#### FR-17: Source Acquisition Hierarchy Enforcement

The system enforces acquisition-method priority: official APIs > partnerships > RSS/JSON-LD > email/ICS import > web crawling (last resort). A Source is added with the highest-priority method available; crawling is permitted only when no higher-priority method exists and a ToS review has been logged. Realizes UJ-1.

**Consequences (testable):**
- A request to add a crawlable source without a logged ToS review is rejected.
- An existing crawl source whose API becomes available is migrated to API and `acquisition_method` updated.

**Notes:** This FR is the **explicit compliance guardrail** for the platform. See §5 Non-Goals and §11 Cross-Cutting NFRs.

---

### 4.5 Personal Event Management

**Description:** Users can create and manage personal events directly in EventPulse24. Personal events coexist with public events in the Pulse Digest. Phase 2 unifies them onto a Timeline.

#### FR-18: Manual Personal Event Creation

The user can create a Personal Event with name, start time, location, optional end time, optional notes, and optional Reminder Plan. Realizes UJ-1.

**Consequences (testable):**
- A Personal Event is created with required fields: name, start time.
- A Personal Event is saved to the user's Personal Calendar with `source = user_created`.
- A user can edit or delete a Personal Event.

**Out of Scope:** Personal event creation via email forward (Phase 3 — FR-37). Voice input (Phase 3 — FR-36).

#### FR-19: Personal Event in Pulse Digest

The user's Personal Events are eligible to appear in the Pulse Digest as a Pulse Card with a warm-tone color. Realizes UJ-1, UJ-2.

**Consequences (testable):**
- A Personal Event with `start_time` within the next 48 hours is eligible for the Pulse Digest.
- A Personal Event in the Pulse Digest is visually distinct from a public event.
- A user can opt out of personal events appearing in the Pulse Digest.

**Out of Scope:** Personal event in Timeline (Phase 2 — FR-32).

#### FR-20: Personal Event Reminder Defaults

A Personal Event created with a default Reminder Plan inherits 1d + 1hr. The user can edit. Realizes UJ-1.

**Consequences (testable):**
- A new Personal Event has a Reminder Plan of 1d + 1hr by default.
- The user can remove all reminders.

---

### 4.6 Explainability & Trust

**Description:** Every recommendation must show its reasoning. "Why this?" is a feature, not a hidden cost. Source transparency is the moat against the engagement-trap incumbents.

#### FR-21: Why-this Tags

Each Pulse Card shows up to 3 Why-this Tags (3 keywords explaining why the event was surfaced). Tags are dynamically generated from the Pulse Card's reasoning signal. Realizes UJ-1, UJ-4.

**Consequences (testable):**
- A Pulse Card never shows more than 3 Why-this Tags.
- Why-this Tags are human-readable, not raw model output (e.g., `nearby, tonight, music` not `loc_score=0.92, time_match=1, cat=music`).
- Why-this Tags are consistent on the Pulse Card and on the Detail Screen.

**Out of Scope:** Natural-language "Why this?" (Phase 3 — Why Now? — FR-38).

#### FR-22: Confidence Pulse

Each Pulse Card shows a 1–5 dot Confidence Pulse (●●●●○ = 4/5). The Confidence Pulse is computed from the AI's certainty about relevance (not just trust in the source). Realizes UJ-1, UJ-4.

**Consequences (testable):**
- A Pulse Card always shows a Confidence Pulse.
- A 1-dot event has lower Confidence in the user's likely interest (could still be surfaced as "serendipity").
- A 5-dot event has high Confidence in the user's likely interest.
- **Formula (Algorithm spec):** `confidence = floor(5 * relevance_score)` where `relevance_score` is a weighted sum of: (a) preference-graph match (0–1), (b) source reliability score (0–1), (c) recency-vs-event-time fit (0–1), (d) novelty-vs-exploration (0–1). Weights are tunable; the formula is in the Architecture spec. The 1–5 discretization is deliberate UX choice (not 1–100).

#### FR-23: Source Badge

Each Pulse Card shows a Source Badge (✅ official_site / 👥 community / 🔗 aggregator / 📥 user_imported / ⚠️ crawled_html). Realizes UJ-1, UJ-4.

**Consequences (testable):**
- A Pulse Card always shows a Source Badge.
- A `crawled_html` source Source Badge triggers a one-time "Why does this show ⚠️?" explanation tooltip.

#### FR-24: "Why this?" Detail Screen

Tapping any Pulse Card opens a Detail Screen showing: full event description, location with map, reminder picker, share, save, dismiss, **Why-this breakdown** (expanded from tags), **similar events user has attended**, **neighbor count**. Realizes UJ-4.

**Consequences (testable):**
- The Detail Screen always shows the Why-this breakdown.
- The Detail Screen shows similar events the user has attended (when computable).
- The Detail Screen shows a neighbor count (`👥 X neighbors`) when at least 1 user is in the same area and same event.

**Out of Scope:** Friend-attending count (Phase 2 — Pulse the Group). Public event ratings/reviews.

#### FR-25: "Less like this" Adjustment

Swiping a Pulse Card down dismisses it and signals "less like this" to the AI. Realizes UJ-4.

**Consequences (testable):**
- A dismissal is recorded as a negative signal in the Preference Graph.
- After 3 consecutive dismissals of similar events, the system shows a calm prompt: "Less rooftop jazz in your next digest?" — one tap to mute.
- A mute is reversible from settings.

**Out of Scope:** Mass "less like this" controls. Category-wide mute UI in MVP (Phase 2).

---

### 4.7 Sharing & Discovery (SEO)

**Description:** Growth comes through SEO and shareability. Every event gets a public URL with Schema.org structured data. SEO is the cold-start unlock.

#### FR-26: Public Event Pages with Structured Data

The system publishes a public URL for every Event with Schema.org Event JSON-LD embedded. Realizes UJ-5.

**Consequences (testable):**
- Every Event has a unique public URL.
- Every Event URL includes valid Schema.org Event JSON-LD.
- The public URL is crawlable by external search engines.
- The public URL includes a "Save to Pulse" CTA.

**Out of Scope:** Per-event Open Graph tuned for SEO (Phase 2). UGC reviews on the public page.

#### FR-27: SEO City Pages

The system publishes "Events in [city]" pages with structured data, ranked organically, intended to capture "events in [city]" search traffic. Realizes UJ-3.

**Consequences (testable):**
- A city page exists for every city in the Source Registry with >5 events.
- A city page is indexable and ranks for the long-tail query "events in [city]."
- A city page degrades gracefully when no events are present (shows "coming soon" copy).

**Out of Scope:** User-generated content on city pages. Paid placements on city pages.

#### FR-28: Share-Card Public Link

From any Pulse Card or Detail Screen, the user can generate a public share-link URL (already in the form of FR-26) with pre-filled metadata. Realizes UJ-5.

**Consequences (testable):**
- A share-link opens the public Event URL with a "Save to Pulse" CTA.
- The share-link is Open Graph–rich (title, description, image) for social unfurls.

---

### 4.8 AI Cost Discipline

**Description:** AI cost is the product's existential risk. Every surface tracks per-event cost. On-device and batch optimization are first-class concerns.

#### FR-29: AI Cost Dashboard (Internal)

The system provides an internal-facing AI Cost Dashboard with per-feature telemetry: extraction cost per source, embedding cost per event, personalization cost per user, total cost per MAU. Realizes PRD-disciplined "calm" economics.

**Consequences (testable):**
- The dashboard updates at least daily.
- The dashboard surfaces per-feature cost trends (week-over-week).
- The dashboard alerts when blended cost per MAU exceeds a configurable threshold (default: $0.50/month). **Alert owner:** AI engineering lead. **Alert channel:** Slack #pulse-cost-alerts. **Cadence:** weekly summary + immediate Slack on threshold breach.

**Out of Scope:** External-facing cost transparency. User-facing AI-cost control.

#### FR-30: Caching & Batching Defaults

The system batches non-realtime inference (extraction, embedding, classification) and caches results to avoid redundant compute. Realizes FR-29.

**Consequences (testable):**
- Re-extracting the same source URL within the dedup window does not re-trigger LLM extraction.
- Embedding computation is reused across the dedup pipeline and the personalization pipeline.
- Re-running a Pulse Digest composition for the same user within the same day returns the cached composition.

**Out of Scope:** On-device inference (Phase 3 — FR-39).

---

### 4.9 Phase 2 / 3 Features (Named FRs for Future Planning)

*These features are deferred beyond MVP. They are named FRs here so epics and stories can be planned against them without ambiguity. The behavioral notes below are minimum-viable scope hints; details land in the Phase 2 PRD when activation begins.*

#### FR-31: Calendar Sync (Google / Apple / Outlook) — Phase 2

The system performs two-way sync with Google Calendar, Apple Calendar (via CalDAV), and Outlook Calendar. Personal events from these calendars appear in the Pulse Digest and Timeline. Recurring events are handled. Realizes UJ-2.

**Behavioral notes:** OAuth flow for Google/Outlook; CalDAV for Apple. Sync interval: 15 min pull + push on write. Conflict resolution: server-side wins on field-level merge with user-visible conflict log.

#### FR-32: Unified Personal+Public Timeline — Phase 2

The system presents a Timeline view combining Personal Events (warm tones) and Public Events (cool tones) in a week- or month-view. Conflicts highlighted, never alarmed. Realizes UJ-2.

**Behavioral notes:** Conflicts are surfaced as a subtle marker (no red, no sound). Conflicts are typological (work vs. social, family vs. solo) — not just temporal.

#### FR-33: Conflict-Aware Scheduling — Phase 2

The system detects scheduling conflicts between Personal Events and Public Events and suggests gentle alternatives (e.g., "Soccer practice overlaps — want a different time?"). Realizes UJ-2.

**Behavioral notes:** No auto-rebook. Surface alternatives via the **three-action pattern**: (a) **Move the personal event earlier/later**, (b) **Skip the public event** (dismiss with one tap), (c) **Keep both — I'll manage** (no further prompting). User decides; no second-guessing. Conflicts are typological (work vs. social, family vs. solo) — not just temporal.

#### FR-34: Pulse the Group — Phase 2

Small group (≤10 people) coordination via AI-assisted availability heatmap and event suggestions. Realizes UJ-6.

**Behavioral notes:** Privacy-respecting — no event titles, only free/busy shown to the group. Group size cap. Opt-in per group.

#### FR-35: Pro Tier with Calendar Sync & Group Features — Phase 2

Pro tier unlocks Calendar Sync (FR-31), Unified Timeline (FR-32), and Pulse the Group (FR-34). Free tier retains Pulse Digest + Reminders + Personal Events.

**Behavioral notes:** Pricing open (see §8 Open Questions). Free tier caps: 1 group, 1 calendar, 1 saved collection.

#### FR-36: Voice Quick-Add — Phase 3

Voice-input personal event creation. Realizes UJ-1 (Phase 3+).

**Behavioral notes:** Demo-grade UX. Adoption expected to be niche; treated as showcase feature.

#### FR-37: Email-to-Event Forwarding — Phase 3

User forwards emails to a personal @pulse.email address; LLM extracts structured Events and saves to Personal Calendar. Realizes UJ-2 (Phase 3+).

**Behavioral notes:** Power-user feature. Adoption expected to be niche.

#### FR-38: Why Now? — Phase 3

Natural-language per-event explanation of why this event in particular (vs. Why-this Tags which explain *why surfaced*). Realizes UJ-4 (Phase 3+).

**Behavioral notes:** Augments, not replaces, Why-this Tags.

#### FR-39: On-Device Personal AI — Phase 3

Local preference learning for personal events. Privacy + cost optimization phase. Realizes UJ-1 (Phase 3+).

**Behavioral notes:** Personal data never leaves device. Federated learning optional.

#### FR-40: Travel Mode — Phase 3

Hyperlocal event discovery in visited cities without per-city setup. Detects trip via calendar/email parsing. Realizes UJ-1 (Phase 3+).

**Behavioral notes:** Trip-detection via shared calendar (Phase 2 dependency). Auto-suggest only — never assume.

#### FR-41: Group Availability Heatmap — Phase 3

Visual heatmap of group availability. Realizes UJ-6 (Phase 3+).

**Behavioral notes:** Opt-in per group. Privacy-respecting (no event titles).

#### FR-42: White-Label B2B2C — Year 2+

Universities, tourism boards, sports venues reskin EventPulse24 with their branding. Deferred.

#### FR-43: B2B Insights API — Year 2+

API to query aggregated event trends for enterprise customers. Deferred.

#### FR-44: Already-Handled Reminder Suppression — Phase 2

The system suppresses a Reminder Plan slot when it detects the user has already acted on the event (RSVP'd, saved, dismissed, or marked "less like this") since the slot was scheduled. Realizes UJ-1.

**Behavioral notes:** Detection channels in Phase 2: app activity (any user action on the event card), email-link click tracking, calendar-sync integration (RSVP/move/delete from external calendar), mobile device activity (Phase 2 mobile dependency). Suppression is silent — no "we didn't send this because…" copy. A reminder slot still fires if the user hasn't acted in any channel, even if quiet hours would have otherwise suppressed.

#### FR-45: Adaptive Pulse Digest Card Count — Phase 3

The system supports adaptive digest sizing (3 / 5 / 7 cards) keyed to user's engagement signal — opted-in via a single setting after MVP data validates whether the 3-card discipline holds or breaks.

**Behavioral notes:** MVP enforces 3 cards as a discipline. Phase 3 adapts based on the user's "more like this" / "less like this" / dismissal-rate signal. If a user with a strong negative-feedback history still wants to see more, offer the choice. Default remains 3 cards.

#### FR-46: Pulse Streak — Year 2+

Calm gamification: the user keeps a "streak" of opening the Pulse Digest on time. Honors calm — no streak shaming, no missed-day punishment. Realizes the brief's "Headspace of events" ambition.

**Behavioral notes:** Treat as a brand-loyalty signal, not a metric to optimize. No "Don't break your streak!" copy. Avoid Duolingo anti-pattern. (See addendum §B Option G for why "always-on push" was rejected.)

#### FR-47: Year in Pulse Recap — Year 2+

Annual recap ("Your Year in Pulse") — Spotify-Wrapped parallel. Calm, reflective, shareable. Realizes brand ambition.

**Behavioral notes:** Opt-in to share. Generated in December each year. Personal event + public event recap.

---

## 5. Non-Goals (Explicit)

These are the things EventPulse24 **is not** and **will not** do in v1. Reviewers can hold us to this list.

- **Ticketing infrastructure.** Not building payment processing, ticket issuance, fee handling. Affiliate to Eventbrite/Ticketmaster. Capital-heavy, low-margin, and a distraction from the intelligence layer.
- **Social features / friend activity feeds.** Engagement-trap. Reinforces FOMO. Conflicts with the product's "calm" promise.
- **Event creation UI for organizers.** Not our job. Organizers are pipeline inputs, not users.
- **Ad-supported revenue.** Direct conflict with the "calm" positioning. The engagement metric is the metric the user hates.
- **Real-time trending carousels.** Manufactures FOMO. Real estate better spent on the 3 Pulse Cards.
- **Account-required browsing.** Reduces conversion; Pulse Preview exists precisely to avoid this.
- **Push-notification-spam product philosophy.** The Pulse Ping is the single daily notification. We will not become the noise the user disabled.
- **Algorithmic ranking / leaderboards.** The Pulse Digest is bounded and explainable; no "most popular this week" boards.
- **Multi-step interest quizzes.** Onboarding is ≤3 steps.
- **Creator economy or organizer tooling.** Out of scope indefinitely.
- **Group social features that look like a feed.** "Pulse the Group" (Phase 2) is coordination, not a feed.
- **Native mobile apps in MVP.** Web-first. Mobile in Phase 2+.
- **Voice Quick-Add, Email-to-Event, Travel Mode.** Phase 3+. Not in v1.
- **B2B2C / White-Label / B2B Insights API.** Year 2+.

### 5.1 Locked Product Principles

These principles are the moral core of the product. They are not aspirational — they are constraints that shape every FR, every review, every decision. If a future proposal violates a principle, the principle wins.

| Principle | Meaning |
|---|---|
| **Calm > Engagement** | Optimize for *fewer*, *better* notifications. The business model is misaligned with the engagement metric — and that's the moat. |
| **Explainable AI** | Every recommendation shows its reasoning. "Why this?" is a feature, not a hidden cost. |
| **Calendar-sync-in, not replace** | Extend Google/Apple/Outlook. Don't fight OS-level distribution. |
| **3 cards max** | Decision fatigue is the enemy. Pulse Digest is bounded by design. |
| **Trust through transparency** | Source badges, confidence pulses, no hidden ranking algorithms. |
| **No dark patterns** | No urgency badges, no "trending now," no "Don't miss out!" copy. |

**Star principle:** *The business model is misaligned with the metric — and that's the moat.* Every feature must answer: "Does this optimize for the user, or for our engagement metric?" If the answer is the latter, drop it.

---

## 6. MVP Scope

### 6.1 In Scope (Months 0–6)

Ship-ready functional requirements for the launch MVP:

- FR-1, FR-2, FR-3, FR-4 — Onboarding & Account
- FR-5, FR-6, FR-7, FR-8 — Pulse Digest
- FR-9, FR-10, FR-11, FR-12 — Reminders & Notifications
- FR-13, FR-14, FR-15, FR-16, FR-17 — Event Extraction & Source Pipeline
- FR-18, FR-19, FR-20 — Personal Event Management
- FR-21, FR-22, FR-23, FR-24, FR-25 — Explainability & Trust
- FR-26, FR-27, FR-28 — Sharing & Discovery
- FR-29, FR-30 — AI Cost Discipline

**Total:** 30 MVP FRs (FR-1 through FR-30), 17 named FRs for Phase 2/3+ (FR-31 through FR-47), 6 User Journeys, 13 Open Questions, 10 Assumptions, 9 Success Metrics + 5 Counter-metrics, 12 Risks.

**Operational:** AI Cost Dashboard, Source Registry, ToS review log.

### 6.2 Out of Scope for MVP

| Feature | Reason for deferral | Target Phase |
|---|---|---|
| FR-31 Calendar Sync (Google/Apple/Outlook) | OAuth + sync infra complexity; solo value can be proven without it | Phase 2 |
| FR-32 Unified Personal+Public Timeline | Needs calendar sync; complex UI w/ conflict logic | Phase 2 |
| FR-33 Conflict-Aware Scheduling | Needs unified timeline | Phase 2 |
| FR-34 Pulse the Group | Needs trust established first; solo must be excellent first | Phase 2 |
| FR-35 Pro Tier | Calendar sync + Pulse the Group are the value props; feature dependency | Phase 2 |
| FR-36 Voice Quick-Add | Demo magnet, niche adoption | Phase 3 |
| FR-37 Email-to-Event Forwarding | Power-user only, niche | Phase 3 |
| FR-38 Why Now? | Augments not replaces Why-this Tags | Phase 3 |
| FR-39 On-Device Personal AI | Privacy + cost optimization; not core to MVP | Phase 3 |
| FR-40 Travel Mode | Requires trip detection logic | Phase 3 |
| FR-41 Group Availability Heatmap | Needs Phase 2 group features | Phase 3 |
| FR-42 White-Label B2B2C | Year 2+ pivot option | Year 2+ |
| FR-43 B2B Insights API | Year 2+ revenue diversification | Year 2+ |
| FR-44 Already-Handled Reminder Suppression | Detects user action and suppresses duplicate reminders | Phase 2 |
| FR-45 Adaptive Pulse Digest Card Count | Data-dependent; 3-card discipline holds in MVP | Phase 3 |
| FR-46 Pulse Streak | Brand loyalty feature, not metric to optimize | Year 2+ |
| FR-47 Year in Pulse Recap | Annual brand-love feature | Year 2+ |
| Native mobile apps (iOS, Android) | Web-first; mobile in Phase 2+ | Phase 2+ |
| Real-time push notifications to mobile | Email digest first; push in Phase 2 | Phase 2 |
| Event reviews / ratings on Detail Screen | Engagement pressure; trust via neighbors + similar-events | Deferred indefinitely |

`[NON-GOAL for MVP]` callouts inside feature sections cover deferred items within features; this section captures the broader "we are not building X" statements.

---

## 7. Success Metrics

*Each SM cross-references FRs it validates. Counter-metrics counterbalance primary metrics.*

### 7.1 Leading Indicators (Weeks 1–8)

**Primary**
- **SM-1: Time-to-first-relevant-event** — Median time from first visit to first Pulse Card the user saves. Target: <30 seconds. Validates FR-1, FR-2, FR-5.
- **SM-2: Pulse Digest daily open rate** — % of users who click into the Pulse Digest on the day the Pulse Ping is delivered. Target: >60%. Validates FR-5, FR-10.
- **SM-3: Onboarding completion rate** — % of new users who complete the onboarding flow (any path) and reach the first Pulse Digest. Target: >85%. Validates FR-1.
- **SM-4: "Why this?" trust score** — % of users who answer "I trust Pulse's recommendations" YES in a weekly pulse survey. Target: >70%. Validates FR-21, FR-22, FR-23, FR-24.
- **SM-5: Per-event reminder setup rate** — % of saved Pulse Cards where the user customizes a Reminder Plan (vs. accepts default). Target: >80%. Validates FR-9.

**Secondary**
- **SM-6: D7 retention** — % of new users who return on Day 7. Target: >40%. Validates FR-5, FR-10, FR-25.
- **SM-7: Pulse Preview conversion** — % of Pulse Preview visitors who sign up. Target: >20%. Validates FR-2.
- **SM-8: Privacy page dwell > 30s** — Proxy for trust explanation depth. Target: >40% of returning users. Validates FR-21, FR-22.
- **SM-9: Personal Event creation rate** — % of returning users who create at least one Personal Event. Target: >30% by W4. Validates FR-18, FR-19.
- **SM-16: Digest novelty rate** — % of Pulse Digest cards the user has not seen in the prior 30 days. Target: >50%. Validates H2 (innovation-strategy: serendipity / discovery-of-new-events). Lower signals corpus is too narrow; higher signals the relevance filter is too loose. Validates FR-5, FR-15.

### 7.2 Counter-Metrics (Do Not Optimize)

- **SM-C1: Notification suppression rate** — % of Pulse Pings suppressed (empty digest, quiet window, etc.). Target: ≥30%. *Higher is better.* Quiet is the product. Counterbalances SM-2 (open rate).
- **SM-C2: Pulse Digest bounce rate** — % of users who open the Pulse Digest and immediately close within 5 seconds. Target: <25%. If rising, signals the digest is too noisy. Counterbalances SM-2.
- **SM-C3: Per-user reminder opt-out rate** — % of reminders marked "less like this" or muted. Target: <20%. If rising, signals bad recommendations, not bad UX. Counterbalances SM-5.
- **SM-C4: Free-tier signup cap conversion** — % of users who hit the free-tier save cap and don't upgrade paths. Target: <10%. Counterbalances growth-vs-monetization trade. Counterbalances SM-7 (Pulse Preview conversion).
- **SM-C5: AI cost per MAU** — Blended AI cost per monthly active user. Target: <$0.50/month MAU. Trend MUST be down over time. Counterbalances any "more personalization" push. Counterbalances SM-6 (D7 retention) — keeping cost down is the discipline that keeps growth sustainable.

### 7.3 Lagging Indicators (Months 2–12)

- **SM-10: Monthly Active Users (MAU)** — Target: 100K by Month 6, 1M by Month 18.
- **SM-11: Pro paid conversion rate** — Target: >5% (Phase 2). Counter-balanced by SM-C1 (notification suppression) — premium must not mean *more* notifications.
- **SM-12: Net Revenue Retention** — Target: >110%.
- **SM-13: LTV/CAC ratio** — Target: ≥3.
- **SM-14: Viral coefficient (invites per user)** — Target: >0.5 (Phase 2 unlocks invite tooling).
- **SM-15: North Star — "% of users who report Pulse made their week better"** — Weekly NPS-style survey. Target: >40% by Month 6. Counter-balanced by SM-C3 (per-user reminder opt-out) — if "made the week better" rises but opt-outs rise, the product is succeeding in spite of itself.

### 7.4 Decision Gates

- **Gate 1 (Month 3):** SEO traction + D7 retention >40% → ship MVP + invest in growth.
- **Gate 2 (Month 9):** Freemium conversion + group feature adoption → continue vs. pivot to B2B.
- **Gate 3 (Month 18):** Unit economics + viral coefficient >0.5 → scale, else niche focus.

---

## 8. Open Questions

| # | Question | Owner | Phase |
|---|---|---|---|
| 1 | Which 20 event sources to crawl / acquire for MVP? (Mix of official sites, aggregators, niche blogs?) | Eng + Product | Pre-launch |
| 2 | Calendar sync vendor — build vs. partner with Nylas/SyncGene? (Deferrable to Phase 2.) | Eng | Phase 2 prep |
| 3 | LLM provider strategy — single vendor (OpenAI/Anthropic) vs. multi-model routing? | Eng + CTO | Pre-launch |
| 4 | Pricing for Pro tier — $4.99/mo vs. $7.99/mo vs. annual-only? | Product | Pre-launch |
| 5 | Should Pulse Digest be (1 must-know + 1 nearby + 1 surprise) or rank dynamically? | Product + Data | Post-MVP |
| 6 | Geographic beachhead — 3 US cities (NYC, SF, Austin) or 1 city deeply? | Product + Marketing | Pre-launch |
| 7 | Funding runway — bootstrap vs. seed round vs. angel? | Founder | Pre-launch |
| 8 | Founding team gaps — who's the technical co-founder, AI/ML lead, designer? | Founder | Pre-launch |
| 9 | How aggressively to gate free-tier save? (1/day vs. 3/day vs. 5/day.) | Product | Pre-launch |
| 10 | Phase 2 mobile platform priority — iOS first, Android first, or both? | Eng + Product | Phase 2 prep |
| 11 | **Launch blocker** — Live research validation gap. 2 of 4 research subagents reported no live search results. Re-verify competitive landscape (esp. Luma, Apple Intelligence, Gemini in Calendar) via live search before public launch. This is a Go/No-Go gate, not a polish item. | Product | Pre-launch (blocking) |
| 12 | Source-count ceiling — at what source count does the dedup pipeline degrade? | Eng | Pre-launch |
| 13 | Personal-event default surfacing — Personal Events in Pulse Digest: opt-in or opt-out default? | Product | Pre-launch |

---

## 9. Assumptions Index

*Every `[ASSUMPTION]` inline, surfaced for explicit confirmation.*

- **[ASSUMPTION-1]** From §4.1 FR-4 Notes — Web cookies are sufficient for MVP authentication; mobile/session tokens in Phase 2.
- **[ASSUMPTION-2]** From §4.2 FR-5 Notes — Pulse Digest composition is deterministic per user per day; A/B testing done via shadow composition, not live user experience.
- **[ASSUMPTION-3]** From §4.3 FR-9 — iOS/Android push notifications are *not* in MVP. Email digest is the primary reminder channel; push comes in Phase 2 with mobile apps.
- **[ASSUMPTION-4]** From §4.9 FR-35 — Pricing for Pro tier is open (see §8 Open Question #4). $4.99–$7.99/mo range is an illustrative range, not a decision.
- **[ASSUMPTION-5]** From §4.8 FR-29 — Default AI cost threshold per MAU is $0.50/month. Configurable; this is the launch default.
- **[ASSUMPTION-6]** From §4.4 FR-13 — Source Registry is internal-only; user-facing source management is Phase 3+.
- **[ASSUMPTION-7]** From §4.5 FR-19 — Personal Events appear in the Pulse Digest by default; the user must opt out. (Open Question #13 — this is the default pending confirmation.)
- **[ASSUMPTION-8]** From §4.6 FR-25 — "Less like this" swipe is the only dismissal signal in MVP. Nuanced dismissals (e.g., "not for me but similar events are fine") in Phase 2.
- **[ASSUMPTION-9]** From §4.7 FR-26 — Public event pages are not user-generated-content; they reflect the registry's source-of-truth only.
- **[ASSUMPTION-10]** From §7.1 SM-1 — "Time-to-first-relevant-event" includes both Pulse Preview (anonymous) and post-signup first Pulse Digest. The 30-second target is for the post-signup path.

---

## 10. Constraints & Guardrails

### 10.1 Compliance & Legal

**The product's ingestion pipeline must respect the source-acquisition hierarchy (FR-17).** Crawling is permitted only when no higher-priority method exists and a ToS review has been logged in the Source Registry. The Source Registry is auditable; every change is timestamped and attributed to an owner.

**User data handling** must comply with GDPR (EU users), CCPA (California users), and equivalent regional privacy frameworks. User data export (JSON + ICS) and account deletion must be available within 30 days of request.

**Email deliverability** must comply with CAN-SPAM, GDPR, and applicable transactional-vs-marketing distinctions. Pulse Digest and reminders are transactional; one-click unsubscribe per RFC 8058 is mandatory.

**Accessibility** must target WCAG 2.1 AA. The Pulse Card, Detail Screen, and onboarding flow are audit-grade for screen-reader and keyboard navigation.

### 10.2 Privacy

- Personal data minimization: the system stores only what personalization requires.
- Personal events and personal calendar data are isolated from public event data in the database (separate tables, encryption at rest).
- Analytics are aggregated; no per-user PII in event logs.
- A user-requested account deletion purges all personal data within 30 days; aggregated anonymous analytics are retained.

### 10.3 AI Cost

The AI Cost Dashboard (FR-29) is **operational from day 1.** The default per-MAU cost threshold is $0.50/month. Any feature that pushes blended cost above threshold triggers a review.

**Lifting-cost-out-of-the-loop principle:** every Phase 2+ feature MUST include an AI cost estimate in its spec. Phase 3+ features MUST include a cost optimization plan (on-device, caching, batching).

### 10.4 Operational SLAs

- **Source freshness:** Source Registry ingestion completes at least daily; high-priority sources (official sites) within 4 hours.
- **Pulse Digest delivery:** at the user's chosen time ±15 minutes. >5-minute delays are logged.
- **Reminder delivery:** at the slot time ±5 minutes. >5-minute delays are logged.
- **Email deliverability:** bounce rate <2%, spam complaint rate <0.1%.
- **Uptime:** 99.5% for the Pulse Digest, reminders, and personal event flows. SEO public pages: 99.9%.

---

## 11. Cross-Cutting NFRs

### 11.1 Performance

- **Pulse Digest composition:** <500ms p95 (cached); <3s p95 (cold).
- **Event extraction:** <2s p95 per event.
- **Dedup pass:** <500ms p95 per event; supports batch dedup at 10K events/hour.
- **Page load:** <1.5s LCP on Pulse Digest and Detail Screen, 3G-fast.
- **API response:** <300ms p95 for read-heavy endpoints.

### 11.2 Security

- OAuth credentials for Calendar Connect (Phase 2) stored encrypted at rest.
- No PII in event logs; structured logs only.
- HTTPS-only; HSTS preload.
- CSP and SRI on all public assets.
- Rate limiting on all public endpoints (per-IP and per-user).
- Source ingestion is sandboxed; no arbitrary code execution from source content.

### 11.3 Reliability

- The Pulse Digest and reminders are SLO-monitored at 99.5% monthly.
- Source Registry ingestion failures are retried with exponential backoff (3 retries, max 8h backoff).
- User data is backed up nightly; recovery point objective (RPO) <1 hour.
- Recovery time objective (RTO) for the Pulse Digest system: <4 hours.

### 11.4 Observability

- Structured JSON logs; no PII; sampled at 100% for errors, 10% for info.
- Distributed tracing across extraction, dedup, personalization, and delivery.
- Per-feature cost metrics (FR-29) on the same dashboard as performance metrics.
- Anomaly detection on dedup merge rate (sudden changes signal pipeline drift).

### 11.5 Accessibility

- WCAG 2.1 AA target across all surfaces.
- Keyboard navigation on Pulse Digest, Detail Screen, and onboarding.
- Color contrast on Pulse Cards verified for warm-tone (Personal) and cool-tone (Public) variants.
- Screen-reader labels on all interactive elements.
- Reduced-motion preference respected.

### 11.6 Internationalization

- English-first MVP. i18n architecture in place (string externalization, locale-aware date/time).
- Multi-region rollout (EU, APAC) is Phase 2+.

---

## 12. Why Now

Three timing vectors align. Missing any one and the window closes.

1. **AI capability is here.** LLM-based structured extraction (Pydantic + Instructor + constrained decoding) is reliable enough for production event extraction at <$0.005/event. Embedding-based dedup is sub-cent at scale. (See addendum §E for tooling details.)

2. **Attention fatigue is acute.** Consumers have disabled notifications on most event apps. The "calm" positioning is a *demand* signal, not just a marketing choice. Industry-average 5–15 notifications/day is the problem EventPulse24 solves.

3. **The platform-owner window is closing.** Apple (Apple Intelligence) and Google (Gemini in Workspace) are moving into the "smart calendar" lane. They do NOT cover the **aggregation + curated calm digest across sources Apple/Google don't index** (Luma, Partiful, Bandsintown, local newsletters, personal calendars). EventPulse24 wins the consumer brand for "calm event intelligence" before the OS-level copy lands in 12–18 months.

**Risk note:** If the platform owners ship aggregation-tier features (events from Luma, Partiful, etc.) in their OS-layer events, EventPulse24's defensibility depends on the brand moat + the data moat (proprietary event corpus + user preference graph). Both are being built intentionally.

---

## 13. Aesthetic & Tone

### 13.1 Visual Aesthetic

**Anti-reference:** Eventbrite's transaction-heavy cards, Facebook Events' FOMO carousel, Eventbrite's "promoted" placements.

**Reference:** Headspace (calm illustration, parallel to "Headspace of events" brand ambition), Notion (decision-friendly minimalism), Apple Calendar (week-view restraint).

**Principles:**
- **Whitespace over density.** A Pulse Card uses ~30% of viewport vertical real estate; the rest is breath. Concrete wireframe spec lives in the UX artifact.
- **3 cards, max.** The Pulse Digest is bounded on purpose.
- **Warm tones for personal, cool tones for public.** Creates instant visual differentiation.
- **No urgency badges.** No "trending now," no "limited slots," no countdown timers.
- **No emoji-as-CTA.** Emoji are status indicators, not action prompts.

### 13.2 Voice & Tone

**Voice:** Calm, knowledgeable, restrained. Like a friend who knows the city well but doesn't oversell.

**Principles:**
- **Plain language.** "Three things worth your time this week" not "We've curated the perfect agenda for your daily life."
- **No superlatives.** No "amazing," "incredible," "must-see" — let the user decide.
- **Acknowledge the empty case.** "No pulse for today" is honest; "Nothing matches your interests yet" is condescending.
- **Why-this Tags are first-class.** They are the voice of the product.
- **No exclamation points.** Calm products don't shout.

### 13.3 Anti-patterns

- No "🚀" in subject lines.
- No "Don't miss out!" copy.
- No urgency badges on events.
- No "X people are attending" pressure.
- No "Sponsored" or "Promoted" placements.

---

## 14. Information Architecture

### 14.1 Top-Level Surfaces

| Surface | Purpose | Reaches |
|---|---|---|
| **Pulse Digest** (home) | 3-card daily brief | All users |
| **Detail Screen** | Single event deep-dive | All users |
| **Timeline** (Phase 2) | Unified calendar | All users |
| **Add Personal Event** | Manual personal event creation | All users |
| **Settings** | Reminders, quiet hours, source mute, account | All users |
| **Onboarding** | First-time flow | New users |

### 14.2 Navigation

- Bottom-tab web navigation (responsive): **Digest** · **Timeline** · **Add** · **Settings**.
- Phase 2 adds: **Groups** (Pulse the Group).
- Phase 3 adds: **Travel**.

### 14.3 Detail Screen Composition

```
[ Source Badge · Confidence Pulse ]
[ Event Name (large, calm) ]
[ When · Where ]
[ Why-this Tags (3 keywords) ]
[ Description (2-3 lines) ]
[ Reminder Picker (chips: 5d / 2d / 1d / 1hr) ]
[ Save to Pulse · Share · Dismiss ]
[ Why-this breakdown (expandable) ]
[ Similar events you've attended ]
[ 👥 X neighbors (if available) ]
```

**No reviews / ratings element.** Design Thinking wireframe Screen 7 included a "⭐ 4.7 (213 reviews)" element. This is explicitly excluded from MVP. Rationale: reviews are (a) a moderation burden, (b) gamification pressure ("X people attended and rated 4.7"), (c) inline with the engagement-trap incumbents. The "neighbor count" + "similar events you've attended" carry the trust signal without reviews. If a future Phase 3+ team proposes reviews, the principle **Trust through transparency** applies — and the threshold is high.

---

## 15. Monetization

### 15.1 Free Tier

- Pulse Digest (3 cards/day)
- Personal Events (manual, ≤50 active)
- Multi-tier reminders (email)
- Pulse Preview (anonymous)
- Pulse Ping (1/day)

**Caps:** `[ASSUMPTION: 1 calendar (own only), 1 saved collection, 50 active personal events, 1 group (Phase 2).]`

### 15.2 Pro Tier (Phase 2 — FR-35)

- Calendar Sync (Google/Apple/Outlook)
- Unified Timeline
- Pulse the Group (unlimited)
- Why Now? (Phase 3)
- On-Device Personal AI (Phase 3)
- Travel Mode (Phase 3)

**Pricing:** `[ASSUMPTION: $4.99–$7.99/mo range, open; final pricing in Phase 2 PRD.]`

**No ads. No commissions. No data sales.** The business model is misaligned with the engagement-trap metric. That misalignment is the moat.

### 15.3 Future

- **B2B2C (Year 2+):** White-label for universities, tourism boards.
- **B2B Insights API (Year 2+):** Aggregated event trend queries for enterprise.

---

## 16. Platform

| Phase | Surface |
|---|---|
| **MVP** | Responsive web (mobile-first, desktop-friendly) |
| **Phase 2** | Native iOS + Android (priority order open; see §8) |
| **Phase 3+** | Voice assistants (Alexa, Google Assistant surface); Email-to-Event integration |

**MVP form factor:** Web-first. Tailwind + responsive layouts. No native app in MVP. The Pulse Digest is the canonical surface; mobile web is the dominant access method.

---

## 17. Risks & Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | **Apple/Google add AI to native calendar** (covered: aggregation + curated calm digest lane, not smart calendar) | Medium | Critical | Web-first, cross-platform, brand moat; move fast on consumer brand before OS-level copy; re-verify positioning pre-launch (Open Q #11) |
| 2 | **AI inference costs spiral** | Medium | High | AI Cost Dashboard (FR-29); cache + batch (FR-30); on-device AI (Phase 3 — FR-39); per-feature cost targets from day 1 |
| 3 | **Web crawling legally blocked** | High | High | Source-acquisition hierarchy (FR-17); legal review on every source; pivot to partnerships / ICS-import / email-to-Event |
| 4 | **Cold start unsolved (personalization requires data)** | High | Critical | SEO flywheel for public events first; Pulse Preview shows anonymous value before signup; Phase 2 unlocks personalization |
| 5 | **Incumbent copycat (Eventbrite ships Pulse Digest)** | Very High | Medium | Brand + data moat; Pulse Digest is a feature, calm is the brand; Pulse the Group (Phase 2) is the network-effect moat. Likelihood is High because the pattern is *familiar*; impact is only Medium because a single product surface is replicable, not the brand. |
| 6 | **Luma expansion into the calm-digest lane** | Medium | High | Cadence + explainability differentiators; brand moat; aggregation breadth (Luma covers tech/community, we cover everything else) |
| 7 | **Source-corpus drift (small MVP corpus)** | Medium | Medium | 20-source MVP target; geographic beachhead focus (Open Q #6); SEO crawl + city pages fill gap |
| 8 | **Solo value prop too weak (no group/network effects)** | Medium | High | Pulse the Group in Phase 2 (network effect unlock); solo value must be excellent first |
| 9 | **Dedup pipeline degrades at scale** | Low | Medium | Source-count ceiling tracked (Open Q #12); embedding model swap path; canonical URL primary signal |
| 10 | **Pulse Digest is too noisy at Phase 1** | Medium | High | Counter-metric SM-C2 (bounce rate); A/B shadow composition; explicit empty-state card |
| 11 | **User-trust collapse** — opaque ranking, surprise data use, or security breach erodes the brand moat. | Medium | Critical | FR-21–24 explainability; Source Badge transparency; no ads / no data sales; ToS-reviewed sources only (FR-17); kill-switch to revert to anonymous-only mode if breach or compliance event. Trust-eroding failure ends the company. |
| 12 | **MAU target conflict** — Innovation strategy names 100K MAU by Month 18; PRD SM-10 names 1M. | — | — | Owner: Product. Reconcile via a revised marketing plan once funding runway is decided (Open Q #7). PRD uses 1M as the success target; 100K is the live-or-die threshold for the B2B pivot decision (Gate 2). |

**Backup plan:** If consumer traction fails by Month 9, pivot to B2B2C (university/tourism board white-label) using same AI infrastructure.

---

## 18. References

- **Product Brief:** `_bmad-output/planning-artifacts/briefs/brief-EventPulse360-2026-08-19/brief.md`
- **Innovation Strategy:** `_bmad-output/innovation-strategy-2026-08-19.md`
- **Design Thinking:** `_bmad-output/design-thinking-2026-08-19.md`
- **Blue Ocean Strategy:** `_bmad-output/blue-ocean-strategy-2026-08-19.md`
- **Original scope:** `docs/scope.txt`
- **Addendum (this run):** `prd-EventPulse360-2026-08-19/addendum.md`
- **Memlog (this run):** `.memlog.md`

---

_Generated using BMad PRD Workflow. Synthesis sources: Product Brief + Innovation + Design Thinking + Blue Ocean + 2025-2026 landscape research._
