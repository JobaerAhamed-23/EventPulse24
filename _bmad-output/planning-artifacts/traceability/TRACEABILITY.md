# EventPulse24 — Traceability Matrix

Generated: 2026-11-21 (produced by the project's own `doc-trace` skill — `.agents/skills/doc-trace/SKILL.md`)

**Supersedes the 2026-11-17 matrix.** That version read "0 missing / 0 partial" across all
three sections. **A fresh pass does not reproduce that**, and the differences are not
cosmetic — they are five places where the previous matrix scored against *intent* rather
than against the code:

| FR | Was | Now | Why it moved |
|---|---|---|---|
| FR-14 | *(not scored — outside a user-facing check)* | Implementation `PARTIAL` | The LLM extraction path does not exist. Only JSON-LD / RSS / ICS / API parsers run. The codebase's own docstring says *"When FR-14's LLM path **ships**, it will also come from `extraction_confidence < 0.70`."* |
| FR-29 | Implementation `FULL` | Implementation `PARTIAL` | `AICostRowAdmin` is a per-call row list with a filtered total. FR-29 demands **per-MAU TCO with a nine-category breakdown**, **week-over-week per-feature trends**, and **alerting at 20% over target**. None of the three exists. |
| FR-53 | Implementation `FULL` | Implementation `PARTIAL` | Polling ships. **Provider webhooks do not** — the only `webhook` code in `backend/apps/` is Stripe billing under `identity`. |
| FR-24 | Implementation `FULL` | Implementation `PARTIAL` | "Similar events you've attended" has no surface. The API contract documents the absence itself: *"Reviews and similar-events are absent from this contract, not present and empty."* |
| FR-55 | Implementation `FULL` | Implementation `PARTIAL` | The postponed-event-overlaps-another message has no surface in the Detail Screen. |

**Two of these are new findings** (FR-14, FR-53's webhook half) and three are
**over-scores retired** (FR-29, FR-24, FR-55). The retired ones are recorded with evidence
rather than silently dropped.

**Section A also moved.** FR-57 and FR-29 are now `MISSING` for Design — the previous
matrix scored FR-29 `N/A (no design needed)` on the reasoning that "internal Django admin
tool, outside this design system". **That reasoning holds for the design system's scope,
but the skill's question is whether a design element exists that an engineer could build
the UI from** — and for an internal tool the admin screen *is* that UI. Both are now
scored `MISSING` with the reason stated, rather than `N/A`.

**Sources scanned:**
- PRD: `_bmad-output/planning-artifacts/prds/prd-EventPulse24-2026-08-19/prd.md` — **60 FR headings: 45 MVP (FR-1–30, FR-32, FR-33, FR-48–FR-60) and 15 deferred (FR-31, FR-34–FR-47)**, listed separately and not scored. The MVP/deferred split is taken from the PRD's own §6.1 / §6.2, not inferred from FR numbering.
- Architecture Spine: `_bmad-output/planning-artifacts/architecture/architecture-EventPulse24-2026-09-04/ARCHITECTURE-SPINE.md` — Capability → Architecture Map, 15 rows, 21 ADs.
- UX Design: `_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/DESIGN.md`
- UX Experience: `_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/EXPERIENCE.md`
- UX Mockups: `_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/mockups/` — **42 HTML files confirmed against `ls`** (33 at the top level, 6 under `mobile/`, 3 under `light-archive/`). Each file's leading HTML comment was read for FR and Amendment tokens. **`light-archive/` files are archived and are not counted as evidence** — every one has a current equivalent.
- Implementation: the `frontend/app/` route tree (every `page.tsx`), `frontend/components/`, and `backend/apps/*/api.py` + `backend/apps/*/admin.py`. Every component cited in Section C was checked for a **real importer rooted in a route**, not merely for existing.
- Epics/Stories: no BMad epics document exists. FIRE work items under `.specs-fire/intents/*/work-items/` are the closest equivalent — see Epic/Story Coverage.

---

## Section A — PRD ↔ Design Alignment

For each MVP FR: does a design element exist, in enough detail that an engineer could build
the UI from it? `FULL` = a self-tagged mockup (tier 1) or a named DESIGN.md/EXPERIENCE.md
section citing the FR (tier 2). `PARTIAL` = inferable by adjacency only. `MISSING` = a
requirement with a user-facing or internal-tool surface and nothing found. `N/A` = no UI
surface by nature.

**Counts: 36 FULL · 0 PARTIAL · 2 MISSING · 7 N/A** (45 total)

| FR-ID | Title | Design element found (source) | Status | Note |
|---|---|---|---|---|
| FR-1 | 30-Second Onboarding Flow | `onboarding-step1/2/3-desktop.html`; `signup-desktop.html` (self-tagged FR-1); `onboarding-skip-all-state-desktop.html` (self-tagged FR-1); `mobile/onboarding-step1-mobile.html`; EXPERIENCE.md Flow 2 | **FULL** | `light-archive/onboarding-step1-*` are archived; current equivalents exist. |
| FR-2 | Pulse Preview (No-Auth First Value) | `pulse-preview-desktop.html`; `geo-consent-banner-desktop.html` (self-tagged FR-2); `mobile/pulse-preview-mobile.html`; DESIGN.md `component.control.toggle.location` | **FULL** | Soft-wall at the 3rd card; geo-IP consent banner with Change / Use this / Don't use my location. |
| FR-3 | Calendar Connect | `onboarding-step1-desktop.html` (3 equal-weight providers); `mobile/onboarding-step1-mobile.html`; DESIGN.md §Calendar Connect Provider Parity names "PRD FR-3 / FR-50" | **FULL** | The current mockup header omits the FR-3 token, but DESIGN.md names the FR directly. |
| FR-4 | Authenticated User State | `signin-desktop.html` (self-tagged FR-4); `signup-desktop.html`; `account-delete-confirmation-modal-desktop.html`; EXPERIENCE.md `Component.Auth.SignIn` | **FULL** | Session persistence specified in the component entry. |
| FR-5 | Pulse Digest Composition | `pulse-digest-desktop.html` (Slot 1 personal / Slot 2 must-know / Slot 3 discovery); `mobile/pulse-digest-mobile.html`; DESIGN.md `component.card.pulse.digest.category.discovery` | **FULL** | The A-2 serendipity/discovery tag rule is in DESIGN.md verbatim. |
| FR-6 | Pulse Card Information Density | `pulse-digest-desktop.html`; EXPERIENCE.md §4 `Card.PulseDigest` ("PRD FR-6"), §12 | **FULL** | Name, time, location, ≤3 why-tags, confidence pulse, source badge. |
| FR-7 | Pulse Digest Delivery Time | `onboarding-step3-desktop.html`; `settings-desktop.html` §Notifications; EXPERIENCE.md Surface Coverage rows 4 & 10 | **FULL** | Settings is the change surface. |
| FR-8 | Empty-State Pulse Digest | `pulse-digest-empty-state-desktop.html` (self-tagged FR-8); EXPERIENCE.md §5 Empty Patterns | **FULL** | The "Suggest an event" link is **withdrawn by A-26**; the FR as amended requires no link. |
| FR-9 | Multi-Tier Reminder Picker | `reminder-picker-desktop.html` (self-tagged FR-9); `event-detail-desktop.html`; `personal-event-reminders-desktop.html`; EXPERIENCE.md §4 `Input.ReminderSlot` | **FULL** | 5d/2d/1d/1hr + custom slot + quiet-hours deferral. |
| FR-10 | Pulse Ping — Single Daily Notification | No in-app inbox by design (EXPERIENCE.md §10 Platform: Web Notification API). The *time picker* that sets the ping is designed. | **N/A (no design needed)** | Notification-channel-only mechanism. |
| FR-11 | Email Multi-Tier Reminders | No email-template surface; EXPERIENCE.md §10 states email digest only. The slot plan editor (FR-9) is designed. | **N/A (no design needed)** | Transactional-email content is backend. |
| FR-12 | Quiet Hours | `settings-desktop.html` §Quiet hours; `reminder-picker-desktop.html` deferral note; `settings-quiet-hours-pro-desktop.html`; EXPERIENCE.md §4 | **FULL** | Free single-window surface present. |
| FR-13 | Source Registry | `settings-sources-desktop.html` (user-facing read of the registry); DESIGN.md `component.control.source-mute` cites "PRD FR-13's source registry governance" | **N/A (no design needed)** | The registry itself is backend; only its read is designed, and that read is credited to FR-16/23. |
| FR-14 | Hybrid Event Extraction Pipeline | No UI in the FR; the PRD scopes out a user-facing extraction-quality dashboard. | **N/A (no design needed)** | Backend pipeline. See Section C — the *implementation* is PARTIAL. |
| FR-15 | Event Deduplication | No user-facing surface; the queue it routes to is FR-57. | **N/A (no design needed)** | Backend identity pass. |
| FR-16 | Source Reliability Score | `settings-sources-desktop.html` (1–5 reliability dots); EXPERIENCE.md `Component.Settings.Sources` names FR-16 explicitly | **FULL** | Read-only display of the score. |
| FR-17 | Source Acquisition Hierarchy Enforcement | Backend compliance guardrail; no UI in the FR. | **N/A (no design needed)** | — |
| FR-56 | RSS / Email-ICS Source Acquisition | Not user-facing; the user's own calendar ICS import is FR-3/FR-50, which is designed. | **N/A (no design needed)** | — |
| FR-57 | Editorial Review Queue (Internal) | **Nothing.** EXPERIENCE.md §2: *"No `/admin`, no `/debug` — internal AI Cost Dashboard (FR-29) and Editorial Review Queue (FR-57) live outside this surface map."* No mockup, no component entry. | **MISSING** | An internal tool still has a design surface. None exists — no Approve/Reject/Edit screen is specified. |
| FR-60 | Timezone Source of Truth | Data policy; no component names FR-60. | **N/A (no design needed)** | The venue-local-time display is a rule, not a screen. |
| FR-18 | Manual Personal Event Creation | `personal-event-create-desktop.html` (self-tagged FR-18); `personal-event-edit-desktop.html`; EXPERIENCE.md row 7 | **FULL** | — |
| FR-19 | Personal Event in Pulse Digest | `personal-event-reminders-desktop.html` (FR-19); `pulse-digest-desktop.html` Slot 1 warm-personal card; DESIGN.md `component.card.pulse.digest.category.personal` | **FULL** | Warm tone **plus** a visible "Personal" text label — colour is never the sole carrier. |
| FR-20 | Personal Event Reminder Defaults | `personal-event-reminders-desktop.html` (self-tagged FR-20); DESIGN.md `component.reminders.personal.plan` ("PRD **FR-20**") and `component.emptystate.chosen` | **FULL** | Three states: as-created / edited / chosen-empty. |
| FR-58 | Personal Event Conflict Detection | `conflict-prompt-desktop.html` (self-tagged FR-58); `conflict-indicator-card-state-desktop.html`; `mobile/conflict-prompt-mobile.html`; EXPERIENCE.md §4 `Sheet.ConflictResolution` | **FULL** | Three forced choices, no dismiss. |
| FR-59 | User-Reported Event Quality | `report-event-modal-desktop.html` (self-tagged FR-59 / A-4) | **FULL** | 4 categories, rate-limit state, confirmation toast. |
| FR-21 | Why-this Tags | `pulse-digest-desktop.html` (why-tag row); `event-detail-desktop.html`; EXPERIENCE.md §12 ("PRD FR-21") | **FULL** | — |
| FR-22 | Confidence Pulse | `ranking-algorithm-transparency-desktop.html` (self-tagged FR-22); `pulse-digest-desktop.html` (1–5 dot pulse); `settings-desktop.html` §Privacy ranking table; EXPERIENCE.md §4 `Indicator.Confidence` | **FULL** | `light-archive/ranking-algorithm-transparency-desktop.html` is archived; a current equivalent exists. |
| FR-23 | Source Badge | `pulse-digest-desktop.html` (✅/👥/📥 variants); `event-detail-desktop.html`; DESIGN.md `component.badge.source`; EXPERIENCE.md §4 `Badge.Source` | **FULL** | Five variants including the `crawled_html` warning triangle. |
| FR-24 | "Why this?" Detail Screen | `event-detail-desktop.html` (self-tagged FR-24: breakdown, "12 neighbors", reminder picker); `mobile/event-detail-mobile.html`; EXPERIENCE.md §12 | **FULL** | The "similar events you've attended" block is designed here; see Section C for why it is not built. |
| FR-25 | "Less like this" Adjustment | `less-like-this-mute-prompt-desktop.html` (self-tagged FR-25: 3-cluster dismissal prompt); EXPERIENCE.md §4 `Card.PulseDigest` long-press sheet | **FULL** | — |
| FR-53 | Event State Polling + Webhooks | `sold-out-card-state-desktop.html` (self-tagged FR-53/FR-54); DESIGN.md `component.badge.soldout` ("PRD FR-53, FR-54"); EXPERIENCE.md `Component.Badge.SoldOut` | **FULL** | The visible Sold-Out / Cancelled / Postponed state is designed; the detection cadence is backend. |
| FR-54 | User-Facing State-Change Notifications | `sold-out-card-state-desktop.html`; DESIGN.md `component.banner.state-notice` ("PRD FR-54"); EXPERIENCE.md §3 (email subject line) | **FULL** | In-app banner + per-kind email subject. |
| FR-55 | Conflict Resolution on State Change | `event-state-conflict-desktop.html` (self-tagged FR-55); `conflict-prompt-desktop.html`; `conflict-indicator-card-state-desktop.html`; DESIGN.md `component.control.notice-mute`, `component.banner.state-notice`, `component.indicator.conflict.cleared` | **FULL** | — |
| FR-26 | Public Event Pages with Structured Data | `public-event-page-desktop.html` (self-tagged FR-26, Schema.org JSON-LD in the head); `share-affordance-desktop.html`; `share-link-desktop.html` | **FULL** | — |
| FR-27 | SEO City Pages | `city-page-desktop.html` (self-tagged FR-27); `browse-desktop.html` (A-12 merge reuses the vocabulary) | **FULL** | Graceful "coming soon" empty state specified. |
| FR-28 | Share-Card Public Link | `share-affordance-desktop.html` (self-tagged FR-28); DESIGN.md `component.control.share` and `component.feedback.share` ("PRD **FR-28**") | **FULL** | `share-link-desktop.html` is the recipient end (UJ-5), not FR-28. |
| FR-29 | AI Cost Dashboard (Internal) | **Nothing.** Same EXPERIENCE.md §2 exclusion as FR-57; no mockup, no DESIGN.md component. | **MISSING** | See Section C — an admin surface *does* exist in code, but it is not the dashboard FR-29 describes, and no design for the dashboard exists. |
| FR-30 | Caching & Batching Defaults | Backend compute policy; offline digest caching is a behaviour in EXPERIENCE.md §5, not a designed screen. | **N/A (no design needed)** | — |
| FR-32 | Unified Personal+Public Timeline | `timeline-desktop.html` (self-tagged FR-32); `mobile/timeline-mobile.html`; DESIGN.md §Timeline (A-8); EXPERIENCE.md §4 `Surface.Timeline`, Flow 5 | **FULL** | Read-only week view; warm/cool + text labels. |
| FR-33 | Conflict-Aware Scheduling | `conflicts-desktop.html` (self-tagged FR-33); EXPERIENCE.md §5 Conflict Patterns, §4 `Sheet.ConflictResolution`, Flow 6 | **FULL** | Three-action pattern + `/conflicts` route both designed. |
| FR-48 | Pro Tier with MVP-Only Features | `pricing-page-desktop.html` (self-tagged FR-48); `pro-upgrade-cta-desktop.html` (self-tagged FR-48); DESIGN.md `component.card.pro.upsell` | **FULL** | The entitlement has a real upgrade surface, not just marketing bullets. |
| FR-49 | Unlimited Saves + Saved Collections | `collections-desktop.html` (self-tagged FR-49); DESIGN.md `component.manager.collections` ("PRD **FR-49**"); EXPERIENCE.md row 23 | **FULL** | Create / rename / reorder / delete + the free-tier cap prompt. |
| FR-50 | Calendar Provider Read-Only Sync | `onboarding-step1-desktop.html` (3 providers); `settings-desktop.html` §Calendar sync; DESIGN.md §Calendar Connect Provider Parity ("PRD FR-3 / FR-50") | **FULL** | Same surface as FR-3 — provider parity is one screen. |
| FR-51 | Per-Day-of-Week Custom Quiet Hours | `settings-quiet-hours-pro-desktop.html` (A-19); DESIGN.md `component.control.day-picker` ("PRD FR-51"); EXPERIENCE.md §4 `Component.Settings.QuietHours.Pro` | **FULL** | Free-locked rows with upgrade microcopy. |
| FR-52 | JSON + ICS Data Export | `export-request-modal-desktop.html` (self-tagged FR-48/FR-52); DESIGN.md `component.modal.export-request`; EXPERIENCE.md §4 `Component.Modal.ExportRequest` | **FULL** | 3 jurisdictional states + 24h SLA notice. |

### Open gaps (Design)

- **FR-57** — Editorial Review Queue (Internal): no admin/review screen designed. EXPERIENCE.md §2 explicitly excludes it from the surface map ("No `/admin`, no `/debug`"), and no mockup or component entry describes Approve / Reject / Edit of queued events. **The internal tool has no UI at all.**
- **FR-29** — AI Cost Dashboard (Internal): no dashboard designed. Same exclusion note; no mockup, no DESIGN.md component. FR-29's own acceptance criteria — per-MAU TCO breakdown, week-over-week per-feature trends, 20%-breach alerting — are undesigned.

---

## Section B — PRD ↔ Architecture Alignment

For each MVP FR: does the Architecture Spine's **Capability → Architecture Map** have an
explicit row naming this FR (or a range covering it), with a module and at least one
`AD-N`? `FULL` = such a row. `PARTIAL` = covered only by adjacency. `MISSING` = no row.

**Counts: 45 FULL · 0 PARTIAL · 0 MISSING · 0 N/A** (45 total)

**Every MVP FR is named by a Capability Map row.** The map's 15 rows cover all 45 MVP FRs
between them, and no row names a deferred FR. The Architecture Spine has no gap here.

| FR-ID | Title | Architecture (module · AD-N) | Status | Note |
|---|---|---|---|---|
| FR-1 | 30-Second Onboarding Flow | `identity`, `personalization`, frontend, `adapters/calendar` · AD-5, AD-12, AD-15, AD-18 | **FULL** | Row "FR-1–4 Onboarding & account". |
| FR-2 | Pulse Preview | `identity`, `personalization`, frontend, `adapters/calendar` · AD-5, AD-12, AD-15, AD-18 | **FULL** | Same row. |
| FR-3 | Calendar Connect | `identity`, `personalization`, frontend, `adapters/calendar` · AD-5, AD-12, AD-15, AD-18 | **FULL** | Same row. |
| FR-4 | Authenticated User State | `identity`, `personalization`, frontend, `adapters/calendar` · AD-5, AD-12, AD-15, AD-18 | **FULL** | Same row. |
| FR-5 | Pulse Digest Composition | `personalization`, frontend · AD-3, AD-10, AD-11 | **FULL** | Row "FR-5–8 Pulse Digest". |
| FR-6 | Pulse Card Information Density | `personalization`, frontend · AD-3, AD-10, AD-11 | **FULL** | Same row. |
| FR-7 | Pulse Digest Delivery Time | `personalization`, frontend · AD-3, AD-10, AD-11 | **FULL** | Same row. |
| FR-8 | Empty-State Pulse Digest | `personalization`, frontend · AD-3, AD-10, AD-11 | **FULL** | Same row. |
| FR-9 | Multi-Tier Reminder Picker | `delivery`, `worker` · AD-6, AD-7, AD-16, AD-17 | **FULL** | Row "FR-9–12 Reminders & Pulse Ping". |
| FR-10 | Pulse Ping | `delivery`, `worker` · AD-6, AD-7, AD-16, AD-17 | **FULL** | Same row. |
| FR-11 | Email Multi-Tier Reminders | `delivery`, `worker` · AD-6, AD-7, AD-16, AD-17 | **FULL** | Same row. |
| FR-12 | Quiet Hours | `delivery`, `worker` · AD-6, AD-7, AD-16, AD-17 | **FULL** | Same row. |
| FR-13 | Source Registry | `ingestion`, `worker`, `adapters/crawl` · AD-4, AD-6, AD-8, AD-9 | **FULL** | Row "FR-13–17, FR-56, FR-60 Ingestion & sources". |
| FR-14 | Hybrid Event Extraction Pipeline | `ingestion`, `worker`, `adapters/crawl` · AD-4, AD-6, AD-8, AD-9 | **FULL** | Same row. |
| FR-15 | Event Deduplication | `ingestion`, `worker`, `adapters/crawl` · AD-4, AD-6, AD-8, AD-9 | **FULL** | Same row. AD-4 additionally binds FR-15 explicitly. |
| FR-16 | Source Reliability Score | `ingestion`, `worker`, `adapters/crawl` · AD-4, AD-6, AD-8, AD-9 | **FULL** | Same row. |
| FR-17 | Source Acquisition Hierarchy | `ingestion`, `worker`, `adapters/crawl` · AD-4, AD-6, AD-8, AD-9 | **FULL** | Same row. |
| FR-56 | RSS / Email-ICS Source Acquisition | `ingestion`, `worker`, `adapters/crawl` · AD-4, AD-6, AD-8, AD-9 | **FULL** | Same row. |
| FR-60 | Timezone Source of Truth | `ingestion`, `worker`, `adapters/crawl` · AD-4, AD-6, AD-8, AD-9 | **FULL** | Same row; AD-4 and AD-6 both name FR-60 in their *Binds* lines. |
| FR-18 | Manual Personal Event Creation | `personalization` · AD-3, AD-6, AD-16, AD-21 | **FULL** | Row "FR-18–20, FR-58 Personal events & conflict". |
| FR-19 | Personal Event in Pulse Digest | `personalization` · AD-3, AD-6, AD-16, AD-21 | **FULL** | Same row. |
| FR-20 | Personal Event Reminder Defaults | `personalization` · AD-3, AD-6, AD-16, AD-21 | **FULL** | Same row. |
| FR-58 | Personal Event Conflict Detection | `personalization` · AD-3, AD-6, AD-16, AD-21 | **FULL** | Same row; AD-6 binds FR-58 explicitly. |
| FR-32 | Unified Personal+Public Timeline | `personalization`, frontend · AD-3, AD-6, AD-21 | **FULL** | Own row (A-8 lift). |
| FR-33 | Conflict-Aware Scheduling | `personalization`, `delivery`, frontend · AD-6, AD-17, AD-21 | **FULL** | Own row (A-8 lift). |
| FR-21 | Why-this Tags | `personalization` · AD-9, AD-10 | **FULL** | Row "FR-21–25 Explainability & trust". |
| FR-22 | Confidence Pulse | `personalization` · AD-9, AD-10 | **FULL** | Same row. |
| FR-23 | Source Badge | `personalization` · AD-9, AD-10 | **FULL** | Same row. |
| FR-24 | "Why this?" Detail Screen | `personalization` · AD-9, AD-10 | **FULL** | Same row. |
| FR-25 | "Less like this" Adjustment | `personalization` · AD-9, AD-10 | **FULL** | Same row. |
| FR-26 | Public Event Pages | `catalog`, frontend · AD-12, AD-19 | **FULL** | Row "FR-26–28 Sharing & SEO". |
| FR-27 | SEO City Pages | `catalog`, frontend · AD-12, AD-19 | **FULL** | Same row. |
| FR-28 | Share-Card Public Link | `catalog`, frontend · AD-12, AD-19 | **FULL** | Same row. |
| FR-29 | AI Cost Dashboard | `adapters/llm`, `editorial` (Django admin) · AD-8, AD-14 | **FULL** | Own row. **A caution this section cannot see, and Section C does:** the row says where the capability *lives*, not how much of it is built. |
| FR-30 | Caching & Batching | `adapters/llm` · AD-8 | **FULL** | Own row. |
| FR-48 | Pro Tier with MVP-Only Features | `identity`, `adapters/billing`, `adapters/calendar` · AD-5, AD-15, AD-18 | **FULL** | Row "FR-48–52 Pro tier". |
| FR-49 | Unlimited Saves + Collections | `identity`, `adapters/billing`, `adapters/calendar` · AD-5, AD-15, AD-18 | **FULL** | Same row. |
| FR-50 | Calendar Provider Read-Only Sync | `identity`, `adapters/billing`, `adapters/calendar` · AD-5, AD-15, AD-18 | **FULL** | Same row. |
| FR-51 | Per-Day-of-Week Quiet Hours | `identity`, `adapters/billing`, `adapters/calendar` · AD-5, AD-15, AD-18 | **FULL** | Same row. |
| FR-52 | JSON + ICS Data Export | `identity`, `adapters/billing`, `adapters/calendar` · AD-5, AD-15, AD-18 | **FULL** | Same row. |
| FR-53 | Event State Polling + Webhooks | `ingestion`, `delivery`, `personalization` · AD-4, AD-7, AD-17, AD-21 | **FULL** | Row "FR-53–55 Event state sync". |
| FR-54 | User-Facing State-Change Notices | `ingestion`, `delivery`, `personalization` · AD-4, AD-7, AD-17, AD-21 | **FULL** | Same row. |
| FR-55 | Conflict Resolution on State Change | `ingestion`, `delivery`, `personalization` · AD-4, AD-7, AD-17, AD-21 | **FULL** | Same row. |
| FR-57 | Editorial Review Queue | `editorial` (Django admin) · AD-4, AD-8, AD-14 | **FULL** | Own row. |
| FR-59 | User-Reported Event Quality | `personalization`, `editorial` · AD-3, AD-14 | **FULL** | Own row (A-4). |

### Open gaps (Architecture)

**None.** All 45 MVP FRs are named by an explicit Capability Map row with a module and at
least one AD-N.

---

## Section C — PRD ↔ Implementation

For each MVP FR: **can a user reach this, in the running product, today?** `FULL` = a
user-reachable path exists — a route, a mounted component, or a control on a surface that
renders. `PARTIAL` = the machinery exists and the surface is incomplete. `MISSING` = no
user-reachable path, **including a backend that is complete and tested but that no control
can set**. `N/A` = no user surface by nature.

**This section cites running code only.** A mockup is Section A's evidence and an
architecture row is Section B's; neither is reused here. Every component cited was checked
for a real importer rooted in a route — **the mount, not just the call** — because
`frontend/tests/endpoint-coverage.test.ts` can catch an orphaned endpoint but explicitly
cannot see a component that calls an endpoint and is never rendered.

**Counts: 35 FULL · 6 PARTIAL · 0 MISSING · 1 N/A · 0 UNASSESSED** (45 total)

| FR-ID | Title | Implementation evidence (file:line) | Status | Note |
|---|---|---|---|---|
| FR-1 | 30-Second Onboarding Flow | `frontend/app/onboarding/page.tsx:53` → `components/onboarding/onboarding-flow.tsx:73-89` (exactly 3 steps); `step-shell.tsx:93,103` (Skip all / Skip for now); `onboarding-flow.tsx:221` `POST /api/personal/onboarding/skip-all` | **FULL** | 3 steps, all skippable, resume via the server's `current_step`. |
| FR-2 | Pulse Preview | `frontend/app/preview/page.tsx:37,77`; `components/preview/preview-section.tsx:64` `GET /api/public/preview`, `:40,175` soft wall at the 3rd save → `/signup`; `components/preview/geo-banner.tsx:34` | **FULL** | 3 cards, geo-IP consent, soft wall. |
| FR-3 | Calendar Connect | `components/onboarding/calendar-step.tsx:269` renders `CALENDAR_PROVIDERS`; `frontend/lib/calendar-providers.ts:30-55` (google/apple/outlook); `calendar-step.tsx:178` `POST /api/personal/calendars` | **FULL** | All three providers, equal-weight, skippable. |
| FR-4 | Authenticated User State | `frontend/app/signin/page.tsx`, `frontend/app/signup/page.tsx`; `frontend/lib/session.ts` `getSession()`; session read on every route | **FULL** | Web cookie + server session; reachable from the topbar and the preview. |
| FR-5 | Pulse Digest Composition | `frontend/app/page.tsx:126-128` → `DigestCardList` / `DigestEmpty`; `backend/apps/personalization/services/digest_composition.py:492` `_assign_slots` (must_known / nearby / serendipity), `:604`, `:606` | **FULL** | 3 cards, slot-specific scoring, the A-2 serendipity term in `domain/ranking.py`. |
| FR-6 | Pulse Card Information Density | `frontend/components/digest/pulse-card.tsx:93` `MAX_WHY_THIS_TAGS = 3`; `:257` `ConfidencePulse` + `SourceBadgeBadge`; `:300-320` tags; `:322-334` time + place | **FULL** | All seven elements always rendered. |
| FR-7 | Pulse Digest Delivery Time | `frontend/app/settings/general/page.tsx:274` `DigestDeliveryTime`; `components/settings/digest-delivery-time.tsx`; `:151` reads `delivery_time`/`timezone` | **FULL** | — |
| FR-8 | Empty-State Pulse Digest | `frontend/app/page.tsx:128` `<DigestEmpty>`; `components/digest/digest-empty.tsx:38-58` — one card, no link | **FULL** | As amended by A-26 the link is withdrawn; the card stands and carries none. |
| FR-9 | Multi-Tier Reminder Picker | `frontend/app/events/[id]/reminders/page.tsx:93`; `components/reminders/reminder-picker.tsx:40`; `frontend/lib/reminder-slots.ts` `SLOT_IDS` (5d/2d/1d/1hr + custom); `frontend/app/personal-events/[id]/reminders/page.tsx:97` | **FULL** | 0–4 slots + custom; both event kinds. |
| FR-10 | Pulse Ping | `frontend/app/settings/general/page.tsx:271` `PulsePingSwitch`; `components/settings/pulse-ping-switch.tsx` `PUT /api/settings/notifications`; `backend/apps/delivery/services/pulse_ping.py:164` `mint_ping_send` | **FULL** | One ping per user per day, suppression honoured. |
| FR-11 | Email Multi-Tier Reminders | `backend/apps/delivery/services/reminder_plans.py`; `services/scheduled_sends.py`; `templates/delivery/reminder.html:26` (per-event unsubscribe); `backend/apps/identity/…` RFC 8058 `GET/POST /api/email/unsubscribe` | **FULL** | Delivery + per-event unsubscribe. |
| FR-12 | Quiet Hours | `frontend/app/settings/general/page.tsx:216` `QuietHoursWindow`; `components/settings/quiet-hours-window.tsx`; `backend/domain/quiet_hours.py`; deferral surfaced by `reminder-picker.tsx` (`deferred` flag) | **FULL** | Free single-window tier. |
| FR-13 | Source Registry | `backend/apps/ingestion/models.py:57` `Source`; `backend/apps/ingestion/admin.py:262` `SourceAdmin`, `:1206` `IngestionAuditEntryAdmin`; `frontend/app/settings/sources/page.tsx:91` `SourceList` | **FULL** | Registry + full audit log + a read-only user view. |
| FR-14 | Hybrid Event Extraction Pipeline | JSON-LD: `backend/apps/ingestion/parsers/jsonld.py`; **no LLM path**; `backend/apps/ingestion/services/review_intake.py:22` — *"When FR-14's LLM path ships, it will also come from `extraction_confidence < 0.70`"* | **PARTIAL** | **The LLM/HTML extraction path does not exist.** Only structured parsers (jsonld/rss/ics/api) run, and the extraction-confidence quarantine gate is unwired. |
| FR-15 | Event Deduplication | `backend/domain/dedup.py:275` `match()`, `:292` `resolve()`, `:113` `title_fingerprint`, `:135` `jaccard`; `backend/apps/ingestion/services/ingest_item.py:248` source_id+source_event_id merge | **FULL** | Structural identity implemented; embeddings route to review, never merge — per A-1. |
| FR-16 | Source Reliability Score | `backend/domain/reliability.py:140` `posterior_mean` (α=5/β=5), `:189` `is_spike`, `:203` `should_escalate`; `backend/apps/ingestion/admin.py:1166` `SourceReliabilityScoreAdmin`; `frontend/components/settings/source-trust-dots.tsx:30` | **FULL** | Bayesian-smoothed score, spike detection, admin surface for the history. |
| FR-17 | Source Acquisition Hierarchy | `backend/apps/ingestion/models.py:45` `AcquisitionMethod` (priority order); `services/source_registry.py` (the hierarchy guard); `parsers/__init__.py:26` (*"registering one here would quietly widen FR-17's hierarchy"*); `models.py:247` `TosReview` | **FULL** | Hierarchy + ToS gate enforced in the registry service. |
| FR-56 | RSS / Email-ICS Acquisition | `backend/apps/ingestion/models.py:51,53` `RSS`/`EMAIL_ICS`; `parsers/__init__.py:25` `"email_ics": parse_ics`; `parsers/feeds.py` | **FULL** | Both are first-class acquisition methods with parsers. |
| FR-57 | Editorial Review Queue | `backend/config/urls.py:10` mounts `admin.site.urls`; `backend/apps/ingestion/admin.py:621` `ReviewItemAdmin` (Approve/Reject/Dismiss actions, SLA fields); `backend/apps/ingestion/templates/admin/ingestion/reviewitem/change_list.html`; `admin.py:715` queue metrics | **FULL** | A real, staff-gated admin surface with Approve / Reject / Edit verdicts. |
| FR-60 | Timezone Source of Truth | `backend/apps/ingestion/models.py:537-541` `start_time_local`/`start_time_tz`/`tz_inference_confidence`/`tz_review_pending`; `models.py:138` `tz_coverage`; `frontend/lib/detail-time.ts:117` `detailTimes` (user-local + venue-local); `components/detail/detail-header.tsx:119` "Time approximate"; `backend/apps/ingestion/services/catalog_read.py:385` digest gate at 0.7 | **FULL** | tz required, auto-reject below floor, venue-local shown. |
| FR-18 | Manual Personal Event Creation | `frontend/components/add-event-button.tsx:35` → `components/personal-events-panel.tsx:264` `POST /api/personal/events`; `components/sheets/personal-event-form.tsx:230-351` (name/date/time/tz/end/location/notes); `personal-events-panel.tsx:316` `DELETE`, `:260` `PATCH` | **FULL** | Create, edit and delete, reachable from the digest header, sidenav, bottom-tab and Timeline. |
| FR-19 | Personal Event in Pulse Digest | `frontend/components/digest/pulse-card.tsx:119` warm-personal stripe + "Personal" label; `frontend/app/settings/general/page.tsx:280` `DigestPersonalEvents` opt-out | **FULL** | — |
| FR-20 | Personal Event Reminder Defaults | `frontend/app/personal-events/[id]/reminders/page.tsx:97` (`targetKind="personal_event"`); `frontend/app/settings/general/page.tsx:197` `DefaultReminderSlots` (1d + 1hr); `reminder-picker.tsx` (0-slot save allowed) | **FULL** | Defaults inherited at creation, editable and removable. |
| FR-58 | Personal Event Conflict Detection | `frontend/components/sheets/conflict-resolution.tsx:6` *"There is no dismiss"*, `dismissible={false}`; `components/personal-events-panel.tsx:337` `POST /api/personal/events/conflicts/{pair_id}/resolve`; `components/conflicts/conflict-indicator.tsx`; `components/digest/pulse-card.tsx:255` | **FULL** | Forced three-choice prompt, no dismiss, persistent amber indicator. |
| FR-59 | User-Reported Event Quality | `frontend/components/detail/event-report-control.tsx` (flag CTA, 4 categories, no free text); `components/detail/detail-actions.tsx:537` mounts it in the Detail action row; `backend/apps/personalization/services/event_reports.py`; `backend/apps/ingestion/admin.py:621` queue receives `user_reported` | **FULL** | Flag → modal → 4 categories → `EventReport` → editorial queue. |
| FR-21 | Why-this Tags | `frontend/components/digest/pulse-card.tsx:93` (max 3), `:300-320` (rendered); `components/detail/detail-breakdown.tsx:36` `DetailTags` reads the same persisted tags via the same `tagLabel` | **FULL** | Identical on card and detail. |
| FR-22 | Confidence Pulse | `frontend/components/digest/pulse-card.tsx:89` `CONFIDENCE_POSITIONS = 5`; `backend/shared/constants.py:1049-1062` `RANKING_WEIGHT_*` summing to 1.00; `:1138` `RANKING_WEIGHTS_AMENDMENT`; `frontend/app/settings/privacy/page.tsx:131` `RankingFormula` | **FULL** | The A-25 weight mapping is published on Settings → Privacy. |
| FR-23 | Source Badge | `frontend/components/digest/pulse-card.tsx:257` `SourceBadgeBadge`; `frontend/lib/digest-labels.ts:230-232` `crawled_html` badge + "Read from a public page…" tooltip; `pulse-card.tsx:536` | **FULL** | All five badge types. |
| FR-24 | "Why this?" Detail Screen | `frontend/app/events/[id]/page.tsx:397` `DetailHeader`, `:546` `DetailBreakdown`, `:553` `DetailNeighbors` (bucketed, k-anonymity-suppressed, `components/detail/detail-neighbors.tsx:22`), `:511` reminder link, `:529` `DetailActions` | **PARTIAL** | Breakdown, place, reminder, share, save and neighbour count all ship — but **"similar events you've attended" has no surface**. The API contract documents the absence itself: *"Reviews and similar-events are absent from this contract, not present and empty."* |
| FR-25 | "Less like this" Adjustment | `frontend/components/digest/swipe-dismiss.tsx:122` → `frontend/lib/dismissal-write.ts` `POST /api/personal/dismissals`; `components/digest/digest-card-list.tsx:100` `acceptPrompt`; `frontend/app/settings/taste/page.tsx:81` `TasteMuteList` | **FULL** | Swipe, 3-cluster prompt, reversible mute. |
| FR-53 | Event State Polling + Webhooks | Polling: `backend/apps/ingestion/services/scheduling.py:46` `claim_due_sources`, `:112` `report_cadence_floor_breaches`; `services/ingest_source.py`; state badges: `frontend/components/state/event-state-badge.tsx` | **PARTIAL** | Polling, cadence enforcement and the sold-out/cancelled/postponed badges ship. **Provider webhooks do not** — the only `webhook` code under `backend/apps/` is Stripe billing in `identity`. |
| FR-54 | User-Facing State-Change Notices | `frontend/app/page.tsx:123` `NoticeStrip` → `components/state/notice-strip.tsx:120`; dismiss `POST /api/notices/{notice_id}/dismiss`; email `backend/apps/delivery/services/state_notices.py:106` `raise_state_notice` + `templates/delivery/state_notice.html` | **FULL** | One calm in-app strip + per-kind email subject, one-time per event. |
| FR-55 | Conflict Resolution on State Change | `frontend/components/state/detail-mute-control.tsx` (per-event mute, `PUT`/`DELETE /api/notices/events/{id}/mute`); `frontend/app/events/[id]/page.tsx:478-484` `DetailNoticeBanner`; `backend/apps/personalization/models.py:357` `CLEARED_BY_STATE_CHANGE` | **PARTIAL** | Notification, personal-event preservation and per-event mute all ship — but **the "this overlaps with [other event]" message for a postponed event has no surface** in the Detail Screen. |
| FR-26 | Public Event Pages | `frontend/app/events/[id]/page.tsx:295-303` `PublicEventPage` for slugs; `components/public-event/public-event-page.tsx:53` `application/ld+json`; `:221-225` "Save to Pulse →" CTA to `/signup` | **FULL** | Unique slug URL, Schema.org JSON-LD, crawlable. |
| FR-27 | SEO City Pages | `frontend/app/events-in/[slug]/page.tsx:211` `CityPage`; `frontend/lib/city-page-read.ts:133`; `components/city-page/city-page.tsx:127` `CityEventCard`; `is_published=false` degradation (`frontend/lib/api/schema.ts:434`); `frontend/app/sitemap.xml/route.ts:38` | **FULL** | Indexable, in the sitemap, degrades to "coming soon". |
| FR-28 | Share-Card Public Link | `frontend/components/share/share-control.tsx` (clipboard copy of the public slug URL); `components/digest/pulse-card.tsx` renders `ShareControl`; `components/detail/detail-actions.tsx:461`; `frontend/app/events/[id]/page.tsx:168-181` Open Graph + Twitter card | **FULL** | — |
| FR-29 | AI Cost Dashboard | `backend/config/urls.py:10` mounts `admin.site.urls`; `backend/adapters/llm/admin.py:84` `AICostRowAdmin` with filtered totals (`changelist_view`, `:140-152`); `backend/adapters/llm/models.py:41` `AICostRow` | **PARTIAL** | **A reachable, read-only admin surface listing per-call cost with filtered totals exists** — but it is not the dashboard FR-29 describes. **No per-MAU TCO with the nine-category breakdown, no week-over-week per-feature trends, no 20%-breach alerting.** Queue size and review latency live on the review-queue page, not a cost dashboard. **Was scored FULL by the 2026-11-17 matrix; that was an over-score against the FR's own acceptance criteria.** |
| FR-30 | Caching & Batching Defaults | `backend/apps/personalization/services/digest_composition.py:647` `_existing_digest` (same day → cached composition); `backend/apps/ingestion/services/ingest_source.py:144` `unchanged_record_ids`; `backend/apps/ingestion/services/embedding.py` | **N/A** | A backend-only compute policy with no user surface by nature; all three named consequences are implemented server-side. |
| FR-32 | Unified Personal+Public Timeline | `frontend/app/timeline/page.tsx:139` `TimelinePanel`; `components/timeline/timeline-block.tsx:63` accessible name includes "Personal"/"Public event", `:77` warm-personal vs slate stripe, `:16-20` amber conflict indicator | **FULL** | Week view, both kinds, warm/cool + text labels, read-only. |
| FR-33 | Conflict-Aware Scheduling | `frontend/app/conflicts/page.tsx:87` `ConflictsPanel`; `components/conflicts/conflict-pair-card.tsx:51-77` server-supplied three actions; `components/conflicts/conflicts-panel.tsx` `POST /api/personal/events/conflicts/{pair_id}/resolve`; `components/conflicts/conflict-indicator.tsx` | **FULL** | — |
| FR-48 | Pro Tier | `frontend/app/pricing/page.tsx:57` `PricingPage` ($4.99/mo, $49/yr, Free vs Pro); `components/pricing/choose-plan-button.tsx:122` `POST /api/billing/checkout`; `frontend/app/settings/account/page.tsx:106` `PlanSummary`; `components/upgrade/upgrade-prompt.tsx:45` inline cap prompt | **FULL** | Pricing, checkout, portal, plan summary, calm inline upsells. |
| FR-49 | Unlimited Saves + Collections | `frontend/app/settings/collections/page.tsx:101` `CollectionManager`; `components/collections/collection-manager.tsx:156` create, `:165` rename, `:176` delete, `:203` reorder (`PUT /api/personal/collections/order`), `:282/:298` add/remove events; `components/detail/detail-actions.tsx:285-289` `save_cap_reached` → `UpgradePrompt` | **FULL** | — |
| FR-50 | Calendar Provider Read-Only Sync | `frontend/app/settings/calendars/page.tsx:87` `CalendarConnections`; `components/settings/calendar-connections.tsx:506-515` (all three providers), `:268` connect, `:221` disconnect, `:84` revoked→reconnect prompt, `:418` sync-now | **FULL** | Free 1 / Pro 3 cap via `UpgradePrompt`. |
| FR-51 | Per-Day-of-Week Quiet Hours | `frontend/app/settings/general/page.tsx:229` `WeekdayQuietHours` (7 rows); `components/settings/weekday-quiet-hours.tsx:113` whole-week replace write, `:66` `canEdit`; `:219-224` Free user gets an upgrade offer | **FULL** | — |
| FR-52 | JSON + ICS Data Export | `frontend/app/settings/account/page.tsx:123` `DownloadMyData`; `components/settings/download-my-data.tsx:47` `POST /api/exports`; `backend/apps/identity/services/data_export.py`; `backend/worker/tasks.py:694` `build_data_export`; `GET /api/exports/{export_id}/{fmt}` links by email | **PARTIAL** | The request control and the JSON+ICS worker exist, but **the export is deliberately not Pro-gated and not in Pro settings** — GDPR Art. 20 is a right, not a tier feature. FR-52's "UX is in Pro settings for non-EU users" is therefore unimplemented. |

### Open gaps (Implementation)

- **FR-14** — The LLM/HTML structured-extraction path does not exist. Only JSON-LD / RSS / ICS / API parsers run, and the `extraction_confidence < 0.70` quarantine gate is unwired (only the timezone floor is). The code's own docstring says the path has not shipped.
- **FR-24** — "Similar events you've attended" has no surface on the Detail Screen: no component, no API field, no route. The API contract documents the absence rather than returning an empty list, because an empty list would be a lie about a user's history.
- **FR-29** — The admin surface is a per-call cost-row list with filtered totals, not the specified dashboard: no per-MAU TCO breakdown, no week-over-week per-feature trends, no 20%-breach alerting. **This retires the 2026-11-17 matrix's FULL.**
- **FR-52** — The export control is deliberately not Pro-gated and is not placed in Pro settings, so FR-52's "UX is in Pro settings for non-EU users" is unimplemented. The JSON+ICS generation itself works.
- **FR-53** — Provider webhooks for Eventbrite / Meetup / Luma do not exist; state detection is polling-only. The only webhook code is Stripe billing.
- **FR-55** — The "postponed event that overlaps with another saved event → calm 'this overlaps with [other event]' message in the Detail Screen" has no surface.

---

## Amendment Ledger

One row per distinct `Amendment A-N` found anywhere across the PRD, Architecture Spine,
DESIGN.md, EXPERIENCE.md and the mockups. **28 amendments** are in use.

`Consistent?` = **No** where an Amendment appears in one doc but is plausibly relevant to
another doc that does not mention it.

| Amendment | Found in | Consistent? |
|---|---|---|
| A-1 | PRD (FR-15), ARCH, DESIGN | Yes — a backend dedup rule; the design docs carry FR-15's consequence, not the amendment ID. |
| A-2 | PRD (FR-5), DESIGN | Yes — DESIGN.md carries the discovery-category rule verbatim ("Amendment A-2 — serendipity slot"). |
| A-3 | PRD (FR-22) | **No** — A-3 locked FR-22's four static weights, but **no design doc mentions A-3**, and the `settings-desktop.html` Privacy ranking table plus `ranking-algorithm-transparency-desktop.html` publish a *different* formula. A-3 was superseded by A-25 in the PRD, but the design docs' weight tables were never re-stamped. **A reader of the design docs sees weights the PRD no longer holds.** |
| A-4 | PRD (FR-59), mockup (`report-event-modal-desktop.html`) | Yes — the FR-59 mockup is self-tagged A-4. |
| A-5 | PRD (FR-58), EXPERIENCE | Yes — EXPERIENCE.md §4 `Sheet.ConflictResolution` cites "PRD FR-58 / Amendment A-5". |
| A-6 | PRD (FR-60) | **No** — A-6 added FR-60 (timezone source of truth) to MVP, but **neither DESIGN.md, EXPERIENCE.md nor the Architecture Spine mentions A-6**. The Spine's *Binds* lines name FR-60 under AD-4 and AD-6, and its frontmatter says `sources_as_of: 'PRD amendments A-1..A-9'` — so the Spine knows FR-60 exists but does not carry A-6. **No design doc names FR-60 at all.** |
| A-7 | PRD (FR-3/FR-50), EXPERIENCE, 2 mockups | Yes — the provider-parity change is in EXPERIENCE.md §3 and in both onboarding-step1 mockups. |
| A-8 | PRD (FR-32/FR-33), ARCH, DESIGN, EXPERIENCE, 17 mockups | Yes — the widest convention in the project; carried in every doc it touches. |
| A-9 | PRD, ARCH, DESIGN, EXPERIENCE, 3 mockups | Yes — pre-auth chrome and the logo-halo carve-out. |
| A-10 | PRD, DESIGN, EXPERIENCE, 3 mockups | Yes — the Browse surface (6th authed route). **Note:** the PRD records A-25's *original* ID as A-10 before re-minting it to A-25 to avoid this collision; the re-mint is documented in the PRD's own frontmatter and in `docs/adr/ADR-0025.md`. |
| A-11 | DESIGN, EXPERIENCE, 3 mockups | **No** — the Browse inline keyword search appears in no PRD. **It changes what a user sees on a surface the PRD describes**, so the PRD should carry it. |
| A-12 | DESIGN, EXPERIENCE, 3 mockups | **No** — the Browse × city-page merge appears in no PRD, and it is a **merger of two surfaces the PRD describes separately** (FR-27's SEO city page and the authed Browse). The PRD still describes a city page and a browse page as separate things. |
| A-13 | DESIGN, EXPERIENCE, 2 mockups | **No** — the ranking amendment-history timeline inlined into Settings → Privacy appears in no PRD, though §10.2 and FR-22 publish ranking transparency. |
| A-14 | DESIGN, EXPERIENCE, `settings-desktop.html` | **No** — the geo-IP consent toggle on Settings → Privacy appears in no PRD; FR-2 requires the choice to *"also be surfaced in Settings → Privacy after signup"*, so **the PRD already promises this surface without describing it.** |
| A-15 | DESIGN, EXPERIENCE, `sold-out-card-state-desktop.html` | **No** — the Sold-Out badge spine promotion appears in no PRD, though FR-53/FR-54 describe the state. |
| A-16 | DESIGN, EXPERIENCE, 2 mockups | **No** — the account-delete confirmation modal appears in no PRD, though §10.2 and the retention rules imply the screen. |
| A-17 | DESIGN, EXPERIENCE, `export-request-modal-desktop.html` | **No** — the data-export modal's tier-gate and jurisdictional reasoning appears in no PRD; FR-52 does not describe it. |
| A-18 | DESIGN, EXPERIENCE, `settings-sources-desktop.html` | **No** — the `/settings/sources` page appears in no PRD, though FR-13/FR-16/FR-23 imply a source surface. |
| A-19 | DESIGN, EXPERIENCE, `settings-quiet-hours-pro-desktop.html` | **No** — the Pro per-day-of-week quiet-hours picker appears in no PRD, though FR-51 names the capability. |
| A-20 | DESIGN, EXPERIENCE, 2 mockups | **No** — the `/signin` + `/signup` pre-auth routes appear in no PRD, though FR-4 requires an authenticated state to be reachable. |
| A-21 | DESIGN, EXPERIENCE | **No** — the reminder-picker shell migration is a design-only change with no PRD consequence; **consistent by nature.** |
| A-22 | DESIGN | **No** — the Pulse Card state treatment (sold out / cancelled / postponed) is design-only and has no PRD consequence; **consistent by nature.** |
| A-23 | DESIGN, EXPERIENCE | **No** — the traceability design-gap closure appears in no PRD, though it *adds design for FR-20, FR-28, FR-49 and FR-55* — all MVP FRs. **The PRD is not required to describe components, but the amendment it is the counterpart of is not discoverable from the PRD.** |
| A-24 | EXPERIENCE | **No** — EXPERIENCE-only; no PRD consequence identified. |
| A-25 | PRD (FR-22), EXPERIENCE | **No** — A-25 re-mints FR-22's formula and **changes no weight and no requirement**, so the design docs are arguably unaffected — but `settings-desktop.html` and `ranking-algorithm-transparency-desktop.html` publish a weights table that a reader will compare against the PRD's. **The design docs' weight table was never re-stamped with A-25.** This is the same defect as A-3, and it is the one that matters. |
| A-26 | PRD (FR-8), EXPERIENCE | Yes — EXPERIENCE.md's frontmatter records the A-26 withdrawal explicitly. **DESIGN.md does not mention A-26** — but A-26 *removes* a link rather than adding a component, so the design surface is unchanged; **consistent by nature.** |
| A-27 | PRD | **No** — the withdrawal of two published retention categories appears in no other doc. **This is the amendment with the widest blast radius and the fewest echoes**: it removes claims published to users through `/privacy` (§10.2 is published there). Whether a design doc describing "What we store" exists is worth a look — `/privacy` is a legal page in the frontend, not in DESIGN.md. |
| A-28 | PRD | **No** — the corrected training-data statement appears in no other doc. Same reasoning as A-27: §10.2 is published through `/privacy`. |

### The pattern in the ledger

**Three groups, and only one of them is a defect:**

1. **PRD-only, no design consequence (A-1, A-6, A-27, A-28).** A-1 governs a backend dedup
   rule; A-27 and A-28 withdraw *published claims* rather than describing a screen. These are
   consistent by nature — there is no design doc for them to appear in. **A-6 is the
   exception** (below).
2. **Design-only, no PRD consequence (A-11, A-12, A-13 … A-24).** The UX spine and its
   mockups have been far more active than the PRD, and most of these amendments describe
   *how* a surface looks rather than *what* the product promises. **The PRD is a
   requirements document, not a component catalogue — it is not wrong to omit them.**
   The two that matter are **A-12** (it merges two surfaces the PRD describes separately)
   and **A-14** (the PRD *already promises* the surface A-14 builds).
3. **A real inconsistency, in one place (A-3 → A-25).** FR-22's published formula was
   locked by A-3, superseded by A-25, and **the design docs were never re-stamped**. The
   PRD's frontmatter and `docs/adr/ADR-0025.md` both record the supersession; the UX
   spine's weight tables do not. **A reader comparing the Settings → Privacy ranking
   table against the PRD is comparing two formulas, and neither doc says which is
   current.**

**The finding this section is best placed to make:** A-3/A-25 is a *cross-document*
consistency defect about a **published, user-facing** formula, and it is the only
amendment in the ledger where the docs disagree about a fact a user can read on a screen.
The A-11/A-12/A-13…A-24 group is a scope difference, not a disagreement — but A-12 and
A-14 are the two where the PRD's own text is out of step.

---

## Deferred / Out-of-MVP FRs

Listed but **not scored** — the PRD's §6.2 defers these, and the matrix does not hold
deferred work against the build.

| FR | Title | Target phase | Deferred because |
|---|---|---|---|
| FR-31 | Two-Way Calendar Sync + Recurring Event Expansion | Phase 2 | Needs two-way sync and RRULE modeling. |
| FR-34 | Pulse the Group | Phase 2 | Needs trust established first. |
| FR-35 | Pro Tier Augmentation | Phase 2 | Augments the MVP Pro tier. |
| FR-36 | Voice Quick-Add | Phase 3 | Demo magnet, niche. |
| FR-37 | Email-to-Event Forwarding | Phase 3 | Power-user only (source-side email-ICS is MVP via FR-56). |
| FR-38 | Why Now? | Phase 3 | Augments, does not replace FR-21. |
| FR-39 | On-Device Personal AI | Phase 3 | Privacy + cost; AD-8's gateway is the seam. |
| FR-40 | Travel Mode | Phase 3 | Requires trip detection. |
| FR-41 | Group Availability Heatmap | Phase 3 | Needs Phase 2 group features. |
| FR-42 | White-Label B2B2C | Year 2+ | Pivot option. |
| FR-43 | B2B Insights API | Year 2+ | Revenue diversification. |
| FR-44 | Already-Handled Reminder Suppression | Phase 2 | Needs user-action detection. |
| FR-45 | Adaptive Pulse Digest Card Count | Phase 3 | Data-dependent; 3-card discipline holds. |
| FR-46 | Pulse Streak | Year 2+ | Brand loyalty, not a metric to optimize. |
| FR-47 | Year in Pulse Recap | Year 2+ | Annual brand-love feature. |

**Also deferred, and not FRs:** native mobile apps, real-time push notifications to
mobile, event reviews/ratings on the Detail Screen, and native calendar write-back are all
named in the PRD's §6.2 as out of scope for MVP.

---

## Epic/Story Coverage

**— not yet created.** No BMad epics or stories document exists anywhere under
`_bmad-output/planning-artifacts/`.

The closest equivalent is the FIRE work-item set under
`.specs-fire/intents/*/work-items/`. Each FIRE work item carries its own acceptance
criteria and is the unit the build actually plans against, so the intent structure and the
PRD's FR list are two views of the same requirements rather than one being a substitute
for the other.

**The most recently closed intent is `city-picker-and-auto-collection`** (run
`run-eventpulse24-057`, 11 of 11 items complete). Its items map onto the PRD's FR-2
(city in the Pulse Preview), FR-4/FR-7 (the stored city and the digest delivery time) and
FR-13/FR-17 (the source registry and the acquisition hierarchy), and it introduced the
curated 166-city catalog that no FR names explicitly — **a capability the PRD does not
yet describe.** That is a PRD-side gap, not a build gap, and it is the natural next
candidate for an amendment.

---

## What a reader should take from this

**The Architecture Spine is complete.** Every one of the 45 MVP FRs is named by a
Capability Map row with a module and at least one AD. Nothing there needs fixing.

**The Design docs are complete for user-facing surfaces and silent for two internal
tools.** Every user-facing FR has a mockup or a named component. The two gaps — FR-57 and
FR-29 — are both *internal* tools, and both are explicitly excluded from the surface map
by EXPERIENCE.md §2 rather than overlooked. **Whether an internal tool deserves a
designed screen is a product decision, not a traceability defect** — but the exclusion
means no one has ever written down what those screens should do.

**The Implementation is six partials, and five of them are documented absences the code
itself explains.** FR-24's absent similar-events, FR-52's deliberately ungated export, and
FR-14's not-yet-shipped LLM path are each the subject of a docstring in the codebase
explaining why. **That is the codebase being honest about its own edges**, which is a
different thing from a gap someone forgot. FR-29, FR-53's webhooks and FR-55's overlap
message are the three where nothing in the code says "not yet".
