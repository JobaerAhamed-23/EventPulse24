# EventPulse24 — Traceability Matrix

Generated: 2026-09-08 (produced by the project's own `doc-trace` skill — `.agents/skills/doc-trace/SKILL.md` — not the BMad `bmad-testarch-trace` workflow)

**Sources scanned:**
- PRD: `_bmad-output/planning-artifacts/prds/prd-EventPulse24-2026-08-19/prd.md` — 45 MVP functional requirements (FR-1–FR-30, FR-32, FR-33, FR-48–FR-60); FR-31 and FR-34–FR-47 are Phase 2/3/Year 2+, listed separately below and not scored.
- Architecture Spine: `_bmad-output/planning-artifacts/architecture/architecture-EventPulse24-2026-09-04/ARCHITECTURE-SPINE.md`
- UX Design (components/visual system): `_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/DESIGN.md`
- UX Experience (flows/journeys): `_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/EXPERIENCE.md`
- Mockups: all 32 files under `.../mockups/` (26 desktop + 6 mobile), each checked for a self-tagged `FR-N` in its own header comment — the strongest evidence a design exists, since EXPERIENCE.md's own "Surface Coverage Map" table only lists 20 of the 32 files and cannot be trusted alone.
- Epics/Stories: none found yet — expected pre-epics. Not scored below.

---

## Section A — PRD ↔ Design Alignment

For each MVP FR: does a design element exist, in enough detail to build the UI from, in DESIGN.md, EXPERIENCE.md, or a mockup? `FULL` = a named section or a self-tagged mockup exists. `PARTIAL` = only inferable by adjacency, no direct tag anywhere. `MISSING` = a user-facing requirement with nothing found. `N/A` = the FR has no UI surface by nature (backend/internal/policy).

**Counts: 32 FULL · 3 PARTIAL (inferred only) · 1 MISSING · 9 N/A** (45 total)

| FR-ID | Title | Design element found | Status |
|---|---|---|---|
| FR-1 | 30-Second Onboarding Flow | `onboarding-step1/2/3-desktop.html`, `signup-desktop.html`, `onboarding-skip-all-state-desktop.html` — all self-tagged `FR-1` | FULL |
| FR-2 | Pulse Preview (No-Auth First Value) | `pulse-preview-desktop.html`, `geo-consent-banner-desktop.html` — self-tagged `FR-2` | FULL |
| FR-3 | Calendar Connect (OAuth) | `onboarding-step1-desktop.html` (EXPERIENCE.md coverage row: "FR-1 / FR-3 / FR-50"); calendar-provider-parity guidance | FULL |
| FR-4 | Authenticated User State | `Component.Auth.SignIn` (EXPERIENCE.md); `signin-desktop.html` self-tagged `FR-4` | FULL |
| FR-5 | Pulse Digest Composition | `Card.PulseDigest` vocabulary (extensive) | FULL |
| FR-6 | Pulse Card Information Density | `Card.PulseDigest` stripe/density rules | FULL |
| FR-7 | Pulse Digest Delivery Time | `onboarding-step3-desktop.html` (EXPERIENCE.md row: "FR-1 / FR-7. Time presets + AM/PM segmented control"); also cited on the Settings coverage row | FULL |
| FR-8 | Empty-State Pulse Digest | `component.emptystate.quiet` (DESIGN.md); `pulse-digest-empty-state-desktop.html` self-tagged `FR-8` | FULL |
| FR-9 | Multi-Tier Reminder Picker | `reminder-picker-desktop.html`, `event-detail-desktop.html` — self-tagged `FR-9` | FULL |
| FR-10 | Pulse Ping — Single Daily Notification | No UI is designed — and one exists deliberately: `onboarding-skip-all-state-desktop.html`'s header explains the topbar Notifications button "is removed entirely... per PRD FR-10 there is no in-app notifications inbox." Push/email only by design. | N/A (no design needed) |
| FR-11 | Email Multi-Tier Reminders | Same UI as FR-9 (reminder tiers configure both channels together) | FULL |
| FR-12 | Quiet Hours | Reminder-picker aside panel ("Edit quiet hours"); Pro variant explicit (`component.control.day-picker`) | FULL |
| FR-13 | Source Registry | `settings-sources-desktop.html` (EXPERIENCE.md row: "FR-13"); `Component.Settings.Sources` | FULL |
| FR-14 | Hybrid Event Extraction Pipeline | — backend pipeline | N/A (no design needed) |
| FR-15 | Event Deduplication | — backend | N/A (no design needed) |
| FR-16 | Source Reliability Score | Reliability dots; `settings-sources-desktop.html` | FULL |
| FR-17 | Source Acquisition Hierarchy Enforcement | — internal policy | N/A (no design needed) |
| FR-56 | RSS/Email-ICS Source Acquisition (MVP) | — backend | N/A (no design needed) |
| FR-60 | Timezone Source of Truth | — backend data-truth policy (the *display* of timezone during onboarding is FR-1/FR-7's UI, but FR-60 itself is about stored-timestamp truth, not a UI concern) | N/A (no design needed) |
| FR-18 | Manual Personal Event Creation | `personal-event-create-desktop.html`, `personal-event-edit-desktop.html` — self-tagged `FR-18` | FULL |
| FR-19 | Personal Event in Pulse Digest | `color.warm.personal` token + "Personal" label spec | FULL |
| FR-20 | Personal Event Reminder Defaults | Nothing found in DESIGN.md, EXPERIENCE.md, or any mockup header — only inferable by reusing FR-9's reminder-picker UI | **PARTIAL (inferred only) — open gap** |
| FR-58 | Personal Event Conflict Detection | `conflict-prompt-desktop.html`, `conflict-indicator-card-state-desktop.html` — self-tagged `FR-58` | FULL |
| FR-21 | Why-this Tags | `type.scale.microtag` italic hint token spec | FULL |
| FR-22 | Confidence Pulse | `ranking-algorithm-transparency-desktop.html`, `settings-desktop.html` — self-tagged `FR-22`; `Indicator.Confidence` | FULL |
| FR-23 | Source Badge | `Badge.Source.verified` | FULL |
| FR-24 | "Why this?" Detail Screen | `event-detail-desktop.html` self-tagged `FR-24`; `Tooltip.Confidence`/`Tooltip.Source` | FULL |
| FR-25 | "Less like this" Adjustment | `less-like-this-mute-prompt-desktop.html` self-tagged `FR-25` | FULL |
| FR-26 | Public Event Pages with Structured Data | `public-event-page-desktop.html` self-tagged `FR-26` — contains real Schema.org `application/ld+json` | FULL |
| FR-27 | SEO City Pages | `city-page-desktop.html` self-tagged `FR-27` | FULL |
| FR-28 | Share-Card Public Link | Only a one-line platform-capability footnote in EXPERIENCE.md ("Web Share API... PRD FR-28"); the plausible mockup (`share-link-desktop.html`) is tagged `UJ-5` (recipient landing), not `FR-28` (sender share action) — no design for the actual share affordance | **PARTIAL (inferred only) — open gap** |
| FR-29 | AI Cost Dashboard (Internal) | — internal Django admin tool, outside this design system | N/A (no design needed) |
| FR-30 | Caching & Batching Defaults | — backend | N/A (no design needed) |
| FR-32 | Unified Personal+Public Timeline (MVP) | `timeline-desktop.html` self-tagged `FR-32`; `Surface.Timeline`, `layout.timeline.grid` | FULL |
| FR-33 | Conflict-Aware Scheduling (MVP) | `conflicts-desktop.html` self-tagged `FR-33`; `/conflicts` route, "FR-33 three-action pattern" | FULL |
| FR-48 | Pro Tier with MVP-Only Features | `pricing-page-desktop.html`, `pro-upgrade-cta-desktop.html`, `export-request-modal-desktop.html` — self-tagged `FR-48` | FULL |
| FR-49 | Unlimited Saves + Saved Collections (Pro) | Nothing designed. "Named collections" exists only as a marketing bullet on the `FR-48`-tagged pricing pages — no screen shows creating, viewing, or managing a collection. (EXPERIENCE.md's own coverage table claims `settings-desktop.html` covers FR-49; the mockup contains zero "collection" content.) | **MISSING** |
| FR-50 | Calendar Provider Read-Only Sync | Parity row (shared with FR-3); `onboarding-step1-desktop.html` | FULL |
| FR-51 | Per-Day-of-Week Custom Quiet Hours (Pro) | `component.control.day-picker`; `settings-quiet-hours-pro-desktop.html` | FULL |
| FR-52 | JSON+ICS Data Export (Pro) | `export-request-modal-desktop.html` self-tagged `FR-48 FR-52`; `component.modal.export-request` | FULL |
| FR-53 | Event State Polling + Webhooks | `sold-out-card-state-desktop.html` self-tagged `FR-53 FR-54`; `component.badge.soldout` | FULL |
| FR-54 | User-Facing State-Change Notifications | Same mockup, self-tagged `FR-54`; `Component.Badge.SoldOut` ("Closes PRD FR-53 / FR-54 partial gap") | FULL |
| FR-55 | Conflict Resolution on State Change | Nothing found tagged anywhere — only overlap with FR-58's conflict UI, with no documented acknowledgment it also serves this trigger | **PARTIAL (inferred only) — open gap** |
| FR-57 | Editorial Review Queue (Internal) | — internal Django admin tool | N/A (no design needed) |
| FR-59 | User-Reported Event Quality | `report-event-modal-desktop.html` self-tagged `"FR-59 / Amendment A-4"` — 4 categories, rate-limit state, confirmation toast, triggered from "Report this event" on Event Detail | FULL |

**Open Design gaps** (need a real design pass before they can be FULL): **FR-20**, **FR-28**, **FR-55** (all PARTIAL/inferred-only), **FR-49** (MISSING).

---

## Section B — PRD ↔ Architecture Alignment

For each MVP FR: does the Architecture Spine's `Capability → Architecture Map` have an explicit row naming this FR, with a module and at least one `AD-N`?

**Counts: 43 FULL · 2 MISSING** (45 total)

| FR-ID | Title | Architecture (module · AD-N) | Status |
|---|---|---|---|
| FR-1 – FR-4 | Onboarding / Preview / Calendar Connect / Auth State | `identity`, `web`, `adapters/calendar` · AD-5,12,15,18 | FULL |
| FR-5 – FR-8 | Pulse Digest group | `personalization`, `web` · AD-3,10,11 | FULL |
| FR-9 – FR-12 | Reminder/Quiet-Hours group | `delivery`, `worker` · AD-6,7,16,17 | FULL |
| FR-13 – FR-17, FR-56, FR-60 | Source Registry / Extraction / Dedup / Reliability / Hierarchy / RSS-ICS / Timezone | `ingestion`, `worker`, `adapters/crawl` · AD-4,6,8,9 (AD-6 governs FR-60) | FULL |
| FR-18 – FR-20, FR-58 | Personal Event group + Conflict Detection | `personalization` · AD-3,6,16 | FULL |
| FR-21 – FR-25 | Trust/Transparency group (Why-this, Confidence, Badge, Detail, Less-like-this) | `personalization` · AD-9,10 | FULL |
| FR-26 – FR-28 | Public Pages / SEO / Share-link | `catalog`, frontend · AD-12,19 | FULL |
| FR-29 | AI Cost Dashboard (Internal) | `adapters/llm`, `editorial` (Django admin) · AD-8,14 | FULL |
| FR-30 | Caching & Batching Defaults | `adapters/llm` · AD-8 | FULL |
| **FR-32** | **Unified Personal+Public Timeline — lifted to MVP** | **none — no Capability Map row** | **MISSING** |
| **FR-33** | **Conflict-Aware Scheduling — lifted to MVP** | **none — no Capability Map row** | **MISSING** |
| FR-48, FR-50 | Pro Tier / Calendar Read-Only Sync | `identity`, `adapters/billing`, `adapters/calendar` · AD-5,15,18 | FULL |
| FR-49, FR-51, FR-52 | Saved Collections / Quiet Hours Pro / Data Export | same group | FULL |
| FR-53 – FR-55 | Event State Polling / Webhooks / Notifications / Conflict-on-change | `ingestion`, `delivery` · AD-4,7,17 | FULL |
| FR-57 | Editorial Review Queue (Internal) | `editorial` (Django admin) · AD-4,8,14 | FULL |
| FR-59 | User-Reported Event Quality | `personalization`, `editorial` · AD-3,14 | FULL |

**Open Architecture gaps:** **FR-32** and **FR-33** — both explicitly "lifted to MVP" by PRD Amendment A-8, both fully designed in UX (Section A: FULL), but the Architecture Spine's Capability Map has no row for either, and the word "Amendment" appears nowhere in `ARCHITECTURE-SPINE.md`. This is the single highest-value finding in this matrix: two of three source docs treat this as real, shipped MVP scope; Architecture has never accounted for it.

---

## Amendment Ledger

Cross-cutting across PRD, Architecture, Design, and Experience — one row per distinct `Amendment A-N` found anywhere.

| Amendment | Found in | Consistent? |
|---|---|---|
| A-1 (FR-15 dedup revision) | PRD | Consistent — backend-only, no UX impact expected; Architecture's AD-4 implements the substance but doesn't cite the tag. |
| A-2 (FR-5 revision) | PRD | **No** — FR-5 is core UX real estate (`Card.PulseDigest`); neither DESIGN.md nor EXPERIENCE.md has a matching tag. |
| A-3 (FR-22 revision) | PRD | **No** — UX references FR-22 directly but never cites "Amendment A-3". |
| A-4 (FR-59 added) | PRD | **Consistent** — Architecture has an FR-59 Capability-Map row, and `report-event-modal-desktop.html` is itself tagged "FR-59 / Amendment A-4". |
| A-5 (FR-58 revision) | PRD | **No** — UX covers FR-58 extensively but under its own tags (A-8, A-15), never citing "Amendment A-5". |
| A-6 (FR-60 added) | PRD | Consistent — backend-only, no UX impact expected. |
| A-7 (FR-3 calendar OAuth→ICS correction) | PRD | **No** — UX's calendar-parity guidance carries no A-7 tag. |
| A-8 (FR-32/FR-33 lifted to MVP) | PRD, UX | Consistent between PRD and UX. **Missing from Architecture** — see Section B gap above. |
| A-9 – A-21 (UX-originated "PRD-coverage reconciliation" + shell migrations) | UX only | Not found in PRD at all — per EXPERIENCE.md's own frontmatter these exist specifically to close PRD-coverage gaps, so the PRD arguably should reflect that this reconciliation happened. |

---

## Deferred (Phase 2 / Phase 3 / Year 2+, correctly out of MVP — not scored)

FR-31 (explicitly in Architecture's own Deferred table), FR-34–FR-47 (14 FRs, all Phase 2/3/Year 2+ per PRD headings, none expected in Architecture or UX yet).

## Epic/Story Coverage

No epics or stories exist yet in `_bmad-output/planning-artifacts/`. This section will populate automatically on the next `/doc-trace` run once they're created.
