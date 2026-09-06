---
title: "EXPERIENCE.md — EventPulse24"
status: final
created: 2026-08-23
updated: 2026-09-06
updated_note: "Subsequent update 2026-09-06 (sidenav-footer pattern): added Component.Sidenav.Footer to §4 Component Patterns, documenting the Search + Account footer block pinned to the bottom of the 240px sidenav rail. Search + Account do not fit the route list and do not belong in the topbar (topbar-quiet rule, ASSUM-11). All tokens reused from existing DESIGN.md palette — no new colors, no new CSS variables. Pattern sourced from mockup changes to pulse-digest-desktop.html and conflicts-desktop.html, then promoted to spine so the remaining sidenav surfaces (timeline-desktop.html, settings-desktop.html, ranking-algorithm-transparency-desktop.html) can adopt it without re-derivation. Subsequent update 2026-09-06 (ranking-algorithm IA): ranking transparency (PRD FR-22) lives inside Settings → Privacy as an in-page section, not a separate route. Updated §2 IA table row 9 to spell out ranking transparency as a sub-section. **Spine update 2026-09-06 (sidenav link-reset prerequisite):** added a new bullet under Component.Sidenav.App in §4 — 'Global reset prerequisite: the page's CSS must include `a { color: inherit; text-decoration: none; }` before the sidenav is applied, otherwise the browser default underlines bleed through on every route label and the Account row.' Documents a real bug from the 2026-09-06 batch migration of pulse-digest-empty-state-desktop and personal-event-edit-desktop, both of which shipped the shell without the reset (the original pre-sidenav files had no <a> in the topbar zone). Earlier updates preserved: 2026-09-03 pulse-preview audit additions, 2026-09-03 v1 onboarding audit, 2026-09-06 Amendment A-8 lift."
project: EventPulse24
source_prd: _bmad-output/planning-artifacts/prds/prd-EventPulse24-2026-08-19/prd.md
source_brief: _bmad-output/planning-artifacts/briefs/brief-EventPulse24-2026-08-19/brief.md
references:
  design: DESIGN.md
  prd: _bmad-output/planning-artifacts/prds/prd-EventPulse24-2026-08-19/prd.md
  reconcile_design_thinking: _bmad-output/planning-artifacts/prds/prd-EventPulse24-2026-08-19/reconcile-design-thinking.md
  reconcile_blue_ocean: _bmad-output/planning-artifacts/prds/prd-EventPulse24-2026-08-19/reconcile-blue-ocean.md
  mockups: mockups/
---

# EventPulse24 — Experience Spine

> The behavioral contract for the product. Visual identity lives in `DESIGN.md`; this spine is the experience.

## 1. Foundation

**Project:** EventPulse24 — the calm intelligence layer above all event sources. Anti-Eventbrite. "Headspace of events."

**Form factor:** Responsive web. Mobile-first at 375 px CSS width. Tablet/desktop breakpoint at 768 px. Maximum canvas width 1180 px (content never exceeds this; whitespace expands outward). No native iOS/Android app at MVP (web only; Phase 2+).

**UI system:** None — vanilla web components plus a thin token layer defined in `DESIGN.md.{Tokens}`. We do not adopt Material, shadcn, or a full kit; the surface vocabulary is small and bespoke. Headline typography is `Text.Display`; body is `Text.Body`; metadata is `Text.Meta`.

**Theme (added 2026-08-30):** Dark mode is the default and primary theme at MVP (PRD update + user direction). Engineering ships with `data-theme="dark"` set on the `<html>` element by default. Light mode is provided as an opt-in alternative in `Settings → Appearance`, but the visual identity, contrast, motion, and component behaviors in `DESIGN.md` are calibrated for the dark surface first. There is no `prefers-color-scheme: dark` auto-switch at MVP — the user picks theme explicitly from `Settings → Appearance`. A "System" option (follow OS) is a Phase 2 candidate. The rationale for dark-first: it matches the brand posture of *instrument-grade calm* and is OLED-friendly — the deep near-black canvas with a single terracotta glow reads as a precision tool, not a marketing site.

**Form-factor reasoning:**
- Web-first because the value prop is read-mostly (a Pulse Digest is a 30-second check-in), and the corpus of public events is best indexed from the open web. SEO is the cold-start unlock — search-engine crawlers do not see a native app.
- Mobile-first because Maya's UJ-1 starts on her phone at 7:42 am. Desktop adds whitespace; it does not add features. A pulse read on a laptop is the same pulse read on a phone.
- Responsive because the same calm promise must hold across contexts. The product never feels like "a mobile app stretched" or "a desktop site shrunk."

**Visual identity:** See `DESIGN.md` for `color.accent.terracotta`, `color.surface.paper`, `color.ink.primary`, `color.warm.personal`, `color.cool.public`, and the full token set. This spine references tokens by `{path.to.token}` wherever behavior depends on them.

**Locked principles (PRD §5.1, ratified for behavior):**
- Calm > Engagement — fewer, better notifications. Counter to industry spam.
- Explainable AI — every recommendation shows its reasoning.
- Calendar-sync-in, not replace — extend Google/Apple/Outlook; do not fight OS distribution.
- 3 cards max — with the adaptive exception (5–7 for engaged users, §4.2 of this spine).
- Trust through transparency — Source Badges, Confidence Pulse, no hidden ranking.
- No dark patterns — no urgency badges, no FOMO carousels, no "Don't miss out!" copy.

---

## 2. Information Architecture

Numbered site map. Each route is reachable; each route defines default / empty / loading / error states. Cross-reference `DESIGN.md.Surfaces.{RouteName}` for the corresponding visual composition.

| # | Route | Purpose | Phase | Auth |
|---|---|---|---|---|
| 1 | `/` | **Pulse Digest** (home) — 3-card daily brief | MVP | Authed |
| 2 | `/onboarding` | 3-step first-run flow (calendar → interest inference → first pulse) | MVP | Anon → Authed |
| 3 | `/events/:id` | **Event Detail** ("Why this?") — single event deep-dive | MVP | Authed + Anon (read-only) |
| 4 | `/preview` | **Pulse Preview** — anonymous 3-card preview of city events | MVP | Public |
| 5 | `/events/near-me` | **SEO landing page** — public events for a city, no auth | MVP | Public |
| 6 | `/settings/reminders` | Default Reminder Plan editor | MVP | Authed |
| 7 | `/settings/quiet-hours` | Quiet Hours window editor (single window Free; per-day Pro) | MVP | Authed |
| 8 | `/settings/sources` | Source transparency — list of sources, reliability, mute controls | MVP | Authed |
| 9 | `/settings/privacy` | Data inventory, export (FR-52), deletion, training opt-out, **Ranking algorithm version (FR-22)** with the formula, weights table, bucket boundaries, amendment history, and pledge | MVP | Authed |
| 10 | `/timeline` | **Unified Timeline** — Personal + Public events, week view (Amendment A-8) | MVP | Authed |
| 11 | `/conflicts` | **Conflict Review** — list of active + resolved conflict pairs (Amendment A-8); the three-action pattern itself lives in `Sheet.ConflictResolution` (FR-58 / Amendment A-5) and on Detail Screen (FR-33 / Amendment A-8) | MVP | Authed |
| 12 | `/groups/:id` | **Pulse the Group** — small-group coordination, vote, RSVP | Phase 2 | Authed |

Total: 12 routes.

**State coverage per route.** Every route must handle the four canonical states. The specific copy is in §5 (State Patterns); the table below tells you which states each route is expected to ship at MVP vs Phase 2.

| Route | default | empty | loading | error |
|---|---|---|---|---|
| `/` | 3-card Pulse Digest | "Nothing on the pulse today." (no CTA, no carousel) | 3 paper skeletons fading 1px toward ink at 60% then back | "Couldn't reach Pulse. Try again." + retry |
| `/onboarding` | Step 1 (calendar connect) | n/a (no empty state — every user starts at step 1) | Inline spinner only on the OAuth round-trip | "Connection failed. Skip for now?" |
| `/events/:id` | Full event detail with Why-this breakdown | An event the source removed: "This event is no longer available." | Detail skeleton: header + meta row + 3 Why-this chips fading in | "Couldn't load this event. Back to Pulse Digest." |
| `/preview` | 3-card preview for inferred city | "No preview available in {city} yet." — for search-engine referrers, render a subtle `Text.Meta` "Suggest an event" link opening `/suggest?city={city}` (see §5 Empty Patterns → Empty Preview, SEO referrer) | Card skeletons (3, parallel to digest) | "Couldn't load the preview. Refresh." |
| `/events/near-me` | SEO list of events for city | "Coming soon — we're growing {city}'s coverage." | List skeletons (5 rows) | "Couldn't load events. Try again." |
| `/settings/reminders` | Default Reminder Plan chips (5d/2d/1d/1hr) | n/a (defaults exist) | Inline save spinner on chip change | "Couldn't save. We'll try again on your next change." |
| `/settings/quiet-hours` | Default 10pm–8am window | n/a | Inline save spinner | "Couldn't save." |
| `/settings/sources` | Grouped source list (official/community/aggregator/crawled) | "No sources muted." | List skeletons | "Couldn't load sources. Refresh." |
| `/settings/privacy` | Data inventory + Export/Delete CTAs | n/a | Inline spinner on export trigger | "Couldn't start export. Email us." |
| `/timeline` | Week-view, Personal+Public events (read-only at MVP — Amendment A-8) | "Your week is quiet. Pulse Digest is the place to discover." | Week-row skeletons | "Couldn't reach Timeline. Try again." |
| `/conflicts` | Conflict list grouped by Active / Resolved (Amendment A-8) | "No overlaps." | Skeleton rows | "Couldn't analyze conflicts. Try again." |
| `/groups/:id` | Group home, members, next event proposal | "No group yet. Create or join one." (Phase 2) | Skeleton | "Couldn't load group. Try again." |

**Notes:**
- `/settings/privacy` is implied by the PRD §14.1 Settings → Privacy sub-screen (not in the locked IA list above; see _Assumptions_ at end of document, ASSUM-2).
- No `/admin`, no `/debug` — internal AI Cost Dashboard (FR-29) and Editorial Review Queue (FR-57) live outside this surface map.

---

## 3. Voice and Tone

**Voice:** Calm, knowledgeable, restrained. Like a friend who knows the city well but doesn't oversell. (PRD §13.2.)

**Tone:** Plain, direct, modern utility. No flourish, no flourish-free *posturing* either. Functional prose.

**Locked principles (PRD §13.2, ratified for behavior):**
- Plain language. "Three things worth your time this week" not "We've curated the perfect agenda for your daily life."
- No superlatives. No "amazing," "incredible," "must-see."
- Acknowledge the empty case. "No pulse for today" is honest; "Nothing matches your interests yet" is condescending.
- Why-this Tags are first-class — they are the voice of the product.
- No exclamation points. Calm products don't shout.

**Microcopy contract — examples by surface (10 surfaces).** Use the locked voice. Cite `{Text.Body}` for body copy.

| Surface | Do | Don't |
|---|---|---|
| Pulse Digest headline (above cards) | "Today, three things matter." — _see §5 Empty Patterns for full default vs. empty behavior; §5 is canonical_ | "We've hand-curated the perfect day for you!" |
| Pulse Digest empty state | "Nothing on the pulse today. The calendar is yours." — _canonical; see §5 Empty Patterns_ | "No events match your interests yet — keep exploring!" |
| Why-this Tag (max 3 keywords, comma-separated) | "nearby · tonight · music" | "Within walking distance and a perfect acoustic match for your refined taste!" |
| Source Badge tooltip (on hover/tap of `Badge.Source`) | "Official site. Verified venue." | "Trusted by EventPulse24! 🌟" |
| Confidence Pulse tooltip ("Why this confidence?") | "4 of 5. Strong match on your top three interests and within 2 km." | "We think you'll love this! Confidence: 4.7/5" |
| Reminder Picker label | "Remind me:" | "Set up smart reminders to never miss out!" |
| Quiet Hours label | "10pm–8am. Nothing during this window." | "Sleep tight! We've got your back." |
| Onboarding step header | "Connect a calendar (optional)" | "Let's supercharge your events!" |
| Onboarding step 1 — provider button label (Google) | "Google Calendar · Read-only · 1-click OAuth" | "Connect Google (recommended)" |
| Onboarding step 1 — provider button label (Apple) | "Apple Calendar · CalDAV · app-specific password" | "Apple Calendar (iCloud only — Pro tier)" |
| Onboarding step 1 — provider button label (Outlook) | "Outlook Calendar · Microsoft Graph · 1-click OAuth" | "Outlook Calendar (work accounts — Pro tier)" |
| Onboarding step 1 — provider parity | All three providers render with identical visual weight (no "primary" Google + ghost Apple/Outlook). Provider parity per PRD FR-3 / FR-50 + `DESIGN.md` `component.button.provider`. | Visually elevate Google as the "real" provider; demote Apple/Outlook to secondary ghost links or text. |
| Onboarding step 1 — Apple CalDAV failure | "We couldn't reach your iCloud calendar. Double-check the app-specific password." + inline help link "How do I get this password?" | "Invalid credentials (HTTP 401)." / "OAuth failed." / "Apple Calendar is not supported on your plan." |
| Onboarding step 1 — any-provider failure | "Connection failed. Skip for now?" with two equal-weight buttons | "We could not connect to your calendar. Please try again later or contact support." (no skip, no retry, no escape) |
| Conflict Resolution sheet header | "These overlap." | "Uh oh! Looks like you have a scheduling conflict!" |
| Conflict Resolution three-action labels | "Move dinner earlier / Skip concert / Keep both — I'll manage" | "Quickly resolve this clash to keep your calendar tidy" |
| `/conflicts` page heading (Amendment A-8) | "These days overlap." | "Your Schedule Conflicts" / "Conflict Center" / "Conflicts (12)" |
| `/conflicts` empty state (Amendment A-8) | "No overlaps. Conflicts appear here as you save events." | "You're all clear! 🎉" |
| FR-33 three-action labels (Personal↔Public, Amendment A-8) | "Move {personal event} earlier / Skip {public event} / Keep both — I'll manage" | "Quickly resolve this overlap to keep your schedule tidy" |
| Timeline empty day (Amendment A-8) | "Quiet day." | "Nothing scheduled." / "Free as a bird!" |
| Timeline empty week (Amendment A-8) | "Your week is quiet. Pulse Digest is the place to discover." | "No events this week." |
| State-change email subject | "EventPulse24: {event name} was moved to {new date}" | "⚠️ Important update about your event!" |
| Source transparency page intro | "Here's where events come from and how we trust each one." | "We work with the best event sources in the world!" |
| Empty onboarding-interest step | "We'll figure this out from your calendar. Skip?" | "Tell us what you love so we can personalize!" |
| Pulse Preview hero / preview header | "Three picks, every morning." | "We show you exactly those." |
| Soft-wall on anonymous action (Save / Follow) | "We'll hold your seat." / "We'll save your spot." | "→ Sign up to save." / "Sign up to continue." |
| Adaptive-digest inline expand | "Show all 5" | "Unlock the full Pulse experience!" |
| Free-tier save-cap prompt | "You saved one event today. Save more with Pro." | "LIMITED TIME: Upgrade now and get UNLIMITED saves!" |
| Status page incident copy | "Source X paused. ~3% of events affected. We are working on it." | "We're aware of an issue and working hard to fix it ASAP!" |
| Privacy / export confirm | "Your export is ready. Link in your inbox." | "🎉 Success! Your data is on its way!" |
| Already-handled reminder suppression (FR-44 Phase 2) | (silent — no copy) | "We've suppressed this reminder because we noticed you already RSVP'd." |
| Streak-broken (Pulse Streak, Phase 3 §11) — _no copy at MVP; see §11_ | (no copy — silence on broken streak) | "You broke your 12-day streak! Don't lose your progress!" | Listed to document the principle: §11 Pulse Streak forbids any streak-broken copy at MVP. The Do cell intentionally shows _no copy_, not "Welcome back." — that form is not approved microcopy for streak breakage and must not be substituted. |

**Why-this Tags are first-class.** A Why-this Tag is the smallest unit of trust. The exact three keywords on a Pulse Card are repeated on the Detail Screen (PRD §4.6 FR-21). The tags use sentence-case nouns and short verb-free phrases (`nearby, tonight, music` not `you might enjoy this because it is nearby and tonight and music`).

**Zone roles — topbar carries identity, hero carries the benefit.** Each visible zone on a public-facing surface has a fixed role. The topbar (brand mark + tagline) carries *identity* — who the product is and what its posture is. The hero (eyebrow + h1 + lede paragraph) carries the *benefit* — what the product does for the visitor today. The hero never carries the positioning tagline ("the calm intelligence layer for events"); that lives in the topbar. The topbar never carries a benefit claim; it never asks the visitor to do anything. Inversions of this rule (positioning taglines in the hero, benefit claims in the topbar) are forbidden microcopy placements. Locked examples: hero eyebrow is a *what you get* sentence (`Three events a day. Hand-picked, not algorithmic.`); topbar brand lockup is the *who we are* lockup (`EventPulse24 · calm intelligence for events`).

**Topbar-quiet rule (locked).** The topbar of every surface holds only the brand mark + (optionally) the tagline. Action affordances — "Skip — take me to my brief", "Sign in", "Sign up", "Open menu" — live in the page footer, in surface-level CTAs, or in section-level decision moments. The topbar never carries a Skip button; the Skip lives in the footer (`← Back` / `Skip for now` / `Continue →`). This rule applies to `/onboarding` Step 1–3, `/settings/*`, `/preview`, and any future anonymous or authed surface with a topbar. Inversions are bugs.

**Voice in error states.** Errors are honest and brief. "Couldn't reach Pulse. Try again." — no apologies, no exclamation marks, no emoji. (See §6 Error Patterns.)

**Voice in success states.** Success is quiet. "Saved." not "🎉 You saved this event!" (See §6 Empty States.)

---

## 4. Component Patterns

Behavioral specs only. Visual composition lives in `DESIGN.md.Components`.

### `Card.PulseDigest`
A single Pulse Card on the home surface. Always shows: event name, time, location, up to 3 Why-this Tags, 1–5 dot Confidence Pulse, Source Badge (PRD FR-6). Visual spec: `DESIGN.md.Components.PulseDigestCard`.

- **Default state:** Card is `Card.PulseDigest` with body `Text.Body`, headline `Text.Display.sm`, metadata `Text.Meta`. No paper-darker shade. The card is `color.surface.paper` with a 1px hairline border in `color.ink.faint`.
- **Hover (desktop only):** Background shifts to `color.surface.paper.darker` (a 1-step paper-darker variant). A small `▸` affordance appears at the trailing edge, indicating the card is tappable to open Detail. The `▸` is **decorative information about tappability, not a click target of its own** — the entire card remains the tap target. The same `▸` affordance is shown on mobile when the card is in any focused or long-pressed state (keyboard focus, Switch Control focus, Touch & Hold), so the desktop hover cue has a mobile equivalent and §6 "No hover-only affordances on `sm` viewports" is honored. The `▸` is rendered with `aria-hidden="true"` (decorative) and the full tap target is announced via the card's `aria-label`.
- **Tap:** Opens `/events/:id`.
- **Long-press (mobile):** Shows a quick-actions sheet anchored to the card: Save, Dismiss, Less like this. Sheet uses `color.surface.paper` and standard mobile sheet affordances.
- **Swipe-left:** Dismiss (records "less like this"). Card animates off-screen to the left, snaps back if cancelled mid-swipe.
- **Swipe-right:** Save (to user's saved collection or default). Card animates off-screen to the right with a brief save confirmation.
- **Focus state (keyboard):** Visible 2px focus ring in `color.accent.terracotta` at AA contrast against `color.surface.paper`. `aria-label` reads the full card content.
- **Reduced motion:** All swipe animations collapse to instant transition with no fade. (See §7 Interaction Primitives.)
- **Adaptive expansion (engaged user ≥10 saves/30d):** Card count grows from 3 to 5 (top of the responsive matrix) or 7 (max). At 5+, a "Show all 5" inline link replaces the bottom card with the remainder of the stack, in place — no modal, no carousel. (See §10 Adaptive Density.)

### `Input.ReminderSlot`
The Reminder Plan editor on Detail Screen (PRD FR-9). Chips for 5d / 2d / 1d / 1hr plus a custom-slot picker.

- **Default:** Four chips (5d / 2d / 1d / 1hr) rendered horizontally with current selection filled with `color.ink.primary` and label inverted to `color.ink.inverse` (per `DESIGN.md.component.input.reminder.slot` — no terracotta on this chip; selection is communicated by ink inversion, not by accent). Unselected chips use `color.ink.primary` text on `color.surface.subtle`.
- **Drag-to-add:** The user can drag a chip along a horizontal timeline representing the time-to-event. The chip snaps to 5d / 2d / 1d / 1hr markers (snap distance: 12px). Releasing adds the slot to the active Reminder Plan.
- **Quiet Hours interaction:** If the **delivery time** of the resulting notification (slot offset added to event start) would land inside the user's Quiet Hours window (PRD FR-12), the chip dims to 40% opacity and shows a small `color.ink.meta` tooltip: "Will deliver at {end of quiet hours}." The chip is still selectable; on selection, the reminder is queued but its delivery is rescheduled to the end of Quiet Hours (PRD FR-12 contract). Quiet Hours is evaluated on **wall-clock delivery time in the user's local timezone**, not on the slot offset itself — the slot offset is a pre-event interval, so it almost never falls inside Quiet Hours, while delivery times do.

  _Worked examples:_
  - _Event Saturday 7:00 pm, slot 1hr → would deliver at 6:00 pm Saturday (outside default 10pm–8am Quiet Hours). No dim. Selectable normally._
  - _Event Friday 11:30 pm, slot 1hr → would deliver at 10:30 pm Friday (inside Quiet Hours). Chip dims to 40%, tooltip reads "Will deliver at 8:00 am Saturday." Selectable; selecting queues delivery for 8:00 am Saturday._
  - _Event Sunday 6:00 am, slot 5d → would deliver at Tuesday 6:00 am (outside Quiet Hours). No dim._
  - _Event Sunday 6:00 am, slot 1hr → would deliver at Sunday 5:00 am (inside Quiet Hours). Chip dims, tooltip reads "Will deliver at 8:00 am Sunday."_
- **Custom slot:** Long-press a chip → opens a time picker (relative to the event start). Min: 15 minutes before; max: 30 days before. Out-of-range snaps back.
- **Empty state:** No chips selected. Label reads "No reminders. You'll still see this event in Pulse Digest."
- **Loading:** Chips render immediately (no loading state — local save).
- **Error:** Inline below the chip row, 1 line: "Couldn't save. We'll try again on your next change." Color: `color.warn.amber` desaturated.

### `Indicator.Confidence`
The 1–5 dot Confidence Pulse on each Pulse Card (PRD FR-22). Five discrete states; no partial fills.

- **Visual:** Five dot placeholders arranged horizontally. Filled dots use `color.ink.primary`; empty dots use `color.ink.faint`. Spacing: 4px between dots. (Confidence Pulse is not on the terracotta-sanctioned list — its filled dots use ink-primary for the same reason the rest of the trust-signal dots do; the today indicator (`color.accent.terracotta`) is the single chromatic dot in the system.)
- **Default:** Dots only. No numeric label visible. `aria-label="4 of 5"` for screen readers (per §8 Accessibility Floor).
- **Hover/focus:** Tooltip "Why this confidence?" appears with 1–3 lines of contributing factors: e.g., "Strong match on your top three interests. Within 2 km. Source reliability 0.92." Tooltip uses `Text.Meta` on `color.surface.paper.darker`.
- **Bucket boundaries (PRD FR-22):** ≥0.85 = 5 dots, ≥0.65 = 4, ≥0.45 = 3, ≥0.25 = 2, else 1. No interpolation.
- **Hysteresis (transition rule):** Hysteresis is **per-event-per-day** — once a bucket is assigned at Pulse composition time for a given event on a given calendar day (in the user's local timezone), the event stays in that bucket for the remainder of the calendar day. The bucket recomputes only if the raw score changes by **≥0.10** within the same day (rare; happens only when the underlying recommendation model re-scores the same event mid-day). Across days, hysteresis resets — a new composition starts fresh bucket assignment. No persistent bucket is stored between days. On an exact bucket boundary (raw score e.g. 0.850), the **lower** bucket is used (≥0.85 means strictly greater than 0.85; 0.85 itself → 4 dots).

  _Worked example:_ Event X first appears on Tuesday with raw score 0.83 → 4 dots. Model re-scores mid-day to 0.86 → below the 0.10 delta threshold (delta = 0.03), so the event stays at 4 dots. If the model re-scored to 0.97 (delta = 0.14 from 0.83), the event moves to 5 dots. Next morning Wednesday, a fresh composition assigns the bucket from the new raw score without inheriting Tuesday's bucket.
- **Tap on a dot:** Same as hover (shows tooltip).

### `Badge.Source`
The Source Badge on each Pulse Card and Detail Screen (PRD FR-23). Five types: `official_site`, `community`, `aggregator`, `user_imported`, `crawled_html`.

- **`official_site`:** `color.accent.terracotta`-filled checkmark icon. Inline label "Official" in `Text.Meta`. Tooltip: "Verified venue or organizer."
- **`community`:** Ink-bordered checkmark (no fill, 1.5px border in `color.ink.primary`). Inline label "Community" in `Text.Meta` italic. Tooltip: "Posted by a community member."
- **`aggregator`:** Ink-bordered link icon (chain glyph). Inline label "Listing site." Tooltip: "Aggregated from a public listing."
- **`user_imported`:** Ink-bordered inbox icon. Inline label "Forwarded." Tooltip: "Added by you or from your calendar."
- **`crawled_html`:** A small `color.warn.amber` warning triangle. One-time "Why does this show ⚠?" tooltip on first view per user per event.
- **Text alternative:** Every variant includes a visible inline text label, not icon-only. (WCAG 1.1.1 per §8.)

### `Sheet.ConflictResolution`
The three-action conflict prompt (MVP, PRD FR-58 / Amendment A-5). This is the **minimum viable guard at MVP** — the system never lets a user double-book without an explicit decision. Locked pattern from Design Thinking wireframe Screen 6, extended with the forced-choice rule.

- **Trigger:** (a) On Personal Event creation, the system scans for other Personal Events within ±30 minutes. If found, the prompt appears inline in the creation flow. (b) On Personal Event creation, when a likely duplicate is detected (same name, ≥80% Jaccard, within 24h). (c) When a saved public event overlaps a saved personal event by >15 minutes (the existing Pulse Card of both events shows `Indicator.Conflict`).
- **Three actions, fixed order (top-to-bottom):**
  1. **"Keep both — I'll manage"** — confirms both events. `Indicator.Conflict` remains on both Pulse Cards permanently. No further prompting for this conflict pair. A `ConflictResolution` value object is recorded with `value=keep_both`.
  2. **"Edit the new one"** — opens the new event in edit mode with the conflicting time pre-highlighted. After editing, conflict detection re-runs. (For duplicate detection, this action is relabeled "Update the existing one" and opens the existing event.)
  3. **"Delete the new one"** — removes the new event. A confirmation step is required before deletion completes.
- **No fourth action. No dismiss button. No "X" close. No escape-key close. No outside-click close.** The user must choose. PRD FR-58 is explicit: *"There is no 'dismiss' or 'X' button."* This is non-negotiable for the calm contract — letting the user silently close without resolving would re-create the exact harm (missed double-booking) the prompt is preventing.
- **Visual treatment:**
  - Desktop: centered modal (`component.surface.modal`) on `Surface.PersonalEventCreate` or `Surface.PulseDigest`.
  - Mobile: bottom-anchored sheet (`component.surface.sheet`) with the same three-action body. The modal header uses an amber-circle exclamation glyph (`color.warn.amber`) — never red.
  - Header copy: "This overlaps with another event." (PRD §13.2 voice — direct, not alarmist.) Subhead: "You've already saved {conflicting event name}. Choose how to handle it."
  - The two affected events render as small stacked cards with the `Indicator.Conflict` amber dot on each. The new event is marked "NEW" in a terracotta pill above its card (one of the four sanctioned terracotta uses — `Badge.State.New` is a derived use of the verified-badge pattern, justified because it is a state marker on a personal event the system is bringing to the user's attention, not a decorative accent).
  - Each of the three action buttons is a full-width `Button.Secondary` with a leading icon glyph (✓ / ✎ / ✕ in a neutral circular frame). On hover in dark mode, the icon frame tints to terracotta (`rgba(255,106,71,0.12)`); the button fill stays `color.surface.paper`. The buttons are not primaries — the prompt is a forced choice, not a marketing CTA, and a row of three terracotta buttons would feel alarmist.
- **Live region (a11y):** When the conflict sheet/modal opens, focus moves to the header and the live region announces: "Schedule conflict. Three choices." (`aria-live="assertive"`.) Each action button has a full `aria-label` describing both the action and its consequence (e.g., "Keep both events. The conflict indicator remains on both.").
- **Persistence:** Once a choice is recorded for a conflict pair, the system never re-prompts. The `ConflictResolution` value object lives with the user-event pair. The `Indicator.Conflict` on each Pulse Card persists permanently after "Keep both" as a calm permanent reminder (per PRD §3 Glossary — *Conflict Indicator* entry).
- **Edge case:** If the user backgrounds the prompt and returns later, the prompt is still open. There is no timeout that auto-dismisses the conflict.
- **Z-index:** `Sheet.ConflictResolution` sits above the bottom-tab nav (mobile) and the sidebar nav (desktop) — it is the single overlay level on top of page content. The bottom-tab nav is always below the sheet so the user cannot tap-navigate away from a forced choice; the sidebar nav (desktop) is also below the modal backdrop. The modal/sheet backdrop itself uses `color.surface.paper` at 70% opacity (dark) with `backdrop-filter: blur(8px)` (per `component.surface.modal` in DESIGN.md).
- **Pulse Card sync after resolution:** On any of the three actions, the system invalidates the Pulse Card cache for both events in the pair. On the next Pulse Digest render (typically the user's return to `/` via the sidebar / bottom-tab nav), the cards reflect the new state: "Keep both" keeps `Indicator.Conflict` on both cards; "Skip public" removes `Indicator.Conflict` from the public card and removes the public card from the digest on the next refresh; "Edit the new one" re-runs conflict detection on save. Timeline event-blocks sync on the next Timeline render — no manual refresh required.

### `Surface.{RouteName}`
Generic behavior for all routes:
- **Default:** Renders content. Animated card entrance uses `motion.fadeIn` (240ms) — disabled under `prefers-reduced-motion`.
- **Empty:** Empty-state copy from §6 Empty Patterns. No CTA when none is appropriate.
- **Loading:** Skeleton: 3 paper rectangles (`color.surface.paper`) fading 1px toward `color.ink.faint` at 60% opacity, then back. No spinners.
- **Error:** "Couldn't reach {surface}. Try again." with a single retry button. No stack traces. Error copies to status page on SEV-2+ events.

### `Surface.Timeline` (Amendment A-8 — MVP)
The Unified Timeline surface at `/timeline`. Week view combining Personal Events (warm tone) and Public Events (cool tone) on one grid. Read-only at MVP — no inline edits, no drag-to-reschedule.

- **Default (desktop `md+`):** 7-column week grid, Mon–Sun, each column a stack of event-blocks time-ordered. Header row shows day-of-week + date number in `Text.Meta`. Today is highlighted via `Indicator.Today` (the sanctioned terracotta dot with glow). Week navigator above the grid: `←` / `Today` / `→` in `Text.Meta`.
- **Default (mobile `sm`):** Single-column day view, one day visible at a time. Day navigator: `← Sep 7 →` centered, "Today" pill in `Text.Meta`. Horizontal swipe advances/retreats the day.
- **Personal vs Public event rendering:** Each event-block carries a 2px left-edge category stripe (`color.warm.personal` for personal, `color.cool.public` for public) AND a visible text label in the top-right corner ("Personal" / "Public event" in `Text.Meta`). Color is never the sole carrier of meaning. (Locked rule from DESIGN.md §Color usage rules and §Stripe color rule.)
- **Conflict indicator:** When a saved public event overlaps a saved personal event by >15 minutes, both events render `Indicator.Conflict` (the 6 px filled amber circle, `aria-label="Schedule conflict"`). Tapping either indicator opens a Detail Screen header panel that surfaces the FR-33 three-action pattern. For cross-midnight overlaps (a personal event runs past midnight into the next day), the `Indicator.Conflict` fires on the day-cell whose interval contains the overlap, evaluated per-day boundary per addendum FR-33 — both day-cells of a multi-day personal event show the indicator in the week grid, not just one.
- **Tap an event block:** Routes to `/events/:id`. Read-only from Timeline — no edit affordance in the block.
- **Empty day:** Centered "Quiet day." in `Text.Meta` muted. No CTA, no upsell, no carousel.
- **Empty week:** "Your week is quiet. Pulse Digest is the place to discover." in `Text.Display.sm` headline, with a single `Text.Meta` "Open Pulse Digest" link below.
- **Hover (desktop):** `color.surface.subtle` fill swap on the event-block. The tap target stays the entire block; the affordance is communicated by the fill swap, not a `▸` chevron (the timeline is denser than the digest).
- **Focus (keyboard):** Visible 2px focus ring in `color.accent.terracotta` at AA contrast. `aria-label` exposes event name + time + "Personal" / "Public event" label.
- **Reduced motion:** All entrance animations collapse to instant render. No skeleton pulse on load.
- **Read-only at MVP (FR-32 deferral):** Edits happen on Detail Screen or in the Personal Event modal — never from Timeline. Drag-to-reschedule ships in Phase 3.

### `Component.BottomTab` (mobile `sm` — Amendment A-8)
Mobile bottom navigation. Replaces any topbar nav. Five slots: **Digest / Timeline / Add / Conflicts / Settings**.

- **Layout:** `position: fixed; bottom: 0; left: 0; right: 0;` height 56px + `env(safe-area-inset-bottom)`. Background `color.surface.elevated`. 1px `color.border.subtle` top edge. Five equal-width slots (20% each).
- **Resting slot:** Icon (16×16 stroke-only SVG, never filled chromatic) + label in `color.ink.muted` (`Text.Meta`).
- **Active slot:** Ink-inverted background on the slot only (`color.ink.primary` fill + `color.ink.inverse` icon + `color.ink.inverse` label) per the locked `Control.Segmented` pattern in DESIGN.md §Components. **Never** a full-bar terracotta fill — terracotta on a small-control toggle burns the accent on a control used many times per day.
- **Active indicator:** A 2px `color.accent.terracotta` underline bar above the active slot, mirroring the desktop topnav active pattern (`pulse-digest-desktop.html` L75–76). The only chromatic use in the bottom-tab.
- **Tap:** Routes to the destination. Long-press is disabled.
- **Add slot behavior:** The Add slot opens the Personal Event creation flow — `Sheet.PersonalEventCreate` (mobile, bottom sheet; desktop, modal). Tap does not route to a `/events/new` page; it opens the creation surface in place. The creation surface is `Sheet.PersonalEventCreate`, the same component reached from Pulse Digest long-press on an empty day. The Add slot's icon is a `+` glyph (16×16 stroke-only SVG). The Add slot is **always visually present** but does not carry the terracotta fill — primary fill is reserved for actions inside a decision moment, not for navigation (terracotta on a tap-anytime nav control would burn the accent). The Add slot uses the same `ink-inverted active state` (white fill on the slot only, with the 2 px terracotta underline above the active slot) as the other slots — never solid terracotta fill.
- **Z-index:** Above page content, below modals/sheets (the `Sheet.ConflictResolution` and `Sheet.PersonalEventCreate` overlays sit above the bottom-tab).
- **Reduced motion:** No slide-in on mount.

### `Component.Sidenav.App` (desktop `md+` — Amendment A-8)
Desktop left-rail navigation. Replaces any topbar nav on desktop. Same five routes as `Component.BottomTab`.

- **Layout:** Sticky left `<aside>`. Width 220px on `md`, 240px on `lg+`. Background `color.surface.paper` (same as canvas — the sidenav is a layout container, not a visual element). Inset from page edge: `spacing.6` (24px) on top and sides.
- **Brand mark:** At the top of the sidenav — 28×28 logo + "EventPulse24" wordmark in `Text.Body` `color.ink.primary`. Below the brand: 1px `color.border.subtle` divider.
- **Route items:** Five links (Digest / Timeline / Add / Conflicts / Settings) in `Text.Body` `color.ink.secondary`. Resting state on the page background. Active item: `color.ink.primary` label on a `color.surface.subtle` pill background with 1px `color.border.subtle` stroke. The active pill mirrors the `Control.Segmented` ink-inversion pattern in miniature — no terracotta fill on the active route.
- **Keyboard:** `Tab` cycles through sidenav links after the topbar (topbar comes first in tab order) and before page content. `g d` / `g t` / `g c` / `g a` / `g s` shortcuts (already in §6) route directly.
- **Topbar interaction:** The topbar still carries only the brand mark + (optionally) the tagline. The sidenav is the nav, the topbar is the identity zone (topbar-quiet rule, ASSUM-11). No affordance duplication.
- **Global reset prerequisite:** The sidenav renders five `<a>` route items plus an `<a>` `account-row` in the footer. The page's global CSS must include `a { color: inherit; text-decoration: none; }` (or the host CSS reset must already kill link underlines), otherwise the browser default renders visible underlines under every sidenav label and the Account row. This is a silent contract: mockups that previously had no nav anchors in the topbar zone (e.g., the empty-state and personal-event-edit files) often lack this reset until the sidenav is applied. When applying the shell to any new mockup, audit for this reset first; if missing, add it alongside `button` and `input` resets. Source incident: 2026-09-06 migration of `pulse-digest-empty-state-desktop.html` and `personal-event-edit-desktop.html` shipped the shell without the reset; user reported underlines on all five nav items + the account row. Patched both files.

### `Component.Sidenav.Footer` (desktop `md+` — Amendment A-8)
Optional footer block pinned to the bottom of the 240px sidenav rail. Carries two affordances that do NOT fit the route list (Search and Account) but also do NOT belong in the topbar (topbar-quiet rule, ASSUM-11). The nav-item list stays the 5 routes from `Component.Sidenav.App`; the footer is additive.

- **Layout:** Full-width inner column, 1px `color.border.subtle` top edge (visually echoes the divider under the brand mark). `margin-top: auto` on the wrapper so it sits flush at the bottom of the 100vh rail regardless of how many nav-items are above it. Vertical gap 4px between the two children.
- **Search button (`footer-btn`):** 16×16 stroke-only magnifier SVG (icon-only, never filled chromatic) + "Search" label in `Text.Body` `color.ink.secondary`. Resting state on the canvas. Hover: `color.surface.subtle` fill swap, label lifts to `color.ink.primary`. Active/focus: 2px `color.accent.terracotta` focus ring at AA contrast. The button is a placeholder for an inline search overlay (PRD L447 — search is a deferred surface for archived event retrieval); route name not yet locked.
- **Account row (`account-row`):** 28×28 circular avatar with the warm-personal → cool-public gradient (existing token usage, no new color) + two-line label (user name in `Text.Body`, "Account" subtitle in `Text.Meta` `color.ink.muted`). Hover: `color.surface.subtle` fill swap, label lifts to `color.ink.primary`. Routes to `/settings` (account has no separate profile route at MVP per PRD §4.1 "Detailed profile completion: out of scope").
- **Keyboard:** `Tab` continues from the last nav-item into Search, then into the Account row, in that order. Both are reachable after the nav-item list, before any page content.
- **No notification badges.** Per DESIGN.md Brand & Style anti-patterns: no unread counters, no red dots, no streak popups. If Search or Account ever needs an unread state in a future iteration, the answer is inline text ("1 saved this week") in `Text.Meta`, not a badge.
- **Reduced motion:** No entrance animation. Appears with the page.
- **Token alignment:** Reuses `color.surface.subtle`, `color.ink.secondary`, `color.ink.primary`, `color.ink.muted`, `color.border.subtle`, `color.accent.terracotta` (focus ring only) — all existing DESIGN.md tokens. No new hex values, no new CSS variables.
- **When to omit:** Empty/skeleton/loading variants of the sidenav should render the footer in its resting state, not omit it. The footer is structural, not situational.

---

## 5. State Patterns

Global state decisions. Each pattern is invoked wherever the relevant state is encountered.

### Empty Patterns

**Empty Pulse Digest (`/`)** — the cardinal empty state:
- Copy: "Nothing on the pulse today. The calendar is yours."
- Visual: A single `Card.PulseDigest` variant (no second card). Card body shows the headline in `Text.Display.sm`. Below the card: a single line in `Text.Meta` reading "No qualifying events in {city}."
- **No CTA. No carousel. No "Explore trending events" upsell. No upsell at all.**
- A small "Suggest an event" link in `Text.Meta` ink color, low visual weight — present, not prominent. Opens a `/suggest` form (PRD FR-8).
- Reasoning: A user opening Pulse to nothing should feel the absence of the product's noise, not be marketed at. The empty state is the product's strongest voice.

**Empty saved collection:** "Nothing saved yet. Tap a card to save it." Single primary CTA pulses to the home.

**Empty Preview (SEO referrer) — `/preview`:** When the preview list is empty AND the document referrer is a search engine (e.g. Google, Bing, DuckDuckGo), render a single subtle `Text.Meta` "Suggest an event" link below the empty copy. The link opens `/suggest?city={city}` with the city query parameter pre-filled. For all other referrers (direct, social, internal), no link is shown — the empty state is the message. (Rationale: SEO cold-start is the unlock (§1 Foundation); a brand-new visitor from Google "events near me {city}" who hits the empty state must have a path to express interest without breaking the No-CTA Discipline for the rest of the audience.)

**Empty onboarding interests (step 2 skipped):** "We'll figure this out from your calendar." Single Skip button.

**Empty Timeline day (Amendment A-8 — MVP):** "Quiet day." No card, no CTA. (PRD §14 wireframe Screen 3.)

**Empty Timeline week (Amendment A-8 — MVP):** "Your week is quiet. Pulse Digest is the place to discover." A single `Text.Meta` "Open Pulse Digest" link below the headline routes to `/`. No carousel, no upsell.

**Empty `/conflicts` (Amendment A-8 — MVP):** "No overlaps. Conflicts appear here as you save events." A single `Text.Meta` "What counts as a conflict?" inline help link below — opens a single help article, not a modal. (No CTAs, no upsell.)

**Empty Search (Phase 3):** "No matches." No suggestions, no "Did you mean."

### Loading Patterns

**Pulse Digest skeleton:** 3 paper rectangles rendered in `color.surface.paper`, fading 1px toward `color.ink.faint` at 60% opacity, then back. Pulse period: 1800ms. No text inside the skeletons.

**Detail Screen skeleton:** One full-width header block + one meta row + 3 chip skeletons. Same fade animation.

**Settings list skeletons:** N rows (where N matches expected content length), each a 40px-tall `color.surface.paper` rectangle fading identically.

**Timeline skeletons (Amendment A-8):** Week-grid skeletons — 7 columns desktop (each column a stack of 3–5 `color.surface.elevated` rectangles fading identically, 40px tall each) or 1 column mobile (single stack). No day labels in the skeleton frame. Same 1800ms pulse period as other skeletons.

**`/conflicts` skeletons (Amendment A-8):** Two section skeletons (Active / Resolved) with row skeletons inside each, identical fade pattern. No spinners.

**No spinners, anywhere.** PRD §13.1 and §13.2: "No urgency badges." A spinner is a visual urgency badge.

**No loading states for instant local actions** (toggling a chip, opening a sheet, dismissing a card). Local save feedback uses inline 1-line "Saved." for 800ms.

### Error Patterns

**Generic error:** "Couldn't reach Pulse. Try again." Single retry button. No stack trace. No emoji. The retry button uses `Button.Primary` (filled, `color.accent.terracotta` background, `color.surface.paper` text). On second consecutive failure, the retry button label changes to "Refresh page."

**Detail Screen load failure:** "Couldn't load this event. Back to Pulse Digest." Single primary action navigates home.

**Calendar OAuth failure (onboarding step 1):** "Connection failed. Skip for now?" Two buttons: "Skip" (secondary, opens step 2) and "Try again" (primary, re-triggers OAuth).

**Reminder save failure:** Inline below the chip row, 1 line: "Couldn't save. We'll try again on your next change." No modal, no toast.

**Timeline load failure (Amendment A-8):** "Couldn't reach Timeline. Try again." Single retry button (terracotta-filled `Button.Primary`). The bottom-tab (mobile) and sidebar (desktop) nav remain functional so the user can escape.

**`/conflicts` load failure (Amendment A-8):** "Couldn't analyze conflicts. Try again." Single retry button. The conflict indicator on Pulse Cards remains accurate (it's a separate read path) so the user is not blocked from seeing conflicts elsewhere.

**Status page integration (PRD §10.5):** SEV-1 errors propagate to `status.eventpulse24.com` (or equivalent) within 30 minutes. The product surfaces a calm inline banner on relevant surfaces when a known incident affects the user.

### Conflict Patterns (MVP via FR-58 + Amendment A-8)

The three-action pattern (PRD FR-33). See `Sheet.ConflictResolution` in §4. The sheet:
- **Header:** "These overlap."
- **Body:** Two event names + times in `Text.Body`.
- **Three actions:** "Move {personal event name} earlier" / "Skip {public event name}" / "Keep both — I'll manage"

Once "Keep both" is chosen for a pair, the system records the decision and never re-prompts.

**Indicator persistence (post-resolution).** "Keep both" leaves the `Indicator.Conflict` on both Pulse Cards and Timeline event-blocks permanently — a calm permanent reminder (per PRD §3 Glossary). "Skip public" or "Move personal" removes the indicator from both events on the next render; the pair moves from `/conflicts` Active to Resolved; Pulse Card cache invalidates on return navigation.

**Cross-midnight conflicts.** When a personal event runs past midnight into the next day (e.g., 11:00 pm Mon → 2:00 am Tue) and a saved public event overlaps any portion of the personal event's interval, the conflict fires. The personal event's Timeline block renders on both day-cells it spans (with the conflict dot on the day-cell whose overlap crosses midnight, evaluated per-day boundary per addendum FR-33). The `/conflicts` pair row shows the full personal event span ("11:00 PM Mon → 2:00 AM Tue") plus the public event time.

**Multi-day events.** A multi-day personal event (e.g., a 3-day conference) renders `Indicator.Conflict` on every day-cell it spans when any portion of that cell's interval overlaps a public event. The Pulse Card always shows the conflict once (top-right) regardless of how many days the personal event spans.

**Three+ mutually-overlapping events.** The first launch of `Sheet.ConflictResolution` always pairs the personal event with the closest-overlapping public event (largest overlap interval). If a third saved event (Personal or Public) overlaps the same personal event, it is listed at the bottom of the sheet in `Text.Meta`: "Also overlaps with: {event name}, {time}." No second sheet fires for the third event until the first pair is resolved; the third event's conflict indicator still renders on Pulse Cards and Timeline event-blocks.

**Recurring personal events.** MVP scope: conflict detection runs against expanded instances within the visible week (Mon–Sun). If the recurrence is not RRULE-expanded (per MVP), the conflict indicator fires only for the single instance the user created — future recurring instances are out of scope at MVP.

**State change (PRD FR-53/54/55 cancel / postpone / move).** When a source event is cancelled, postponed, or moved, the system recomputes the conflict set on the next Pulse Card render. A cancelled partner event clears its `Indicator.Conflict` immediately. A postponed event keeps its `Indicator.Conflict` if its new interval still overlaps; the indicator clears if it does not.

**Backgrounded conflict sheet.** If the user backgrounds `Sheet.ConflictResolution` (browser tab change, app switch on mobile) and returns, the sheet is still open. There is no auto-timeout, no dismiss-on-background. The system waits calmly for the user to choose.

**Free-tier parity.** FR-33 fires regardless of tier for any saved public event overlapping a saved personal event. The free-tier save cap does not gate conflict detection.

**Empty state.** For a brand-new user with zero saved events, `/conflicts` renders "No events saved yet. Open Pulse Digest." with a single `Text.Meta` link to `/`. For a user with events but no overlaps, "No overlaps. Conflicts appear here as you save events." (matches §3 microcopy contract). For a user with resolved-but-no-active pairs, the Resolved section renders; Active is absent.

### Offline Patterns

**Cached Pulse Digest (read-only when offline):**
- The system caches the most recent Pulse Digest on device (service worker, 24h TTL).
- When offline, the user sees the cached digest with an inline banner at the top: "Offline — showing last sync." The banner uses `color.surface.paper.darker` background and `Text.Meta` copy.

**Queued actions contract (the offline write path):**
- **Storage.** Queued actions are stored in IndexedDB keyed by `userId + eventId + actionType` (one entry per unique action; idempotent on replay). Each entry carries `{userId, eventId, actionType, queuedAt, eventEndTime}`. Storage is per-device; no cross-device queue.
- **Capacity.** Queue cap: **50 actions** per device. On cap, the oldest non-conflicting action is evicted; a one-time `Text.Meta` notice appears: "Some offline actions couldn't sync." (The notice appears once per eviction event, not per action evicted.)
- **Lifecycle on logout / cookie clear.** Queued actions are **purged** on user logout and on cookie / storage clear. They were never sent to the server; the user has not lost data, only un-submitted intent. No copy is shown on purge (no "your offline actions were discarded" toast).
- **Lifecycle on replay.** When the device reconnects, queued actions are replayed serially in `queuedAt` order. For each replay, the server validates the action against the current event state:
  - If the action's `eventEndTime < now()` (event has passed since queue), the action is **silently dropped**. No error, no toast — the event has no meaning to save/dismiss past its end.
  - If the action is a duplicate of an already-synced action (server already received it), it is silently dropped.
  - If the event has been deleted by its source, the action is silently dropped; no error to the user.
  - If the event has been rescheduled past its original `eventEndTime`, the action is replayed against the new event instance.
- **Replay notification.** On successful replay of ≥1 action, a single batched inline notice appears at the top of the next digest render: "{N} actions synced." The notice is dismissable by the next user interaction (tap, scroll, keyboard). It does not appear if zero actions were replayed.
- **Counter display during offline.** While offline, the user sees a quiet inline indicator: "1 action queued" (or "N actions queued" for N>1). The counter updates as actions are queued and clears on replay.

**No internet + no cache (cold offline open):**
- Empty state variant: "You're offline. Pulse will be here when you reconnect."
- No CTAs, no animations.

### No-CTA Discipline

The product does not push the user. Every CTA exists to fulfill a stated user goal; there are no nudges, no "while you're here" suggestions, no "you might also like."

---

## 6. Interaction Primitives

Touch, keyboard, and accessibility primitives. The product is keyboard-first on desktop, touch-first on mobile.

### Keyboard

All primary actions have a keyboard shortcut, shown in a `?` help menu (visible at the bottom-right of every surface on `md+` viewports; tap to expand on `sm`).

| Shortcut | Action | Surface |
|---|---|---|
| `?` | Open keyboard shortcuts menu | Global |
| `j` / `k` | Move to next / previous card | `/` (Pulse Digest) |
| `Enter` | Open Detail on focused card | `/` |
| `s` | Save focused card | `/`, `/events/:id` |
| `d` | Dismiss focused card | `/`, `/events/:id` |
| `l` | Less like this | `/`, `/events/:id` |
| `r` | Open Reminder Picker | `/events/:id` |
| `1` `2` `3` `4` | Toggle reminder slot 5d/2d/1d/1hr | `/events/:id` |
| `Esc` | Close sheet / cancel edit | Any |
| `g d` | Go to Digest | Global |
| `g s` | Go to Settings | Global |
| `g t` | Go to Timeline (Amendment A-8 — MVP) | Global |
| `g c` | Go to Conflicts (Amendment A-8 — MVP) | Global |
| `g a` | Open Add Personal Event sheet (Amendment A-8 — MVP) | Global |
| `n` | Create new personal event | Global |
| `/` | Focus search (Phase 3+) | Global |

**Cards are focusable.** Arrow keys (and `j`/`k`) move between cards in the digest. Focus is visible at AA contrast (2px ring, `color.accent.terracotta`).

**Reminder picker keyboard support:** Reminder chips are focusable. `Tab` cycles through chips; `Enter` toggles; arrow keys move within the chip group; `Esc` closes the picker.

**Conflict Resolution keyboard support (MVP, FR-33 / Amendment A-8):** The three actions are focusable in order (`Move / Skip / Keep both`). `Tab` cycles; `Enter` confirms the focused action; `Esc` cancels (treated as `Keep both`).

### Touch

- **Tap** — primary action.
- **Long-press** — opens quick-actions sheet on a Pulse Card (save, dismiss, less like this). Long-press is reserved for system context menus on iOS (text selection) on text content; on cards it's ours.
- **Swipe-left** — dismiss (records "less like this").
- **Swipe-right** — save.
- **Swipe-down** — refresh on the Pulse Digest only.
- **Pull-to-refresh** is disabled on all surfaces except `/`. PRD: no infinite scroll, no carousel-driven browsing.

### Mouse

- **Click** — primary action.
- **Hover** — reveals secondary affordances (Confidence tooltip, Source Badge tooltip). Hover affordances are duplicated as tap-on-mobile. No hover-only affordances on `sm` viewports.
- **Drag** — supported on Reminder Slot chips only.

### Banned Primitives

These are explicitly out of scope in MVP:
- Infinite scroll (pagination only).
- Drag-to-reorder lists (deferred to Phase 2 for Saved Collections).
- Hover-only affordances on `sm` viewports.
- Modal stacks > 1 level deep.
- Full-screen takeover animations.
- Carousels (Pulse Digest is a stack, not a carousel).
- Bottom-sheet on a modal (one level of overlay only).

### Reduced Motion

`prefers-reduced-motion: reduce` disables:
- Card-fade entrance animation.
- Card swipe animations.
- Skeleton pulse animation (skeletons render statically).
- Tooltip fade.

Text and layout remain unchanged. The product does not become a wall of static — it just doesn't animate.

---

## 7. Accessibility Floor

WCAG 2.2 AA across the responsive web surface. PRD §11.5 sets the floor; this spine ratifies the behaviors.

### Color Contrast

- **Body text:** ≥4.5:1 against `color.surface.paper`.
- **Large text (≥18pt regular, ≥14pt bold):** ≥3:1 against `color.surface.paper`.
- **`color.accent.terracotta` as text on `color.surface.paper`:** verified ≥4.5:1.
- **`color.accent.terracotta` as UI element / border:** verified ≥3:1.
- **`color.warm.personal` and `color.cool.public` (PRD §13.1):** verified ≥3:1 against `color.surface.paper`; *not* the sole carrier of meaning (see "Non-color signals" below).

### Touch & Click Targets

- All interactive elements ≥44×44 px CSS.
- Card-level targets wrap the entire card; subordinate buttons inside cards are themselves ≥44×44.
- Spacing between adjacent targets ≥8 px to prevent mis-tap.

### Focus

- Visible 2px focus ring on every focusable element.
- Ring color: `color.accent.terracotta`.
- Ring offset: 2 px from the element edge.
- Focus order matches reading order on every surface.
- `Esc` closes the topmost modal/popover; `Tab` from inside a closed modal returns focus to the trigger.

### Non-Color Signals

Color is never the sole carrier of meaning:
- Conflict indicator (PRD FR-58): filled circle in `color.warn.amber` *and* `aria-label="Schedule conflict"`. Shape distinct from Source Badge and Confidence Pulse dots.
- Source Badge: visible inline text label, not icon-only.
- Pulse Card warm/cool tone (Personal vs Public): accompanied by text label "Personal" / "Public event" in `Text.Meta`.
- Why-this Tags: each tag is a visible keyword, not a colored dot.

### Live Regions

- **Pulse Digest ready:** When the 3 cards finish loading and render, a live region announces "Pulse Digest ready, 3 events for today." `aria-live="polite"`.
- **Save / Dismiss confirmation:** Announced via live region: "Saved. {event name}" / "Dismissed. {event name}."
- **Conflict Resolution (MVP, FR-33 / Amendment A-8):** When the conflict sheet opens, focus moves to the header ("These overlap.") and the live region announces the conflict summary.

### Screen-Reader Specifics

- **Confidence Pulse:** `aria-label="4 of 5"` (not just "4 dots").
- **Source Badge:** Full label announced, e.g., "Official site. Verified venue."
- **Why-this Tags:** Announced as comma-separated text: "nearby, tonight, music."
- **Adaptive digest expand:** When the digest expands from 3 → 5 cards, announced: "Pulse Digest has 5 events today. Showing 3."
- **Visible helper text is in the DOM, not in pseudo-elements.** Helper text that a sighted user reads (e.g., the line under a "Save" button explaining what happens next) is rendered as a real text element in the DOM, not injected via CSS `::before` / `::after`. Screen readers do not announce `::after` content by default; visible-to-sighted, invisible-to-screen-reader is an accessibility regression. If the helper is decoration-only, hide it with `aria-hidden="true"`; if it carries information, render it in the DOM and pair it with the trigger via `aria-describedby`.

### Motion

- `prefers-reduced-motion: reduce` disables non-essential animation (see §6 Reduced Motion).
- No auto-playing video or audio at MVP.
- All transitions ≤500ms; default 240ms.

### Pre-Launch Audit Gate

Per PRD §11.5, an accessibility audit report is required before MVP launch:
- NVDA + Firefox (Windows): full Pulse Digest traversal.
- VoiceOver + Safari (macOS, iOS): mobile-web Pulse Digest.
- TalkBack + Chrome (Android): mobile-web Pulse Digest.
- Switch Control / Switch Access: save and dismiss a card without fine-motor gesture.
- Lighthouse accessibility score ≥95 on all primary pages.
- axe-core CI gate: zero serious/critical violations.

---

## 8. Key Flows

Named-protagonist journeys. Each flow names a protagonist, an entry state, a path, a climax, and a failure mode.

### Flow 1 — Maya's morning (PRD UJ-1, the moment-of-truth flow)

**Persona:** Maya, 32, senior product designer in Brooklyn. Has connected Google Calendar during yesterday's onboarding.

**Entry state:** 7:42 am. Phone in hand. Maya opens Pulse manually (the morning check-in slot she chose during onboarding; see _Assumptions_, ASSUM-3). The manual-open path renders the same Pulse Digest as the Pulse Ping tap path.

**Path:**
1. Maya taps the Pulse Ping notification (or opens `eventpulse24.com` on her phone).
2. Pulse Digest loads. Three cards render in `Card.PulseDigest`:
   - (a) "Sam's birthday dinner — 7pm tonight" with Why-this Tags `close-friend, tonight, restaurant`. Confidence Pulse 4 of 5. Source Badge: User-imported (calendar).
   - (b) "Free tech meetup Thu, 2 blocks from work" with `nearby, thursday, free`. Confidence 3 of 5. Source: Community.
   - (c) "Rooftop jazz in your neighborhood Sat" with `nearby, weekend, novel`. Confidence 3 of 5. Source: Official.
3. Maya reads the headline "Today, three things matter." (above the cards).
4. She reads card (a)'s Why-this Tags: `close-friend, tonight, restaurant`. The tags confirm her mental model — yes, this is Sam's thing.
5. She taps card (a) → Detail Screen at `/events/:sam-birthday`. Sees the full Why-this breakdown: source badge, confidence pulse, three Why-this Tags, similar events she's attended, and a one-line `Text.Meta` neighbor-count row when ≥5 qualifying neighbors exist (per §12 Neighbor Count Privacy — below threshold the line is silently absent, not stated as zero).
6. She taps "Remind me" → Reminder Picker opens. Default 1d + 1hr is pre-selected. She taps the 2d chip. Saves.
7. She closes the app.

**Climax:** "Total time: 28 seconds." She knows what matters this week. She set one reminder. Nothing else pushed itself. (PRD UJ-1 climax.)

**Failure modes:**
- Notification delayed >5 minutes: logged but invisible to Maya. PRD §10.4 SLAs: no "delayed" status to user.
- Card (a) removed between Pulse composition and Maya's tap (state change, PRD FR-53): Detail Screen shows "This event is no longer available." with a back link. Maya returns to digest.
- Maya swipes card (b) down (dismiss / less like this): card animates off; live region announces "Dismissed." The system records the dismissal for the Preference Graph (PRD FR-25). The 3-consecutive-similar-dismissal prompt does not fire on a single dismissal.

### Flow 2 — First-time onboarding (PRD UJ-3)

**Persona:** Pary, new visitor. Has never used EventPulse24.

**Entry state:** Lands on `eventpulse24.com/events/near-me/brooklyn` from a Google search for "events near me Brooklyn." Sees the SEO landing page (PRD FR-27).

**Path:**
1. SEO page renders 3 Pulse Cards for Brooklyn today, plus the headline "Events near Brooklyn today." Each card has Why-this Tags, a Confidence Pulse, and a Source Badge. The cards are crawlable, Schema.org JSON-LD embedded.
2. Pary taps "See today's full Pulse" → routes to `/preview`. Pulse Preview shows 3 cards in `Card.PulseDigest`, each with Why-this Tags, a Confidence Pulse, and a Source Badge. **Below the cards** (in its own decision moment, separated by `spacing.16`+ from the grid): a section with copy "Get Pulse like this in your inbox." and a single primary CTA "Sign up" (terracotta-filled). The section is wrapped in `<section class="signup">` and is the second `Button.primary` on the surface (the topbar "Sign up" is the first, in a separate visual zone).
3. Pary taps "Sign up" → routes to `/onboarding` step 1.
4. Step 1: "Connect a calendar (optional)." Three equal-weight provider buttons render in a vertical stack: **Google Calendar**, **Apple Calendar (CalDAV)**, **Outlook Calendar**. Each provider button is `component.button.provider` per `DESIGN.md §Components` — identical visual weight, no primary elevation between providers. Below the stack: a single `Button.Secondary` "Skip for now" + a `Button.Primary` "Continue →" in the footer. The Skip is at equal visual weight to a Continue affordance — onboarding is genuinely skippable either per-provider (don't tap a provider) or per-step (tap Skip). All three providers ship at MVP per PRD FR-3 / FR-50; provider parity is enforced by the visual system.
5. Pary taps Connect Google → OAuth round-trip → returns to step 2. (Alternative: Pary taps Apple Calendar → CalDAV credentials form → returns to step 2. Alternative: Pary taps Outlook → Microsoft Graph OAuth round-trip → returns to step 2. All three paths are first-class.)
6. Step 2: "Pick a few interests (optional)." A grid of ~12 chips (Music, Tech, Food, Sports, Family, Arts, etc.). "Skip" and "Pick 3" buttons. Pary picks 3.
7. Step 3: "When should we send your daily Pulse?" A time picker (default 8:00 am). Timezone pre-filled from browser. "Done" button.
8. Pary lands on `/` (Pulse Digest). The first Pulse Digest is rendered from the cached composition (PRD FR-1 consequence) — 3 cards for Brooklyn, calibrated to her 3 interests.

**Climax:** "First relevant event in 15 seconds." (PRD FR-1 + Design Thinking wireframe Screen 1 target.)

**Failure modes:**
- Geo-IP wrong (shows NYC instead of Brooklyn): a calm banner at the top of Pulse Preview reads "Showing events near NYC. Use a different city?" with "Change" / "Use this" / "Don't use my location" buttons. (PRD FR-2 consequence.)
- Calendar connect fails (any provider): "Connection failed. Skip for now?" Pary skips; Pulse infers from her 3 interest chips and geo-IP. The handler is provider-agnostic (no "Google failed but Apple/Outlook are still options to try" branching on a single failure). Failed connect leaves no half-state — the provider button returns to its resting state and the user can retry or move on.
- Apple CalDAV credentials pasted incorrectly: a calm inline error reads "We couldn't reach your iCloud calendar. Double-check the app-specific password." Below the field, an inline help link "How do I get this password?" (opens a single help article, not a modal). The user can retry or skip without leaving the step.
- Pary abandons at step 2: resumed at step 2 within 7 days. (PRD FR-1 consequence.)

### Flow 3 — Conflict Resolution (MVP, PRD FR-58)

**Persona:** Maya. Friday afternoon. Creating "Anniversary dinner with Rahul — Fri 7:00 PM @ Lilia" as a new Personal Event. Already has a saved public event "Free tech meetup — Fri 6:30 PM @ Brooklyn Arts Council" within 30 minutes.

**Entry state:** Maya is in the Personal Event creation flow (`Sheet.PersonalEventCreate`). She's filled in name, date, time, location. She taps "Save to my Pulse."

**Path:**
1. The system detects the ±30-minute overlap with the saved "tech meetup" event. The `Sheet.ConflictResolution` modal opens immediately on top of the creation flow.
2. Modal header: "This overlaps with another event." Subhead: "You've already saved 'Free tech meetup — Designing for Calm'. Choose how to handle it."
3. The two affected events render as stacked card rows. The new event ("Anniversary dinner") is marked with a "NEW" terracotta pill above its card (sanctioned state-marker use). Both show the amber `Indicator.Conflict` filled circle on the top-right.
4. Three actions, top to bottom — secondary buttons (full-width, neutral), NOT primaries:
   - **Keep both — I'll manage** (with check icon) → both events saved. `ConflictResolution{value=keep_both}` is recorded. `Indicator.Conflict` remains on both Pulse Cards permanently.
   - **Edit the new one** (with pencil icon) → creation form re-opens with the conflicting time field focused and pre-highlighted. Maya shifts the dinner to 8:00 PM. Conflict detection re-runs. No conflict. Save completes.
   - **Delete the new one** (with X icon) → a confirmation step asks "Delete 'Anniversary dinner with Rahul'? This cannot be undone." On confirm, the event is removed; creation flow resets.
5. There is NO fourth action, NO close button, NO outside-click dismiss. Maya must choose one.

**Climax:** "Three actions, no anxiety, no way to look away." The calm contract: the system surfaces the issue and waits calmly for the user to resolve it before proceeding.

**Resolution:** Maya picks "Edit the new one," moves dinner to 8:30 PM, the conflict clears, her anniversary dinner saves cleanly, the tech meetup is untouched, and she's back in the digest at 7:55 PM ready to close the app.

**Failure modes:**
- Maya taps the conflict dot on an existing Pulse Card (not during creation): the same `Sheet.ConflictResolution` opens, this time scoped to a saved-confirmed pair. The "Edit the new one" action is relabeled "Edit one of these" and shows both as editable targets.
- More than 2 events overlap: pairwise prompt. The MVP caps the prompt at the first 2 overlapping events; remaining overlaps are listed at the bottom of the modal in a `Text.Meta` block ("Also overlaps with: …") without prompting for resolution on those pairs.
- User backgrounds the prompt and returns: the prompt is still open. There is no timeout.

### Flow 4 — Adaptive expansion (Phase 3+, but designed now)

**Persona:** Maya. Has been a user for 60 days. Has saved 12 events in the last 30 days. The system qualifies her for adaptive expansion (≥10 saves in 30d).

**Entry state:** Pulse Digest loads. 5 cards render.

**Path:**
1. Five cards visible in stack.
2. At the bottom of the digest, after card 5, an inline link: "Show all 5" (subtle, `Text.Meta`, `color.ink.primary` underlined). The link is **present-but-deemphasized**; the default render is all 5 cards, and the link is a redundant affordance for users who missed the count (see _Assumptions_, ASSUM-4).
3. No modal. No upsell. The 5 cards stay where they are; the link exists to confirm count.

**Climax:** "No modal. No upsell. Just more cards, inline." Visible card count grows up to 5 at MVP; 7 is the eventual upper bound and is tested in Phase 3 (see _Assumptions_, ASSUM-5).

**Failure modes:**
- Adaptive expansion violates the 3-card default for an engaged user: this is the explicit adaptive exception (PRD §4.5.1 reconcile, locked in this brief). The setting is opt-out, not opt-in (locked decision).
- User engagement drops below threshold (e.g., 10 saves/30d no longer holds): Pulse Digest returns to 3 cards. No announcement.

### Flow 5 — Maya's week planning (PRD UJ-2, Amendment A-8 — MVP)

**Persona:** Maya, 32, senior product designer in Brooklyn. Has connected Google Calendar. Friday evening, planning the week ahead.

**Entry state:** Maya taps the **Timeline** item in the bottom-tab (mobile) or left sidebar (desktop). She lands on `/timeline`, current week (Mon Sep 7 – Sun Sep 13). (Prior weeks — Thu Sep 10 yoga vs. tech meetup and Sat Sep 12 anniversary dinner vs. comedy show — were already resolved via the FR-33 three-action pattern; those resolved pairs live in the `/conflicts` Resolved list, not on this week's Timeline.)

**Path:**
1. The week grid renders with `motion.fadeIn` (240ms, disabled under reduced-motion). Today's column is highlighted via `Indicator.Today` (the terracotta dot with the sanctioned glow). The week navigator at the top reads "Sep 7 – Sep 13" with `←` / `Today` / `→` affordances in `Text.Meta`.
2. Maya scans the week. She sees:
   - **Monday:** Quiet day. (Empty cell — centered "Quiet day." in `Text.Meta` muted.)
   - **Tuesday:** Work standup 9:00 am (Personal, warm stripe) + saved "Designers coffee chat" 9:15 am (Public, cool stripe). Both carry `Indicator.Conflict` (amber dots, top-left of each block — see `Surface.Timeline` and `ASSUM-13`).
   - **Wednesday:** Quiet day.
   - **Thursday:** Yoga class 7:00 pm (Personal) — no conflict. (The Thu yoga vs. tech meetup overlap was resolved earlier — Maya moved yoga to 6:00 am — and the pair is now in `/conflicts` Resolved.)
   - **Friday:** Sam's birthday dinner 7:00 pm (Personal) + saved "Poetry reading" 7:15 pm (Public). Both carry `Indicator.Conflict`.
   - **Saturday:** Anniversary dinner with Rahul 8:30 pm (Personal) — no conflict. (The Sat anniversary vs. comedy show overlap was resolved by "Keep both — I'll manage" earlier and lives in `/conflicts` Resolved.)
   - **Sunday:** Free comedy show 4:00 pm (Public) — no conflict.
3. Maya notices the Tuesday conflict first. She taps the work standup block (Personal). Routes to `/events/:work-standup-tuesday`. From there she can shift the standup earlier in the day. The conflict indicator on the Tuesday column clears on the next Timeline render.
4. She returns to `/timeline` (back button). She now notices the Friday conflict (Sam's birthday dinner vs. Poetry reading). She taps the Poetry reading block. Routes to `/events/:poetry-reading`. She decides to skip the public event (one-tap dismiss from the Detail Screen's FR-33 three-action panel: "Skip this public event"). The conflict indicator clears on both Friday blocks.
5. She is done. The week is now conflict-free.

**Climax:** "Glanceable week in 6 seconds. No edits from Timeline — just see." Maya saw the whole week's shape, identified the two active conflicts, resolved them by jumping to Detail Screen, and was back on Timeline in under a minute. No modal opened, no carousel spun, no upsell shown.

**Failure modes:**
- Maya tries to drag a block to reschedule: nothing happens. Timeline is read-only at MVP. A subtle `Text.Meta` cursor hint ("Read-only — open event to edit") appears on hover (desktop) or long-press (mobile).
- Maya taps an empty day expecting to add an event: nothing happens. The "Add Personal Event" affordance lives in the bottom-tab (or sidebar), not on the Timeline grid.
- Maya is on the Friday conflict and the Detail Screen fails to load: `Sheet.ConflictResolution` is not opened automatically; the conflict indicator on the Friday blocks remains. Maya retries from Detail Screen or returns to Timeline. The indicator persists across retries — it is a calm permanent reminder, not a transient toast.

### Flow 6 — Conflict review (Amendment A-8 — MVP)

**Persona:** Maya, on Sunday afternoon. Curious about how many overlaps she has accumulated. She has been a Pulse user for several weeks and has resolved conflicts across multiple prior weeks (Thu Sep 10 yoga vs. tech meetup, Fri Sep 11 Sam's birthday dinner vs. poetry reading, Sat Sep 12 anniversary dinner vs. comedy show). This week she has 1 unresolved pair (Tue Sep 8 work standup vs. designers coffee chat).

**Entry state:** Maya taps the conflict indicator on her Pulse Digest `Indicator.Conflict` dot. A Detail Screen header panel opens with the FR-33 three actions + a new affordance: "See all overlaps." (`/conflicts` is also reachable directly from the bottom-tab Conflicts slot on mobile and the sidebar Conflicts link on desktop; the "See all overlaps" link is the route from a Pulse Card indicator.)

**Path:**
1. Maya taps "See all overlaps." Routes to `/conflicts`.
2. The page heading renders: "These days overlap." (Locked microcopy, §3.) Below, two sections:
   - **Active (1)** — one pair awaits a decision: Tue Sep 8, 9:00 am Work standup (Personal) ↔ 9:15 am Designers coffee chat (Public). Three actions render against the pair (Move earlier / Skip / Keep both).
   - **Resolved (3)** — collapsed list of the three pairs Maya resolved across the past two weeks. Each row shows the pair side-by-side (Personal + Public blocks), the resolution method (e.g., "Skipped public · Poetry reading · Fri Sep 11"), and a `Text.Meta` timestamp. (Mocks this state at `conflicts-desktop.html`.)
3. Maya scans the active pair, decides to keep the coffee chat and "Move standup earlier," and the action clears the conflict on the next render. The pair moves from Active to Resolved.
4. She taps the back button (or the topbar's brand mark) to return to Pulse Digest.

**Climax:** "Every conflict, one place, no anxiety." Maya reviews her conflict history in 15 seconds and resolves the open one in another 15 seconds. No modal opens, no upsell asks her to "prevent future conflicts with Pro," no streak badge shows up.

**Failure modes:**
- Maya has many conflicts (e.g., 12 active): the Active section renders a scrollable list (no pagination, no "show more" — the list is bounded to a reasonable count per week by design; conflicts beyond the visible window are grouped into "Older overlaps" with a `Text.Meta` week label).
- Maya tries to delete a resolved conflict: no edit affordance. Resolved pairs are immutable history. A subtle `Text.Meta` cursor hint on hover ("History — cannot be edited") explains.
- Maya is on `/conflicts` and a new conflict is detected (e.g., a saved public event moves to overlap her birthday dinner): the page does not auto-refresh. The next user interaction triggers a fetch. (Auto-refresh on `/conflicts` would be a passive pressure element — banned per §3 microcopy and §9 anti-patterns.)

---

## 9. Inspiration & Anti-patterns

### Sources We Borrow From

- **Linear** — keyboard-first discipline. `⌘K` is the command center (in our case `?`); `j`/`k` to move between cards; no drag for primary navigation; status-pill vocabulary. We borrow the *posture*, not the chrome.
- **Are.na** — restraint and editorial calm. Channels of curated content read like a slow magazine, not a feed. We borrow the posture of "a small set, presented without selling."
- **Headspace** — calmer moments. The brand is "a friend who knows you well and isn't trying to sell you." We borrow the visual restraint and the empty-state-as-feature instinct. PRD §13.1 cites Headspace as the aesthetic anchor for "Headspace of events."
- **Bandcamp** — editorial card design. Cards are dense with information but never noisy; the editorial posture makes the user feel like they're being shown, not sold to. We borrow the card composition and the absence of promotional badges.
- **Notion** — decision-friendly minimalism. The UI is a quiet workspace, not a sales surface. We borrow the minimalism and the "no shouting" voice. PRD §13.1.
- **Apple Calendar** — week-view restraint. PRD §13.1. We borrow the calm layout pattern for the Timeline (Amendment A-8 — MVP) and the absence of badges, urgency, or color-noise.
- **Day One / iA Writer** (cited from `experience-example-mobile.md` Quill spine) — the single daily framing and the no-toolbar discipline. We borrow the "one moment per day" calibration of Pulse Digest and the "compose without chrome" rhythm of personal event creation.

### Anti-patterns We Explicitly Avoid

These are the patterns we will *not* ship, ever. PRD §13.3 anchors the list; this spine ratifies the full set.

- **Notification badges.** No unread counts on the app icon. No "23 new events" badges on cards. PRD §5.1: No dark patterns.
- **Streak popups.** No "🔥 5-day streak!" toasts. The streak is internal at most (Pulse Streak, Phase 3 §11); it never yells at the user.
- **Social-proof counters.** No "12 of your neighbors are going." (Neighbor count exists per PRD FR-24, but only on Detail Screen with k-anonymity, and never as a CTA or pressure element.)
- **"People are viewing this" widgets.** Banned everywhere. Engagement theater.
- **Infinite scroll.** Pulse Digest is bounded (3, 5, or 7 cards max). Search results paginate.
- **FOMO carousels.** No "Trending now" hero carousels. No "Don't miss out!" rotation. PRD §5 Non-Goals: "Real-time trending carousels."
- **Dark-pattern nudges.** No urgency timers, no countdown badges, no "Only 2 left!" copy on event tickets (we don't sell tickets anyway, but the principle holds).
- **Hidden ranking algorithms.** Pulse Digest composition is explainable. The Why-this breakdown is visible to the user; ranking is not hidden.
- **Modal stacks.** No modals on modals. One overlay level only.
- **Emoji as CTAs.** Emoji are status indicators (Source Badge icons), never action prompts.
- **Exclamation points.** PRD §13.2: "No exclamation points. Calm products don't shout."
- **"Promoted" or "Sponsored" placements.** PRD §15.2: "No ads. No commissions. No data sales."
- **"🎉 You saved this!" celebration animations.** Saved is quiet: inline "Saved." for 800ms.
- **Empty-state upsell.** Empty Pulse Digest never asks the user to upgrade, browse trending, or take action. The empty state is the message.

### The Three Most Important Anti-patterns

If a future contributor can only remember three lines from this section, these are the three:

1. **No FOMO. No urgency. No "Don't miss out!" copy. Ever.** (PRD §5.1, §13.3.)
2. **No hidden ranking. Every recommendation shows its reasoning.** (PRD §5.1: Explainable AI.)
3. **3 cards max, with the adaptive exception.** The Pulse Digest is bounded on purpose. Don't propose "let users pick how many cards they see." (PRD §5.1, §6.1 Out of Scope, FR-5 Out of Scope.)

---

## 10. Responsive & Platform

### Responsive Breakpoints

| Breakpoint | Width | Behavior |
|---|---|---|
| `sm` | ≤767 px (default MVP target: 375 px) | Mobile. Bottom-tab navigation (Digest / Timeline / Add / Conflicts / Settings — see `Component.BottomTab`). Single-column digest. Single-column timeline (one day visible, swipe or `←` / `→` to advance days). Sheet-based overlays. Card stack vertical. |
| `md` | 768–1023 px | Tablet. Left sidebar nav (220 px, see `Component.Sidenav.App`). Two-column digest on landscape; single-column portrait. Timeline renders as a 7-day week grid. |
| `lg` | 1024–1179 px | Desktop. Sidebar visible (240 px). Two-column digest: today's pulse on the left, "this week" preview on the right. Timeline as 7-day week grid. |
| `xl` | ≥1180 px | Max canvas. Content constrained to 1180 px. Whitespace expands outward. No content reflow. |

**Desktop does not add features.** Desktop adds whitespace and (optionally) reveals hover affordances on `Badge.Source` and `Indicator.Confidence`. No new screens, no new actions, no new copy. PRD §13.1: "Whitespace over density."

**Mobile-first discipline.** Every screen is designed for 375 px first; the desktop view is a whitespace-expanded version of the mobile view, not a separate design.

### Platform

- **Web:** responsive web (PWA) is the only MVP surface.
- **Native mobile apps (iOS, Android):** Phase 2+. PRD §5 Non-Goals.
- **Browser notifications:** Web Notification API for Pulse Ping. PRD FR-10.
- **Web Share API:** for outbound shares (Pulse share-link, PRD FR-28).
- **Service worker:** for offline-cached Pulse Digest (24h TTL) and queued local actions (§5 Offline Patterns).
- **No push notifications to mobile** at MVP (email digest only, PRD FR-11; push in Phase 2 with native apps).
- **No iOS / Android conventions** beyond standard responsive web behavior — no bottom-sheet-from-bottom on desktop, no hamburger menu on mobile (bottom-tab navigation instead — see `Component.BottomTab` in §4; the nav includes Timeline and Conflicts as 3rd and 4th slots).

### Browser Support

- Latest 2 versions of Chrome, Edge, Firefox, Safari.
- iOS Safari 16+.
- Android Chrome (latest).
- No IE / legacy Edge.

### Performance Budgets (PRD §11.1)

- **Pulse Digest composition:** <500ms p95 (cached); <3s p95 (cold).
- **Page load:** <1.5s LCP on `/` and `/events/:id`, 3G-fast.
- **API response:** <300ms p95 for read-heavy endpoints.

Performance is a behavioral contract: a slow digest is a broken digest.

---

## 11. Pulse Streak & Year in Pulse (Phase 3)

Restoring from `reconcile-blue-ocean.md` §G6: the dropped CREATE factors "Pulse Streak" (calm gamification, retention without FOMO) and "Year in Pulse" (Spotify-Wrapped-style annual recap, brand love + viral moment). PRD FR-46 and FR-47.

### Pulse Streak (PRD FR-46, Year 2+)

**Behavior:** A gentle streak counter on the Pulse Digest home. The streak increments when the user opens the Pulse Digest on the same calendar day as their chosen Pulse Ping delivery time, ±6 hours.

- **Default:** Visible only on the home surface, after the digest. A single line in `Text.Meta`: "Opened Pulse {N} days this week." Below: "Streak: {N}."
- **No streak-broken copy.** If the user misses a day, the streak number quietly resets to 0 the next time they open. No toast. No email. No "Don't break your streak!" prompt.
- **No streak-shame.** PRD FR-46: "no missed-day punishment." The streak is a brand-loyalty signal we observe internally; it is not a metric we optimize for.
- **Opt-out:** Settings → Reminders → "Show streak counter." Off by default for users who have explicitly opted out.

**Anti-pattern to avoid:** Duolingo's streak shaming (orange owl, push notifications, "Your streak is in danger!"). PRD §13.3 explicitly bans this. (Cross-reference: §3 microcopy table lists a "Streak-broken" row marked _context only; §11 forbids_ — the "Do" example there ("Welcome back.") is illustrative of the calm principle, not approved copy for streak breakage. Any streak-shame copy is out.)

**Annual recap milestone:** When the streak hits a year (365 days), the system offers a single, quiet one-time prompt: "Your year on Pulse is ready. See it?" Tap routes to `/year-in-pulse`. (See below.)

### Year in Pulse (PRD FR-47, Year 2+)

**Behavior:** An annual recap, generated in early December each year, that surfaces the user's event engagement: events saved, events attended, top categories, top neighborhoods, longest streak, a "this month you showed up" stat. Visualized as a calm, scrollable single-page report.

- **Trigger:** Eligible on December 1 each year for users active in the prior 12 months.
- **Delivery:** Email + in-app banner: "Your Year in Pulse is ready." One email, one banner. No push.
- **Surface:** `/year-in-pulse/[year]` — a single scrollable page. Sections in `Text.Display` headlines, body in `Text.Body`. Color: `color.surface.paper` background. Key numbers are rendered in `type.scale.numeric` (mono) at `type.scale.display.lg` weight with `color.ink.primary` — no terracotta accent on numbers (terracotta is reserved for the four sanctioned uses in `DESIGN.md` §Color usage rules and is not added to recap surfaces). The recap derives its visual distinction from typography and layout, not from new accent uses.
- **Share:** Optional share-card generates a public URL with OG image, opt-in only. The share-card has no PII — only the user's category distribution and a "this was your year" tagline.
- **Viral posture:** This is the brand-love moment. Calm, reflective, shareable. Not gamified.

**Anti-patterns to avoid:**
- "You attended 47 events! 🎉" (no emoji, no exclamations)
- "You missed 12 events this year!" (no negative framing)
- Push notifications prompting users to share
- "Unlock your full recap with Pro" (the recap is free for all users)

---

## 12. Trust Signals as First-Class Surface

The "Why this?" pattern is the heart of the product. PRD §4.6 (FR-21–24) makes trust signals an MVP requirement; this section ratifies the *first-class surface* posture — trust signals are not hidden, not behind a tap on the card alone, but elevated in the design language.

### On the Pulse Card (home surface)

Every `Card.PulseDigest` carries these trust signals inline, without an extra tap:

- **Source Badge** (PRD FR-23) — top-right of card. Visible inline label (`Official`, `Community`, `Listing site`, `Forwarded`, or warning triangle for `crawled_html`).
- **Confidence Pulse** (PRD FR-22) — top-right of card, immediately left of Source Badge. 1–5 dots. `aria-label="4 of 5"` for screen readers.
- **Why-this Tags** (PRD FR-21) — below the event name. Up to 3 keywords in `Text.Meta` ink color, comma-separated.

The trust signals are *visible*, not behind a tap. PRD §13.1: "Why-this Tags are first-class." Design Thinking §Next Steps #7: "Inline trust beats click-to-reveal." The rationale is locked.

### On the Detail Screen

The Detail Screen is the trust-signal elevation surface. PRD §14.3 wireframe. From top to bottom:

1. **Source Badge** (inline, top, with `Tooltip.Source` on hover).
2. **Confidence Pulse** (inline, with `Tooltip.Confidence` showing contributing factors on hover).
3. **Event name** (`Text.Display.sm`).
4. **When · Where** (`Text.Body`).
5. **Why-this Tags** (3 keywords — same as on the card).
6. **Description** (2–3 lines max).
7. **Reminder Picker** (chips for 5d/2d/1d/1hr).
8. **Save to Pulse · Share · Dismiss** (3 buttons in `Button.Secondary` weight).
9. **Why-this breakdown** (expandable) — the human-readable reasoning behind the tags. E.g., "Comedy is in your top 3 categories. Within 2 km of your work. 12 of your neighbors saved this." Each factor on its own line.
10. **Similar events you've attended** (when computable).
11. **Neighbor count** (per PRD FR-24, k-anonymity threshold ≥5 qualifying users; bucketed as **prose labels in `Text.Meta`** to honor §3 + §9 anti-emoji discipline — see `_RECONCILE_` note below):
    - 5–9: "A few neighbors saved this."
    - 10–24: "Some neighbors saved this."
    - 25–99: "Many neighbors saved this."
    - 100+: "A lot of neighbors saved this."
    - Below 5: silently suppressed (no "0 neighbors" copy, no empty row).
12. **Reviews count** — restored from Design Thinking wireframe Screen 7 per `reconcile-design-thinking.md` §5 (Top 5 Reconciliation #5). Deferred to Phase 3+ pending an engagement-trap design review (see _Assumptions_, ASSUM-6); **the Detail Screen does not show reviews at MVP.** The reconcile recommendation is acknowledged but not adopted at MVP.

> `_RECONCILE:` Neighbor-count bucketing (item 11) was originally specified with `👥` emoji prefixes per the prior draft. This was revised to prose-only `Text.Meta` labels to honor §3 Voice and Tone ("Emoji as CTAs" ban) and §9 Anti-patterns ("Emoji as CTAs"). The k-anonymity contract (≥5 minimum threshold, bucketed display) is preserved verbatim. Anyone reading the older wireframe or the Design Thinking Screen 7 mock should use the prose labels above.

### Why-this Breakdown (the heart)

The Why-this breakdown is the human-readable explanation of why the AI surfaced this event. It expands from the 3 keywords on the card. Example:

> "Surfaced because:
> - Comedy is in your top 3 categories.
> - 2 km from your work.
> - 12 of your neighbors saved this.
> - Source reliability 0.92."

Each factor has a tooltip explaining what it means. The expansion uses `motion.fadeIn` (240ms, disabled under reduced-motion).

### Neighbor Count Privacy

Per PRD FR-24:
- Threshold: ≥5 qualifying users in the same area (haversine ≤2 km or same city-zip-cluster).
- Display: bucketed. Exact counts never exposed.
- Suppression: silently below threshold (no "0 neighbors" copy).
- Tier-agnostic: Pro and Free users count identically.

### Community Corroboration Count (optional, deferred)

`Deferred to Phase 3+ pending a Trust Review against engagement-trap principles (see _Assumptions_, ASSUM-7). The PRD does not require it; do not adopt without a Trust Review pass.`

---

## 13. Adaptive Density

The principle: cards reveal more detail on long-press, focus, or desktop hover. Mobile default is intentionally spartan. The default mobile view of `Card.PulseDigest` shows only:

- Event name (`Text.Display.sm`)
- When · Where (`Text.Meta`)
- 3 Why-this Tags (`Text.Meta`)
- 1 Confidence Pulse (top-right)
- 1 Source Badge (top-right)

That's it. No description, no image, no map, no price, no attendee count, no share button. The mobile default is the *decision surface*, not the *browsing surface*.

### Density Modes

| Mode | Trigger | Adds |
|---|---|---|
| **Default (mobile, idle)** | Always | Name, When · Where, 3 Why-this Tags, Confidence, Source |
| **Focused (keyboard)** | Tab focus on the card | Visible focus ring (2px, terracotta). `aria-label` exposes full card content to screen readers. |
| **Hovered (desktop)** | Mouse hover | Background shifts to `color.surface.paper.darker`. `▸` affordance appears. Tooltips available on Source Badge and Confidence Pulse. |
| **Long-pressed (mobile)** | Long-press on card | Quick-actions sheet anchored to card: Save, Dismiss, Less like this. |
| **Adaptive expansion** | ≥10 saves in 30d | Card count grows from 3 to 5 (top of the responsive matrix) or 7 (Phase 3 max). Inline "Show all 5" link below the last card. |
| **Default (Timeline event-block, mobile)** | Always | Event name, time, "Personal" / "Public event" label, conflict indicator if active |
| **Hovered / focused (Timeline event-block, desktop)** | Mouse hover or Tab focus | Adds location (`Text.Meta`) and 1 Why-this Tag (read-only at MVP — full Why-this breakdown expansion is on Detail Screen, never on Timeline). |

### Anti-pattern: progressive disclosure that hides trust signals

Adaptive density must not hide the trust signals (Why-this Tags, Confidence Pulse, Source Badge) at any density mode. The mobile default exposes all three; hover/focus/long-press *add* detail but never *remove* the trust signals. PRD §13.1: "Why-this Tags are first-class."

### Anti-pattern: progressive disclosure that hides the conflict indicator

If a card is in conflict (PRD FR-58), the conflict indicator is always visible — top-right of the card, in the same visual zone as Source Badge and Confidence Pulse. Adaptive density may add detail (e.g., a tooltip on the conflict indicator explaining the conflict), but the indicator itself never collapses below 6×6 px (the locked size for both Pulse Cards and Timeline event-blocks per `DESIGN.md` `component.indicator.conflict`).

### Desktop Hover Discipline

On desktop (`md+`), hover affordances are *additions*, not requirements. A user with a mouse and a user with a touchscreen get the same default; hover only adds detail. Per `DESIGN.md.Do's-and-Dont's` (per the locked brief), the desktop view is "whitespace and hover-revealed detail" — not "more features."

### What Adaptive Density Does Not Do

- Does not change the 3-card discipline (except via the explicit adaptive exception).
- Does not introduce infinite scroll.
- Does not introduce a carousel.
- Does not reorder cards based on engagement signal — card composition is determined by Pulse Digest logic (PRD FR-5), not by per-card density.
- Does not introduce paywalled density tiers ("Upgrade to Pro for full event descriptions").

---

## Appendix — DESIGN.md Token Reference

All behavior in this spine references `DESIGN.md` tokens by `{path.to.token}` syntax. The token names below are referenced in this spine; they are the canonical names the DESIGN.md author is using in parallel:

- `color.accent.terracotta` — primary accent (CTAs, focus ring, filled Source Badge).
- `color.surface.paper` — base background.
- `color.surface.paper.darker` — hover/darker paper variant.
- `color.ink.primary` — body text.
- `color.ink.meta` — metadata text.
- `color.ink.faint` — subtle dividers, empty dot placeholders.
- `color.warm.personal` — Personal Event tone (PRD §13.1).
- `color.cool.public` — Public Event tone (PRD §13.1).
- `color.warn.amber` (desaturated) — conflict indicator (PRD FR-58).
- `Text.Display` — headlines.
- `Text.Display.sm` — card-level headlines.
- `Text.Body` — body copy.
- `Text.Meta` — metadata, tags, timestamps.
- `Card.PulseDigest` — home card component.
- `Input.ReminderSlot` — reminder picker chips.
- `Indicator.Confidence` — 5-dot confidence indicator.
- `Badge.Source` — source type indicator.
- `Sheet.ConflictResolution` — FR-58 / Amendment A-5 conflict prompt (modal on Personal Event creation; three forced choices, no dismiss).
- `Surface.Timeline` — Unified Timeline surface at `/timeline` (Amendment A-8 — MVP). Read-only week view, Personal + Public events on one grid, conflict indicator on overlapping pairs.
- `Component.BottomTab` — Mobile bottom-tab navigation (Amendment A-8). Digest / Timeline / Add / Conflicts / Settings. Active slot uses ink inversion + 2px terracotta underline above the slot.
- `Component.Sidenav.App` — Desktop left-sidebar navigation (Amendment A-8). Same five routes as the bottom-tab. Active route uses ink-inversion pill, no terracotta fill.
- `Component.Sidenav.Footer` — Optional footer block pinned to the bottom of the 240px sidenav rail. Search + Account affordances; lives in the sidenav (not the topbar) per topbar-quiet rule. All tokens reused from existing DESIGN.md palette.
- `motion.fadeIn` — 240ms entrance transition (disabled under reduced-motion).
- `Button.Primary` — terracotta-filled CTA.
- `Button.Secondary` — ink-bordered CTA.
- `Tooltip.Source` / `Tooltip.Confidence` — hover/focus tooltips.

Visual definitions (exact hex values, spacing scales, type ramps) live in `DESIGN.md`. This spine assumes them and references by name.

---

## Assumptions

All open `[ASSUMPTION:…]` markers in this document, consolidated. Each entry has a stable ID (`ASSUM-N`) for cross-reference from the body. Status: OPEN = needs a decision before engineering ships; RESOLVED = owner has answered; DEFERRED = explicitly parked to a later phase.

> **Cross-doc note.** `DESIGN.md` uses the same `ASSUM-N` numbering scheme (currently `ASSUM-1` — hex palette calibration). Future additions to either doc should append to the higher number, not reuse IDs.

- **ASSUM-1.** _Cross-doc — see `DESIGN.md`._ Hex values for the palette are estimated from named descriptions; only `color.accent.terracotta #C4502B` was provided by brand. The rest (including `color.ink.faint`, `color.ink.meta`, `color.surface.paper.darker`, `color.warm.personal`, `color.cool.public`, `color.warn.amber`) are derived. Sample brand collateral before engineering token implementation; re-verify AA contrast.
  - Status: OPEN. Owner: TBD (brand / design). Decision deadline: before token implementation begins.

- **ASSUM-2.** `/settings/privacy` route is added as the 9th MVP route. PRD §14.1 implies it; FR-52 (export) and FR-50 (deletion) need a UI home. Without this route the Privacy PRD requirements have no surface at MVP.
  - Status: DEFERRED. Owner: PM. Decision deadline: MVP scope lock.
  - Action: either add `/settings/privacy` to the locked IA list and confirm PRD alignment, or move FR-52 / FR-50 to Phase 2.

- **ASSUM-3.** _Resolved by structure pass._ Maya's morning entry state: **Maya opens Pulse manually at 7:42 am** (the morning check-in slot she chose during onboarding). The manual-open path renders the same Pulse Digest as the Pulse Ping tap path. Pulse Ping delivery is configured for 8:00 am ±15 min in this flow; Maya opens Pulse before the notification fires. (The earlier "alternative: Ping at 7:42 am" wording is superseded — Maya's manual open is the canonical 7:42 am entry, the Ping is the 8:00 am follow-up.)
  - Status: RESOLVED. Owner: design.

- **ASSUM-4.** Adaptive-expansion inline "Show all N" link is **present-but-deemphasized** at all adaptive counts (5 and 7). The default render shows all expanded cards; the link is a redundant affordance for users who missed the count, not a progressive-disclosure gate. Tone: quiet confirmation, not upsell.
  - Status: RESOLVED. Owner: design.

- **ASSUM-5.** Visible card count at MVP is **5** for the adaptive-expansion engaged-user tier. The eventual upper bound is **7**, tested in Phase 3 only. Below the fold on mobile at 5 cards is acceptable; below the fold at 7 cards is acceptable. The "Show all 7" link exists at the Phase 3 7-card state only — at MVP the "Show all 5" link is the highest state.
  - Status: OPEN. Owner: design + engineering. Decision deadline: before adaptive-expansion ships.

- **ASSUM-6.** Reviews count on the Detail Screen is **not adopted at MVP**. The reconcile-design-thinking recommendation is acknowledged but parked pending an engagement-trap review (reviews can become social-proof / FOMO chrome if not framed carefully). Phase 3+ candidate.
  - Status: DEFERRED. Owner: design + Trust Review. Decision deadline: Phase 3 scope lock.

- **ASSUM-7.** Community Corroboration Count (number of users who saved or opened Detail Screen for an event, regardless of proximity) is a **deferred Phase 3 candidate**. The PRD does not require it; the reconciliation against engagement-trap principles is pending. Do not adopt without a Trust Review pass.
  - Status: DEFERRED. Owner: design + Trust Review. Decision deadline: Phase 3 scope lock.

- **ASSUM-8.** _Derived from §7 Live Regions._ Live-region announcements are `aria-live="polite"` and serialized (queued, not interrupted). Rapid-fire save / dismiss / save sequences are debounced and announced once per discrete action with a 250ms settle window. The "Pulse Digest ready" announcement uses the same queue. Concrete debounce timing is left to engineering; the spec asserts the queueing behavior, not the millisecond timing.
  - Status: OPEN. Owner: engineering. Decision deadline: before live-region implementation.

- **ASSUM-9.** _Derived from §4 `Badge.Source`._ Tooltip text per source variant (`official_site`, `community`, `aggregator`, `user_imported`, `crawled_html`) is locked in §4 — `Tooltip.Source` is approved microcopy. No additional source types are accepted without a Trust Review pass; if the source roster grows, the variant list in §4 must be updated and reviewed.
  - Status: OPEN. Owner: design. Decision deadline: before source ingestion pipeline ships.

- **ASSUM-10.** _Locked 2026-09-03 (v1 onboarding audit, Amendment A-7)._ All three calendar providers (Google OAuth 2.0, Apple CalDAV, Outlook Microsoft Graph) ship at MVP per PRD FR-3 / FR-50. Provider parity is enforced visually — no provider is rendered as `Button.Primary` over the others. Provider parity copy is in §3 microcopy contract. Apple CalDAV credential UX requires an inline help link to a single article (not a modal). The topbar of every onboarding step holds the brand mark only; Skip/Continue affordances live in the footer.
  - Status: RESOLVED. Owner: design + engineering. Decision deadline: before token implementation begins.

- **ASSUM-11.** _Locked 2026-09-03 (v1 onboarding audit)._ The topbar-quiet rule: topbar holds only brand + tagline; action affordances (Skip, Sign in, Sign up, Open menu) live in the footer or in surface-level CTAs. Inversions of this rule are bugs. Applies to `/onboarding`, `/settings/*`, `/preview`, and any future anonymous or authed surface with a topbar.
  - Status: RESOLVED. Owner: design.

- **ASSUM-12.** _Locked 2026-09-06 (Amendment A-8 lift)._ `/timeline` at MVP is a **read-only** Week view combining Personal + Public events (Amendment A-8). No edit-from-Timeline, no drag-to-reschedule, no inline conflict resolution on Timeline itself. Edits happen on Detail Screen or the Personal Event modal; conflict resolution happens via the FR-33 three-action pattern on the Detail Screen header panel. The `/conflicts` route is a review surface for conflict pairs the system has recorded (active + resolved) — it does not surface user-added notes. The conflict indicator is a 6px filled amber circle on both Pulse Cards and Timeline event-blocks (`aria-label="Schedule conflict"`) — color is paired with the `Indicator.Conflict` shape so color is never the sole carrier of meaning (WCAG 1.4.1). Both routes are reachable from `Component.BottomTab` (mobile, 5 slots; Conflicts is the 4th slot between Add and Settings) and `Component.Sidenav.App` (desktop md+, Conflicts link between Add and Settings); the topbar stays brand-only (topbar-quiet rule, ASSUM-11).
  - Status: RESOLVED. Owner: design + engineering. Decision deadline: before token implementation begins.

- **ASSUM-13.** _Locked 2026-09-06 (Amendment A-8 lift, FR-58 follow-on)._ The conflict indicator dot is locked at **6px diameter** for both Pulse Cards and Timeline event-blocks (`DESIGN.md` `component.indicator.conflict` and `component.timeline.event-block`). The dot sits at the top-right of the block (Pulse Card) or top-left of the event-block (Timeline) so the Personal/Public text label in the top-right remains visible (WCAG 1.4.1). The size was chosen for Timeline density (matches `Indicator.Confidence` 6px dots on Pulse Cards) and is the same value on Pulse Cards to avoid re-coding two sizes. Density: pulsing glow (`box-shadow: 0 0 6px rgba(216,168,106,0.6)`) is permitted on the dot on dark surfaces to lift it from the page — glow does not appear on the dot in light mode.
  - Status: RESOLVED. Owner: design + engineering. Decision deadline: before conflict indicator implementation.

- **ASSUM-14.** _Locked 2026-09-06 (Amendment A-8 lift)._ The `/conflicts` page renders two sections in fixed order: **Active** (1+ conflict pairs awaiting a decision) then **Resolved** (decision-recorded pairs). The Active section's last action taken by the user on any conflict in the section clears that pair from Active and moves it to Resolved on the next render. The page does not auto-refresh; the next user interaction triggers a fetch (per Flow 6 failure mode). Resolved pairs are immutable history — the system never re-prompts for a decided pair. The Active section uses `aria-live="polite" aria-atomic="false"` so screen readers re-announce count changes; the page itself ships a visually-hidden live region announcing the initial Active + Resolved counts on first render.
  - Status: RESOLVED. Owner: design + engineering. Decision deadline: before `/conflicts` implementation.

---

_End of EventPulse24 experience spine. Generated 2026-08-23; last revised 2026-08-30 to add dark-first theme, lift conflict prompt to MVP per PRD FR-58, and lock the surface-coverage map below. Paired with `DESIGN.md`. Source PRD: `prd-EventPulse24-2026-08-19`. Reconciles: `reconcile-design-thinking.md`, `reconcile-blue-ocean.md`._

---

## Surface Coverage Map (mockups)

The `mockups/` directory contains 32 HTML files covering every MVP surface in both Desktop and Mobile breakpoints where applicable (26 in `mockups/` + 6 in `mockups/mobile/`). The 4 light-mode mocks in `mockups/light-archive/` are preserved for reference but excluded from the MVP count. **Spines win on conflict with any mockup** — if a mockup diverges from a token in `DESIGN.md` or a behavior in this spine, fix the mockup, not the spine. The mockups exist to anchor visual decisions; they are not the source of truth.

| # | Surface | Route / component | Desktop mockup | Mobile mockup | Notes |
|---|---|---|---|---|---|
| 1 | Pulse Preview (public landing) | `/preview` | `pulse-preview-desktop.html` | `pulse-preview-mobile.html` | FR-2, UJ-3. Includes geo-IP consent banner. |
| 2 | Onboarding — step 1 (calendar connect) | `/onboarding` step 1 | `onboarding-step1-desktop.html` | `onboarding-step1-mobile.html` | FR-1 / FR-3 / FR-50. Three providers (Google / Apple / Outlook) at MVP with provider parity. Step is skippable. |
| 3 | Onboarding — step 2 (interest chips) | `/onboarding` step 2 | `onboarding-step2-desktop.html` | `onboarding-step2-mobile.html` (pending — see coverage gaps) | FR-1. Up to 3 picks. |
| 4 | Onboarding — step 3 (digest time + timezone) | `/onboarding` step 3 | `onboarding-step3-desktop.html` | `onboarding-step3-mobile.html` (pending — see coverage gaps) | FR-1 / FR-7. Includes time presets + AM/PM segmented control (ink inversion, not terracotta). |
| 5 | Pulse Digest (home, 3 cards) | `/` | `pulse-digest-desktop.html` | `pulse-digest-mobile.html` | FR-5 / FR-6. Slot 1 + Slot 2 + Slot 3 with the conflict indicator on Slot 2. |
| 6 | Event Detail | `/events/:id` | `event-detail-desktop.html` | `event-detail-mobile.html` | FR-9 / FR-24. Why-this breakdown + multi-tier reminders + neighbors. |
| 7 | Personal Event creation | `/events/new` modal | `personal-event-create-desktop.html` | _(desktop-first; mobile uses bottom sheet, same tokens)_ | FR-18. |
| 8 | Conflict Resolution prompt | `Sheet.ConflictResolution` | `conflict-prompt-desktop.html` | `conflict-prompt-mobile.html` | FR-58. Three forced choices, no dismiss. |
| 9 | Empty Pulse Digest | `/` empty state | `empty-pulse-digest-desktop.html` | _(covered by pulse-digest-mobile empty)_ | FR-8. Includes suggested-sources strip. |
| 10 | Settings (theme, notifications, quiet hours, calendar, account, plan) | `/settings/*` | `settings-desktop.html` | _(deferred — desktop-first at MVP)_ | FR-7 / FR-12 / FR-48 / FR-49 / FR-51 / FR-52. |
| 11 | Public share-link landing | `/share/:slug` | `share-link-desktop.html` | _(deferred — desktop-first at MVP)_ | UJ-5. SEO public URL with Schema.org Event JSON-LD. |
| 12 | Unified Timeline (week view) | `/timeline` | `timeline-desktop.html` | `mobile/timeline-mobile.html` | FR-32 (Amendment A-8). Read-only week view, Personal + Public, sidebar nav (desktop) + bottom-tab (mobile) — first mockups to render these nav components. |
| 13 | Conflict Review list | `/conflicts` | `conflicts-desktop.html` | _(deferred — desktop-first at MVP)_ | FR-33 (Amendment A-8). List of active + resolved conflict pairs. The Conflict Resolution prompt itself (`Sheet.ConflictResolution`, FR-58) is row 8 above. |

**Coverage gaps to fill before launch** _(logged here as `mockups/pending` items)_:

- Mobile settings (single-stacked-tab pattern; can follow the desktop mockup 1:1 using tokens).
- Mobile share-link landing (small follow-up).
- Personal Event creation on mobile (bottom-sheet variant — pattern already shown in the conflict-prompt mobile mock, just applied here).
- Mobile empty-state confirmation (still pending — the desktop variant is canonical).
- Mobile `/conflicts` page (can follow `conflicts-desktop.html` 1:1 using tokens; the desktop pattern is canonical).
- Mobile Timeline empty-week state (single-column variant of the desktop empty-state).
- Mobile empty-Timeline-day state (the `Quiet day.` row, vertical-stack variant).
- Mobile bottom-tab nav variants beyond Timeline (Digest / Add / Settings — pattern locked in `mobile/timeline-mobile.html` and reused).

**Visual identity rule for all mockups:** tokens are declared in `:root` and overridden under `[data-theme="dark"]`. The dark variant is the default at `<html data-theme="dark">`. Every mockup carries the conditional layer at the top of its `<style>` so engineering can paste the same template for any new surface.

**Mockup-onboarding parity rule:** the onboarding mockups (`onboarding-step1/2/3-desktop.html` + mobile) render the three calendar providers with identical visual weight per `DESIGN.md` `component.button.provider` and the §3 provider-parity microcopy. The earlier mockup variants that rendered Apple/Outlook as "Coming Phase 2 · Join the waitlist" links are **superseded**; v1 mockups render all three as first-class connect affordances. Old archived variants (if any) live in `mockups/light-archive/`.
