---
title: "PRD: EventPulse24"
status: amended-2026-08-29
created: 2026-08-19
updated: 2026-09-03
project: EventPulse24
author: Jobaer
sources:
  - _bmad-output/planning-artifacts/briefs/brief-EventPulse24-2026-08-19/brief.md
  - _bmad-output/planning-artifacts/briefs/brief-EventPulse24-2026-08-19/addendum.md
  - _bmad-output/innovation-strategy-2026-08-19.md
  - _bmad-output/design-thinking-2026-08-19.md
  - _bmad-output/blue-ocean-strategy-2026-08-19.md
  - docs/scope.txt
amendments:
  - 6 amendments (A-1 Event Identity, A-2 Serendipity slot, A-3 Static weights, A-4 User reports in MVP, A-5 Conflict resolution, A-6 Timezone source) merged on 2026-08-29
  - 43 MVP FRs (was 41; +2 from FR-59 and FR-60); 17 named FRs for Phase 2/3+
---

# PRD: EventPulse24

> **The calm intelligence layer above all event sources.**

## 0. Document Purpose

This PRD is the source of truth for Product, Engineering, Design, and the downstream BMad workflows (UX, Architecture, Epics) for the launch of EventPulse24. It is anchored in the **Product Brief** (`brief-EventPulse24-2026-08-19/brief.md`) and the three strategy documents it synthesizes (Innovation, Design Thinking, Blue Ocean). Sections build on those artifacts instead of duplicating them — depth and rationale that does not earn its place in the PRD-main narrative lives in `addendum.md`.

Vocabulary is Glossary-anchored; every domain noun is defined once in §3 and used verbatim from there. Functional Requirements (FRs) are numbered globally and stable across downstream references. Inferred items are tagged `[ASSUMPTION: ...]` inline and indexed in §9. Open Questions are tracked in §8 and re-checked at Finalize.

Stakes: **Seed-stage public launch.** Sections reflect full quantitative rigor (NFRs, metrics, risks, mitigations).

---

## 1. Vision

EventPulse24 is the **calm intelligence layer above all event sources.** Users are drowning in events they didn't ask about, missing events they care about, and exhausted by notifications that don't respect their attention. EventPulse24 is the single, trustworthy surface that uses AI to surface the small number of events that matter to each user, and delivers them via context-aware, multi-tier reminders that *reduce* notification volume instead of adding to it.

The product unifies **personal** calendar events (birthdays, meetings, weddings) with **public** events (concerts, tech meetups, government programs, sports) from across the open web into a single calm timeline with intelligent conflict detection — a capability no incumbent owns. EventPulse24 monetizes **calm** — a business model whose metric is *fewer, better* notifications, in deliberate misalignment with the engagement-optimized industry.

The MVP ships as a web-first product with AI-curated daily **Pulse Digest** (3 cards), **Pulse Ping** (one daily notification, not many), per-event **multi-tier reminder** picker (5d/2d/1d/1hr), explainable **"Why this?"** micro-tags, and a **Source Badge** for trust. Growth comes through SEO-driven public-event discovery, then viral group coordination ("Pulse the Group") as the compounding network effect in Phase 2.

**Why now:** AI cost curves have collapsed, attention fatigue is acute, and Apple/Google's native calendar AI features cover the "smart calendar" lane but not the **aggregation + curated calm digest** across sources Apple/Google don't index. The window is 12–18 months before platform owners notice the consumer layer EventPulse24 defends. (See §12 for the full Why-Now analysis; §17 Risk #1 for the platform-owner threat; §12.1 for the pre-launch competitive re-verification gate.)

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

- **Event creators / organizers**: we do not host creation UIs, payment infrastructure, or organizer tooling. Organizers are pipeline inputs, not users.
- **Power users who want every event**: the product philosophy is *less*, not *more*. Power users prefer Eventbrite, Meetup, or Facebook Events.
- **Ticketing-driven users**: if the primary goal is to buy a ticket, EventPulse24 redirects to Eventbrite/Ticketmaster via affiliate.
- **Tightly coupled social-feed users**: if the value of events is the social graph (Facebook Events), this is the wrong product.
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
1. EventPulse24 (MVP — FR-3 / FR-50) syncs Maya's **Apple Calendar (CalDAV)** in the background via the iCloud shared-calendar surface that Maya's EventPulse24 connect is already linked to (shared iCloud calendars are surfaced by the Apple CalDAV connect). Note: deep-linking to a non-user's primary iCloud calendar remains a Phase 2 enhancement — at MVP, Maya sees events that her husband adds to a calendar shared with her Apple ID.
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
1. Pulse Preview (home page) shows 3 events in her inferred city (geo-IP default), each with `Why this?` micro-tags, an inline `Source Badge` (FR-23), and a 1–5 dot `Confidence Pulse` (FR-22). Trust signals are inline and first-class — not behind a tap.
2. She clicks "Sign up" → onboarding flow: 30 seconds, max 3 steps.
3. Step 1: optionally connect any of three supported calendar providers (Google Calendar via OAuth 2.0, Apple Calendar via CalDAV, Outlook Calendar via Microsoft Graph), or skip.
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

- **Event**: A single time-bounded happening with a name, start time, location, and source. May be public (sourced from a public source) or personal (created by the user). Cardinality: 1-to-many Sources, 1-to-1-or-0 ReminderPlan. Every Event has a canonical `event_id` (see **Event Identity**), a `start_time_tz` field with explicit timezone (see FR-60), and a `tz_inference_confidence` field (1.0 if the source provided a timezone; lower if inferred).
- **Event Identity**: The canonical tuple `(source_id, source_event_id, venue_fingerprint, start_time_with_tz, title_fingerprint)` that uniquely identifies an Event across ingestion cycles. Two extracted records refer to the same Event if any of the following hold: (a) `source_id + source_event_id` match exactly; (b) `(venue_fingerprint, start_time_with_tz)` match exactly AND `title_fingerprint` token-overlap (Jaccard, stop-word-filtered) ≥80%; (c) canonical URL matches. Embedding cosine similarity is **not** an identity signal — it is a review-queue routing signal only. Recurring events (e.g., a tech meetup every Thursday) are distinct `event_id`s linked by a shared `series_id`. Postponements within ±30 days of the original start time update the same `event_id`; postponements beyond ±30 days create a new Event. State changes (postpone, cancel, move, sold-out) update the same `event_id` and append to `state_history`.
- **Source**: A provenance record for an Event. Types: `official_site` (verified venue/organizer), `community` (community-posted, e.g., Luma), `aggregator` (e.g., Eventbrite public listing), `user_imported` (user-forwarded email/ICS), `crawled_html` (last resort, ToS-reviewed). Each Source has a reliability score.
- **Pulse Digest**: The home surface. A daily, fixed-cadence, 3-card brief delivered to the user. Default delivery: 8:00 AM local. Each card is a Pulse Card.
- **Pulse Preview**: The no-auth public surface shown to first-time and unauthenticated visitors. 3 Pulse Cards in the user's inferred city (geo-IP default, one-tap city override). Soft-walls at the "Save to Pulse" CTA — signup is required to save, not to browse.
- **Pulse Card**: A *projection* of an Event in a specific User's Pulse Digest at a specific composition time. Not a separate entity. Shows: event name, time (user-local; venue-local on Detail Screen if cross-timezone), location, up to 3 Why-this Tags, 1–5 Confidence Pulse, Source Badge, and (if applicable) Conflict Indicator. Tappable to Detail Screen.
- **Pulse Ping**: The single daily notification that brings the user back to the Pulse Digest. **Not** an event-specific reminder. Counter to industry's 5–15/day blast.
- **Quiet Hours**: The user-configured time window during which no notifications or emails are sent. Free tier: a single window (e.g., 10pm–7am). Pro tier: per-day-of-week windows (FR-51). Reminders and Pulse Pings falling inside Quiet Hours are silently deferred to the window end; no next-day surprise.
- **Why-this Tags**: Up to 3 keywords on a Pulse Card explaining *why* the event was surfaced (e.g., `nearby, tonight, music`). Why-this Tags are **category descriptors**, not full explanations; the full reasoning is on the Detail Screen (FR-24). On Slot 3 (serendipity) cards, the tag reads `discovery` or `new-to-you` instead of a category name (per Amendment A-2 / FR-5). Same tags appear on the Pulse Card and on the Detail Screen.
- **Confidence Pulse**: A 1–5 dot indicator on each Pulse Card showing AI certainty about relevance. 5 = very strong match; 1 = weak. Persisted on the Event record.
- **Source Badge**: A small visual label on each Pulse Card and Detail Screen indicating the Source type. `official_site` = ✅, `community` = 👥, `aggregator` = 🔗, `user_imported` = 📥, `crawled_html` = ⚠️.
- **Detail Screen**: The expanded view of a Pulse Card. Shows: full event description, location with map, reminder picker, share, save, dismiss, Why-this breakdown, similar events user has attended, neighbor count.
- **Neighbor Count**: A signal on the Detail Screen showing how many other EventPulse24 users are in the same area and tracking the same event (`👥 X neighbors`). Revealed only when at least 1 qualifying user exists; absence is silent, not a zero. Privacy-respecting — no identifying information.
- **Timeline**: A unified calendar view (Phase 2) showing Personal Events (warm tones) and Public Events (cool tones) in one week- or month-view. Conflicts highlighted, never alarmed.
- **Personal Event**: A user-created or calendar-synced event (birthday, meeting). Exists in the user's Personal Calendar. Phase 2 surfaces a Personal Event in the Timeline; MVP surfaces it only via manual add in the EventPulse24 UI.
- **Conflict Indicator**: A small (8–10 px) filled, neutral-tone circle icon positioned at the top-right corner of the Pulse Card, indicating that the event overlaps with another event the user has saved or set a Reminder Plan for. Color is desaturated amber (#B8893D or equivalent), never red. Accompanied by `aria-label="Schedule conflict"`. Distinct in shape from the Source Badge (✅/👥/🔗/📥/⚠️) and the Confidence Pulse (● dots). The indicator is symmetric across the conflict pair (both events show it). The indicator persists after the user has explicitly chosen "Keep both" (FR-58) as a calm permanent reminder.
- **Conflict Resolution**: A user decision on a conflict prompt, recorded as one of: `keep_both`, `edit_new`, `delete_new` (Personal-vs-Personal time conflict); or `keep_both`, `update_existing`, `delete_new` (Personal-vs-Personal duplicate). The resolution is recorded as a `ConflictResolution` value object. There is no `dismiss` resolution — the user must make an explicit choice.
- **Public Event**: A Source-sourced event not created by the user.
- **Reminder Plan**: A per-Event set of up to N reminder slots (default: 5d, 2d, 1d, 1hr before). **Pulse Ping is NOT part of any Reminder Plan** — it is a separate, global per-day notification (FR-10). User-editable per event. All slots subject to Quiet Hours deferral.
- **Preference Graph**: Per-user behavior-derived data structure (dwell, swipes, dismissals, saves) that drives Pulse Digest composition. Built incrementally; cold-start is SEO/geo-derived.
- **Pulse the Group**: Phase 2 feature: AI-assisted small-group coordination (UJ-6). NOT a social feed.
- **Travel Mode**: Phase 3 feature: hyperlocal event discovery in visited cities without per-city setup.
- **Voice Quick-Add**: Phase 3 feature: voice-input personal event creation. Demo magnet, niche adoption.
- **On-Device Personal AI**: Phase 3 feature: local preference learning for personal events. Privacy + cost optimization.
- **Why Now?**: Phase 3 feature: per-event "why should I attend this in particular" natural-language explanation (vs. Why-this Tags which explain *why surfaced*).
- **Pro Tier**: The paid tier. **Ships at MVP launch** ($4.99/month or $49/year) with: unlimited saves + saved collections (FR-49), up to 3 connected calendar providers — Google + Apple + Outlook (FR-50), per-day-of-week custom quiet hours (FR-51), JSON+ICS data export (FR-52). Free tier caps saves (1/day) and connected providers (1 of 3); see FR-48. Phase 2 augmentation adds two-way calendar sync, Pulse the Group, Unified Timeline (FR-35).
- **Free Tier**: Unauthenticated browsing via Pulse Preview. Authenticated users on the free tier see the full Pulse Digest (3 cards/day) and can save up to **1 Pulse Card per 24-hour period**; the 2nd save action triggers a calm in-app CTA to upgrade to Pro (FR-48). Feature caps apply (see §15.1).
- **Source Reliability Score**: Per-Source trust score (0.0–1.0) computed from extraction accuracy, user dismissal rate, and editorial review. Lowers ≠ removes a Source; changes its ranking.
- **AI Cost Dashboard**: Internal-facing per-feature telemetry (FR-29) tracking spend on extraction, embeddings, classification, and personalization.
- **EventReport**: A user-submitted quality report on an Event, created via FR-59. Composed of (User, Event, category ∈ {wrong_date, wrong_venue, not_exist, duplicate}, timestamp). Rate-limited to 5 per user per day. Routed to the editorial review queue (FR-57) with priority `user_reported`. Retained 24 months.
- **Source tz_coverage**: A per-Source field (`full` / `partial` / `none`) indicating whether the source emits event timestamps with explicit timezones. See FR-60.

---

## 4. Features

Features grouped into coherent behavioral clusters. FRs globally numbered and stable. Each FR is testable. References to UJs inline (`realizes UJ-X`). Inferred items tagged `[ASSUMPTION: ...]`.

### 4.1 Onboarding & Account

**Description:** A user from cold start to first personal Pulse Digest in ≤30 seconds (post-signup path). Realizes UJ-3. The flow is glass-floor simple: skip most steps, get immediate value, configure later. Onboarding never asks for things the system can infer (city from geo-IP, interest from first interactions).

**Two distinct first-value moments (decomposed promise):**
1. **Pulse Preview (pre-signup, anonymous):** ≤1.5s page load on 3G-fast. 3 cards rendered from pre-computed city-page cache (not live AI). See FR-2.
2. **First authenticated Pulse Digest (post-signup):** ≤30 seconds from "Sign up" tap to digest visible. Cached composition for first-paint; live personalization kicks in on second visit.

**Promise rationale:** The 30-second target is the post-signup path. Pulse Preview is the no-auth gateway — the user sees the product's value before being asked to sign up.

#### FR-1: 30-Second Onboarding Flow

The system provides an onboarding flow with at most 3 user-visible steps: (1) optional calendar connect, (2) optional interest chips (3 picks), (3) digest delivery time + timezone. The user can skip any step. Realizes UJ-3.

**Consequences (testable):**
- An onboarding flow that exceeds 3 steps before the first Pulse Digest is shown violates FR-1.
- An onboarding step that *requires* user input (rather than allows skip) violates FR-1.
- A user who skips all steps still sees a geo-IP-inferred Pulse Digest on first login.
- The first post-signup Pulse Digest is rendered from a pre-computed cached composition (city + time-of-day hash); the live personalized composition replaces it on the second digest.
- A user who abandons onboarding mid-step is resumed at the same step on return within 7 days (per §10 privacy/UX).

**Out of Scope:** Multi-step "interest quizzes" of more than 3 picks. Detailed profile completion. Account verification before Pulse Digest.

#### FR-2: Pulse Preview (No-Auth First Value)

The system surfaces a Pulse Preview (3 events in the user's inferred city) on the public home page and as the first surface for unauthenticated visitors. Realizes UJ-3.

**Consequences (testable):**
- A first-time visitor without an account sees at least 2 Pulse Cards without signup.
- A "Save to Pulse" CTA on a Pulse Card in Pulse Preview soft-walls at the 3rd card (signup required at the save tap).
- Geo-IP is the default city; one-tap change to override.
- **Geo-IP consent disclosure:** On first Pulse Preview visit, a small banner appears at the top of the page: "Showing events near [city]. Use a different city? [Change] [Use this] [Don't use my location]." The user's choice persists in a cookie for the session; "Don't use my location" suppresses geo-IP and falls back to the most-popular city (NYC at MVP). The choice is also surfaced in Settings → Privacy after signup.

**Out of Scope:** Personal event surfacing in Pulse Preview. Personalization before signup.

#### FR-3: Calendar Connect (Optional OAuth — Google / Apple / Outlook)

The system supports optional auth-based connection of three calendar providers at MVP: **Google Calendar** (OAuth 2.0), **Apple Calendar** (CalDAV, app-specific password), and **Outlook Calendar** (Microsoft Graph OAuth 2.0). All three are presented as equal-weight options in the onboarding Step 1 picker (UX: `mockups/onboarding-step1-desktop.html` §1). Skippable per provider and per step. Realizes UJ-2.

**Consequences (testable):**
- A user sees all three providers in the onboarding Step 1 picker, with the active provider at MVP (Google) styled as a primary CTA and the two onboarding-paired providers (Apple, Outlook) styled as primary-equivalent buttons (per `DESIGN.md` Form Control Patterns).
- A user can complete auth for any of the three providers and see their personal events in the Calendar Connect step without leaving the onboarding flow.
- A user can skip Calendar Connect entirely and still receive a Pulse Digest from public events + on-platform Personal Events.
- Revoked auth credentials are detected on next sync and the user is prompted to reconnect, not silently denied.
- A user can connect multiple providers (e.g., Google for work + Apple iCloud for family); events from all connected sources flow into the Pulse Digest as warm-tone Pulse Cards.

**Provider parity contract at v1:** All three providers ship the same read-only sync behavior at MVP — same polling interval, same event-shape normalization, same Source Badge attribution (`user_imported` with provider tag), same conflict detection, same personal-event surfacing in Pulse Digest. The only provider-specific differences are: (a) auth handshake (OAuth 2.0 vs. CalDAV), and (b) provider name in UI/tooltips. Engineering does not ship a "Pro-only" gate on Apple/Outlook sync — the Free tier gets the same one-calendar connect at MVP (the Free-tier calendar cap is removed; see Amendment A-7 below).

**Amendment A-7 (v1-spec):** The deferred "Apple/Outlook sync is Phase 2 / Pro-only" stance from prior versions is **superseded**. Calendar Connect is now a **Free-tier, three-provider, MVP-ship** feature. Apple (CalDAV) and Outlook (Microsoft Graph) ship alongside Google at MVP launch. The earlier FR-50 carve-out and the Phase 2 deferral language in §6.2 / §4.11 are updated below.

**Out of Scope at MVP:** Calendar write-back (push events from EventPulse24 → calendar). Two-way sync with field-level conflict resolution. Recurring-event RRULE expansion handling beyond simple instance listing (Phase 2 — FR-31). Shared/family iCloud calendar deep-linking (Phase 2 — see addendum C, Maya's husband use case).

#### FR-4: Authenticated User State

The system persists authenticated user state across sessions (web cookie + server session). Realizes UJ-1, UJ-3.

**Consequences (testable):**
- An authenticated user reopening the app within 7 days is not prompted to re-authenticate.
- An unauthenticated user with a stale OAuth token is redirected to onboarding with state preserved.

**Notes:** `[ASSUMPTION: web cookies are sufficient for MVP; mobile/session tokens in Phase 2.]`

---

### 4.2 Pulse Digest (Home)

**Description:** The daily morning brief. The product's moment-of-truth surface. Realizes UJ-1. Bounded by design: 3 cards, max. Decision fatigue is the enemy.

#### FR-5: Pulse Digest Composition (revised by Amendment A-2)

The system composes a Pulse Digest of 3 Pulse Cards per user per day using **slot-specific scoring** keyed to the user's Preference Graph, location, and Source Reliability Scores. Realizes UJ-1.

**Slot structure:**

- **Slot 1 ("must-know")** — Personal Events eligible (warm-tone; see FR-19). If no Personal Event is eligible within the next 48 hours, falls back to the highest-scoring eligible public event in the user's beachhead.
- **Slot 2 ("nearby")** — `score = source_reliability × geographic_distance_factor × freshness_factor`, with city-wide popularity as a **tie-breaker only** (not a multiplier).
- **Slot 3 ("serendipity")** — `score = source_reliability × geographic_distance_factor × freshness_factor × (1 - normalized_popularity)`. Explicit anti-popularity bias. Restricted to a category distinct from the user's most-engaged category (per Preference Graph; default to "least-engaged category in beachhead" during cold start).

**Consequences (testable):**

- A Pulse Digest contains exactly 3 cards on a standard day. Exception: a "No pulse for today" empty state (FR-8).
- A Pulse Card in the digest is not a duplicate (same `event_id`) of another.
- The 3 cards honor the diversity floor by slot design (Slot 3 is structurally serendipity; see also FR-25 for the post-launch regression guarantee).
- The system can run an empty-state Pulse Digest when there are no qualifying public events and no eligible Personal Events. In this case, the digest shows one card: "No pulse for today."
- Per-slot engagement is tracked on the AI Cost Dashboard: `slot_1_save_rate`, `slot_2_save_rate`, `slot_3_save_rate`, `slot_3_bounce_rate`.

**Cold-start composition (users with <7 days of Preference Graph data, until ADR-0007 signal threshold is defined):**

- Slot 1 and Slot 2 use the original cold-start formula: `popularity × source_reliability × geographic_distance_factor × freshness_factor` with Bayesian smoothing (α=5, β=5).
- Slot 3 uses the **inverted** formula above regardless of cold-start state.
- The geographic distance factor decays from 1.0 (same neighborhood) to 0.3 (different city) using haversine on the user's home city centroid. Events outside the user's home country fall to 0.1.
- The freshness factor is 1.0 for events ≥3 days out, 1.2 for events 1–3 days out, 1.5 for events ≤24 hours out.
- "Most-engaged category" during cold start = the highest-popularity category in the user's beachhead over the prior 30 days. "Distinct" means Jaccard overlap on category tags <0.3.
- Popularity tie-breaker (Slot 2 cold start) is the Bayesian-smoothed posterior mean (α=5, β=5 prior; same as FR-16).

**Personalized ranking (after cold-start window):**

- All three slots use personalized ranking with slot-specific weights. Slot weights are tracked on the AI Cost Dashboard and are subject to the static-weights rule (Amendment A-3 / FR-22).
- Personalized ranking weights are NOT applied until the signal threshold in the deferred ADR-0007 is met.

**Out of Scope:** More than 3 cards. User-configurable digest size. Per-event "I want more of this" in MVP — Phase 2 (FR-33).

**Notes:** `[ASSUMPTION-2]` — A/B testing done via shadow composition in the AI Cost Dashboard, not live user experience. Live weights are static post-launch (Amendment A-3).

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
- A reminder is suppressed if the device is active (Phase 2 mobile) or the user is in a user-configured Quiet Hours window.

**Out of Scope:** Push notifications to mobile in MVP (email digest only); see FR-11.

#### FR-10: Pulse Ping — Single Daily Notification

The system sends exactly one Pulse Ping notification per user per day, at the user's chosen delivery time, linking to the Pulse Digest. Realizes UJ-1, UJ-3.

**Consequences (testable):**
- A user with 0 qualifying public events AND 0 Personal Events in the next 48 hours does NOT receive a Pulse Ping.
- A user with 1+ Personal Events (FR-19) in the next 48 hours — even with 0 public events — DOES receive a Pulse Ping (the user's personal commitment is the qualifying event). The Pulse Digest renders with personal-event cards only.
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
- A reminder slot that falls in the Quiet Hours window is sent at the Quiet Hours window end, not during it.
- A Pulse Ping inside the Quiet Hours window is silently deferred (no notification stack, no next-day surprise).

**Out of Scope:** Per-day-of-week Quiet Hours customization in MVP (Free tier — single window only). Per-category Quiet Hours in MVP.

---

### 4.4 Event Extraction & Source Pipeline

**Description:** The system that ingests events from public sources. Architecture is hybrid: official APIs > partnerships > RSS/JSON-LD > email/ICS import > web crawling (last resort, ToS-reviewed). Critical to product: the source registry is the corpus. Each event has a Source. Each Source has a reliability score.

#### FR-13: Source Registry

The system maintains a Source Registry, one record per event source. Each record includes: source name, source type, source URL, acquisition method (API / partnership / RSS / email-ICS / crawl), ToS review status, reliability score, ingestion cadence, last-ingestion timestamp. Realizes UJ-1.

**MVP source-floor requirements (launch gating):**
- The Source Registry must contain at least **40 active sources** at MVP launch, with at least **15 sources per geographic beachhead city** (initial beachhead per Open Q #6).
- The corpus mix: ≥50% official API / partnership sources, ≤30% RSS/JSON-LD, ≤20% web crawl.
- At least 8 distinct event categories are represented (concerts, tech meetups, sports, community, government, family/parenting, arts, food/dining).
- The Source Registry is internally auditable; every change is logged.

**Consequences (testable):**
- A Source with `acquisition_method = crawl` and `tos_review_status != approved` is blocked from ingestion.
- A Source with no ingestion in the last 2× expected cadence is flagged for review.
- The Source Registry is internally auditable; every change is logged.
- A launch-go gate: <40 sources or <15 per beachhead city fails the launch checklist.

**Out of Scope:** Self-serve source registration by users (Phase 3 candidate).

#### FR-14: Hybrid Event Extraction Pipeline

The system extracts structured Events from sources using a hybrid pipeline: structured-API sources emit JSON-LD or direct API responses (preferred); HTML-only sources use LLM-based structured extraction with constrained decoding against a Schema.org Event schema. Realizes UJ-1.

**Hallucination guardrails (launch gating):**
- **Confidence floor to publish:** Every extracted event carries an `extraction_confidence` (0.0–1.0). Events below **0.7** are routed to a quarantine queue (not published to digest). Editorial team reviews; under 0.5 confidence is auto-rejected.
- **Cross-check against raw text spans:** For HTML extraction, key fields (event name, start time, venue) must be present in the source HTML. An extracted event where any of these fields is not verifiable in the source is flagged for human review.
- **Multi-provider fallback:** When the primary LLM provider is unavailable or returns schema-validation failures, the system retries with a secondary provider. After 2 consecutive failures, the source is paused and paged to editorial.
- **Freshness TTL per source:** Each source has a `freshness_ttl_hours` (default 24h). Events older than 2× TTL are not surfaced in fresh digests (they are archived but accessible via search).

**Consequences (testable):**
- A source emitting valid Schema.org Event JSON-LD is parsed without LLM call.
- An HTML-only source triggers LLM extraction with constrained decoding (Pydantic + Instructor + JSON Schema); schema validation rejects any response that fails shape.
- Extraction latency target: <2 seconds per event at p95.
- Extraction cost target: <$0.005 per event blended (LLM extraction for HTML + free for structured).
- An event with `extraction_confidence < 0.7` is never shown in the Pulse Digest until reviewed.

**Out of Scope:** Real-time extraction from social posts (Phase 3+). User-facing extraction quality dashboard.

#### FR-15: Event Deduplication (revised by Amendment A-1)

The system deduplicates extracted events using **Event Identity** (canonical tuple; see §3 Glossary). Identity is computed once at ingestion and is structural, not semantic. **Embedding cosine similarity is a review-queue routing signal, not an identity signal.**

**Consequences (testable):**

- Two extracted records with matching `source_id + source_event_id` are auto-merged (same Event).
- Two extracted records with matching `(venue_fingerprint, start_time_with_tz)` AND `title_fingerprint` Jaccard ≥80% are auto-merged.
- Two extracted records with matching canonical URL are auto-merged.
- Two extracted records with embedding cosine ≥0.95 (summary vectors) are added to the editorial review queue (FR-57) as "possible duplicate" — NOT auto-merged.
- Two extracted records with embedding cosine 0.85–0.95 are flagged on the Source Pipeline dashboard as "watch" — NOT auto-merged.
- Two extracted records with embedding cosine <0.85 produce no dedup action.
- The dedup pass is idempotent: re-extracting the same source does not create duplicates.
- A postponed event whose `start_time_with_tz` changes within ±30 days updates the same `event_id` and appends to `state_history`.
- A postponed event whose `start_time_with_tz` changes by more than ±30 days creates a new Event.
- Recurring events (same `series_id`, multiple `event_id`s) are *not* dedup-merged across instances.
- Embedding model swap does not break dedup: identity is structural.

**Out of Scope:** Cross-language dedup (Phase 3). Auto-merge across >2 ambiguous candidates (always routed to editorial review).

#### FR-16: Source Reliability Score

The system maintains a per-Source reliability score (0.0–1.0) updated from extraction accuracy, user dismissal rate, and editorial review. A low score lowers ranking; it does not remove the source. Realizes UJ-1.

**Statistical guardrails (launch gating):**
- **Bayesian smoothing:** Reliability scores use a beta-binomial model with prior α=5, β=5 — a single negative event cannot crater a source. The display score is the posterior mean, not raw rate.
- **Min-N threshold:** A source needs at least **30 dismissal observations** before its score moves. New sources start at the prior mean (0.5).
- **Spike detection:** A 3× week-over-week drop in reliability score triggers an automatic editorial review (no auto-removal).

**Consequences (testable):**
- A Source with reliability score <0.3 AND ≥30 observations is escalated to editorial review.
- A Source ranked low in the Source Reliability Score is ranked low in the Pulse Digest.
- The score is updated at least weekly.
- A new source (under 30 observations) cannot have its score drop below 0.32 (the prior-posterior floor).

**Out of Scope:** User-facing source blocking.

#### FR-17: Source Acquisition Hierarchy Enforcement

The system enforces acquisition-method priority: official APIs > partnerships > RSS/JSON-LD > email/ICS import > web crawling (last resort). A Source is added with the highest-priority method available; crawling is permitted only when no higher-priority method exists and a ToS review has been logged. Realizes UJ-1.

**Consequences (testable):**
- A request to add a crawlable source without a logged ToS review is rejected.
- An existing crawl source whose API becomes available is migrated to API and `acquisition_method` updated.

**Notes:** This FR is the explicit compliance guardrail for the platform. See §5 Non-Goals and §11 Cross-Cutting NFRs.

#### FR-56: RSS / Email-ICS Source Acquisition (MVP)

The system supports RSS feed and email-ICS-import as first-class source acquisition methods at MVP. This is moved up from Phase 3 to address the 40-source corpus floor (FR-13). Realizes UJ-1.

**Consequences (testable):**
- A Source with `acquisition_method = rss` is ingested at the source's declared cadence (default: every 4 hours) without LLM extraction (RSS already structured).
- A Source with `acquisition_method = email_ics` ingests via a per-source mailbox; events are parsed from the ICS attachment.
- Both methods are subject to the Source Reliability Score (FR-16) and editorial review.
- RSS/ICS sources count toward the 40-source MVP floor.

**Out of Scope:** User-facing RSS/ICS submission (Phase 3 candidate). Auto-discovery of RSS feeds from sources (Phase 3).

#### FR-57: Editorial Review Queue (Internal)

The system exposes an internal-facing editorial review queue for events that fail the FR-14 confidence floor (<0.7), that trigger spike detection in FR-16, or that are flagged by user reports. The queue is the human-override path for the hallucination-guardrail pipeline. Realizes "Trust through transparency" principle.

**Consequences (testable):**
- An event with `extraction_confidence < 0.7` is added to the queue with publication-grade metadata.
- An editor can Approve (publishes to digest), Reject (deletes from registry), or Edit (corrects fields then publishes).
- A rejected event is logged for source reliability score adjustment.
- The queue is reviewed at least daily by the editorial team / on-call engineer.
- The queue's current size and average review latency are tracked on the AI Cost Dashboard (FR-29).

**In Scope (MVP, by Amendment A-4):**

- The Detail Screen surfaces a "Report this event" CTA (see FR-59). `EventReport` records enter this queue with priority `user_reported`.
- The queue's review SLA for user-reported events is 24 hours from submission (vs. the daily-review cadence for non-user-flagged events).

**Out of Scope:** Free-text user feedback in MVP (Phase 2).

#### FR-60: Timezone Source of Truth (added by Amendment A-6)

Every Event has an explicit `start_time_tz` field. Events without an explicit timezone at the source are either inferred via venue resolution or auto-rejected. This is a launch-gating requirement to prevent the "wrong-time event" hallucination class.

**Extraction rule:**

For every extracted Event, the pipeline produces:

- `start_time_local` — the time as written in the source.
- `start_time_tz` — the timezone as written in the source. **Required.**
- `start_time_utc` — UTC equivalent, computed from `start_time_local` + `start_time_tz`.
- `tz_inference_confidence` — 1.0 if the source provided a timezone; lower if inferred (see below).

**Source-coverage tiers:**

| Tier | Source behavior | Pipeline behavior |
|---|---|---|
| `full` | Source emits ISO 8601 with offset | `start_time_tz` = offset; `tz_inference_confidence` = 1.0; no editorial review |
| `partial` | Source emits ISO 8601 without offset but with venue city | Venue registry + IANA timezone database resolves to a timezone. Confidence ≥0.9 → proceed. Confidence 0.7–0.9 → flag with `tz_inference_confidence` and route to editorial review (FR-57). Confidence <0.7 → auto-reject. |
| `none` | Source emits bare local time without timezone and without reliable venue | Auto-reject. The editorial team may add a venue entry to the registry to enable future ingestion. |

The Source Registry (FR-13) gains a `tz_coverage` field per source. Sources with `tz_coverage = none` are flagged in the Source Pipeline dashboard.

**Display rule:**

- Pulse Card displays the event time in the **user's local timezone**.
- Detail Screen displays the event time in the user's local timezone AND the venue-local timezone if the user's timezone differs from the venue's by more than 1 hour (label: "venue local time").
- SEO public URLs (FR-26) include the timezone in Schema.org Event JSON-LD.

**Cross-timezone conflict detection (FR-58):**

- Conflict detection compares events in **UTC**, not local time.
- The ±30-minute conflict window applies in UTC.

**Consequences (testable):**

- An event with `start_time_tz` missing from the source and not resolvable from venue registry is auto-rejected before reaching the Pulse Digest.
- An event with `tz_inference_confidence` in [0.7, 0.9] appears in the Pulse Digest with a "venue time approximated" note on the Detail Screen.
- An event with `tz_inference_confidence` < 0.7 does not appear in any Pulse Digest until editorial review completes.
- A user in NYC viewing an event at a venue in LA sees the event time in NYC local AND "5:00 PM (venue local time)" on the Detail Screen.
- The Source Pipeline dashboard surfaces `tz_coverage = none` sources for editorial action.
- The AI Cost Dashboard (FR-29) tracks: timezone-rejection rate, timezone-review-queue size, mean editorial-review latency for timezone-uncertain events.

**Out of Scope:** Cross-source venue reconciliation beyond the venue registry (Phase 3). Timezone-aware reminder delivery optimization (e.g., send the reminder at 9am venue-local for a user in a different timezone) — current behavior delivers at user-local Reminder Plan slot, deferred to Phase 3.

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

#### FR-58: Personal Event Conflict Detection (revised by Amendment A-5)

The system detects scheduling conflicts and likely-duplicate events at Personal Event creation time. Conflict prompts **require an explicit choice** from the user — there is no dismiss-without-resolution option. This is the minimum viable guard at MVP; Phase 2 unifies on a Timeline (FR-32). Realizes "calm" principle at the basic user-input level: the system should never let a user double-book without an explicit decision.

**Conflict detection rules:**

- On Personal Event creation, the system scans for other Personal Events within ±30 minutes of the new event's start time. If found, the user sees a calm inline prompt listing the conflicting event(s).
- On Personal Event creation, the system flags a likely duplicate when another Personal Event has the same name (case-insensitive, ≥80% Jaccard overlap on tokens) AND starts within 24 hours.
- A saved public event that overlaps with a Personal Event by >15 minutes is marked with a conflict indicator on both Pulse Cards. Tapping the indicator opens a non-alarming conflict-detail panel.

**Conflict prompt structure (testable):**

The prompt lists the conflicting event(s) and presents exactly three buttons. **There is no "dismiss" or "X" button.** The user must choose one:

1. **"Keep both — I'll manage"** — Confirms both events. The conflict indicator (see §3 Glossary) remains on both Pulse Cards permanently. No further prompting for this conflict pair.
2. **"Edit the new one"** — Opens the new event in edit mode with the conflicting time pre-highlighted. After editing, conflict detection re-runs.
3. **"Delete the new one"** — Removes the new event. Confirmation required before deletion completes.

For duplicate-detection prompts, option 2 is relabeled **"Update the existing one"** and opens the existing event in edit mode.

**Conflict indicator visual spec (wireframe-locked):**

- Position: top-right corner of the Pulse Card.
- Size: 8–10 px.
- Shape: filled circle.
- Color: desaturated amber (#B8893D or equivalent). Never red.
- Accessibility: `aria-label="Schedule conflict"`.
- Symmetric: identical on both Pulse Cards in the conflict pair.
- Persistent: remains after the user chooses "Keep both."
- Distinct from Source Badge (icon-glyph) and Confidence Pulse (● dots) by shape and position alone — color is not the sole carrier of meaning.

**Consequences (testable):**

- A Personal Event creation that triggers a conflict prompt requires the user to make one of the three explicit choices before the creation flow can complete.
- Choosing "Keep both" persists the conflict indicator on both Pulse Cards. Tapping the indicator on either card opens a non-alarming detail panel.
- Choosing "Edit the new one" or "Delete the new one" resolves the conflict; the conflict indicator is removed from the Pulse Card.
- A user choosing "Keep both" is not re-prompted for the same conflict pair.
- A `ConflictResolution` value object is recorded for every conflict prompt, even those resolved by editing or deletion.
- The conflict indicator is not a "Dismiss" affordance — it is informational. Tapping opens the detail panel, not a silent close.

**Out of Scope:** Auto-rebook or alternative suggestions (Phase 2 — FR-33). Public-event vs. public-event conflicts at MVP (Phase 2). A "Hide conflict indicators" toggle (Phase 2 candidate; conflicts with the calm permanent-reminder design).

#### FR-59: User-Reported Event Quality (added by Amendment A-4)

The Detail Screen exposes a "Report this event" CTA so users can flag quality issues they observe. Realizes the "Trust through transparency" principle: the user can participate in the trust infrastructure, not just consume it.

**CTA placement:**

- Detail Screen, secondary action row (alongside Save, Share, Dismiss).
- Icon: small flag glyph. Not a primary button.
- Tap opens a modal with four categories (single-select):
  1. "Wrong date or time"
  2. "Wrong venue or address"
  3. "Doesn't exist or is cancelled"
  4. "Duplicate of another event"

**Consequences (testable):**

- A user can submit a report with one tap after selecting a category. No free-text field in MVP.
- On submission, an `EventReport` record is created (User, Event, category, timestamp) and the Event is added to the editorial review queue (FR-57) with priority `user_reported`.
- The user sees a confirmation toast: "Thanks — we'll review this."
- The editorial review SLA for user-reported events is 24 hours from submission.
- Rate limit: 5 reports per user per day. The 6th attempt in a 24h window is silently rate-limited (the modal opens but the submit button is disabled with the message "You've reported 5 events today — try again tomorrow.").
- All `EventReport`-flagged events require editorial confirmation before action (Approve / Reject / Edit). A single report does not auto-reject an event.
- Repeat reporters (users whose reports are rejected by editorial ≥80% of the time over the prior 30 days) get a soft warning: "Some recent reports weren't actionable — thanks for being careful." Their reports remain in the queue at reduced priority.
- `EventReport` records are retained 24 months (matching audit-log retention in §10.2).
- The AI Cost Dashboard (FR-29) surfaces: `user_reports_per_day`, `report_category_distribution`, `report_to_action_ratio`, `mean_report_review_latency`.

**Out of Scope:** Free-text feedback (Phase 2). User-visible report counter on public Event URLs (rejected — would create a pile-on dynamic violating the calm principle). Auto-rejection on a single report (rejected — editorial confirmation required).

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

#### FR-22: Confidence Pulse (revised by Amendment A-3)

Each Pulse Card shows a 1–5 dot Confidence Pulse (●●●●○ = 4/5). The Confidence Pulse is computed from the AI's certainty about relevance (not just trust in the source). Realizes UJ-1, UJ-4. The formula and weights are **published in the PRD and immutable post-launch** to honor the "Trust through transparency" principle.

**Formula:**

```
relevance_score = 0.40 × preference_graph_match
                + 0.25 × source_reliability
                + 0.20 × recency_fit
                + 0.15 × novelty_vs_exploration
```

Where each component is normalized to [0.0, 1.0]. `preference_graph_match` uses the user's Preference Graph with cold-start fallback. `source_reliability` uses the per-Source reliability score (FR-16, Bayesian-smoothed). `recency_fit` measures how well the event's start time aligns with the user's typical engagement windows. `novelty_vs_exploration` balances familiarity (events similar to past saves) against exploration (events outside the user's usual categories).

**Initial weights (MVP, locked):**

| Weight | Component | Value |
|---|---|---|
| `w1` | preference_graph_match | 0.40 |
| `w2` | source_reliability | 0.25 |
| `w3` | recency_fit | 0.20 |
| `w4` | novelty_vs_exploration | 0.15 |

**Bucket boundaries (wireframe-locked):**

| relevance_score | Displayed dots |
|---|---|
| ≥ 0.85 | 5 (●●●●●) |
| ≥ 0.65 | 4 (●●●●○) |
| ≥ 0.45 | 3 (●●●○○) |
| ≥ 0.25 | 2 (●●○○○) |
| < 0.25 | 1 (●○○○○) |

**No-flicker rule:** a change in `relevance_score` that does not cross a bucket boundary MUST NOT change the displayed Confidence Pulse on the user's next Pulse Digest. The previous bucket is preserved until the new score crosses the threshold (hysteresis on the boundary, ±0.02 tolerance band).

**Range clamp:** `relevance_score` is clamped to [0.0, 1.0] before bucket mapping; the rendered Confidence Pulse is always 1, 2, 3, 4, or 5.

**Immutability and amendment policy:**

- The weights above are the MVP weights and are locked at launch.
- Any change to the weights is a PRD amendment requiring explicit product leadership sign-off.
- Amendments are tracked in `docs/adr/` and surfaced in Settings → Privacy → "Ranking algorithm version" with the amendment date and a link to the relevant ADR.
- A/B testing of weights on live users is forbidden. All weight experimentation happens in shadow composition (per `[ASSUMPTION-2]` and the shadow pipeline).
- The Architecture spec describes the *implementation* of the formula but does not redefine the weights.

**Consequences (testable):**

- A Pulse Card always shows a Confidence Pulse.
- The displayed dot count matches the bucket boundaries above for any given `relevance_score`.
- A weight change without a PRD amendment is a CI-level test failure.
- Settings → Privacy → "Ranking algorithm version" shows the current weights and the last-amendment date.
- A user reading the PRD can compute the Confidence Pulse for any Event given the inputs.

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
- The Detail Screen shows a neighbor count when the k-anonymity threshold (≥5 qualifying users) is met; below the threshold the badge is suppressed silently (no "0 neighbors" copy).
- **Qualifying user:** an authenticated EventPulse24 user who has either saved OR opened the Detail Screen for this event in the last 30 days.
- **Same area:** haversine distance ≤ 2 km OR same city-zip-cluster (whichever is broader); events outside the user's home country do not count.
- **Display rounding (wireframe-locked):** the count is bucketed and rendered as `👥 5–9`, `👥 10–24`, `👥 25–99`, or `👥 100+`. Buckets `<5` are suppressed (k-anonymity). Exact counts are never exposed.
- **Privacy floor:** the count aggregates Pro and Free tier users identically; the badge never differentiates by tier (no Pro-vs-Free density leakage).

**Out of Scope:** Friend-attending count (Phase 2 — Pulse the Group). Public event ratings/reviews.

#### FR-25: "Less like this" Adjustment

Swiping a Pulse Card down dismisses it and signals "less like this" to the AI. Realizes UJ-4.

**Consequences (testable):**
- A dismissal is recorded as a negative signal in the Preference Graph.
- After 3 consecutive dismissals of similar events (clustered by embedding cosine ≥0.7), the system shows a calm prompt: "Less rooftop jazz in your next digest?" — one tap to mute.
- A mute is reversible from settings.

**Diversity floor (launch gating; revised by Amendment A-2):**
- The Pulse Digest composition (FR-5) guarantees Slot 3 is a `serendipity` category by formula — low popularity × high source reliability × distinct from the user's most-engaged category. This is a hard floor enforced at composition time, not a post-hoc check.
- The diversity card is included even if the user's Preference Graph says "no jazz" — serendipity is a product decision, not a user preference.
- Dismissal signals have a **decay window** of 60 days. After 60 days, the negative signal weight is halved; after 180 days, it expires entirely. The system never permanently bans a category for a user.
- Why-this Tag on Slot 3 cards reads `discovery` or `new-to-you` (not a category name) to signal the slot's intent.

**Rage-dismiss guard:**
- The 3-consecutive dismissal cluster requires 3 *distinct events* across a digest window (default: a calendar day). Rapid 3-swipes in <5 seconds are rate-limited: only the first dismissal counts toward the cluster; the next two are recorded but do not advance the cluster counter.

**Out of Scope:** Mass "less like this" controls. Category-wide mute UI in MVP (Phase 2). Per-artist mute (Phase 2).

---

### 4.7 Event State Sync (Cancel / Postpone / Move / Sold Out)

**Description:** Events are not static. Cancellations, postponements, moves, and sell-outs happen between ingestion cycles. The system tracks event state and surfaces changes to the user — silently for harmless changes, with a calm notification for meaningful ones. The "Trust through transparency" principle is violated the moment a user shows up to a cancelled event.

#### FR-53: Event State Polling + Webhooks

The system re-ingests high-priority sources (FR-13) at least every 4 hours. Lower-priority sources at least daily. For sources with state webhooks (Eventbrite ticketing, Meetup, Luma), the system subscribes and receives state changes in near real-time. Realizes UJ-1 (state correctness).

**Consequences (testable):**
- A cancelled event is detected by the system within 4 hours for high-priority sources and within 24 hours for lower-priority sources.
- A postponed event's new time is reflected in the user's saved event within 4 hours.
- A sold-out event is marked with a "Sold Out" tag on the Pulse Card and Detail Screen.
- Webhook subscribers (Eventbrite, Meetup, Luma) receive near-real-time updates; polling is the fallback.

**Out of Scope:** Real-time push notification on every state change (would be engagement-trap; only meaningful changes trigger user-facing notification per FR-54).

#### FR-54: User-Facing State-Change Notifications

When an event the user has saved or set a Reminder Plan for experiences a state change, the system sends a single, calm in-app + email notification. The notification is one-time per event; never repeats. Realizes UJ-1.

**Consequences (testable):**
- A user with a saved event that is cancelled receives: in-app banner + email with subject "EventPulse24: [event name] was cancelled." All future reminders for that event are suppressed.
- A user with a saved event that is postponed receives: in-app banner + email with subject "EventPulse24: [event name] was moved to [new date]." Reminders are re-scheduled to the new time.
- A user with a saved event that is moved to a new location receives: in-app banner + email with subject "EventPulse24: [event name] moved to [new location]." Map pin is updated.
- A user with a saved event that becomes sold out receives: in-app banner + email with subject "EventPulse24: [event name] is sold out." The Detail Screen shows the "Sold Out" badge and removes the "Save Reminder" CTA.
- A user receives at most one state-change notification per event per day (no notification spam).

**Out of Scope:** Push notifications at MVP (Phase 2+). State-change notifications for unsaved events (surfaced only on the public Event URL).

#### FR-55: Conflict Resolution on State Change

When a saved event is cancelled or moved, the system handles conflicts with the user's other saved events. Realizes UJ-2.

**Consequences (testable):**
- A cancelled event with no associated saved personal events: user is notified, event is removed from the digest.
- A cancelled event that conflicts with a personal event: user is notified; the personal event is preserved (no auto-cancel).
- A postponed event that conflicts with another saved event: user is notified; the system surfaces a calm "this overlaps with [other event]" message in the Detail Screen.
- A user can mute event-state-change notifications for a specific event from the Detail Screen.

**Out of Scope:** Automatic rebooking or alternative suggestions (Phase 2 — FR-33 Conflict-Aware Scheduling).

---

### 4.8 Sharing & Discovery (SEO)

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

### 4.9 AI Cost Discipline

**Description:** AI cost is the product's existential risk. Every surface tracks per-event cost. On-device and batch optimization are first-class concerns.

#### FR-29: AI Cost Dashboard (Internal)

The system provides an internal-facing AI Cost Dashboard with per-feature telemetry: extraction cost per source, embedding cost per event, personalization cost per user, total cost per MAU. Realizes PRD-disciplined "calm" economics.

**Full per-MAU TCO (Total Cost of Ownership):**

The dashboard tracks the **complete** cost to serve a monthly active user, not just AI inference. AI cost alone is misleading; the product's economics depend on the full picture.

| Cost category | MVP target per MAU / month | Notes |
|---|---|---|
| **LLM inference** (extraction, dedup, personalization) | $0.30 | Primary cost; subject to FR-30 caching |
| **Embeddings** (dedup, similarity) | $0.05 | Cached aggressively |
| **Transactional email** (Pulse Digest, reminders, exports) | $0.15 | ESP + sending volume |
| **Hosting & compute** (web app, DB, queues) | $0.30 | Self-hosted or modest cloud |
| **CDN + bandwidth** | $0.05 | SEO public pages share cost |
| **Stripe + payment processing** | $0.05 | Pro-tier only (Pro subscribers amortize) |
| **Status page + observability** | $0.05 | Per-engineer-per-month |
| **Editorial & support** (human) | $0.20 | At MVP scale, ~0.5 FTE amortized |
| **Other / buffer** | $0.10 | Slack, legal, etc. |
| **TOTAL MVP TCO target** | **$1.25 / MAU / month** | At 100K MAU = $125K/month burn |

**Targets at scale (illustrative, not commitments):**
- 100K MAU: $1.25/MAU (MVP TCO)
- 500K MAU: $0.80/MAU (cache hits, batched inference, fewer per-user support touches)
- 1M MAU: $0.55/MAU (steady-state with on-device + batch + mature pipeline)

**Consequences (testable):**
- The dashboard updates at least daily.
- The dashboard surfaces per-feature cost trends (week-over-week).
- The dashboard surfaces per-MAU TCO with the breakdown above.
- The dashboard alerts when any cost category exceeds its MVP target by 20% (default). **Alert owner:** AI engineering lead. **Alert channel:** Slack #pulse-cost-alerts. **Cadence:** weekly summary + immediate Slack on threshold breach.
- **A sustained TCO breach for 2+ consecutive weeks triggers a feature review** (not an auto-rollback — this is honest engineering, not automation theater).

**Out of Scope:** External-facing cost transparency. User-facing AI-cost control.

#### FR-30: Caching & Batching Defaults

The system batches non-realtime inference (extraction, embedding, classification) and caches results to avoid redundant compute. Realizes FR-29.

**Consequences (testable):**
- Re-extracting the same source URL within the dedup window does not re-trigger LLM extraction.
- Embedding computation is reused across the dedup pipeline and the personalization pipeline.
- Re-running a Pulse Digest composition for the same user within the same day returns the cached composition.

**Out of Scope:** On-device inference (Phase 3 — FR-39).

---

### 4.10 Phase 2 / 3 Features (Named FRs for Future Planning)

*These features are deferred beyond MVP. They are named FRs here so epics and stories can be planned against them without ambiguity. The behavioral notes below are minimum-viable scope hints; details land in the Phase 2 PRD when activation begins.*

#### FR-31: Two-Way Calendar Sync + Recurring Event Expansion — Phase 2

The system performs **two-way** sync with Google Calendar, Apple Calendar (via CalDAV), and Outlook Calendar, extending the MVP read-only connect (FR-3 / FR-50). Personal events from these calendars appear in the Pulse Digest and Timeline. Recurring events are expanded via RRULE and surfaced as individual instances with edit-this-instance / edit-the-series controls.

**Behavioral notes:** OAuth flow for Google/Outlook; CalDAV for Apple (already shipped at MVP for read). Sync interval: 15 min pull + push on write. Conflict resolution: server-side wins on field-level merge with user-visible conflict log.

**Amendment A-7 (v1-spec):** The MVP read-only sync is FR-3 + FR-50 (all three providers, all tiers with Free-tier 1-provider cap). FR-31 is the Phase 2 *augmentation* — two-way write, RRULE expansion, field-level conflict UI.

#### FR-32: Unified Personal+Public Timeline — Phase 2

The system presents a Timeline view combining Personal Events (warm tones) and Public Events (cool tones) in a week- or month-view. Conflicts highlighted, never alarmed. Realizes UJ-2.

**Behavioral notes:** Conflicts are surfaced as a subtle marker (no red, no sound). Conflicts are typological (work vs. social, family vs. solo) — not just temporal.

#### FR-33: Conflict-Aware Scheduling — Phase 2

The system detects scheduling conflicts between Personal Events and Public Events and suggests gentle alternatives (e.g., "Soccer practice overlaps — want a different time?"). Realizes UJ-2.

**Behavioral notes:** No auto-rebook. Surface alternatives via the **three-action pattern**: (a) **Move the personal event earlier/later**, (b) **Skip the public event** (dismiss with one tap), (c) **Keep both — I'll manage** (no further prompting). User decides; no second-guessing. Conflicts are typological (work vs. social, family vs. solo) — not just temporal.

#### FR-34: Pulse the Group — Phase 2

Small group (≤10 people) coordination via AI-assisted availability heatmap and event suggestions. Realizes UJ-6.

**Behavioral notes:** Privacy-respecting — no event titles, only free/busy shown to the group. Group size cap. Opt-in per group.

#### FR-35: Pro Tier — Phase 2 Augmentation

The MVP Pro tier (FR-48) is augmented in Phase 2 to add: **two-way** calendar sync + recurring-event expansion (FR-31), Unified Timeline (FR-32), Pulse the Group (FR-34), and Why Now? (FR-38). (Apple/Outlook read-only sync already ships at MVP per Amendment A-7.) Phase 2 may revise pricing. Subscribers at MVP retain grandfathered pricing for 12 months.

**Behavioral notes:** Free tier caps in Phase 2: 1 group, 1 calendar (Google only at MVP; Apple/Outlook at Phase 2), unlimited saved collections. Pricing open (see §8 Open Questions).

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

### 4.11 MVP Pro Tier (Shipped at MVP Launch)

*Pro tier ships at MVP to validate monetization alongside core product. Apple/Outlook calendar sync is **no longer deferred to Phase 2** (see Amendment A-7) — all three providers ship at MVP for all tiers with a Free-tier 1-provider cap. The remaining Phase 2 Pro augmentations (Pulse the Group, two-way calendar sync) come later.*

#### FR-48: Pro Tier with MVP-Only Features

The system offers a Pro Tier at $4.99/month (or $49/year). Free tier retains Pulse Digest + Reminders + Personal Events + 1-save/day cap + 1 connected calendar provider. Pro unlocks: unlimited saves + saved collections, up to 3 connected calendar providers (Google + Apple + Outlook), per-day-of-week custom quiet hours, and JSON+ICS data export.

**Behavioral notes:** Stripe-powered checkout; web-only (no native mobile paywall). Free-tier 1-save/day cap is the gate; on 2nd save attempt in a 24h window, show calm in-app CTA to upgrade. Pricing page is a single screen; no upsell copy beyond "fewer interruptions, more control." Pricing subject to A/B test post-launch; Open Q #14.

#### FR-49: Unlimited Saves + Saved Collections (Pro)

A Pro user can save unlimited Pulse Cards per day, organized into named collections (e.g., "Music this month," "For the kids"). Realizes the value prop of Pro.

**Consequences (testable):**
- A Pro user can save 10+ events in a single day without a soft-wall CTA.
- A Pro user can create, rename, delete, and reorder saved collections.
- A free user hitting the 1-save/day cap sees a calm in-app upgrade prompt (no modal interruption).

**Out of Scope:** Shared collections (Phase 2 — Pulse the Group). Collection-level reminders in MVP.

#### FR-50: Calendar Provider Read-Only Sync (Free + Pro)

A user (any tier) can connect any of three supported calendar providers — **Google Calendar**, **Apple Calendar (CalDAV)**, or **Outlook Calendar (Microsoft Graph)** — via the appropriate auth handshake; personal events from any connected provider flow into the Pulse Digest as warm-tone Pulse Cards. Read-only in MVP (no write-back). Realizes UJ-2 at MVP for all three providers.

**Consequences (testable):**
- A user can complete auth for Google, Apple, or Outlook in the onboarding flow without leaving the page.
- A user's personal events from any connected provider appear in the Pulse Digest within 24 hours of the first successful sync.
- A user can disconnect a connected provider; previously-imported personal events are removed within 24 hours.
- A user can connect multiple providers simultaneously (e.g., Google for work + Apple iCloud for family); events merge into the user's Personal Calendar view.
- Calendar credentials are encrypted at rest (per §11.2); revocation is detected on next sync.
- Free tier: 1 connected provider. Pro tier: up to 3 connected providers (one of each). The Free-tier cap is enforced at the connect step (calm in-app upgrade prompt on 2nd provider attempt; no modal interruption).

**Per-provider auth handshake:**
- **Google Calendar** — OAuth 2.0 (1-click flow via Google Identity Services).
- **Apple Calendar** — CalDAV with app-specific password (user generates in Apple ID settings; copy-paste into EventPulse24). UX: clear inline guidance, no secret-leakage risk (password input is masked, never logged).
- **Outlook Calendar** — Microsoft Graph OAuth 2.0 (1-click flow via Microsoft Identity Platform, supports personal Microsoft accounts and Microsoft 365 work/school accounts).

**Out of Scope:** Calendar write-back. Two-way sync with field-level conflict resolution (Phase 2 — FR-31). Recurring-event RRULE expansion beyond simple instance listing (Phase 2). Shared/family iCloud calendar deep-link subscriptions (Phase 2). Cross-user delegation (giving someone else write access to your calendar via EventPulse24 — out of scope indefinitely).

**Amendment A-7 (v1-spec):** Supersedes the prior "Google-only / Pro-only / Phase 2 Apple+Outlook" stance. All three providers ship at MVP for all tiers (with the Free-tier 1-provider cap).

#### FR-51: Per-Day-of-Week Custom Quiet Hours (Pro)

A Pro user can configure different quiet hours for each day of the week (e.g., no reminders on Saturday mornings; 10pm–9am on weeknights). Realizes the value prop of granular control.

**Consequences (testable):**
- A Pro user can set 7 distinct Quiet Hours windows (one per weekday).
- Quiet Hours windows are stored as wall-clock local time, recomputed on timezone change / DST event.
- Reminder slots that fall inside a configured Quiet Hours window are deferred to the window's end.

**Out of Scope:** Per-category Quiet Hours (Phase 3 — FR-33+). Per-event Quiet Hours.

#### FR-52: JSON + ICS Data Export (Pro)

A Pro user can export all their data (saved events, personal events, preference graph, reminder plans) as JSON + ICS via Settings → "Download my data." Realizes GDPR Article 20 right-to-portability for all users (export is free for GDPR compliance but UX is in Pro settings for non-EU users).

**Consequences (testable):**
- A Pro user requesting export receives an email with download links within 24 hours.
- JSON export includes all user-created records; personal-event locations are redacted if user opted out of precise location sharing.
- ICS export is importable into Google Calendar / Apple Calendar / Outlook.
- Account deletion completes within 30 days (per §10.1); export remains available for 30 days post-deletion.

**Out of Scope:** Real-time data streaming API (Year 2+ — FR-43 B2B Insights API).

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
- FR-13, FR-14, FR-15, FR-16, FR-17, FR-56, FR-57, FR-60 — Event Extraction & Source Pipeline
- FR-18, FR-19, FR-20, FR-58 — Personal Event Management
- FR-21, FR-22, FR-23, FR-24, FR-25, FR-59 — Explainability & Trust
- FR-26, FR-27, FR-28 — Sharing & Discovery
- FR-29, FR-30 — AI Cost Discipline
- FR-53, FR-54, FR-55 — Event State Sync (cancel/postpone/move/sold-out)
- FR-48, FR-49, FR-50, FR-51, FR-52 — MVP Pro Tier (shipped at launch)

**Total:** 43 MVP FRs (FR-1 through FR-30, FR-48 through FR-60; +2 from Amendment A-4 / FR-59 and Amendment A-6 / FR-60), 17 named FRs for Phase 2/3+ (FR-31 through FR-47), 6 User Journeys, 15 Open Questions, 13 Assumptions (was 10; +3 from Amendments A-3, A-5, A-6), 18 Success Metrics (was 16; +2 from Amendments A-2 and A-4) + 6 Counter-metrics (was 5; +1 from Amendment A-6), 12 Risks.

**Operational:** AI Cost Dashboard, Source Registry, ToS review log, Pro-tier billing integration (Stripe), webhooks for source state sync, editorial review queue.

### 6.2 Out of Scope for MVP

| Feature | Reason for deferral | Target Phase |
|---|---|---|
| FR-31 Calendar Sync — two-way + RRULE expansion | Two-way sync + recurring-event modeling needs Phase 2 architecture | Phase 2 |
| FR-32 Unified Personal+Public Timeline | Complex UI w/ conflict logic | Phase 2 |
| FR-33 Conflict-Aware Scheduling | Needs unified timeline | Phase 2 |
| FR-34 Pulse the Group | Needs trust established first; solo must be excellent first | Phase 2 |
| FR-35 Pro Tier Augmentation (Apple/Outlook sync, Pulse the Group, Pricing A/B) | Augments MVP Pro tier; needs Phase 2 anchors | Phase 2 |
| FR-36 Voice Quick-Add | Demo magnet, niche adoption | Phase 3 |
| FR-37 Email-to-Event Forwarding (user-forwarded) | Power-user only, niche; **source-side email-ICS is now MVP via FR-56** | Phase 3 |
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
- **SM-1: Time-to-first-relevant-event**: Median time from first visit to first Pulse Card the user saves. Target: <30 seconds. Validates FR-1, FR-2, FR-5.
- **SM-2: Pulse Digest daily engagement rate**: % of users who click into the Pulse Digest on the day the Pulse Ping is delivered. Target: **>40% by Month 3, >55% by Month 6** (industry benchmark for daily digest emails is 15–25%; transactional Pulse Ping is differentiated by being daily + personalized, but tracking at 60% out of the gate is unrealistic). **Measurement:** server-side click-tracking on the digest CTA, not email open-pixel (open pixels are unreliable and inflate metrics). Validates FR-5, FR-10.
- **SM-3: Onboarding completion rate**: % of new users who complete the onboarding flow (any path) and reach the first Pulse Digest. Target: >85%. Validates FR-1.
- **SM-4: "Why this?" trust score**: % of users who answer "I trust Pulse's recommendations" YES in a weekly pulse survey. Target: >70%. Validates FR-21, FR-22, FR-23, FR-24.
- **SM-5: Per-event reminder setup rate**: % of saved Pulse Cards where the user customizes a Reminder Plan (vs. accepts default). Target: >80%. Validates FR-9.

**Secondary**
- **SM-6: D7 retention**: % of new users who return on Day 7. Target: >40%. Validates FR-5, FR-10, FR-25.
- **SM-7: Pulse Preview conversion**: % of Pulse Preview visitors who sign up. Target: >20%. Validates FR-2.
- **SM-8: Privacy page dwell > 30s**: Proxy for trust explanation depth. Target: >40% of returning users. Validates FR-21, FR-22.
- **SM-9: Personal Event creation rate**: % of returning users who create at least one Personal Event. Target: >30% by W4. Validates FR-18, FR-19.
- **SM-10: Digest novelty rate**: % of Pulse Digest cards the user has not seen in the prior 30 days. Target: >50%. By slot design (Amendment A-2), Slot 3 is structurally low-novelty-saturation, raising the overall digest novelty rate. Lower than 50% signals the corpus is too narrow or the relevance filter is too loose. Validates FR-5, FR-15.
- **SM-17: Per-slot engagement** (added by Amendment A-2): Per-slot save rate (`slot_1_save_rate`, `slot_2_save_rate`, `slot_3_save_rate`) and Slot 3 bounce rate (`slot_3_bounce_rate`). Target: Slot 3 save rate ≥10% by Month 3 (validates the anti-popularity inversion); Slot 3 bounce rate <40% (validates the inverted formula). Validates FR-5.
- **SM-18: User-reported event action rate** (added by Amendment A-4): % of `EventReport`-flagged events for which editorial takes action (Approve, Reject, or Edit) within 24 hours. Target: ≥90% by Month 1. Validates FR-57, FR-59.

### 7.2 Counter-Metrics (Do Not Optimize)

- **SM-C1: Notification suppression rate**: % of Pulse Pings suppressed (empty digest, Quiet Hours window, etc.). Target: ≥30%. *Higher is better.* Quiet is the product. Counterbalances SM-2 (open rate).
- **SM-C2: Pulse Digest bounce rate**: % of users who open the Pulse Digest and immediately close within 5 seconds. Target: <25%. If rising, signals the digest is too noisy. Counterbalances SM-2.
- **SM-C3: Per-user reminder opt-out rate**: % of reminders marked "less like this" or muted. Target: <20%. If rising, signals bad recommendations, not bad UX. Counterbalances SM-5.
- **SM-C4: Free-tier signup cap conversion**: % of users who hit the free-tier save cap and don't upgrade paths. Target: <10%. Counterbalances growth-vs-monetization trade. Counterbalances SM-7 (Pulse Preview conversion).
- **SM-C5: Per-MAU TCO**: Total cost to serve one monthly active user, per FR-29's cost-category breakdown. Target: ≤$1.25/month at MVP; ≤$0.55/month at 1M MAU. Trend MUST be down over time. Replaces the older "AI cost per MAU" lens — full TCO catches hosting, email, support, and other costs that AI-only metrics miss. Counterbalances any "more personalization" push. Counterbalances SM-6 (D7 retention) — keeping cost down is the discipline that keeps growth sustainable.
- **SM-C6: Timezone-rejection rate** (added by Amendment A-6): % of extracted events auto-rejected for missing `start_time_tz`. Target: <5% at MVP launch. Counterbalances FR-13's source-count floor — sources with `tz_coverage = none` are penalized for the corpus floor but not removed. Counterbalances SM-10 (Digest novelty rate) by ensuring novelty comes from legitimate sources, not timezone-broken ones. Validates FR-60.

### 7.3 Lagging Indicators (Months 2–12)

- **SM-11: Monthly Active Users (MAU)**: Targets: **30K by Month 6 (acquisition path: organic SEO + product-led referrals + 1 paid acquisition pilot)**, 100K by Month 12, 500K by Month 18, 1M by Month 24. **SEO-only 100K by Month 6 is unrealistic**; the Open Q #6 beachhead and Open Q #15 growth-channel mix feed this. If Month-6 actuals are tracking materially below the 30K plan, the Gate 1 threshold (revised) does not penalize but flags for triage.
- **SM-12: Pro paid conversion rate**: Target: >5% by Month 6 (testable at MVP with FR-48). Counter-balanced by SM-C1 (notification suppression) — premium must not mean *more* notifications.
- **SM-13: Net Revenue Retention**: Target: >110%.
- **SM-14: LTV/CAC ratio**: Target: ≥3.
- **SM-15: Viral coefficient (invites per user)**: Target: >0.5 (Phase 2 unlocks invite tooling).
- **SM-16: North Star — "% of users who report Pulse made their week better"**: Weekly NPS-style survey. Target: >40% by Month 6. Counter-balanced by SM-C3 (per-user reminder opt-out) — if "made the week better" rises but opt-outs rise, the product is succeeding in spite of itself.

### 7.4 Decision Gates

- **Gate 1 (Month 3):** D7 retention >40% + SM-15 North Star >25% + cost dashboard trending under per-MAU TCO target → ship MVP + invest in growth. (Gate 1 does *not* gate on raw MAU; SEO-driven MAU ramp lags the engagement metrics by 60–90 days.)
- **Gate 2 (Month 9):** Freemium conversion + group feature adoption → continue vs. pivot to B2B.
- **Gate 3 (Month 18):** Unit economics + viral coefficient >0.5 → scale, else niche focus.

---

## 8. Open Questions

| # | Question | Owner | Phase |
|---|---|---|---|
| 1 | Which 20 event sources to crawl / acquire for MVP? (Mix of official sites, aggregators, niche blogs?) | Eng + Product | Pre-launch |
| 2 | Calendar sync vendor — build in-house OAuth/CalDAV handshake vs. partner with Nylas/SyncGene for the MVP three-provider read-only sync (FR-3 / FR-50)? Build-vs-buy decision is blocking for token-implementation start; defer to Phase 2 only for the two-way + RRULE augmentation (FR-31). | Eng | MVP build-vs-buy gate |
| 3 | LLM provider strategy — single vendor (OpenAI/Anthropic) vs. multi-model routing? | Eng + CTO | Pre-launch |
| 4 | Pricing for Pro tier — $4.99/mo vs. $7.99/mo vs. annual-only? | Product | Pre-launch |
| 5 | Should Pulse Digest be (1 must-know + 1 nearby + 1 surprise) or rank dynamically? | Product + Data | Post-MVP |
| 6 | Geographic beachhead — 3 US cities (NYC, SF, Austin) or 1 city deeply? | Product + Marketing | Pre-launch |
| 7 | Funding runway — bootstrap vs. seed round vs. angel? | Founder | Pre-launch |
| 8 | Founding team gaps — who's the technical co-founder, AI/ML lead, designer? | Founder | Pre-launch |
| 9 | How aggressively to gate free-tier save? (1/day vs. 3/day vs. 5/day.) | Product | Pre-launch |
| 10 | Phase 2 mobile platform priority — iOS first, Android first, or both? | Eng + Product | Phase 2 prep |
| 11 | **Launch blocker — see §12.1 Go/No-Go gate.** Live competitive re-verification (Apple Intelligence, Gemini in Workspace, Luma, Partiful, Eventbrite, Facebook Events, new entrants) is required within 30 days before any public launch. Quarterly re-verification thereafter. Failure to re-verify = automatic launch hold. See §12.1 for Go/No-Go criteria. | Product | Pre-launch (blocking) |
| 12 | Source-count ceiling — at what source count does the dedup pipeline degrade? | Eng | Pre-launch |
| 13 | Personal-event default surfacing — Personal Events in Pulse Digest: opt-in or opt-out default? | Product | Pre-launch |
| 14 | Free-tier save cap A/B — 1/day vs. 3/day vs. 5/day, and Pro pricing ($4.99 vs. $7.99 vs. $59 annual-only) — which test first? | Product + Growth | Post-launch (Month 1) |
| 15 | Growth-channel mix beyond SEO — referral program (Phase 2 dependency), at least one paid acquisition pilot (Meta/Reddit/Google ads), partnership with a community org per beachhead city. Required for SM-10 realism. | Product + Growth | Pre-launch |

---

## 9. Assumptions Index

*Every `[ASSUMPTION]` inline, surfaced for explicit confirmation.*

- **[ASSUMPTION-1]** From §4.1 FR-4 Notes — Web cookies are sufficient for MVP authentication; mobile/session tokens in Phase 2.
- **[ASSUMPTION-2]** From §4.2 FR-5 Notes — Pulse Digest composition is deterministic per user per day; A/B testing done via shadow composition, not live user experience.
- **[ASSUMPTION-3]** From §4.3 FR-9 — iOS/Android push notifications are *not* in MVP. Email digest is the primary reminder channel; push comes in Phase 2 with mobile apps.
- **[ASSUMPTION-4 (resolved)]** ~~From §4.9 FR-35~~ — Pro tier pricing decided at MVP: $4.99/month or $49/year (annual). Subject to A/B test post-launch (Open Q #14).
- **[ASSUMPTION-5 (revised)]** From §4.9 FR-29 — Default per-MAU TCO target is $1.25/month at MVP (full breakdown in FR-29). AI-only cost ceiling was $0.50; the TCO lens supersedes it. Configurable per-category.
- **[ASSUMPTION-6]** From §4.4 FR-13 — Source Registry is internal-only; user-facing source management is Phase 3+.
- **[ASSUMPTION-7]** From §4.5 FR-19 — Personal Events appear in the Pulse Digest by default; the user must opt out. (Open Question #13 — this is the default pending confirmation.)
- **[ASSUMPTION-8]** From §4.6 FR-25 — "Less like this" swipe is the only dismissal signal in MVP. Nuanced dismissals (e.g., "not for me but similar events are fine") in Phase 2.
- **[ASSUMPTION-9]** From §4.7 FR-26 — Public event pages are not user-generated-content; they reflect the registry's source-of-truth only.
- **[ASSUMPTION-10]** From §7.1 SM-1 — "Time-to-first-relevant-event" includes both Pulse Preview (anonymous) and post-signup first Pulse Digest. The 30-second target is for the post-signup path.
- **[ASSUMPTION-11]** From Amendment A-3 / FR-22 — Confidence Pulse formula weights (`w1=0.40, w2=0.25, w3=0.20, w4=0.15`) are locked at MVP launch. Any change requires a PRD amendment with a changelog entry visible in Settings → Privacy → "Ranking algorithm version." A/B testing on live weights is forbidden; shadow composition is the only sanctioned channel.
- **[ASSUMPTION-12]** From Amendment A-5 / FR-58 — Conflict prompts require an explicit choice (Keep both / Edit the new one / Delete the new one). No dismiss-without-resolution option. The conflict indicator persists on Pulse Cards after "Keep both" is chosen as a calm permanent reminder.
- **[ASSUMPTION-13]** From Amendment A-6 / FR-60 — Every Event has an explicit `start_time_tz`. Sources with `tz_coverage = none` (bare local time without reliable venue) are auto-rejected for corpus inclusion. The venue registry is a new infrastructure component supporting both FR-60 timezone resolution and FR-15 Event Identity `venue_fingerprint`.

---

## 10. Constraints & Guardrails

### 10.1 Compliance & Legal

**The product's ingestion pipeline must respect the source-acquisition hierarchy (FR-17).** Crawling is permitted only when no higher-priority method exists and a ToS review has been logged in the Source Registry. The Source Registry is auditable; every change is timestamped and attributed to an owner.

**User data handling** must comply with the privacy frameworks of every jurisdiction the product is offered in at launch. Launch-go gate: legal review sign-off on every jurisdiction listed below.

**Launch-jurisdictions matrix (MVP):**

| Jurisdiction | Framework | MVP obligations |
|---|---|---|
| **United States (federal)** | CAN-SPAM, COPPA (if <13 audience; MVP excludes), Section 230 (content moderation safe harbor) | CAN-SPAM compliance for transactional emails; one-click unsubscribe (RFC 8058); no third-party PII resale |
| **United States (states)** | CCPA/CPRA (California), VCDPA (Virginia), CPA (Colorado), CTDPA (Connecticut), UCPA (Utah) | Right to know, delete, correct, opt-out of "sharing"; privacy policy disclosure; data processing agreement (DPA) for service providers |
| **European Union + UK** | GDPR (EU), UK GDPR, ePrivacy Directive | Lawful basis (consent for analytics, contract for service); data export (JSON + ICS) per Article 20; deletion within 30 days per Article 17; DPIA (Data Protection Impact Assessment) **before** EU launch (target: 30 days pre-launch); EU representative appointed if no EU establishment |
| **Canada** | PIPEDA, Quebec Law 25 | Privacy policy; data localization disclosure for Quebec users; data export; deletion |
| **Brazil** | LGPD (Lei Geral de Proteção de Dados) | Right to confirmation, access, correction, anonymization, portability, deletion; consent for non-essential processing; DPO appointment (can be remote) |
| **Australia** | Privacy Act 1988 + APPs | Privacy policy; data export; deletion; cross-border disclosure notice (US-hosted data) |
| **Other (global launch)** | Local privacy + email frameworks | Honor user-jurisdiction opt-outs at the IP/geo-IP level; default to GDPR-aligned protections where local law is silent |

**EU/UK launch gate:** DPIA must be completed and signed off by a privacy counsel **before any EU user is on-boarded**. Target completion: 30 days before public EU marketing begins.

**Email deliverability** must comply with CAN-SPAM, GDPR, and applicable transactional-vs-marketing distinctions. Pulse Digest and reminders are transactional; one-click unsubscribe per RFC 8058 is mandatory.

**Accessibility** must target WCAG 2.1 AA. The Pulse Card, Detail Screen, and onboarding flow are audit-grade for screen-reader and keyboard navigation.

**Pre-launch launch-blocker (Open Q #11 + §10.5 incident response):** Live competitive re-verification (Apple Intelligence, Gemini in Workspace, Luma, Partiful) and incident-response runbook must be signed off before any public launch.

### 10.2 Privacy

- Personal data minimization: the system stores only what personalization requires.
- Personal events and personal calendar data are isolated from public event data in the database (separate tables, encryption at rest).
- Analytics are aggregated; no per-user PII in event logs.
- A user-requested account deletion purges all personal data within 30 days; aggregated anonymous analytics are retained.
- **No user-data model training.** EventPulse24 does not use personal data (personal events, saved events, preference-graph signals, user-submitted content) to train, fine-tune, or otherwise improve any third-party or first-party AI model. Public-event ingestion data (the Source Registry contents) is third-party content and is governed by source-specific ToS — see FR-17. Where the LLM provider's terms permit opt-out of training-data retention, the system is configured to opt out at the API level.
- **Data retention windows per category:**
  - **Personal events + saved events:** retained while account is active; purged within 30 days of account deletion.
  - **Preference graph signals (dwell, swipes, dismissals):** retained 12 months rolling; auto-purged thereafter.
  - **Personal email addresses and OAuth tokens:** retained while account is active; encrypted at rest; purged on disconnect or account deletion.
  - **Email delivery events (sent, opened, clicked):** retained 90 days for spam-complaint monitoring; aggregated counts beyond.
  - **Audit logs (auth events, settings changes, deletions):** retained 24 months.
  - **Source Registry contents (third-party event data):** retained while event is in date-range + 12 months; auto-archived.
  - **Source-acquisition ToS review records:** retained 7 years (legal).
  - **Billing records (Pro subscribers):** retained 7 years (tax/legal).
  - **Anonymized analytics aggregates:** retained indefinitely (no PII).
- **User-visible data inventory:** Settings → Privacy → "What we store" displays the categories and current retention windows in plain language. The export CTA (FR-52) gives all data in <24h; deletion CTA completes in ≤30 days (per §10.1).
- **No third-party data sales.** Not now, not ever. (See §15.2 "No ads. No commissions. No data sales.")

### 10.3 AI Cost

The AI Cost Dashboard (FR-29) is **operational from day 1.** The default per-MAU cost threshold is $0.50/month. Any feature that pushes blended cost above threshold triggers a review.

**Lifting-cost-out-of-the-loop principle:** every Phase 2+ feature MUST include an AI cost estimate in its spec. Phase 3+ features MUST include a cost optimization plan (on-device, caching, batching).

### 10.4 Operational SLAs

- **Source freshness:** Source Registry ingestion completes at least daily; high-priority sources (official sites) within 4 hours.
- **Pulse Digest delivery:** at the user's chosen time ±15 minutes. >5-minute delays are logged.
- **Reminder delivery:** at the slot time ±5 minutes. >5-minute delays are logged.
- **Email deliverability:** bounce rate <2%, spam complaint rate <0.1%.
- **Uptime:** 99.5% for the Pulse Digest, reminders, and personal event flows. SEO public pages: 99.9%.

### 10.5 Incident Response & On-Call

**No launch without an incident response plan.** A product whose value prop is "calm" cannot itself become the source of 3am panic.

**On-call rotation:**
- At MVP launch (≤2-person team): one named on-call engineer carries a pager 24/7 for 7-day rotations. Backup: founder or second engineer. Coverage gaps are explicitly prohibited; if a gap cannot be filled, the team delays launch or pauses new features until covered.
- At 5+ MAU milestones (100K, 500K, 1M): rotation expands to ≥2 named engineers with a documented handoff process.

**Severity tiers:**
- **SEV-1**: *Critical.* Pulse Digest delivery broken for >5% of users; reminder dispatch broken; data breach; trust-eroding source content reaches users (e.g., hallucinated event with real-world harm). Target time to acknowledge: **15 minutes.** Target time to mitigation: **2 hours.**
- **SEV-2**: *Major.* Single-source ingestion failure; partial degradation of Pulse Digest (>30 minutes); email deliverability drops below thresholds (bounce >2% or complaint >0.1%); AI cost ceiling breach. Target ack: **30 min.** Target mitigation: **4 hours.**
- **SEV-3**: *Minor.* Single user-facing error; minor UI bug; non-blocking ingestion delay. Target ack: **next business day.**

**Communication:**
- A public status page (status.eventpulse24.com or equivalent) is updated within 30 minutes of any SEV-1 and within 4 hours of any SEV-2. Status changes are calm and explicit: "Source X paused, ~3% of events affected, we are working on it."
- No emoji, no urgency language, no marketing spin. Same voice as the product.

**Post-mortem obligation:** Every SEV-1 generates a written post-mortem within 5 business days. Post-mortems are public (for SEV-1) — published to the company's transparency page; this is on-brand with "Trust through transparency."

**Runbook:** A living `runbook.md` lives in the repo and is reviewed monthly. It includes source-specific failure playbooks (Eventbrite 401, Luma webhook drop, LLM provider outage, ESP DMARC failure, OAuth provider 5xx). The runbook is the on-call engineer's first stop.

**Test cadence:** Quarterly "fire drill" simulation — a deliberate SEV-1 drill (e.g., disable a critical source, see how fast the on-call detects and mitigates). Drill results are reviewed but not graded against punitive metrics.

---

## 11. Cross-Cutting NFRs

### 11.1 Performance

- **Pulse Digest composition:** <500ms p95 (cached); <3s p95 (cold).
- **Event extraction:** <2s p95 per event.
- **Dedup pass:** <500ms p95 per event; supports batch dedup at 10K events/hour.
- **Page load:** <1.5s LCP on Pulse Digest and Detail Screen, 3G-fast.
- **API response:** <300ms p95 for read-heavy endpoints.

### 11.2 Security

- OAuth tokens for Google Calendar + Microsoft Graph, and CalDAV app-specific passwords for Apple Calendar (FR-3 / FR-50), stored encrypted at rest. Token rotation: Google/Outlook per provider refresh-token flow; Apple CalDAV — user-initiated re-auth on password change (no automatic refresh).
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

**Target:** WCAG 2.1 AA across all surfaces, with concrete acceptance testing pre-launch.

**Automated checks (continuous):**
- `axe-core` or equivalent integrated into CI; zero serious/critical violations on Pulse Digest, Detail Screen, Onboarding, Settings, Detail Screen wireframe.
- Lighthouse accessibility score ≥95 on all primary pages.
- Color-contrast verification on Pulse Card warm-tone (Personal) and cool-tone (Public) variants — minimum 4.5:1 for text, 3:1 for UI elements.
- HTML semantic structure (proper landmark roles, heading hierarchy, button vs. link discipline).

**Manual screen-reader tests (pre-launch gate + quarterly):**
- **NVDA + Firefox on Windows**: full Pulse Digest traversal: each card's name, time, location, Why-this Tags, Confidence Pulse, Source Badge, CTAs reachable via single Tab cycle; all actions (save, share, dismiss, detail) operable via Enter / Space.
- **VoiceOver + Safari on macOS**: same traversal, plus keyboard-only navigation.
- **VoiceOver + Safari on iOS**: mobile web Pulse Digest: swipes announce card title + Why-this Tags; tap targets ≥44×44 CSS pixels.
- **TalkBack + Chrome on Android**: mobile web Pulse Digest: focus traversal covers all CTAs; no trap-focus bugs.
- **Switch Control on iOS / Switch Access on Android**: minimum: can save and dismiss a card without fine-motor gesture.

**User-facing acceptance:**
- Keyboard navigation on Pulse Digest, Detail Screen, and onboarding (no mouse required to complete UJ-1, UJ-3, UJ-5).
- All interactive elements have ARIA labels.
- Reduced-motion preference (`prefers-reduced-motion`) respected on all transitions.
- Color is never the sole carrier of meaning (warm/cool tone also conveyed via iconography or label).
- Linearized card list for screen readers (no grid tab-order gymnastics; tabbing through cards is consistent in the visual reading order).

**Documentation:**
- A pre-launch accessibility audit report is required before MVP public launch. The report lists each test, results, and any open issues (with severity and remediation owner).
- Quarterly re-audit with the same scope; results published internally.

### 11.6 Internationalization

- English-first MVP. i18n architecture in place (string externalization, locale-aware date/time).
- Multi-region rollout (EU, APAC) is Phase 2+.

**Event timezone handling (per Amendment A-6 / FR-60):**

- Every Event has an explicit `start_time_tz` field. Timezone inference uses a venue registry + IANA timezone database.
- The Pulse Card displays event time in the user's local timezone. The Detail Screen displays venue-local time when the user's timezone differs by >1 hour.
- Conflict detection (FR-58) operates in UTC.
- Cross-timezone event delivery (e.g., a user in NYC viewing an LA event) is a core MVP capability, not a Phase 2 feature.

**Multi-region rollout (EU, APAC) is Phase 2+.** The GDPR / UK GDPR / EU-launch-gate commitments in §10.1 are jurisdiction-dependent and proceed independently of i18n rollout.

---

## 12. Why Now

Three timing vectors align. Missing any one and the window closes.

1. **AI capability is here.** LLM-based structured extraction (Pydantic + Instructor + constrained decoding) is reliable enough for production event extraction at <$0.005/event. Embedding-based dedup is sub-cent at scale. (See addendum §E for tooling details.)

2. **Attention fatigue is acute.** Consumers have disabled notifications on most event apps. The "calm" positioning is a *demand* signal, not just a marketing choice. Industry-average 5–15 notifications/day is the problem EventPulse24 solves.

3. **The platform-owner window is closing.** Apple (Apple Intelligence) and Google (Gemini in Workspace) are moving into the "smart calendar" lane. They do NOT cover the **aggregation + curated calm digest across sources Apple/Google don't index** (Luma, Partiful, Bandsintown, local newsletters, personal calendars). EventPulse24 wins the consumer brand for "calm event intelligence" before the OS-level copy lands in 12–18 months.

**Risk note:** If the platform owners ship aggregation-tier features (events from Luma, Partiful, etc.) in their OS-layer events, EventPulse24's defensibility depends on the brand moat + the data moat (proprietary event corpus + user preference graph). Both are being built intentionally.

### 12.1 Pre-Launch Competitive Re-Verification Gate (Go/No-Go)

This is a **launch blocker**, not a polish item. Live competitive re-verification is required before any public launch.

**Cadence:** within 30 days before public launch; re-verified quarterly thereafter (the platform-owner window is 12–18 months; the threat surface changes).

**What gets verified:**
1. **Apple Intelligence / Siri Suggestions** — Does it now aggregate events from non-Apple sources (Luma, Partiful, Bandsintown)? Are calendar suggestions "smart" beyond personal-calendar inference?
2. **Gemini in Workspace / Google Calendar** — Does Gemini surface third-party event aggregations in calendar suggestions? Has Google acquired or partnered with an event aggregator (Eventbrite, Luma, etc.)?
3. **Luma** — Has Luma shipped a daily/weekly digest feature? Has it expanded beyond tech/community categories (food, arts, family)?
4. **Partiful** — Has Partiful shipped discovery for non-Partiful events? Has it opened a public-events surface?
5. **Eventbrite** — Has Eventbrite shipped a "discover" surface with AI curation? Has it acquired a calm-positioned competitor?
6. **Facebook Events** — Still alive? Still relevant? (Re-baseline the threat model.)
7. **New entrants** — Any funded seed/Series-A "calm events" or "AI event curator" startup that didn't exist at PRD authoring?

**Go / No-Go criteria:**
- **GO**: At least 5 of 6 platform-owner lanes remain un-aggregated (Apple/Google still don't cover third-party events; Luma/Partiful still don't have a curated calm digest). Documented evidence in the re-verification report.
- **NO-GO**: Any platform-owner lane has shipped aggregation in the calm-digest lane. The PRD is re-scoped to defend against the new threat; MVP launch is delayed or repositioned.
- **CONDITIONAL GO**: One lane has shipped a feature, but it's not a direct competitor (e.g., Google adds Luma data but no curated digest). Launch proceeds with documented risk-mitigation moves (data moat acceleration, partnership lock-ins).

**Re-verification report artifact:** `competitive-reverification-YYYY-MM-DD.md` in the planning-artifacts directory. Report is referenced in §17 Risks.

**Owner:** Product lead. **Cadence:** quarterly + every launch milestone (MVP, 100K MAU, 1M MAU). **Failure to re-verify = automatic launch hold.**

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
| **Settings** | Reminders, Quiet Hours, source mute, account, **Privacy (data export + deletion)** | All users |
| **Onboarding** | First-time flow | New users |

**Settings → Privacy sub-screen (MVP):**

| Item | Purpose | Reaches |
|---|---|---|
| **Your data** | Plain-language list of categories stored (personal events, saved events, preference graph, etc.) and current retention windows per §10.2 | All users |
| **Download my data** | CTA → email with JSON + ICS download links within 24h (FR-52). Free in EU/UK/CA/BR/AU (GDPR Art. 20); Pro-only elsewhere. | All users |
| **Delete my account** | CTA → 30-day grace period → permanent deletion (per §10.1). Confirmation modal explains what is and isn't retained (anonymized aggregates survive). | All users |
| **Geo-IP usage** | Toggle to opt out of geo-IP inference; fallback to "most popular city" or manually-selected city | All users |
| **Training opt-out** | Confirms EventPulse24 never uses personal data for model training (per §10.2); informational | All users |
| **Ranking algorithm version** | Displays the Confidence Pulse formula weights (currently `w1=0.40, w2=0.25, w3=0.20, w4=0.15`), the bucket boundaries, and the last-amendment date. Links to the relevant PRD section and the ADR changelog. Read-only. Satisfies the "Trust through transparency" principle. | All users |

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

### 15.1 Free Tier (MVP — FR-1 through FR-30)

- Pulse Digest (3 cards/day)
- Personal Events (manual, ≤50 active)
- Multi-tier reminders (email)
- Pulse Preview (anonymous)
- Pulse Ping (1/day)
- **Save cap: 1 Pulse Card saved per 24-hour period** (post-1-save, calm in-app upgrade prompt)

**Caps:** `[ASSUMPTION: 1 calendar (own only — no OAuth at MVP), 1 saved collection, 50 active personal events, 1 group (Phase 2).]`

**Rationale for 1-save/day cap:** The cap is the only monetization hook at MVP. It is set conservatively low to test upgrade intent without forcing a hard paywall. A/B test variants (3/day, 5/day) in Open Q #14. The cap is on **saves**, not on **views** — Pulse Digest is always free.

### 15.2 Pro Tier (MVP — FR-48 through FR-52, $4.99/month)

**Pricing:** $4.99/month or $49/year (annual = ~17% discount). Subject to A/B test post-launch (Open Q #14).

**Pro unlocks:**
- **Unlimited saves + saved collections** (FR-49) — beyond 1 save/day, no cap.
- **Up to 3 connected calendar providers — Google + Apple + Outlook read-only sync** (FR-50 / FR-3) — personal events from any connected provider flow into the Pulse Digest. Free tier caps at 1 connected provider.
- **Per-day-of-week custom quiet hours** (FR-51) — granular control over reminder delivery.
- **JSON + ICS data export** (FR-52) — GDPR Article 20 right-to-portability; available to all users in EU/UK/CA jurisdictions; gated to Pro for non-jurisdictional users.

**Pro does NOT include at MVP:**
- Two-way write-back to connected calendars (Phase 2 — FR-31)
- Recurring-event RRULE expansion beyond simple instance listing (Phase 2 — FR-31)
- Pulse the Group (Phase 2 — FR-34)
- Unified Timeline (Phase 2 — FR-32)
- Why Now? (Phase 3 — FR-38)
- On-Device Personal AI (Phase 3 — FR-39)
- Travel Mode (Phase 3 — FR-40)

**No ads. No commissions. No data sales.** The business model is misaligned with the engagement-trap metric. That misalignment is the moat.

### 15.3 Future

- **Phase 2 Pro Augmentation (FR-35):** Apple/Outlook sync, Pulse the Group, Unified Timeline, A/B-tested pricing.
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

- **Product Brief:** `_bmad-output/planning-artifacts/briefs/brief-EventPulse24-2026-08-19/brief.md`
- **Innovation Strategy:** `_bmad-output/innovation-strategy-2026-08-19.md`
- **Design Thinking:** `_bmad-output/design-thinking-2026-08-19.md`
- **Blue Ocean Strategy:** `_bmad-output/blue-ocean-strategy-2026-08-19.md`
- **Original scope:** `docs/scope.txt`
- **Addendum (this run):** `prd-EventPulse24-2026-08-19/addendum.md`
- **Memlog (this run):** `.memlog.md`

---

_Generated using BMad PRD Workflow. Synthesis sources: Product Brief + Innovation + Design Thinking + Blue Ocean + 2025-2026 landscape research._
