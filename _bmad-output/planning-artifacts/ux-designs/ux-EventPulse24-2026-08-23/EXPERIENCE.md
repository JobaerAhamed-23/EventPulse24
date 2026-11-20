---
title: "EXPERIENCE.md — EventPulse24"
status: final
created: 2026-08-23
updated: 2026-11-19
updated_note: "**Spine update 2026-11-20 (Amendment A-26 — the \"Suggest an event\" link, withdrawn on both surfaces):** §5 Empty Patterns specified this link twice — on the empty Pulse Digest (`Text.Meta`, low weight, opening *\"a `/suggest` form (PRD FR-8)\"*) and on the empty `/preview` for search-engine referrers only (`/suggest?city={city}`), with a matching §2 IA row. **`/suggest` exists in no layer of the product.** There is no suggestion FR in the PRD, and no model, endpoint, table, serializer or admin in `backend/` — the route was never built because it was never specified beyond the word \"link\". **The digest link shipped as a real `<Link>` and 404'd; a user reported it on 2026-11-20.** The preview link was never built, so that promise was unkept rather than broken. **Both are withdrawn, not deferred**, the preview one so that a later build cannot plant the same dead link on a second surface. **This removes no trust signal and breaks no copy lock:** §5's locked empty-digest copy (*\"Nothing on the pulse today. The calendar is yours.\"* and the `No qualifying events in {city}.` meta line) is byte-identical, and the row's own No-CTA rule (*\"No CTA. No carousel. No upsell at all.\"*) is better served without it — §5's reasoning is that *\"a user opening Pulse to nothing should feel the absence of the product's noise, not be marketed at,\"* and a link that 404s is noise that costs a click to discover. **The option taken here was never on the list it replaces.** `digest-empty.tsx` argued in its own header that a real link beats a disabled control and beats an inert button; on those three options it was right, and the fourth — not making the promise — was not considered. **The Empty Preview rationale is preserved verbatim in §5 because it is the revisit condition, not because it was wrong:** SEO cold-start is §1's unlock, and a visitor arriving from Google in a city the catalog does not cover has no other way to signal that they exist. That argument is **unfunded, not refuted**. If a suggestion feature is ever specified — an FR, a destination that accepts input, and a path for what happens to it — the SEO placement is the strongest case for where it lands first, and §5's Empty Preview row should be restored **before** the digest link is. **The absence is enforced, not remembered:** `frontend/tests/internal-links.test.ts` fails on any internal `href` resolving to nothing. **This update touches this document, PRD FR-8 and TRACEABILITY.md only** — no new tokens, no new components, no new mockups, and no Surface Coverage row, because A-26 adds no surface. **Spine update 2026-11-19 (Amendment A-24 — the Timeline block's Why-this Tag, withdrawn):** §13's Density Modes row for the hovered/focused desktop Timeline event-block promised *location and 1 Why-this Tag*. The location shipped (`d1d6c83`, `b4ba162`), resolved server-side onto `TimelineBlockOut.place`. **The tag is withdrawn.** **The reason is that the tag carries no information on this surface, not that it is expensive.** Every public block on the Timeline *is* a saved event, so `is_saved` is universally true; `discovery` requires a digest slot (`serendipity=True`) and never fires here; and the time tags (`tonight` / `tomorrow` / `weekend`) are computed against `now`, so on any week but the current one none of them fire — and the Timeline navigates by arbitrary week. The single tag this row asked for therefore resolves to `nearby` on every block in the user's own city, or, for a user with no city (`DigestPreference.city` is nullable), an out-of-town event, or any non-current week, to `saved` — which on a surface that shows only saved events answers *\"why is this here?\"* with *\"because you saved it.\"* The one informative tag, `matches_<chip_key>`, sorts **last** in `RANKING_TAG_ORDER` and is unreachable whenever any fixed tag applies. **This is not a trust-signal removal.** §13's own anti-pattern (*\"Adaptive density must not hide the trust signals\"*) governs the **Pulse Card**, whose mobile default exposes Why-this Tags, Confidence Pulse and Source Badge; the Timeline block's default shows none of the three at any density, so nothing is hidden — a promise is withdrawn before it was ever kept, and §13 already routes the full Why-this breakdown to the Detail Screen. **And it is not a cost decision.** Building it would cost **one** extra query, not the four the splitting work item recorded: `why_this_tags` reads only `inputs.city_match` from `RankingInputs`, the user's city rides on the `DigestPreference` row the Timeline already reads, and `chip_keys_for` is pure text over columns the batched catalog read already selects — only `_read_interest_keys` is new. **AD-10 is likewise not the blocker**: the import contract bars `apps.ingestion.event_fit`, and the Relevance Pulse path never touches it. Both corrections are recorded so the deferral is not reversed on a premise that does not hold. If FR-25's preference graph later makes `matches_<chip_key>` reachable and meaningful here, this decision is revisitable on that evidence. **This update touches only this document** — no new tokens, no new components, no new mockups, and no Surface Coverage row, because A-24 adds no surface. **Spine update 2026-11-13 (A-18 `/settings/sources` — as-built corrections):** the `Component.Settings.Sources` row is corrected against the implementation. (1) **Reliability scoring** now states the algorithm that actually runs — FR-16's beta-binomial posterior (`domain/reliability.py`), floored at 0.32 until 30 observations, read as the 0.50 prior when never reached — instead of the forward-reference to a forthcoming ADR-0024, which does not exist. The 1–5 band is the **stored score** banded (`source_trust_band`), never a week-over-week delta, and **0.50 is band 3** so a never-scored source reads as unproven rather than bad. The band is the server's number; the client draws it and does not recompute it. (2) **'Show less'** is documented as a **post-score penalty applied outside FR-22's published formula** — the formula is exactly five weighted terms summing to 1.00 and is pinned against ADR-0025 (PRD **Amendment A-25**), so a penalty cannot be a sixth term; it is applied to the score the formula produced, before the ordering, so the formula and its pin stay byte-identical. A show-less that *hid* events would be indistinguishable from a mute on the wire and would lie to a user who asked for fewer rather than none. (3) **Default** is documented as the *absence* of a preference row rather than a third stored state, which is what makes 'Restore all defaults' a single bulk delete. (4) **Bulk reset** confirmation is documented as an **in-place two-step**, not the type-to-confirm pattern of `Component.Modal.AccountDelete` — A-16 reserves that weight for account deletion, and the endpoint is a single idempotent bulk delete, so the confirmation is the client's job; a server-owned confirmation would have to survive a page refresh, which is a state machine to buy a dialog. No request is sent on the first press. **No new tokens, no new components, no new mockups.** This update touches only this document — `TRACEABILITY.md` and the mockup headers are deliberately untouched, because editing a document to move a matrix score in the same pass that measures it is how a matrix stops being trustworthy. **Spine update 2026-09-06 (Amendment A-20 — `/signin` + `/signup` pre-auth routes):** adds two pre-auth routes that close the returning-user gap (no landing surface currently exists for users whose session expired — currently they get silently redirected to onboarding, which violates the calm contract for users who have already converted). New components: `Component.Auth.SignIn` (returning-user email + password sign-in, routes to `/` on success) and `Component.Auth.SignUp` (OAuth stack + email/password account creation, splits off the calendar-connect step so the post-signup onboarding flow stays within FR-1's ≤3 user-visible steps). Both surfaces use the per-field inline validation error pattern from DESIGN.md `component.input.field.error` (Amendment A-20) — `color.signal.warn` paired with `⚠` glyph, NOT `color.signal.error` which is reserved for destructive actions. Auth-error copy bank added to §3 (7 verbatim strings). `Component.Topbar.PreAuth` listing at L301 extended in-place to include `/signin` + `/signup` in the 8-route pre-auth family — topbar-quiet rule (ASSUM-11) applies. §2 IA table: +2 rows. State coverage table: +2 rows. Surface Coverage Map: +2 rows (19, 20). §Do's-and-Dont's: 1 new row locking the auth-error color treatment. All palette tokens reused; no new hex values; no new CSS variables. 2 new mockups: `signin-desktop.html`, `signup-desktop.html`. **`mockups/city-page-desktop.html` and the other 6 pre-auth mockups remain in their pre-A-9 topbar state** — migration is part of the existing pre-auth migration backlog, NOT part of this amendment. **Spine update 2026-09-06 (Amendments A-13 → A-19 — PRD-coverage reconciliation):** seven gap-closing amendments closing the remaining PRD ↔ UX gaps surfaced in the 2026-09-06 gap audit. **A-13:** amendment-history timeline inlined into Settings → Privacy §Amendment history — vertical timeline using `color.border.subtle` divider + 8px ink-muted dots; the latest entry's dot is terracotta-glowing per Amendment A-8 Indicator.Today treatment; each entry links to its ADR record. **A-14:** Geo-IP consent toggle on Privacy — 2-position segmented control with ink-inversion selected state (per `component.control.segmented` rule), default ON, off-state persists in `ep_geo_choice` cookie + falls back to most-popular city (NYC). **A-15:** Sold Out badge spine promotion — `component.badge.soldout` adopts `color.signal.warn` (NOT a new `--signal-mute` token); lifecycle locked (appears on Pulse Card + Detail Screen when `event.status = sold_out` per FR-53; persists until event ends; Save & reminder CTAs on Detail Screen replaced by calm 'Sold out — tickets no longer available.' line). **A-16:** Delete-account confirmation modal — `component.modal.account-delete` max-width 480px; header `Text.Headline.md` 'Delete your account?'; body 3 paragraphs (what gets deleted / what survives as anonymized aggregates / 30-day grace); type-to-confirm input 'Type DELETE to confirm' gates the primary; secondary Cancel + primary terracotta 'Start 30-day deletion'. **A-17:** Data Export modal — `component.modal.export-request` carries jurisdictional copy ('You're in {country}, so this export is free.' / 'Pro is required for exports outside the EU/UK/CA/BR/AU per our retention policy.'); Free-tier non-EU routes through `component.card.pro.upsell` to `/settings/plan`; post-submit inline notice 'Export started. We'll email {user.email} within 24 hours.'. **A-18:** `/settings/sources` page — `component.control.source-mute` (3-state: `Mute / Show less / Default`) + reliability dots reusing `component.indicator.confidence` token (1–5 ink-primary dots); grouped list (Official / Community / Aggregator / Crawled); ~10 sample sources. **A-19:** Pro per-day-of-week Quiet Hours — `component.control.day-picker` 7-row vertical list (Mon–Sun), each row carries day-name + active-window chip + ink-inversion activation toggle (NOT terracotta); Free users see locked rows with `Lock` glyph + 'Upgrade for per-day' microcopy on hover; Pro tier can set 7 distinct windows. All amendments reuse existing palette tokens, no new hex values, no new CSS variables. 4 new mockup files: `settings-sources-desktop.html`, `settings-quiet-hours-pro-desktop.html`, `account-delete-confirmation-modal-desktop.html`, `export-request-modal-desktop.html`. 3 mockup edits: `settings-desktop.html` Privacy section inlined timeline + toggle; `sold-out-card-state-desktop.html` adopted `color.signal.warn`; ranking-algorithm-transparency-desktop.html unchanged (its content remains the canonical pre-deprecation reference). Numbering note: A-12 is reserved in the existing spine chronology for the Browse × city-page merge (see the prior entry); gap-closing amendments start at A-13 to avoid clashing with the existing A-12 spine lock and the mockup's internal 'Amendment A-12 — Browse × city-page merge' header in `mockups/browse-desktop.html`. §2 IA table gained 2 new rows (sources page, quiet-hours Pro); existing rows for `/settings/sources` and `/settings/quiet-hours` updated with the new sub-rows. All earlier updates preserved verbatim. Subsequent update 2026-09-06 (sidenav-footer pattern): added Component.Sidenav.Footer to §4 Component Patterns, documenting the Search + Account footer block pinned to the bottom of the 240px sidenav rail. Search + Account do not fit the route list and do not belong in the topbar (topbar-quiet rule, ASSUM-11). All tokens reused from existing DESIGN.md palette — no new colors, no new CSS variables. Pattern sourced from mockup changes to pulse-digest-desktop.html and conflicts-desktop.html, then promoted to spine so the remaining sidenav surfaces (timeline-desktop.html, settings-desktop.html, ranking-algorithm-transparency-desktop.html) can adopt it without re-derivation. Subsequent update 2026-09-06 (ranking-algorithm IA): ranking transparency (PRD FR-22) lives inside Settings → Privacy as an in-page section, not a separate route. Updated §2 IA table row 9 to spell out ranking transparency as a sub-section. **Spine update 2026-09-06 (sidenav link-reset prerequisite):** added a new bullet under Component.Sidenav.App in §4 — 'Global reset prerequisite: the page's CSS must include `a { color: inherit; text-decoration: none; }` before the sidenav is applied, otherwise the browser default underlines bleed through on every route label and the Account row.' Documents a real bug from the 2026-09-06 batch migration of pulse-digest-empty-state-desktop and personal-event-edit-desktop, both of which shipped the shell without the reset (the original pre-sidenav files had no <a> in the topbar zone). **Spine update 2026-09-06 (Amendment A-9 — pre-auth chrome + logo halo carve-out):** added Component.Topbar.PreAuth to §4 Component Patterns documenting the brand-only topbar used on the 6 pre-auth public/marketing routes (pulse-preview / city-page / public-event-page / share-link / pricing-page / pro-upgrade-cta). No sidenav, no nav links, no topbar action cluster — conversion affordances live in the hero CTA + page footer + section-level decision moments. Logo halo on the brand-mark PNG documented as a brand-asset artifact outside the token system (cross-references DESIGN.md §Color usage rules → Glow carve-out); the 36x36 canonical render size keeps the halo within marketing-page-acceptable visual weight. pro-upgrade-cta explicitly documented as a states-only showcase that omits the brand-wrap (and would gain it when engineering ships /pro/upgrade). Migration status: spine exception paragraph + Do/Don't row locked; the 6 mockups remain in their pre-migration state (some carry legacy How it works / Sign in / Sign up buttons in topright that violate the new rule) — migration deferred to the next build batch, mirroring how the authed + onboarding batches rolled out. **Spine update 2026-09-06 (Amendment A-10 — Browse surface, 6th authed route):** (1) §4 `Component.Sidenav.App` extended with a 6-route variant — adds Browse between Add and Conflicts (order: Digest / Timeline / Add / **Browse** / Conflicts / Settings). Five-route variant retained for onboarding only. New keyboard shortcut `g b` routes directly to /browse. (2) §4 new `Component.BottomTab.MoreMenu` — mobile overflow affordance for the 6th route; bottom-tab stays 5 visible primary slots, More opens a sheet listing Browse + any future overflow route. (3) §4 new `Component.Surface.Browse` — /browse surface spec: all public events in user's city, today + 7 days, day-divider labels in microtag style, no calendar-control widget, no category filter chips, soft-cap of 24 cards with in-place chunk-load past the cap. Reuses Card.PulseDigest vocabulary card-for-card. Explicit anti-pattern list (no count badges, no social proof, no category-color floods, no infinite scroll, no upsell carousels). (4) §4 new `Component.Button.Save.Inline` — quiet Save affordance spec for Browse cards: state machine (idle → saving → saved → idle), free-tier cap integration (FR-48), failure modes (quota-exceeded / conflict-detected), accessibility (aria-label includes event name, aria-live on morph). (5) §2 IA Surface Map — added row 14: Browse, /browse, browse-desktop.html, Amendment A-10. Earlier updates preserved: 2026-09-03 pulse-preview audit additions, 2026-09-03 v1 onboarding audit, 2026-09-06 Amendment A-8 lift, 2026-09-06 pre-auth migration batch. **Spine update 2026-09-06 (Amendment A-11 — Browse inline keyword search):** §4 `Component.Surface.Browse` extended with inline keyword search spec. (1) Single `<input type=\"search\">` above the first day divider, max-width 720px to match the hero column. (2) Grammar: plain words AND-matched against headline + where + why-tag tokens; `tag:<token>` literals constrain to the why-tag set only (vocabulary: music · tech · community · arts · family · food · sports · outdoor · indoor · rooftop). Free text + tag tokens AND-matched. (3) No category chips, no date pickers, no preset toggles — the calm contract requires self-contained, learnable-in-5-seconds grammar. (4) Empty-result state uses component.emptystate.quiet vocabulary: 'Nothing matched.' + a single Text.Meta 'Clear' link that resets the input — distinct from the zero-events empty state ('Nothing nearby tonight. Try a wider city?' + 'Change city'). (5) Placeholder teaches the grammar in-place: 'Search this week — jazz, free, outdoor, tag:music'. Microcopy below the input lists 1-2 example queries + the tag vocabulary. (6) Input fill uses color.surface.paper (matching the existing authed-shell inputs in browse-desktop.html / pulse-digest-desktop.html) — flagged as a deliberate deviation from the spine default of color.surface.elevated so future surfaces know. Mockup coverage: browse-desktop.html now renders the default empty-input state; new browse-desktop-filtered.html demonstrates a 2-card AND-matched result for query 'jazz free'; new browse-desktop-empty.html demonstrates the no-match empty-result state for query 'quantum poetry'. No new color tokens, no new CSS variables, no new components invented. **Spine update 2026-09-06 (Amendment A-12 — Browse × city-page merge):** §4 `Component.Surface.Browse` rewritten to adopt the pre-auth city-page visual structure inside the authed shell. (1) Hero: eyebrow (terracotta dot + Brooklyn · Tonight + 7 days) + `Text.Display.xl` h1 with terracotta-italic `<em>` ('Events in *Brooklyn.*') + lede + city-meta pill (📍 Brooklyn, NY · 147 events this week · Change city) + small mono quota note. (2) Inline keyword search (A-11) stays — replaces the city-page filter chip rail entirely. (3) Day-divider grouping replaced with two attention-tier section heads ('3 worth your attention today' / 'More this week'), each with mono meta. (4) 3-column card grid at ≥1280px (2-col at 1024-1279px, 1-col on mobile) — `grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 20px`. (5) Card vocabulary: A-10 card body + city-page card sizing — 22px padding (down from A-10's 24px), 18px headline (down from 22px for narrower grid widths), 3px left stripe. (6) **Discovery stripe dropped** — explicit cap of 2 stripe colors (slate public + amber must-know at <10%). (7) **Pre-auth CTA leakage forbidden**: Sign-up / How-it-works CTAs and the city-page's `<footer class='seo-foot'>` neighbor-cities rail are omitted from the markup entirely (not display:none). (8) **Filter chip rail forbidden**: city-page's `chips` vocabulary (When: This week / Weekend / Tonight / Free + Category: All / Music / Tech / Community / Arts / Family / Food & drink / Sports) does not migrate. (9) Persona-prefixed 'Maya-fit' copy from city-page L156 dropped — authed users already converted, persona copy is pre-auth framing. (10) Anti-pattern list extended with three explicit Amendment A-12 locks: no discovery stripe, no pre-auth CTA leakage, no filter chip rail. **Mockup coverage:** `browse-desktop.html` rewritten as 3-column grid (3 cards in section 1 + 3 in section 2 = 6 total). `browse-desktop-filtered.html` rewritten for grid (search `jazz free` → 2 cards in a 2-card row with `.match` tag highlighting). `browse-desktop-empty.html` rewritten for grid (search `quantum poetry` → empty-result block inside the grid container, full-width). **`mockups/city-page-desktop.html` untouched** — pre-auth SEO surface per PRD FR-27. No new color tokens, no new CSS variables, no new spacing tokens. No new component invented beyond the implicit `component.hero.citypage` vocabulary that reuses existing eyebrow / h1-em / city-meta pill tokens already declared on `city-page-desktop.html`. **Spine update 2026-09-06 (Amendment A-21 — reminder-picker shell migration):** `mockups/reminder-picker-desktop.html` migrated from standalone modal-style page (`.frame` + `.container` + topbar back-link) to the A-8 shell (240px sidenav with 6-route nav per A-10 + brand-only topbar + sidenav-footer with Search + Account). Active nav-item is **Digest** — the picker is reached by tapping 'Edit reminders' on the Event Detail surface, which itself hangs off the Digest surface in the IA (Detail is reached by tapping a Digest card). Same active-state logic as `event-detail-desktop.html`. The prior '← Free tech meetup' back link becomes a crumb segment (`Digest · Free tech meetup — 'Designing for Calm' · Edit reminders`). All reminder-picker content preserved verbatim: 4 ON reminder slots (5d/2d/1d/1h) with terracotta-tinted backgrounds + filled terracotta markers + on-state toggles, custom slot being added (with `+` marker, value='30 minutes', Add slot button), quiet-hours deferral note (amber tint + 'Edit quiet hours' link), action bar (Reset default ghost + Save reminder plan primary), 3 aside panels (this reminder plan summary / Pro per-event quiet hours upsell / 'less like this' explainer). Nested `<main>` replaced with `<section aria-label='Reminder plan editor'>` to avoid duplicate landmark (outer `<main class='main'>` is already the A-8 page landmark). `text-decoration:none` reset added for sidenav anchors per the locked prerequisite from the 2026-09-06 sidenav-link-reset rule. All tokens reused from the A-8 palette; only hex additions are `#FF7E5E` (terracotta hover, accepted convention from `browse-desktop.html`) and the avatar gradient `#C8967A` → `#6E7E92` (warm-personal → accent-slate, byte-identical to other A-8 mockups). No new CSS variables, no new component invented. Numbering note: A-13 → A-20 are already taken by PRD-coverage reconciliation (A-13 amendment-history, A-14 Geo-IP consent, A-15 Sold Out badge, A-16 Delete-account, A-17 Data Export, A-18 Settings/Sources, A-19 Pro per-day-of-week Quiet Hours, A-20 SignIn + SignUp). A-21 is reserved for this shell migration, which doesn't introduce new components — only extends shell-migration coverage to the last pre-A-8 mockup."
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
| 13 | `/signin` | **Sign In** — returning-user email + password landing surface (Amendment A-20) | MVP | Public |
| 14 | `/signup` | **Sign Up** — account-creation step split from `/onboarding` step 1; OAuth stack (Google / Apple / Outlook at equal weight) + email/password (Amendment A-20) | MVP | Public |

Total: 14 routes.

**State coverage per route.** Every route must handle the four canonical states. The specific copy is in §5 (State Patterns); the table below tells you which states each route is expected to ship at MVP vs Phase 2.

| Route | default | empty | loading | error |
|---|---|---|---|---|
| `/` | 3-card Pulse Digest | "Nothing on the pulse today." (no CTA, no carousel) | 3 paper skeletons fading 1px toward ink at 60% then back | "Couldn't reach Pulse. Try again." + retry |
| `/onboarding` | Step 1 (calendar connect) | n/a (no empty state — every user starts at step 1) | Inline spinner only on the OAuth round-trip | "Connection failed. Skip for now?" |
| `/events/:id` | Full event detail with Why-this breakdown | An event the source removed: "This event is no longer available." | Detail skeleton: header + meta row + 3 Why-this chips fading in | "Couldn't load this event. Back to Pulse Digest." |
| `/preview` | 3-card preview for inferred city | "No preview available in {city} yet." — the search-engine-referrer "Suggest an event" link is **withdrawn by Amendment A-26 and was never built** (see §5 Empty Patterns → Empty Preview) | Card skeletons (3, parallel to digest) | "Couldn't load the preview. Refresh." |
| `/events/near-me` | SEO list of events for city | "Coming soon — we're growing {city}'s coverage." | List skeletons (5 rows) | "Couldn't load events. Try again." |
| `/settings/reminders` | Default Reminder Plan chips (5d/2d/1d/1hr) | n/a (defaults exist) | Inline save spinner on chip change | "Couldn't save. We'll try again on your next change." |
| `/settings/quiet-hours` | Default 10pm–8am window | n/a | Inline save spinner | "Couldn't save." |
| `/settings/sources` | Grouped source list (official/community/aggregator/crawled) | "No sources muted." | List skeletons | "Couldn't load sources. Refresh." |
| `/settings/privacy` | Data inventory + Export/Delete CTAs | n/a | Inline spinner on export trigger | "Couldn't start export. Email us." |
| `/timeline` | Week-view, Personal+Public events (read-only at MVP — Amendment A-8) | "Your week is quiet. Pulse Digest is the place to discover." | Week-row skeletons | "Couldn't reach Timeline. Try again." |
| `/conflicts` | Conflict list grouped by Active / Resolved (Amendment A-8) | "No overlaps." | Skeleton rows | "Couldn't analyze conflicts. Try again." |
| `/groups/:id` | Group home, members, next event proposal | "No group yet. Create or join one." (Phase 2) | Skeleton | "Couldn't load group. Try again." |
| `/signin` | Default (email + password empty, primary enabled when both filled) | n/a (empty is the default state — no other empty variant) | Primary CTA morphs to .spinner + "Signing in…" | Per-field inline `component.input.field.error` in `color.signal.warn` (wrong-password → Password field error; account-not-found → Password field error to avoid enumeration leak per §3 voice-and-tone). |
| `/signup` | Default (OAuth stack + 3 input fields empty, primary enabled when all valid) | n/a (empty is the default state) | Primary CTA morphs to .spinner + "Creating account…" | Per-field inline `component.input.field.error`: password-mismatch → Confirm field error "Passwords don't match."; email-already-exists → Email field error "An account with that email already exists. Sign in →" with inline ghost link to `/signin`. |

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

**Auth-error copy bank (Amendment A-20).** Every auth-validation error string is locked here; mockups + engineering must use these verbatim. Each line obeys the "honest, brief, no emoji, no exclamation" rule above. Color treatment is **per-field inline** in `color.signal.warn` (NOT `color.signal.error`, which is reserved for destructive actions) paired with a `⚠` glyph; full visual spec is `component.input.field.error` in DESIGN.md.

| Trigger | Route | Error string |
|---|---|---|
| Invalid email format | `/signup` | "That doesn't look like a valid email address." |
| Email already exists | `/signup` | "An account with that email already exists. Sign in →" |
| Account not found | `/signin` | "We don't see an account with that email." |
| Wrong password | `/signin` | "That password doesn't match. Try again or reset it." |
| Password too short (< 8 chars) | `/signup` | "Use at least 8 characters." |
| Passwords don't match | `/signup` | "Passwords don't match." |
| Forgot-password email-sent | `/reset-password` | "We've sent a reset link to {email}." |

**Account-enumeration rule (locked).** The `/signin` surface always renders errors on the **Password field**, regardless of which side actually failed (wrong email + right password vs. right email + wrong password). Telling an attacker "this email is not registered" leaks the user database — the attacker can enumerate valid accounts. The `/signup` surface may safely surface "this email is already registered" because signup is opt-in registration (the user is offering their own email); revealing that a given email is taken is information the user already half-suspected and helps them recover via the inline "Sign in →" ghost link. The enumeration guard applies to **signin only**.

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
Desktop left-rail navigation. Replaces any topbar nav on desktop. Same routes as `Component.BottomTab` plus the Browse surface (Amendment A-10).

- **Layout:** Sticky left `<aside>`. Width 220px on `md`, 240px on `lg+`. Background `color.surface.paper` (same as canvas — the sidenav is a layout container, not a visual element). Inset from page edge: `spacing.6` (24px) on top and sides.
- **Brand mark:** At the top of the sidenav — 28×28 logo + "EventPulse24" wordmark in `Text.Body` `color.ink.primary`. Below the brand: 1px `color.border.subtle` divider.
- **Route items:** **Six-route variant (post-A-10, canonical going forward):** Digest / Timeline / Add / **Browse** / Conflicts / Settings in `Text.Body` `color.ink.secondary`. Resting state on the page background. Active item: `color.ink.primary` label on a `color.surface.subtle` pill background with 1px `color.border.subtle` stroke. The active pill mirrors the `Control.Segmented` ink-inversion pattern in miniature — no terracotta fill on the active route. **Five-route variant (onboarding only):** the same spec minus Browse, retained for the onboarding batch (transitional state — user has signed up but not entered the app, Browse is not relevant to the onboarding funnel). The onboarding batch is the only sanctioned place the 5-route order still appears in production.
- **Browse glyph (Amendment A-10):** A stroke-only compass SVG (16×16, `stroke-width: 1.6`, `currentColor` stroke, no fill). Sanctioned alongside the 5 existing glyphs. Same nav-item row geometry; no special-casing.
- **Keyboard:** `Tab` cycles through sidenav links after the topbar (topbar comes first in tab order) and before page content. `g d` / `g t` / `g a` / `g b` / `g c` / `g s` shortcuts route directly. (The `g b` Browse shortcut is added in Amendment A-10; existing shortcuts are unchanged.)
- **Topbar interaction:** The topbar still carries only the brand mark + (optionally) the tagline. The sidenav is the nav, the topbar is the identity zone (topbar-quiet rule, ASSUM-11). No affordance duplication.
- **Global reset prerequisite:** The sidenav renders five or six `<a>` route items plus an `<a>` `account-row` in the footer. The page's global CSS must include `a { color: inherit; text-decoration: none; }` (or the host CSS reset must already kill link underlines), otherwise the browser default renders visible underlines under every sidenav label and the Account row. This is a silent contract: mockups that previously had no nav anchors in the topbar zone (e.g., the empty-state and personal-event-edit files) often lack this reset until the sidenav is applied. When applying the shell to any new mockup, audit for this reset first; if missing, add it alongside `button` and `input` resets. Source incident: 2026-09-06 migration of `pulse-digest-empty-state-desktop.html` and `personal-event-edit-desktop.html` shipped the shell without the reset; user reported underlines on all five nav items + the account row. Patched both files.

### `Component.BottomTab.MoreMenu` (mobile `sm` — Amendment A-10)
Mobile overflow affordance for the 6th authed route (Browse). The bottom-tab stays 5 visible primary slots at 20% width each on mobile; Browse lives behind a 6th slot-shaped affordance ("More") on the right end of the bar that opens an overflow sheet.

- **Layout:** The More slot is the 6th 20% slot on the trailing edge of `component.bottom-tab`. Renders as a `<button>` (not a route link) with the same 16×16 stroke-only SVG + `Text.Meta` label vocabulary as the primary slots. Glyph: a 3×3 grid of small stroke-only dots (or three horizontal dots stacked — both sanctioned; pick whichever the design system ships).
- **No `aria-current="page"`** on the More slot. The corresponding overflow row inside the open sheet carries `aria-current="page"` when on `/browse`.
- **Open behavior:** Tap → opens a `component.sheet` (mobile bottom-anchored sheet per `component.surface.sheet`) anchored above the bottom-tab. The sheet lists overflow routes (Browse today; future routes may add). Each row: 16×16 stroke-only glyph + route label in `Text.Body` `color.ink.primary`, `spacing.3` × `spacing.4` padding, `radius.subtle` (6px), 1px `color.border.subtle` between rows.
- **Close behavior:** Tap outside the sheet (on the dimmed backdrop), swipe-down on the sheet, or `Esc` (mobile keyboards typically omit `Esc`; primary close is tap-outside and swipe-down).
- **Z-index:** Above page content, above the bottom-tab, below modals.
- **Reduced motion:** No slide-in on mount under `prefers-reduced-motion: reduce`; the sheet appears in place.
- **When to omit:** The onboarding batch (no Browse in scope) renders the bottom-tab in its 5-slot 20% geometry with no More slot. The More slot ships when the user has Browse in scope — that is, on every post-onboarding mobile surface (`/digest`, `/timeline`, `/add`, `/conflicts`, `/settings`, `/browse`).

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

### `Component.Topbar.PreAuth` (Amendment A-9 — public/marketing routes; extended A-20)
Brand-only topbar used on the eight pre-auth public/marketing routes: **`/preview` (pulse-preview-desktop.html), `/events/near-me` (city-page-desktop.html), `/events/:id` (public-event-page-desktop.html), `/p/:slug` (share-link-desktop.html), `/pricing` (pricing-page-desktop.html), `/pro/upgrade` (pro-upgrade-cta-desktop.html, states-only showcase — no topbar in the mockup), `/signin` (signin-desktop.html, A-20), `/signup` (signup-desktop.html, A-20)**. These surfaces are anonymous — no sidenav, no nav links, no app affordances. The pre-auth topbar carries identity only (topbar-quiet rule, ASSUM-11); conversion affordances live in the hero CTA, the page footer, and section-level decision moments. The `/signin` + `/signup` addition is in-place (no new heading) — both routes inherit the pre-auth topbar verbatim because they ARE conversion surfaces; placing "Sign in" in the topbar of `/signin` would be the same topbar-quiet inversion as the existing rule forbids elsewhere.

- **Layout:** Full-width top strip, `padding: 28px 0 16px` (desktop) / `padding: 20px 0 12px` (mobile `sm`). Same horizontal gutters as the page container (`spacing.6` / `spacing.10`). Flex layout: brand on the left, no right-side cluster.
- **Brand mark (`brand-wrap`):** The brand-wrap lockup, byte-identical to the authed topbar — 36×36 `mockups/EventPulse24-latest-logo.png` (`<img class="brand-logo" src="EventPulse24-latest-logo.png" alt="" width="36" height="36">`) plus a stacked wordmark column (`EventPulse24` in `Text.Body` `color.ink.primary` weight 600 + "calm intelligence for events" in `Text.Display` italic, `color.ink.muted`, 13px). The PNG includes a near-black halo with a thin red rim — this is a brand-asset artifact shipped with the PNG, **not** a CSS-rendered glow; it is outside the token system and exempt from the terracotta glow rationing rule (DESIGN.md §Color usage rules → Glow). The 36×36 render size keeps the halo within a marketing-page-acceptable visual weight; do not upscale the logo on pre-auth surfaces beyond 40×40 without re-evaluating halo dominance against the void.
- **No sidenav.** The authed `Component.Sidenav.App` does not render on pre-auth routes — there is no current user, no saved events, no conflicts to navigate. Adding a sidenav would falsely imply account-aware navigation (topbar-quiet rule violation by mockup-padding).
- **No nav links, no action buttons.** "Sign in", "Sign up", "How it works", "Log in" — none of these live in the topbar. The brand-wrap carries identity; the hero CTA carries the primary conversion affordance; the page footer carries secondary affordances (Log in, Privacy, Terms, social links). Inversions are bugs.
- **Conversion affordance placement (canonical):**
  - **Hero CTA:** The primary sign-up affordance lives in the hero zone (eyebrow + h1 + lede + CTA cluster). `component.button.primary` "Sign up" is the first primary on the surface; the brand mark is the only thing above it in tab order.
  - **Page footer (`seo-foot` / footer-block):** Login, Privacy, Terms, About, social links, city nav, "Made in [city]" provenance. The footer is where anonymous visitors go to evaluate the product without committing; affordances in the footer carry no conversion pressure.
  - **Section-level decision moments:** `component.card.pro.upsell` on `/pricing` (existing pattern), the Save bar on `/events/:id` public-event-page, the dismissible expanded panel on `/pro/upgrade`. Each decision moment is its own visual zone with `spacing.12`+ whitespace from the next.
- **Keyboard:** Tab order is (1) brand-wrap → (2) hero CTA → (3) page content → (4) footer links. No nav anchors between brand-wrap and hero CTA.
- **Reduced motion:** No entrance animation on the topbar. The brand-wrap appears with the rest of the page.
- **Token alignment:** Reuses `color.ink.primary`, `color.ink.muted`, `color.accent.terracotta` (hero CTA only — same rationing as authed routes). No new hex values, no new CSS variables. The brand mark PNG is the only asset that ships visual content outside the token system.
- **Variant — `/p/:slug` (share-link):** Renders the same brand-wrap topbar; the topbar can be omitted entirely on share-link if the share is being viewed embedded in another context (the page is short, single-event). Locked example: the canonical `share-link-desktop.html` keeps the brand-wrap for shareability ("Who shared this with me?" provenance) but compresses `padding: 12px 0 32px`. Hero carries the shared-by attribution pill. Same chrome rule applies.
- **Variant — `/pro/upgrade` (states showcase):** `pro-upgrade-cta-desktop.html` is a 3-state showcase (inline toast / expanded panel / muted footer) demonstrating the soft-wall pattern. It has no real topbar (the document-level `.page > .container` is the surface; `h1` + `.page-sub` carry the framing). It is documented here as the one pre-auth surface that does not render the brand-wrap — explicitly because it is a states mockup, not a routable surface. When engineering ships `/pro/upgrade`, the surface uses the same brand-wrap topbar as the other pre-auth routes.
- **Migration status (2026-09-06):** Spine exception paragraph locked in this session. The six mockups remain in their prior state (some carry legacy `How it works` / `Sign in` / `Sign up` buttons in the topbar that violate this rule). Migration of those six mockups is deferred to the next build batch — they are documented as known topbar-quiet violations awaiting the same conversion the authed batch received.

### `Component.Surface.Browse` (Amendment A-10 + A-12 merge)
The Browse surface — `/browse`. Authed, location-aware, single-purpose: **browse what's happening in the user's city today + the next 7 days, save what matters.** Visual structure (Amendment A-12) inherits the pre-auth `/c/[city]` city-page vocabulary inside the A-8 shell. The pre-auth `mockups/city-page-desktop.html` is unchanged — it serves SEO crawlers per PRD FR-27, not authed users.

- **When does it load:** Direct navigation to `/browse` from the sidenav (6-route variant) on desktop, from the `component.bottom-tab.more-menu` overflow sheet on mobile. The Digest does **not** deep-link to Browse — Digest is a saved/attention surface; Browse is an unsaved/discovery surface. Cross-links between the two are explicit and one-way: Digest → Browse ("Need a fuller list? Browse tonight + 7 days.") is allowed; Browse → Digest is not (no upsell back to the attention surface; saves are the conversion).
- **Hero (Amendment A-12 — city-page vocabulary, authed content):**
  - **Eyebrow:** `Text.Meta` terracotta dot + "Brooklyn · Tonight + 7 days" in uppercase letter-spaced ink-muted. Mirrors `city-page-desktop.html` L120.
  - **H1:** `Text.Display.xl` (48px source-serif 700) — `Events in *Brooklyn.*` — `<em>` in `color.accent.terracotta` italic. Hero copy is benefit, not positioning.
  - **Lede:** `Text.Body.lg` ink-secondary, max-width 600px — "Browse what's happening nearby. Tap Save to add it to your Pulse."
  - **City-meta pill:** single rounded chip on `color.surface.elevated` 1px ink-faint border — `📍 Brooklyn, NY · 147 events this week · Change city`. The `Change city` link routes to `/settings/account` (same destination as the empty-state recovery). The pill is information-dense and replaces both a stat row and a CTA cluster.
  - **Quota note:** `Text.Meta.md` mono — "Free plan: 0 of 1 save used today · resets 8:00 AM" — small monospace detail below the pill.
  - **No signup row, no SEO footer.** The pre-auth city-page's `.hero .ctas` Sign-up / How-it-works row and `<footer class="seo-foot">` neighbor-cities rail are omitted from the markup entirely (not `display: none`) — they serve crawlers and unauthenticated visitors, not signed-in users.
- **Inline keyword search (Amendment A-11 — replaces the city-page chip rail):** A single `<input type="search">` rendered below the hero, full-width up to `max-width: 720px` (matches the hero column). Field uses `component.input.field` tokens — color.surface.paper fill (documented deviation from spine default of color.surface.elevated, see Amendment A-11 entry). Placeholder: "Search this week — jazz, free, outdoor, tag:music" — teaches the grammar in-place. Replaces the city-page filter chip rail entirely; no chips, no date pickers, no preset toggles.
  - **Query grammar:** Plain words are tokenized (whitespace-split, lowercased, trimmed) and matched AND-style against the card's headline + `where` line + the why-tag tokens. `tag:<token>` literals constrain the match to the why-tag set only and are also AND-matched against any plain words.
  - **Tag vocabulary:** `tag:music` · `tag:tech` · `tag:community` · `tag:arts` · `tag:family` · `tag:food` · `tag:sports` · `tag:outdoor` · `tag:indoor` · `tag:rooftop`.
  - **Empty-result state (matches-empty):** When the query returns zero cards, section heads and the grid are removed and a single `component.emptystate.quiet` block renders in their place inside the grid container, full-width: heading "Nothing matched." + `Text.Meta` "Clear" link that resets the input to empty.
- **Section heads + 3-column grid (Amendment A-12 — replaces the day-divider grouping):** Cards are grouped into two attention-tier sections, not by day. Section heads are layout scaffolding, not interactive widgets.
  - **Section head 1:** `Text.Display.sm` (26px serif 600) "3 worth your attention today" + mono meta "Brooklyn · Thu, Aug 27". Replaces the day-divider "Tonight · Thu, Aug 28" pattern. The persona-prefixed "Maya-fit" copy from `city-page-desktop.html` L156 is **dropped** — authed users already converted and persona copy is pre-auth framing.
  - **Section head 2:** "More this week" + mono meta "144 events · scroll for more".
  - **Grid:** `grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 20px;` from city-page L68. Breakpoints: 3-col at ≥1280px (inner width ~876px → 3 × ~279px cards), 2-col at 1024-1279px, 1-col on mobile via `component.bottom-tab.more-menu`. The authed shell uses `padding: 0 32px` on `.main` — the city-page's full-bleed `padding: 0 80px .frame` wrapper is NOT adopted.
- **Cards:** City-page card sizing + A-10 card vocabulary. 22px padding (down from A-10's 24px for the denser grid), 18px headline (down from 22px for legibility at narrower grid widths), 3px left stripe, `Text.Meta` kicker, `Text.Headline.md` headline (≤ 8 words), `Text.Microtag` italic tag row, `Text.Meta.md` source-and-time row, `component.indicator.confidence` row. Browse cards add ONE element: `component.button.save.inline` in the top-right of the kicker zone (see below).
- **Stripes — explicit cap (Amendment A-12):** Two colors only: `color.accent.slate` for public events, `color.accent.amber` for must-know events (max 1 per page, the existing <10% rule). **Discovery stripe dropped** — the discovery vocabulary on `city-page-desktop.html` is pre-auth SEO framing and does not migrate. Three stripe colors would create a category-color flood that violates the anti-pattern list.
- **Card count:** Soft-cap of 24 cards per surface. Past the cap, render a `Text.Meta` "More events below" anchor that loads the next chunk in place. No pagination chrome, no page-number navigation, no "Load more" button.
- **Save affordance:** `component.button.save.inline` (DESIGN.md §Components → Browse surface) in each card's top-right zone. Tap → saves; button morphs to "Saved ✓" in `color.signal.success` over 240ms. Repeated tap → un-saves (no destructive confirmation; the morph is the confirmation). Free-tier save cap (FR-48) applies: 1 free save per 24h; additional saves from Browse count against the same quota as `/digest`. When the quota is exhausted, the Save button morphs to `component.button.ghost` "1 of 1 used today" with a link to `/settings/plan`.
- **Anti-patterns (explicitly forbidden on this surface, sourced from DESIGN.md Brand & Style):**
  - No category-color floods. **No discovery stripe (Amendment A-12 lock).** No more than 2 stripe colors per page (slate + amber at the existing <10% rule).
  - No "X people going" social proof. No "234 attending" counters.
  - No count badges anywhere. No "saved 7" or "47 nearby" or any numeric tag.
  - No infinite scroll. The chunk-load past 24 cards is bounded, not infinite.
  - No gamification chrome. No streaks, no "you saved 5 days in a row!", no badges.
  - No upsell carousels. The single Pro upsell (`component.card.pro.upsell`) lives only on `/digest` and `/settings/plan`; it does not migrate to Browse.
  - No notification badges.
  - No streak popups.
  - No "you might also like" rails beyond the section-head grouping.
  - **No pre-auth CTA leakage (Amendment A-12 lock).** Sign-up / How-it-works CTAs and the city-page's SEO footer neighbor-cities rail do not migrate. The merged surface inherits the city-page's visual structure but not its conversion scaffolding.
  - **No filter chip rail (Amendment A-11 lock).** The `chips` vocabulary from `city-page-desktop.html` (This week / Weekend / Tonight / Free + Category: All / Music / Tech / Community / Arts / Family / Food & drink / Sports) does not migrate. The inline keyword search is the only filter surface.
- **Empty state (zero-events-in-window):** When there are no public events in the user's city within the 7-day window, render the same `component.emptystate.quiet` vocabulary as `/digest`: "Nothing nearby tonight. Try a wider city?" + a `Text.Meta` "Change city" link to `/settings/account` (PRD §4.1 settings city). No carousel, no upsell, no "you might like" rail.
- **No-match vs no-events distinction:** The empty-result state under the search input ("Nothing matched." + "Clear filters") and the empty zero-events state ("Nothing nearby tonight." + "Change city") use the same `component.emptystate.quiet` vocabulary but different copy and recovery action — the user always knows whether the lack of results is from their query or from the data.
- **Loading state:** Browse skeletons match the existing Pulse Digest skeleton vocabulary — paper rectangles fading 1px toward `color.ink.faint` at 60% opacity, 1800ms pulse period. No spinners. Render 12 card-shaped skeletons matching the expected initial chunk size.
- **Error state:** Generic error pattern from §5: "Couldn't reach Browse. Try again." Single retry button. The sidenav and bottom-tab nav remain functional so the user can escape.
- **Keyboard:** `Tab` cycles through cards (each card's Save button is the tab stop; the card body itself is not a button — Save is the single affordance per card). `g b` routes directly to `/browse`.
- **Reduced motion:** No entrance animation on cards. The Save morph is the only motion on the surface; under `prefers-reduced-motion: reduce`, it collapses to an instant label swap (no 240ms fade).
- **Token alignment:** Reuses every card vocabulary token from `component.card.pulse.digest` + `component.button.save.inline` + `component.input.search.browse` + `component.hero.citypage` (the hero / city-meta vocabulary inherited from the city-page, A-12). No new hex values, no new CSS variables, no new spacing tokens. Reuses the existing `component.sidenav.app` 6-route variant.

### `Component.Button.Save.Inline` (Amendment A-10)
The quiet Save affordance on Browse cards. Visual spec lives in DESIGN.md §Components → Browse surface (`component.button.save.inline`); this entry is the behavioral contract.

- **State machine:** `idle → saving → saved → idle`. `idle` label: "Save". `saving` (during server roundtrip, ≤800ms local): "Saving…" in `color.ink.muted`. `saved` (after server confirms): "Saved ✓" in `color.signal.success`, persisted for at least 1500ms before another interaction is allowed (avoids flicker). From `saved`, tap again → `idle` with no destructive confirmation (the morph is the confirmation).
- **Failure mode:** If the save fails (network, quota-exceeded, conflict detected), the button morphs to a 1-line inline message below the button — no modal, no toast. Quota-exceeded: "You've used your 1 free save today. Upgrade for unlimited." with a `Text.Meta` "Upgrade" link to `/settings/plan`. Conflict detected: "Conflicts with your saved dinner. Open Detail to resolve." with a `Text.Meta` "Open" link to `/events/:id`.
- **Free-tier cap integration (FR-48):** When the user has used 1 of 1 free saves in the current 24h window, all Save buttons on Browse render in the muted "1 of 1 used today" state — they are still visible (so the user sees what's available) but disabled. Tapping a disabled Save button does nothing; the disabled state carries a `title="Upgrade for unlimited saves"` tooltip. This is the same soft-wall pattern as `/digest`; the implementation reuses the existing quota-check service.
- **Pro tier:** Pro subscribers (FR-48) have no save cap. The Save button morphs and persists indefinitely, no quota-exceeded state.
- **Accessibility:** Each Save button is a real `<button>` with `aria-label="Save {event name} to my Pulse"` (the event headline is included in the accessible name; visible label stays "Save" for visual economy). Focus: 2px `color.accent.terracotta` ring at AA contrast. The morph to "Saved ✓" includes `aria-live="polite"` on the button so screen-reader users hear the confirmation without the focus moving.
- **Keyboard:** `Enter` or `Space` on a focused Save button triggers the state machine. `Esc` cancels an in-flight save (sets the button back to `idle`; server-side rollback is the responsibility of the save endpoint).
- **Reduced motion:** Under `prefers-reduced-motion: reduce`, the 240ms fade collapses to an instant label swap.

### `Component.Settings.QuietHours.Pro` (Amendment A-19 — Pro tier, MVP)
Pro per-day Quiet Hours picker — extends the single-window Free control with a vertical 7-row list (Mon–Sun). Closes PRD §8.1 row 7 Pro-tier value prop. Visual spec lives in DESIGN.md §Components → Inputs (`component.control.day-picker`).

- **Anatomy:** Each row contains a day-name (`Text.Body.md` display weight), an active-window chip in `Text.Meta` mono (e.g. "10pm–8am"), and an ink-inversion activation toggle on the right (NOT terracotta — the small-control selected-state rule applies). Tap a row to expand an inline time-range picker beneath it; two `control.preset` rows (start-time, end-time) let the user pick common hours. Tap "Reset to default" inside the expanded row to revert that single day.
- **Tier-gate affordance:** A `Badge.Source.verified`-style "Pro · per-day" pill sits to the right of the h1 on this page for at-a-glance recognition of tier value. Free users who reach `/settings/quiet-hours` via a deep link see the same page but with all 7 rows locked (toggle at 0.4 opacity, lock glyph next to each day-name, microcopy "Upgrade for per-day quiet hours" on hover). The Free single-window control stays at the top of the page.
- **Default values:** "10pm–8am" matches the Free-tier default, so a downgrade never silently changes a user's previous configuration. The "Reset all to default" footer is a bulk-action safeguard — it requires an explicit confirmation tap (not shown in the mockup; ENGINEERING NOTE: a confirmation modal analogous to `Component.Modal.AccountDelete` is required before applying the bulk reset).
- **Propagation rules:** Quiet hours are stored in the user's home timezone (browser-detected; user can override in `Account → Timezone`). When the user travels across timezones, the system converts to local time on a per-event basis at notification-fire time (not at storage time). DST handling: the system snaps the start-time to the user's selected wall-clock hour; an event scheduled during the spring-forward gap defers by 1 hour, an event scheduled during fall-back is sent once (no duplicates).
- **Accessibility:** Each row's heading is a `role="button"` with `aria-expanded`. The toggle is a real `<button aria-pressed>` with a visible focus ring. The expanded time-range picker inherits the modal focus-trap pattern from `Component.Modal.AccountDelete` (Amendment A-16) — Tab cycles between the two preset rows and the row's actions; Esc collapses the row.
- **Keyboard:** `Enter` or `Space` on a focused row expands/collapses the time picker. `Tab` moves to the toggle, then to the next day's row. `Esc` collapses any expanded row.
- **Reduced motion:** Under `prefers-reduced-motion: reduce`, the row-expansion animation collapses to an instant reveal.

### `Component.Settings.Sources` (Amendment A-18 — MVP, transparency)
Settings page that surfaces every source contributing to the user's Pulse digest. Closes PRD FR-13 transparency gap. Visual spec lives in DESIGN.md §Components → Inputs (`component.control.source-mute`).

- **Anatomy:** Sources are grouped into 4 categories — Official (verified venue accounts), Community (community-maintained feeds), Aggregator (third-party aggregators like Eventbrite), Crawled (site-scraped). Each row carries a source-name (with verified-badge for Official sources), a 1–5 reliability-dot indicator (`color.ink.primary` fills — NOT the terracotta confidence pulse from `Indicator.Confidence`), and a 3-state `control.source-mute` control: `Mute / Show less / Default`. The selected state uses ink-inversion, not terracotta.
- **Reliability scoring:** The 1–5 dot count is sourced from a transparent trust algorithm — inputs include cross-source corroboration count, last-crawl freshness, and the proportion of `event.status = cancelled` over the last 90 days. The score updates weekly; users see the latest value, not a stale snapshot. **As built (FR-16):** the score is the beta-binomial posterior over the source's observed outcomes (`domain/reliability.py`), floored at 0.32 until the source has 30 observations, and read as the 0.50 prior when the recompute has never reached it. The dots are the **stored score** banded 1–5 (`source_trust_band`), never a week-over-week delta — a 3× drop is provably impossible, so a delta would assert something the domain says cannot happen. **0.50 is band 3** ("ok"), so a never-scored source reads as unproven rather than bad. The band is the server's number; the client draws it and does not recompute it.
- **Mute semantics:**
  - **Mute** — the source is excluded entirely from the digest. Saved events from the source stay saved; new events never appear. No toast on mute (silent — the segmented control's selected state is the confirmation).
  - **Show less** — the source contributes events but the digest ranks them below Default-tier sources. The user still sees them in `/browse` filtered to that source. **As built:** "show less" is a **post-score penalty applied outside FR-22's published formula** — the formula is exactly five weighted terms summing to 1.00 and is pinned against ADR-0025 (PRD **Amendment A-25**), so a penalty cannot be a sixth term. It is applied to the score the formula produced, before the ordering, so the formula and its pin stay byte-identical. A show-less that *hid* events would be indistinguishable from a mute on the wire and would lie to a user who asked for fewer rather than none.
  - **Default** — the source's natural rank; whatever the ranking algorithm produces is what the user sees. **As built:** Default is the *absence* of a preference row, not a third stored state, so "Restore all defaults" is a single bulk delete.
- **Bulk reset:** A footer ghost button "Restore all defaults" resets every source to its default visibility. Per §10.4 bulk-action safeguard, this requires an explicit confirmation tap (not shown in the mockup). **As built:** the confirmation replaces the button **in place** — a two-step, not the type-to-confirm pattern of `Component.Modal.AccountDelete`, which is reserved for account deletion (A-16 reserves that weight). The endpoint is a single idempotent bulk delete, and the confirmation is the client's job: a server-owned confirmation would have to survive a page refresh, which is a state machine to buy a dialog. **No request is sent on the first press.**
- **Privacy mirror:** `/settings/privacy` mirrors this same list (read-only) — users can see "what sources inform my ranking" without leaving the Privacy section. The Privacy mirror does not include the mute controls (mutes live on `/settings/sources`).
- **Accessibility:** Each segmented control is a `role="group"` with an `aria-label` naming the source. The selected button carries `aria-pressed="true"`. The verified-badge is a `title` + `aria-label` "Verified by EventPulse24".
- **Keyboard:** `Tab` moves through rows; arrow keys move within the segmented control. `Enter` selects.
- **Reduced motion:** N/A — segmented control selection is an instant ink-inversion swap, no transition.

### `Component.Modal.AccountDelete` (Amendment A-16 — MVP, account deletion)
Confirmation modal for `Settings → Privacy → Danger zone → Delete account →`. Closes PRD §10.1 + §14.1 cascade gap. Visual spec lives in DESIGN.md §Components → Inputs (`component.modal.account-delete`).

- **Anatomy:** Centered modal on `component.surface.modal`, max-width 480px, border-radius 16px. Header: `Text.Headline.md` "Delete your account?" Body: 3 paragraphs in `Text.Body.md` — (1) what gets deleted (account, personal events, saved events, preference graph within 30 days), (2) what survives (anonymized aggregates), (3) the 30-day grace period. Type-to-confirm input field with placeholder "Type DELETE to confirm" — the primary submit button stays disabled until the input value matches the literal string `DELETE` (case-sensitive).
- **Trigger flow:** Tap `Delete account →` on Settings → Privacy → Danger zone → modal opens over a backdrop-filtered dim of the Privacy page. Focus moves to the input field; the modal traps focus.
- **Cancel:** Closes the modal. No state change. No toast. Focus returns to the `Delete account →` button in the danger-zone row. The 30-day timer is NOT started.
- **Confirm (after typing `DELETE`):** Submits to the delete-account endpoint. On success, the modal morphs to a state-change confirmation (not shown in mockup; ENGINEERING NOTE: analogous to `Component.Modal.ExportRequest` success-notice pattern): "Your account is scheduled for deletion in 30 days. Cancel anytime from Settings → Privacy or from the email we sent." The Privacy page's danger-zone row also updates to a cancellable state.
- **Backdrop interaction:** Clicking outside the modal closes it (treats as Cancel). `Esc` closes it.
- **Accessibility:** Modal uses `role="dialog"` + `aria-modal="true"` + `aria-labelledby` + `aria-describedby`. The type-to-confirm input is `aria-describedby` connected to the helper hint ("Case-sensitive. The button activates once this matches."). Submit button has `aria-disabled` reflecting its state. Focus-trap pattern from the modal shell (see `Component.Modal.ExportRequest`, A-17).
- **Keyboard:** `Tab` cycles between input, Cancel, Confirm. `Enter` on the input does NOT submit — it must be a deliberate button tap. `Esc` closes.
- **Reduced motion:** Under `prefers-reduced-motion: reduce`, the 240ms backdrop fade collapses to an instant dim.

### `Component.Modal.ExportRequest` (Amendment A-17 — MVP, data export)
3-state modal triggered by `Settings → Privacy → Danger zone → Request export`. Closes PRD FR-52 partial gap. Visual spec lives in DESIGN.md §Components → Inputs (`component.modal.export-request`).

- **3 user states (rendered variant chosen at modal-open time, server-side):**
  - **Free user in EU/UK/CA/BR/AU:** `jurisdiction-badge.eu` (signal-success tint), body copy "You're in {country}, so this export is free under data portability rights." Primary CTA: "Request export". On submit: success-notice replaces the footer — "Export started. We'll email {user.email} within 24 hours."
  - **Free user outside EU/UK/CA/BR/AU:** `jurisdiction-badge.gate` (terracotta tint), body copy "You're in {country}. Data exports outside the EU/UK/CA/BR/AU require Pro — it covers the storage and routing costs beyond what free users can sustain." Primary CTA: "Upgrade to Pro → Export". On submit: routes to `/settings/plan`, NOT to the export endpoint.
  - **Pro user:** `jurisdiction-badge.pro` (amber tint), body copy "Your archive will be ready within 24 hours. We send a one-time download link — the link expires after 7 days." Primary CTA: "Request export". On submit: same success-notice as Free-EU path.
- **Anatomy:** Centered modal, max-width 480px. An itemized "what's included" list (saved events, personal calendar events, preference graph, mute & quiet-hours settings, audit log for Pro) sits below the body copy. Footer: secondary Cancel + primary CTA. Post-submit state: success-notice replaces the footer actions; only a Close button remains.
- **24h SLA enforcement:** The success notice is binding — engineering must guarantee the export is emailed within 24h. Server-side debounce: only ONE active export per user at a time (a second request before the first resolves shows an inline message "Export already in flight — check your email").
- **In-flight affordance:** The primary CTA morphs to a spinner + "Requesting…" for 720ms during the roundtrip. Under `prefers-reduced-motion`, the spinner is static.
- **Accessibility:** Same dialog semantics as `Component.Modal.AccountDelete` (A-16). The success notice uses `role="status"` + `aria-live="polite"` so screen readers announce the confirmation without focus moving.
- **Keyboard:** Standard modal focus-trap. `Esc` closes.
- **Reduced motion:** 720ms spin collapses to a static indicator.

### `Component.Surface.Timeline.AmendmentHistory` (Amendment A-13 — MVP, transparency)
Inline ranking-algorithm amendment-history timeline at the bottom of `Settings → Privacy → Ranking algorithm version`. Closes PRD §10.1 + FR-22 transparency sub-gap.

- **Anatomy:** A vertical timeline under the existing ranking-bucket display. Each entry is a `<li class="timeline-item">` with: a leading dot (terracotta for the latest entry, ink-muted for older entries), a title (`Text.Body.md`), a date (`Text.Meta` mono), and an ADR reference (e.g., "ADR-0022 — v1.0 MVP launch" hyperlinked to the ADR document).
- **Lifecycle:** New entries are prepended on PRD-sign-off via the changelog mechanism documented in PRD FR-22. The oldest visible entry is "2026-08-19 — Pre-launch review (ADR-0020)"; the latest is "2026-08-29 — v1.0 MVP launch (ADR-0022)".
- **Read-only:** Entries cannot be edited or deleted from the UI. Each entry's ADR link is the source of truth.
- **Accessibility:** The timeline is a `<ol>` with `aria-label="Ranking algorithm amendment history"`. Each `<li>` carries the date and ADR reference in a visually-hidden `<span>` for screen readers.
- **Keyboard:** Each ADR link is a standard focusable anchor with the global focus ring.

### `Component.Control.Toggle.Location` (Amendment A-14 — MVP, privacy)
Geo-IP opt-out toggle on `Settings → Privacy`. Closes PRD FR-2 + §10.1 persistent-toggle sub-gap. Visual spec lives in DESIGN.md §Components → Inputs (`component.control.toggle.location`).

- **Anatomy:** A 2-position segmented control: "Use my approximate location" / "Don't use location". The selected state uses ink-inversion, not terracotta. Default state: ON. The row sits above the existing "Training opt-out" row in the Privacy section.
- **Behavior:** Off-state persists in a cookie. Once toggled off, the `geo-consent-banner` never re-prompts. Off-state falls back to the most-popular city (NYC) per PRD FR-2. A `Text.Meta` line beneath the toggle reads: "We'll use the most popular city instead" so the fallback is transparent.
- **First-visit vs persistent:** The first-visit experience is the existing `geo-consent-banner-desktop.html` modal. Once the user makes a choice (whether accept or dismiss), this toggle is the durable record of that choice.
- **Accessibility:** The segmented control is a `role="radiogroup"` with two `role="radio"` buttons. Standard arrow-key navigation between radios.
- **Keyboard:** `←` / `→` switches between the two options. `Enter` is a no-op (the selection is the act).

### `Component.Badge.SoldOut` (Amendment A-15; extended by A-22 — MVP, event lifecycle)
Status badge on Pulse Card and Detail Screen, for the three states an event can reach: **sold out**, **cancelled**, **postponed**. Closes PRD FR-53 / FR-54 partial gap. Visual spec lives in DESIGN.md §Components → Badges and indicators (`component.badge.soldout`).

- **Anatomy:** Small ink-bordered pill (`{color.surface.subtle}` fill, 1px `{color.border.strong}` stroke, `{radius.subtle}`, padding `{spacing.1}` × `{spacing.3}`). Label in `text.scale.meta.sm` — uppercase, weight 600, 0.06em letter-spacing — reading "Sold out", "Cancelled" or "Postponed". (A-22 settles the typography on this document's values: the mockup's mono family and 0.08em tracking are the mockup's own styling and are not adopted.) A leading glyph in `color.signal.warn` (NOT terracotta): `⊘` sold out, `✕` cancelled, `↦` postponed. The pill background is `color.surface.subtle`; the border is `color.border.strong`. No desaturated-grey variant — the warn amber is the canonical signal. **A-22 changed the sold-out glyph from `●` to `⊘`:** `color.signal.warn` and `color.warn.amber` are the same hex, so a filled circle here would be the conflict indicator's shape in the conflict indicator's colour, in the same card. The glyph is hollow where the conflict dot is solid — same hue, different figure. The three states differ by **shape and label only**; no new colour token is introduced.
- **Placement:** Pulse Card: sits in the right-side zone, in **its own row immediately above the title row** (NOT the left-edge category stripe — the 3px stripe stays visible for category identity, and NOT the trust-signal row, which is at capacity). Detail Screen: a soft "Sold out" stripe appears under the title, sitting above the description.
- **Lifecycle:** Appears when the event is sold out, cancelled or postponed (FR-53 / FR-54). Persists until the event ends (no auto-removal on a state reversion). Removed entirely when the event ends — never recycled into another state. A **cancelled** event's badge replaces the badge a **sold-out** one would carry: the cancellation wins, because a cancelled event has stopped happening, and a badge reading "Sold out" on it would invite a reader to wait for tickets for an event that is not happening.
- **Pair with CTAs:** On Pulse Card: the existing "Save Reminder" CTA is **removed**, not greyed, not "Notify me when available". A **sold-out** or **postponed** event keeps its share control — it is still published and still has a public page. A **cancelled** event is still published and still has a public page — the catalog's public read excludes only superseded events — so the server sends its `public_slug` and the **share control stays**: a reader who wants to tell a friend that an event was cancelled needs a link to the page that says so. The card's own link to the Detail Screen stays too, because a reader who sees "Cancelled" may want to read why. On Detail Screen: a calm single-line "Sold out — tickets no longer available." replaces the Save & Reminder actions. A "Find similar events" link is surfaced only on Detail Screen (not on the card) — quietly resolves the user's likely next intent without upselling.
- **Notification pairing:** Sold-out state change triggers exactly one in-app + email notification (per FR-54), capped at one state-change notification per event per day. Future state changes (e.g., a cancellation) replace, not stack.
- **Accessibility:** **The badge is `aria-hidden`** (A-22). The Pulse Card's own link — the tap target and the only focusable thing in the card — carries the state's name in its `aria-label`, so a link-navigating reader hears it; the badge is hidden from the accessibility tree so a browse-mode reader does not hear the same fact **twice** in one card. The **visible** label stays, because it is what makes the state legible at a glance. The leading glyph has `aria-hidden="true"` too. **Colour is never the sole carrier of meaning (WCAG 1.4.1):** the visible label carries it, and the card's `aria-label` names the state for a reader who navigates by link.

### `Component.Auth.SignIn` (Amendment A-20 — MVP, returning-user landing)
`/signin` returning-user landing surface. Closes the FR-4 session-restored-routing gap — currently users whose session expired are silently redirected to onboarding, which violates the calm contract for users who have already converted. Visual spec lives in DESIGN.md §Components → Inputs (`component.input.field.error` + `component.auth.input.password`).

- **Trigger:** Tap "Log in" in the footer of `/preview`, `/events/near-me`, `/events/:id` (public-only), `/pricing`, `/pro/upgrade`, or any pre-auth surface. Direct URL navigation: `/signin`. Returns the user to session if the cookie is still valid (silent redirect to `/`); otherwise renders the form.
- **Anatomy:** Centered form on `layout.container.form` (480px column — narrower than the 720px onboarding column because auth forms are single-decision, not content-rich). Pre-auth `Component.Topbar.PreAuth` above; pre-auth page footer below (`Component.Footer.PreAuth` — the byte-identical footer block reused from `pulse-preview-desktop.html`). Form contains: `component.input.field` × 2 (Email + Password), `component.auth.input.password` reveal toggle on the Password field, a `Text.Meta` ghost link "Forgot password?" right-aligned in the actions row, and a `Button.Primary` "Sign in" (terracotta) on the same row as the forgot-password link. Below the actions row: a footer block with a cross-link "New to EventPulse24? Sign up →" + a 1-line privacy footnote ("By signing in, you agree to our Terms and Privacy Policy.").
- **State machine:** `idle → validating → submitting → success-or-error`. `idle` shows the empty form, both fields below the validator threshold (length 0). `validating` runs as the user types — client-side email format check fires on blur of the Email field (not on every keystroke; that would be hostile). `submitting` morphs the primary CTA to a `.spinner + "Signing in…"` (mirrors A-17 `Component.Modal.ExportRequest` — 720ms linear, `prefers-reduced-motion: reduce` → static dot). On 200 OK, route to `/` (or the user's last-visited authed route if available in the session cookie; default `/`). On 4xx, re-enable the primary + render State B's error.
- **Variant states (per the mockup variants strip):**
  - **State A — valid input:** primary enabled. The rendered default state above the variants strip.
  - **State B — wrong password (server-side):** the Password field receives `.has-error`; border shifts to `color.signal.warn`; `.field-error` row renders below: "That password doesn't match. Try again or reset it." with inline links "Try again" + "reset it" → `/reset-password`. Account-enumeration rule applies: even if the failure was actually "no account with that email," render the error on the Password field, not the Email field.
  - **State C — in-flight:** primary CTA disabled (`aria-busy="true"`), label swaps to `.spinner + "Signing in…"`. Both fields become read-only to prevent flicker.
- **Accessibility:** Standard form semantics — each input has a `<label>` (in `text.scale.meta.sm` mono uppercase); each error has `aria-describedby` linking it to the input + `role="alert"` for live announcement. The reveal toggle has `aria-pressed` reflecting current state + `aria-label` describing the *destination* state ("Show password" / "Hide password"), not the current state (screen-reader users don't need to hear "password is currently hidden" every time the toggle receives focus — they need to know what tapping will do). The page has a `<main>` landmark; the form is the only interactive region; tab order is brand-wrap → topbar skip (none here, topbar-quiet rule) → Email → Password → reveal toggle → forgot-password link → primary submit → footer links.
- **Keyboard:** `Tab` cycles in DOM order. `Enter` on a focused input submits the form (default behavior; both inputs are inside the `<form>`). `Shift+Tab` cycles back. There is no modal focus-trap because this is a full-page route — `Esc` does nothing form-level (the inputs handle Esc natively, clearing the focused field).
- **Reduced motion:** The 720ms spinner collapses to a static dot. Border color transition is instant.
- **Forgot-password flow:** Tap "Forgot password?" → routes to `/reset-password` (a single-input email field + primary "Send reset link" CTA + the same locked copy "We've sent a reset link to {email}." success notice). Visual is deferred — the lock-step is one inline success notice using the existing `.form-footer` vocabulary.

### `Component.Auth.SignUp` (Amendment A-20 — MVP, account creation)
`/signup` account-creation step. Splits the auth-mechanism choice off the calendar-connect step so the post-signup onboarding flow stays within FR-1's ≤3 user-visible steps. Visual spec lives in DESIGN.md §Components → Inputs (`component.input.field.error` + `component.auth.input.password` + the existing `component.button.provider`).

- **Trigger:** Tap "Sign up free" in the footer of any pre-auth surface, or the hero CTA on `/preview` / `/events/near-me`. Direct URL navigation: `/signup`.
- **Anatomy:** Centered form on `layout.container.form` (520px column — slightly wider than `/signin` to fit the OAuth stack). Same pre-auth shell as `/signin`. Form is split into two zones, top-to-bottom:
  1. **OAuth stack** — `component.button.provider` × 3 stacked vertically (Google → Apple → Outlook per alphabetical, with Google first because Google accounts dominate sign-up conversions). All three at *equal visual weight* per the calendar-connect parity rule in DESIGN.md L286 — no primary CTA styling on a single provider. Each button: 32×32 monogram tile + provider name in `Text.Body.md` weight 600 + sub-label "Auto-connects your {calendar}" + a right-arrow `→` affordance.
  2. **"or" separator** — 1px `color.border.subtle` line on each side, with the word `or` in `text.scale.meta.sm` mono uppercase in the middle. Mirrors the visual rhythm of `onboarding-step1-desktop.html`'s OAuth ↔ email/password transition (same component vocabulary, just relocated to its own route).
  3. **Email/password form** — `component.input.field` × 3 (Email, Password, Confirm password); `component.auth.input.password` reveal toggle on both Password fields; a `Text.Meta` hint below the Password field ("8 characters minimum") in `color.ink.faint`; `Button.Primary` "Create account" right-aligned below the third field.
- **Order of operations:** OAuth buttons first, email/password below. Rationale per UX heuristic: users with existing Google/Apple/Outlook accounts (the majority of sign-up conversions) can complete in 2 taps; users without accounts email-typed the alternative path; the OAuth-first ordering reduces friction for the larger cohort without penalizing the smaller one.
- **State machine:** `idle → client-validating → submitting → success-or-error`. `submitting` morphs the primary CTA to `.spinner + "Creating account…"`. On 200 OK, render a single `Text.Meta` inline notice "Account created. Taking you to onboarding…" (1.5s hold, then `location.href = '/onboarding'`). On 4xx, render the relevant State B or State C error.
- **Variant states:**
  - **State A — valid input:** all three fields filled with valid values; primary enabled. The rendered default state above the variants strip.
  - **State B — password mismatch (cross-field):** the Confirm field receives `.has-error`; password-mismatch error renders below it. The Password field stays valid (the user already typed it correctly — clearing it would be unkind). Copy: "Passwords don't match." Validation fires on Confirm blur AND on form submit.
  - **State C — email already exists (server-side 409):** the Email field receives `.has-error`; copy renders with an inline ghost link to `/signin`: "An account with that email already exists. Sign in →". Password fields stay intact. Account-enumeration exception applies: signup is opt-in registration, so revealing "this email is taken" is acceptable and helps the user recover.
- **OAuth hand-off:** Tap any provider → redirect to `{provider}.com/oauth/authorize?client_id=...&redirect_uri=/api/oauth/callback&scope=calendar.readonly`. On callback, calendar is auto-attached (no onboarding-step1 needed) and the user lands at `/onboarding` step 2 (interests), skipping step 1 entirely. Email/password users go through step 1 normally.
- **Accessibility:** Same as `/signin` — form semantics, `aria-describedby`, `role="alert"` on errors, focus order. The OAuth stack is a `role="group"` with `aria-label="Continue with calendar provider"`. The "or" separator is `aria-hidden="true"` (decorative; the OAuth ↔ email/password transition is visually clear without announcing the word "or").
- **Keyboard:** Same as `/signin`. Tab order: brand-wrap → Google → Apple → Outlook → Email → Password → Password reveal → Confirm → Confirm reveal → primary submit → footer links.
- **Reduced motion:** Same as `/signin`. The 1.5s success-hold collapses to 0ms (instant redirect).
- **Skippability:** Per FR-1, no step is required. The user can close the tab at any point and resume later via `/onboarding` (their account creation is incomplete server-side; the partial account is purged after 30 days).
- **Post-signup routing lock:** `/signup` always routes to `/onboarding` step 1 on email/password success (calendar connect still optional). OAuth users skip step 1 entirely (auto-connect already done). `/signin` routes to `/` (or last-visited authed route). Neither routes to `/` directly.

---

## 5. State Patterns

Global state decisions. Each pattern is invoked wherever the relevant state is encountered.

### Empty Patterns

**Empty Pulse Digest (`/`)** — the cardinal empty state:
- Copy: "Nothing on the pulse today. The calendar is yours."
- Visual: A single `Card.PulseDigest` variant (no second card). Card body shows the headline in `Text.Display.sm`. Below the card: a single line in `Text.Meta` reading "No qualifying events in {city}."
- **No CTA. No carousel. No "Explore trending events" upsell. No upsell at all.**
- **No link. (Amendment A-26.)** This row previously specified a small "Suggest an event" link in `Text.Meta` ink color, low visual weight, opening a `/suggest` form (PRD FR-8). **It is withdrawn, not deferred** — `/suggest` exists in no layer of the product and no FR ever asked for one, so the link could only ever 404, which it did until 2026-11-20. The empty state now carries the card and the `Text.Meta` city line and nothing else, which is what the No-CTA rule above already asked for. See the A-26 note in `updated_note` and at PRD FR-8.
- Reasoning: A user opening Pulse to nothing should feel the absence of the product's noise, not be marketed at. The empty state is the product's strongest voice.

**Empty saved collection:** "Nothing saved yet. Tap a card to save it." Single primary CTA pulses to the home.

**Empty Preview (SEO referrer) — `/preview`:** **Withdrawn by Amendment A-26; never built.** This row specified that when the preview list is empty AND the document referrer is a search engine (e.g. Google, Bing, DuckDuckGo), a single subtle `Text.Meta` "Suggest an event" link render below the empty copy, opening `/suggest?city={city}` with the city pre-filled, and shown to no other referrer. `components/preview/preview-section.tsx` renders the empty copy and has never rendered the link, so unlike the digest the promise here was unkept rather than broken. **It is withdrawn so a later build cannot reintroduce a dead link on a second surface** — `/suggest` exists nowhere. **The rationale is preserved because it is the condition for revisiting, not because it was wrong:** *"SEO cold-start is the unlock (§1 Foundation); a brand-new visitor from Google 'events near me {city}' who hits the empty state must have a path to express interest without breaking the No-CTA Discipline for the rest of the audience."* That argument is unfunded, not refuted — a visitor in an uncovered city genuinely has no other way to signal that they exist. If a suggestion feature is ever specified, **this placement is the strongest case for where it lands first, and this row should be restored before the digest link is.**

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
| **Hovered / focused (Timeline event-block, desktop)** | Mouse hover or Tab focus | Adds location (`Text.Meta`) only (**Amendment A-24**). The Why-this Tag this row once promised is **withdrawn, not deferred** — on a surface that shows only saved events the tag is uninformative by construction; see the A-24 note in `updated_note`. The full Why-this breakdown remains on the Detail Screen, never on Timeline. |

### Anti-pattern: progressive disclosure that hides trust signals

Adaptive density must not hide the trust signals (Why-this Tags, Confidence Pulse, Source Badge) at any density mode. The mobile default exposes all three; hover/focus/long-press *add* detail but never *remove* the trust signals. PRD §13.1: "Why-this Tags are first-class."

**Scope (Amendment A-24):** this rule governs the **Pulse Card**, whose mobile default exposes all three signals — that default is what the rule protects. The **Timeline event-block** carries none of the three at any density mode: its default shows name, time, the Personal / Public label and the conflict indicator, and nothing else. A-24's withdrawal of its hover Why-this Tag therefore **removes no trust signal** — it retires a promise that was never kept — and the full Why-this breakdown remains on the Detail Screen, where §13 has always placed it. The rule is unchanged and undiminished for every surface that does expose the signals.

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
| 8 | Conflict Resolution prompt | `Sheet.ConflictResolution` | `conflict-prompt-desktop.html` | `conflict-prompt-mobile.html` | FR-58 **+ FR-55**. Three forced choices, no dismiss. **FR-55 added 2026-11-12 — the same surface, a second trigger.** FR-58 fires when the *user* creates a clash; FR-55 fires when an organiser postpones an event *into* one. Both read the same `CONFLICT_PAIR` row, which AD-21 makes the single source for every conflict indicator — so the reuse is architectural, not incidental. TRACEABILITY.md scored FR-55 `PARTIAL (inferred only)` for the absence of exactly this acknowledgment. |
| 9 | Empty Pulse Digest | `/` empty state | `pulse-digest-empty-state-desktop.html` | _(covered by pulse-digest-mobile empty)_ | FR-8. Includes suggested-sources strip. **Filename corrected 2026-11-12 (A-23):** this row named `empty-pulse-digest-desktop.html`, which does not exist and never has. The design was always present and self-tags `FR-8`; only the reference was wrong. Found by auditing every filename in this table against `ls`, after two other rows in it proved unreliable. |
| 10 | Settings (theme, notifications, quiet hours, calendar, account, plan) | `/settings/*` | `settings-desktop.html` | _(deferred — desktop-first at MVP)_ | FR-7 / FR-12 / FR-48 / FR-51 / FR-52. **~~FR-49~~ struck (2026-11-12): this file contains zero collection content** — verified by count, `collection` ×0, against `quiet` ×10, `Pro` ×7, `export` ×4. TRACEABILITY.md rated FR-49 **MISSING** precisely because this row claimed a design that does not exist here, and a row that over-claims is how a requirement ships undesigned: nobody goes looking for a design the table says is already done. FR-49's surface is row 23. The other five claims on this row were re-verified and hold. |
| 11 | Public share-link landing | `/share/:slug` | `share-link-desktop.html` | _(deferred — desktop-first at MVP)_ | UJ-5. SEO public URL with Schema.org Event JSON-LD. **This is the RECIPIENT's end of FR-28, and deliberately not FR-28 itself** — the sender's affordance is row 22 (`share-affordance-desktop.html`). This row's `UJ-5` scope is stated explicitly because the filename invites the confusion: TRACEABILITY.md scored FR-28 `PARTIAL (inferred only)` precisely by noting that "the plausible mockup is tagged `UJ-5` (recipient landing), not `FR-28` (sender share action)". |
| 12 | Unified Timeline (week view) | `/timeline` | `timeline-desktop.html` | `mobile/timeline-mobile.html` | FR-32 (Amendment A-8). Read-only week view, Personal + Public, sidebar nav (desktop) + bottom-tab (mobile) — first mockups to render these nav components. |
| 13 | Conflict Review list | `/conflicts` | `conflicts-desktop.html` | _(deferred — desktop-first at MVP)_ | FR-33 (Amendment A-8). List of active + resolved conflict pairs. The Conflict Resolution prompt itself (`Sheet.ConflictResolution`, FR-58) is row 8 above. **FR-55 added 2026-11-12:** the list shows pairs raised by a *state change* alongside pairs the user created, because AD-21 gives both the same record. Pairs closed as `cleared_by_state_change` appear as resolved-by-the-world, **not** as user resolutions. |
| 14 | Browse (Amendment A-10 + A-12) | `/browse` | `browse-desktop.html` + `browse-desktop-filtered.html` + `browse-desktop-empty.html` | _(desktop-first; mobile uses `component.bottom-tab.more-menu` overflow sheet)_ | FR-26 + FR-48. Merged city-page grid vocabulary (Amendment A-12). Hero with eyebrow + h1 terracotta-italic em + lede + city-meta pill. 3-column card grid (≥1280px) with section heads. Inline Save per card. Inline keyword search (A-11) replaces the city-page chip rail. 24-card soft cap. 2 stripe colors max (slate + amber at <10%); discovery stripe dropped. Pre-auth `city-page-desktop.html` stays for SEO crawlers per PRD FR-27. See `Component.Surface.Browse`. |
| 15 | Settings — Sources (Amendment A-18) | `/settings/sources` | `settings-sources-desktop.html` | _(deferred — desktop-first at MVP)_ | FR-13. Grouped source list (Official / Community / Aggregator / Crawled) with reliability 1–5 ink-primary dots + 3-state `component.control.source-mute` (Mute / Show less / Default). ~10 sample sources spanning all 4 categories. See `Component.Settings.Sources`. |
| 16 | Settings — Quiet Hours Pro (Amendment A-19) | `/settings/quiet-hours` Pro variant | `settings-quiet-hours-pro-desktop.html` | _(deferred — desktop-first at MVP)_ | FR-7 + FR-49. `component.control.day-picker` — vertical 7-row list (Mon–Sun) with active-window chip + ink-inversion activation toggle per row. Pro-tier gate via `Badge.Source.verified` pattern. Free users see locked rows. See `Component.Settings.QuietHours.Pro`. |
| 17 | Settings — Privacy — Delete-account modal (Amendment A-16) | `component.modal.account-delete` triggered from `/settings/privacy` | `account-delete-confirmation-modal-desktop.html` | _(deferred — desktop-first at MVP)_ | §10.1 + §14.1. Type-to-confirm input ("Type DELETE to confirm") gates the primary. Backdrop `rgba(10,10,11,0.7)` + `backdrop-filter: blur(8px)`. 30-day grace period. See `Component.Modal.AccountDelete`. |
| 18 | Settings — Privacy — Export-request modal (Amendment A-17) | `component.modal.export-request` triggered from `/settings/privacy` | `export-request-modal-desktop.html` | _(deferred — desktop-first at MVP)_ | FR-52. 3-state showcase: Free EU/UK/CA/BR/AU (direct export), Free elsewhere (terracotta "Upgrade to Pro → Export" gate), Pro (direct export + post-submit success notice with 24h SLA binding). See `Component.Modal.ExportRequest`. |
| 19 | Sign-in (Amendment A-20) | `/signin` | `signin-desktop.html` | _(deferred — desktop-first at MVP)_ | FR-4. Returning-user landing surface — closes the session-restore gap. Pre-auth topbar + page footer (byte-identical to `pulse-preview-desktop.html`). Centered form on 480px column (narrower than the 720px onboarding column because auth forms are single-decision). Email + Password fields with `component.auth.input.password` reveal toggle + per-field inline validation in `color.signal.warn` (NOT `color.signal.error`). 3 render states: valid input, wrong password (account-enumeration-safe), in-flight spinner. Routes to `/` (or last-visited authed route) on success. See `Component.Auth.SignIn`. |
| 20 | Sign-up (Amendment A-20) | `/signup` | `signup-desktop.html` | _(deferred — desktop-first at MVP)_ | FR-1. Account creation step split from calendar connect. OAuth stack first (Google / Apple / Outlook at equal weight per onboarding-step1 parity rule) + email/password form (Email + Password + Confirm password). Cross-field password-mismatch validation; server-side email-already-exists with inline ghost link to `/signin`. Routes to `/onboarding` step 1 on email/password success; OAuth users skip step 1 entirely (calendar auto-attached during handshake). Keeps post-signup flow within FR-1's ≤3 user-visible steps. See `Component.Auth.SignUp`. |
| 21 | Personal Event reminders (Amendment A-23) | `/events/:id/reminders` (personal event) | `personal-event-reminders-desktop.html` | _(deferred — desktop-first at MVP)_ | **FR-20**. Closes this document's own FR-20 gap: the requirement had no design anywhere, and `reminder-picker-desktop.html` is self-tagged `FR-9` (reminders on *saved public* events), so FR-20 was being built from it by adjacency. Three states — `as-created` (the inherited 1d + 1hr), `edited`, and `chosen-empty` — because FR-20's two testable consequences are a value and its opposite. Uses `component.reminders.personal.plan` and `component.emptystate.chosen`; warm `{color.warm.personal}` tone per FR-19, always paired with the visible "Personal" label. **Two as-built divergences recorded rather than inherited:** (1) the default attaches **silently** at creation — `personal-event-form.tsx` never mentions reminders — so this surface is the first disclosure, which FR-20 permits ("can edit", not "must disclose"); (2) the default is **user-configurable** at `/settings/reminders`, reading `NOTIFICATION_PREFERENCE.default_reminder_slots` and falling back to the 1d + 1hr constant, which is a **superset of FR-20's text** and a candidate PRD amendment. |
| 22 | Share affordance — the sender's side (Amendment A-23) | `component.control.share` on `/` (Pulse Card) and `/events/:id` (Detail Screen) | `share-affordance-desktop.html` | _(deferred — desktop-first at MVP)_ | **FR-28**. Closes this document's own FR-28 gap, which was a single platform-capability footnote at §964 and no design. The control is mounted on **both** surfaces FR-28 names, at each surface's own weight (`card` with a 44px tap floor; `secondary` on Detail). Uses `component.control.share` and `component.feedback.share`. **Four outcomes, the fourth being silence** — a dismissed Web Share sheet says nothing, because dismissing is the user's choice and not an error. Shares `/events/{slug}` (FR-26's public page, Open Graph–rich, carries the "Save to Pulse" CTA), never `/events/{uuid}`. **Three scope decisions recorded rather than left open:** the Timeline event-block has no share control (read-only per A-8); `share_precise_location` gates FR-52 export only and has no bearing on share metadata, so there is no redacted variant; and `share-link-desktop.html` keeps its `UJ-5` tag and is not repurposed. |
| 23 | Collections (Amendment A-23) | `/settings/collections` | `collections-desktop.html` | _(deferred — desktop-first at MVP)_ | **FR-49**. Closes the only **MISSING** rating in TRACEABILITY.md. Shows all four PRD verbs — create, rename, **reorder**, delete — plus a collection's contents, remove-from-collection, the in-place delete confirmation and the free-tier inline cap prompt. Uses `component.manager.collections`. **Four decisions a reader would otherwise get wrong:** reorder is move-up/move-down buttons and **never drag** (no library, and `styles/motion.test.ts` forbids any animation beyond the single 240ms transition); delete confirms **in place** and the copy names what survives, because "Delete" above a list of events reads as deleting the events; the tier gate covers **only create and assign**, so a lapsed Pro user keeps what they have; and the cap refusal carries `{cap, upgrade_hint}` with no `modal` or `title` field, so it is structurally incapable of being a modal. **Two empty states that are not the same thing** — `component.emptystate.quiet` for *no collections yet* (a found absence), a plain line for *an empty collection* (a container made on purpose). **This surface was built without a design**, and the mockup records what was assembled rather than proposing something new. |
| 24 | Event state change & conflict (Amendment A-23) | `/events/:id` state banner + mute | `event-state-conflict-desktop.html` | _(deferred — desktop-first at MVP)_ | **FR-55** (with FR-54's banner). Closes the TRACEABILITY.md gap that had **nothing tagged anywhere**. Three triggers — cancelled-with-nothing-affected, cancelled-clashing-with-a-personal-event, postponed-into-a-clash — plus the per-event mute in both states. Uses `component.control.notice-mute`, `component.banner.state-notice`, `component.indicator.conflict.cleared`. **The distinction this surface exists to hold:** a conflict that vanishes because the event was cancelled closes as `cleared_by_state_change` and is **not** a user resolution — hollow ring, dashed container, *"You didn't resolve anything"* — while a live overlap keeps the filled amber dot and routes to `Sheet.ConflictResolution`. **And a mute is not silence:** the backend raises a `cancelled` or `superseded` notice *despite* the mute, because FR-55 has already pulled the event from the digest and silence about it is the one failure with no second channel. **The personal event is never touched** — FR-55's "no auto-cancel", pinned by `test_saved_events.py`. |

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
