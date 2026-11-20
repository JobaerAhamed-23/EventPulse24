# EventPulse24 — Traceability Matrix

Generated: 2026-11-17, **regenerated the same day** after the `traceability-gap-closure` intent closed its items (produced by the project's own `doc-trace` skill — `.claude/skills/doc-trace/SKILL.md`)

**Supersedes the 2026-11-13 matrix.** That version scored Sections A and B on 2026-11-12 and
added Section C on 2026-11-13. Four days of work have landed since, and **three of its four
headline findings have expired** — FR-25, FR-16 and FR-13 were all `MISSING` in Section C and
are now reachable; FR-16's Section A `PARTIAL` is now `FULL`. They are retired below with
evidence rather than silently dropped by the re-scan.

**Section C is now a full pass.** The earlier version scored 12 of 45 MVP FRs and left 33
`UNASSESSED`, which was honest but not useful. Every MVP FR is scored here against running
code, and that pass found **one new gap no matrix had ever looked at** (FR-29).

**This regeneration scores the work that closed it.** Between the two runs, the
`traceability-gap-closure` intent shipped FR-29's admin, FR-10's Settings control and
FR-32's location reveal, and repaired six tests that had expired. **All three sections now
read 0 missing and 0 partial.** Two new findings were raised rather than papered over —
`timeline-why-this-tag` and `fr22-published-formula` — and both are decisions for a human,
not work waiting on a runner.

**Sources scanned:**
- PRD: `_bmad-output/planning-artifacts/prds/prd-EventPulse24-2026-08-19/prd.md` — 60 FR headings: 45 MVP (FR-1–30, FR-32, FR-33, FR-48–FR-60) and 15 deferred (FR-31, FR-34–FR-47), listed separately and not scored.
- Architecture Spine: `_bmad-output/planning-artifacts/architecture/architecture-EventPulse24-2026-09-04/ARCHITECTURE-SPINE.md`
- UX Design: `_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/DESIGN.md`
- UX Experience: `_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/EXPERIENCE.md`
- Mockups: **50 HTML files** — 39 in `mockups/`, 6 in `mockups/mobile/`, 5 in `mockups/light-archive/`, confirmed against `ls`. Each file's **entire leading comment** was read for FR tags. Archive files are not counted as evidence; they are superseded light-theme variants.
- Implementation: the `frontend/` route tree (28 `page.tsx` routes) and `backend/` Django admin registrations. Every component cited in Section C was checked for a **real importer rooted in a route**, not merely for existing.
- Epics/Stories: no BMad epics document exists. FIRE work items under `.specs-fire/intents/*/work-items/` are the closest equivalent — see Epic/Story Coverage.

---

## Section A — PRD ↔ Design Alignment

For each MVP FR: does a design element exist, in enough detail to build the UI from?
`FULL` = a self-tagged mockup (tier 1) or a named DESIGN.md/EXPERIENCE.md section citing the
FR (tier 2). `PARTIAL` = inferable by adjacency only. `MISSING` = a user-facing requirement
with nothing found. `N/A` = no UI surface by nature.

**Counts: 36 FULL · 0 PARTIAL · 0 MISSING · 9 N/A** (45 total)

| FR-ID | Title | Design element found | Status | Note |
|---|---|---|---|---|
| FR-1 | 30-Second Onboarding Flow | `light-archive/onboarding-step1-desktop.html`, `light-archive/onboarding-step1-mobile.html`, `onboarding-skip-all-state-desktop.html`, `signup-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-2 | Pulse Preview (No-Auth First Value) | `geo-consent-banner-desktop.html`, `pulse-preview-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-3 | Calendar Connect (read-only ICS/webcal) | `light-archive/onboarding-step1-desktop.html`, `light-archive/onboarding-step1-mobile.html` | FULL | self-tagged mockup header (tier 1) |
| FR-4 | Authenticated User State | `signin-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-5 | Pulse Digest Composition | named in EXPERIENCE.md (3 citations); Slot 3's treatment in DESIGN.md `component.card.pulse.digest.category.discovery`, now tagged **Amendment A-2** | FULL | named section citing the FR (tier 2) |
| FR-6 | Pulse Card Information Density | named in EXPERIENCE.md (2 citations) | FULL | named section citing the FR (tier 2) |
| FR-7 | Pulse Digest Delivery Time | named in EXPERIENCE.md (3 citations) | FULL | named section citing the FR (tier 2) |
| FR-8 | Empty-State Pulse Digest | `pulse-digest-empty-state-desktop.html` | FULL | self-tagged mockup header (tier 1). **Amendment A-26 (2026-11-20)** withdrew the "Suggest an event" link from §5 on both the digest and the (never-built) `/preview` SEO-referrer placement — the card itself is unchanged |
| FR-9 | Multi-Tier Reminder Picker | `event-detail-desktop.html`, `personal-event-reminders-desktop.html`, `reminder-picker-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-10 | Pulse Ping — Single Daily Notification | — | N/A (no design needed) | notification channel, not an in-app screen; incidentally tagged in `onboarding-skip-all-state-desktop.html` |
| FR-11 | Email Multi-Tier Reminders | named in EXPERIENCE.md | FULL | named section citing the FR (tier 2) |
| FR-12 | Quiet Hours | named in EXPERIENCE.md (2 citations) | FULL | named section citing the FR (tier 2) |
| FR-13 | Source Registry | named in DESIGN.md + EXPERIENCE.md | FULL | named section citing the FR (tier 2) |
| FR-14 | Hybrid Event Extraction Pipeline | — | N/A (no design needed) | backend extraction pipeline |
| FR-15 | Event Deduplication | — | N/A (no design needed) | backend dedup |
| FR-16 | Source Reliability Score | EXPERIENCE.md §`Component.Settings.Sources` — **"As built (FR-16)"**, the beta-binomial posterior and the 1–5 band | **FULL** | **upgraded from PARTIAL**; see retired finding R-1 |
| FR-17 | Source Acquisition Hierarchy Enforcement | — | N/A (no design needed) | internal acquisition policy |
| FR-18 | Manual Personal Event Creation | `personal-event-create-desktop.html`, `personal-event-edit-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-19 | Personal Event in Pulse Digest | `personal-event-reminders-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-20 | Personal Event Reminder Defaults | `collections-desktop.html`, `personal-event-reminders-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-21 | Why-this Tags | named in EXPERIENCE.md (3 citations) | FULL | named section citing the FR (tier 2) |
| FR-22 | Confidence Pulse | `ranking-algorithm-transparency-desktop.html`, `settings-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-23 | Source Badge | named in EXPERIENCE.md (2 citations) | FULL | named section citing the FR (tier 2) |
| FR-24 | "Why this?" Detail Screen | `event-detail-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-25 | "Less like this" Adjustment | `less-like-this-mute-prompt-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-26 | Public Event Pages with Structured Data | `public-event-page-desktop.html`, `share-affordance-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-27 | SEO City Pages | `city-page-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-28 | Share-Card Public Link | `share-affordance-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-29 | AI Cost Dashboard (Internal) | — | N/A (no design needed) | internal Django admin tool, outside this design system |
| FR-30 | Caching & Batching Defaults | — | N/A (no design needed) | backend caching/batching policy |
| FR-32 | Unified Personal+Public Timeline | `timeline-desktop.html`, `mobile/timeline-mobile.html` | FULL | self-tagged mockup header (tier 1) |
| FR-33 | Conflict-Aware Scheduling | `conflicts-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-48 | Pro Tier with MVP-Only Features | `export-request-modal-desktop.html`, `pricing-page-desktop.html`, `pro-upgrade-cta-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-49 | Unlimited Saves + Saved Collections (Pro) | `collections-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-50 | Calendar Provider Read-Only Sync | named in DESIGN.md + EXPERIENCE.md | FULL | named section citing the FR (tier 2) |
| FR-51 | Per-Day-of-Week Custom Quiet Hours (Pro) | named in DESIGN.md + EXPERIENCE.md (Amendment A-19) | FULL | named section citing the FR (tier 2) |
| FR-52 | JSON + ICS Data Export (Pro) | `export-request-modal-desktop.html`, `share-affordance-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-53 | Event State Polling + Webhooks | `sold-out-card-state-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-54 | User-Facing State-Change Notifications | `sold-out-card-state-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-55 | Conflict Resolution on State Change | `conflict-indicator-card-state-desktop.html`, `conflict-prompt-desktop.html`, `event-state-conflict-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-56 | RSS / Email-ICS Source Acquisition | — | N/A (no design needed) | backend source acquisition |
| FR-57 | Editorial Review Queue (Internal) | — | N/A (no design needed) | internal Django admin tool |
| FR-58 | Personal Event Conflict Detection | `conflict-indicator-card-state-desktop.html`, `conflict-prompt-desktop.html`, `event-state-conflict-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-59 | User-Reported Event Quality | `report-event-modal-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-60 | Timezone Source of Truth | — | N/A (no design needed) | backend stored-timestamp truth policy; the zone *control* a user sees belongs to FR-7's digest schedule, which is designed |

### Open Design gaps

**None.** Every MVP FR with a user surface carries either a self-tagged mockup or a named
DESIGN.md/EXPERIENCE.md section citing it; the nine `N/A` rows have no UI surface by nature.
This is the first run in which Section A is clean.

**Retired finding R-1 — FR-16 `PARTIAL` → `FULL`.** The 2026-11-13 matrix scored FR-16
`PARTIAL (inferred only)` and stated that `FR-16` was cited *"nowhere — not in DESIGN.md, not
in EXPERIENCE.md, not in any mockup header (verified by search, 0 hits in all three)"*. That
was true when written. EXPERIENCE.md now carries two citations, added by commit `fe307b6`
(2026-11-13) — a frontmatter `A-18` as-built note and a body paragraph in
§`Component.Settings.Sources` reading **"As built (FR-16): the score is the beta-binomial
posterior over the source's observed outcomes (`domain/reliability.py`)…"**. That is tier-2
evidence by this skill's own rule 2, and the gap the previous matrix asked to close ("one line
in EXPERIENCE.md's `settings-sources` row") is the line that closed it.

---

## Section B — PRD ↔ Architecture Alignment

For each MVP FR: does the Capability → Architecture Map have an explicit row naming it (or a
range covering it), with a module and at least one `AD-N`?

**Counts: 45 FULL · 0 PARTIAL · 0 MISSING · 0 N/A** (45 total)

The Capability Map's 15 rows cover all 45 MVP FRs with no gaps and no overlaps:

| Capability row | FRs covered | Lives in | Governed by | Status |
|---|---|---|---|---|
| FR-1–4 Onboarding & account | FR-1, 2, 3, 4 | `identity`, `personalization`, frontend, `adapters/calendar` | AD-5, AD-12, AD-15, AD-18 | FULL |
| FR-5–8 Pulse Digest | FR-5, 6, 7, 8 | `personalization`, frontend | AD-3, AD-10, AD-11 | FULL |
| FR-9–12 Reminders & Pulse Ping | FR-9, 10, 11, 12 | `delivery`, `worker` | AD-6, AD-7, AD-16, AD-17 | FULL |
| FR-13–17, FR-56, FR-60 Ingestion & sources | FR-13, 14, 15, 16, 17, 56, 60 | `ingestion`, `worker`, `adapters/crawl` | AD-4, AD-6, AD-8, AD-9 | FULL |
| FR-18–20, FR-58 Personal events & conflict | FR-18, 19, 20, 58 | `personalization` | AD-3, AD-6, AD-16, AD-21 | FULL |
| FR-32 Unified Timeline | FR-32 | `personalization`, frontend | AD-3, AD-6, AD-21 | FULL |
| FR-33 Conflict-aware scheduling | FR-33 | `personalization`, `delivery`, frontend | AD-6, AD-17, AD-21 | FULL |
| FR-21–25 Explainability & trust | FR-21, 22, 23, 24, 25 | `personalization` | AD-9, AD-10 | FULL |
| FR-26–28 Sharing & SEO | FR-26, 27, 28 | `catalog`, frontend | AD-12, AD-19 | FULL |
| FR-29 AI Cost Dashboard | FR-29 | `adapters/llm`, `editorial` (Django admin) | AD-8, AD-14 | FULL |
| FR-30 Caching & batching | FR-30 | `adapters/llm` | AD-8 | FULL |
| FR-48–52 Pro tier | FR-48, 49, 50, 51, 52 | `identity`, `adapters/billing`, `adapters/calendar` | AD-5, AD-15, AD-18 | FULL |
| FR-53–55 Event state sync | FR-53, 54, 55 | `ingestion`, `delivery`, `personalization` | AD-4, AD-7, AD-17, AD-21 | FULL |
| FR-57 Editorial review queue | FR-57 | `editorial` (Django admin) | AD-4, AD-8, AD-14 | FULL |
| FR-59 User event reports | FR-59 | `personalization`, `editorial` | AD-3, AD-14 | FULL |

### Open Architecture gaps

**None.** FR-32 and FR-33, the September matrix's two `MISSING` rows, have carried their own
Capability rows and AD-21 since the A-8 lift and remain present.

**A caution this section cannot see, and Section C now can.** FR-29 carries a Capability row
naming `adapters/llm` and `editorial` (Django admin) and is scored `FULL` here — correctly,
because the architectural home exists. Section C finds that the admin half of that row was
never built. An architectural home is not a surface.

---

## Section C — PRD ↔ Implementation

**Can a user reach this, in the running product, today?**

Sections A and B cannot see the difference between designed and built. FR-18 once carried
`FULL` in both while its delete control did not exist — scored on a mockup that draws a danger
zone nobody implemented.

**Evidence here is running code — a route, a mount, a control on a surface that renders.** A
mockup is Section A's evidence and is never reused here; an architecture row is Section B's.
Every component cited below was checked for an importer rooted in a route, because *a called
endpoint is not a reachable feature* and *a passing test is not a reachable feature* — the two
traps that have already caught this project.

**Counts: 40 FULL · 0 PARTIAL · 0 MISSING · 5 N/A · 0 UNASSESSED** (45 total)

**This is the first complete pass.** The previous version scored 12 and left 33 `UNASSESSED`.

| FR | Requirement | Status | Evidence (running code) |
|---|---|---|---|
| FR-1 | 30-Second Onboarding Flow | FULL | `app/onboarding/page.tsx` → `components/onboarding/onboarding-flow.tsx` (three optional steps) |
| FR-2 | Pulse Preview (No-Auth First Value) | FULL | `app/preview/page.tsx` → `components/preview/preview-section.tsx` |
| FR-3 | Calendar Connect (ICS/webcal) | FULL | `components/onboarding/calendar-step.tsx`, imported by `onboarding-flow.tsx:54`; also `app/settings/calendars/page.tsx` |
| FR-4 | Authenticated User State | FULL | `app/signin/`, `app/signup/`, `app/reset-password/`; session via `lib/session.ts`, `homeRoute` gating every authed surface |
| FR-5 | Pulse Digest Composition | FULL | `app/page.tsx` → `components/digest/digest-card-list.tsx`; renders the server's composition in the server's order (AD-10) |
| FR-6 | Pulse Card Information Density | FULL | `components/digest/pulse-card.tsx` — kicker, trust row, title, ≤3 tags, time · place; no density branch that hides a trust signal |
| FR-7 | Pulse Digest Delivery Time | FULL | `components/settings/digest-delivery-time.tsx` @ `app/settings/general/page.tsx` |
| FR-8 | Empty-State Pulse Digest | FULL | `components/digest/digest-empty.tsx`, imported by `app/page.tsx`. **The "Suggest an event" link is gone by Amendment A-26, and its absence is enforced, not remembered** — `tests/internal-links.test.ts`. Both matrices scored this row `FULL` while the link 404'd; see the new finding below |
| FR-9 | Multi-Tier Reminder Picker | FULL | `app/events/[id]/reminders/page.tsx` |
| FR-10 | Pulse Ping — Single Daily Notification | FULL | `worker/tasks.py:486` → `mint_ping_send`; **and the user can now turn it off and on** at `components/settings/pulse-ping-switch.tsx` @ `/settings/general`, through `resubscribe_pulse_ping` / `unsubscribe_pulse_ping`. **O-1 closed by `d39c897`** — onboarding's "you can change this anytime" is true as written |
| FR-11 | Email Multi-Tier Reminders | FULL | `apps/delivery` (`ScheduledSend`, `email_api.py`, templates); plans set from the FR-9 picker |
| FR-12 | Quiet Hours | FULL | `components/settings/quiet-hours-window.tsx` @ `app/settings/general/page.tsx` |
| FR-13 | Source Registry | FULL | `app/settings/sources/page.tsx` → `components/settings/source-list.tsx`. **Was MISSING until `fe307b6` (2026-11-13)** |
| FR-14 | Hybrid Event Extraction Pipeline | N/A | backend pipeline, no user surface by nature |
| FR-15 | Event Deduplication | N/A | backend dedup, no user surface by nature |
| FR-16 | Source Reliability Score | FULL | `components/settings/source-trust-dots.tsx` + `source-trust-legend.tsx`, rendered by `source-list.tsx` @ `/settings/sources`. **Was MISSING until `fe307b6`** — `domain/reliability.py` computed a score nothing showed |
| FR-17 | Source Acquisition Hierarchy Enforcement | N/A | internal acquisition policy |
| FR-18 | Manual Personal Event Creation | FULL | `components/sheets/personal-event-form.tsx` incl. its `DangerZone` delete. **Was MISSING until `2ba0073`** |
| FR-19 | Personal Event in Pulse Digest | FULL | `components/settings/digest-personal-events.tsx` @ `app/settings/general/page.tsx` |
| FR-20 | Personal Event Reminder Defaults | FULL | `app/personal-events/[id]/reminders/page.tsx`; defaults at `components/settings/default-reminder-slots.tsx`. **Was MISSING until `63a9535`** |
| FR-21 | Why-this Tags | FULL | `pulse-card.tsx` tag row, capped at `MAX_WHY_THIS_TAGS` = 3, comma-separated in the DOM |
| FR-22 | Confidence Pulse | FULL | `ConfidencePulse` in `pulse-card.tsx` — five positions, explanation kind named visibly and in the `aria-label` |
| FR-23 | Source Badge | FULL | `SourceBadgeBadge` in `pulse-card.tsx`, with tooltip trigger raised above the stretched link |
| FR-24 | "Why this?" Detail Screen | FULL | `components/detail/detail-breakdown.tsx` + `record-detail-open.tsx` @ `app/events/[id]/page.tsx`. **Was PARTIAL until `d064713`** |
| FR-25 | "Less like this" Adjustment | FULL | `components/digest/mute-prompt.tsx` (swipe path) + `components/settings/taste-mute-list.tsx` @ `app/settings/taste/page.tsx`. **Was MISSING until `c114f33`…`bf141f0` (2026-11-14)** |
| FR-26 | Public Event Pages with Structured Data | FULL | `components/public-event/public-event-page.tsx` @ `app/events/[id]/page.tsx` (public shell branch) |
| FR-27 | SEO City Pages | FULL | `app/events-in/[slug]/page.tsx` → `components/city-page/city-page.tsx`; `app/sitemap/`, `app/robots.ts` |
| FR-28 | Share-Card Public Link | FULL | `components/share/share-control.tsx`, mounted by `pulse-card.tsx` and `detail-actions.tsx`, gated on `public_slug` |
| FR-29 | AI Cost Dashboard (Internal) | **FULL** | `adapters/llm/admin.py` — read-only `AICostRow` registration with add/change/delete all refused and a **total over the filtered queryset**, so PRD §10.3's ceiling is answerable at a glance. **Was MISSING until commit `da8d651` (2026-11-17)**: the rows had accrued since the gateway shipped with nothing able to read them back |
| FR-30 | Caching & Batching Defaults | N/A | backend caching/batching policy |
| FR-32 | Unified Personal+Public Timeline | FULL | `app/timeline/page.tsx` → `timeline-panel.tsx`, `timeline-block.tsx`, `timeline-navigator.tsx`; the block now **reveals its location on hover and focus** (`d1d6c83`, `b4ba162`), with the place resolved server-side onto `TimelineBlockOut`. **O-2 closed (2026-11-19)** — §13's Why-this tag is **withdrawn by Amendment A-24**: the block reveals location only, and that is now the spec's position rather than a gap. Reasoning, and two corrections to the original finding, under *Open items* below |
| FR-33 | Conflict-Aware Scheduling | FULL | `app/conflicts/page.tsx` → `components/conflicts/conflicts-panel.tsx` |
| FR-48 | Pro Tier with MVP-Only Features | FULL | `app/pricing/page.tsx`; `components/settings/plan-summary.tsx` @ `/settings/account`; free-cap enforcement at `components/browse/browse-quota-note.tsx` + `components/upgrade/upgrade-prompt.tsx` |
| FR-49 | Unlimited Saves + Saved Collections (Pro) | FULL | `components/collections/collection-manager.tsx` @ `app/settings/collections/page.tsx`. **Assign was MISSING until `da924ca`** |
| FR-50 | Calendar Provider Read-Only Sync | FULL | `components/settings/calendar-connections.tsx` @ `app/settings/calendars/page.tsx`. **Was MISSING until `2dc7432`** |
| FR-51 | Per-Day-of-Week Custom Quiet Hours (Pro) | FULL | `components/settings/weekday-quiet-hours.tsx` @ `app/settings/general/page.tsx`; Pro gate enforced server-side at `preferences_api.py:125` `_refuse_weekday_windows_without_pro` |
| FR-52 | JSON + ICS Data Export (Pro) | FULL | `components/settings/download-my-data.tsx` @ `app/settings/account/page.tsx` |
| FR-53 | Event State Polling + Webhooks | FULL | `components/state/event-state-badge.tsx`, mounted by `pulse-card.tsx` and `browse-card.tsx`, driven by server `status`/`is_sold_out` |
| FR-54 | User-Facing State-Change Notifications | FULL | `components/state/notice-strip.tsx` @ `app/page.tsx`; `components/state/detail-notice-banner.tsx` @ `app/events/[id]/page.tsx`; `apps/delivery/notices_api.py` |
| FR-55 | Conflict Resolution on State Change | FULL | `components/sheets/conflict-resolution.tsx`, mounted by `detail-actions.tsx` and `personal-events-panel.tsx` |
| FR-56 | RSS / Email-ICS Source Acquisition | N/A | backend acquisition, no user surface by nature |
| FR-57 | Editorial Review Queue (Internal) | FULL | `apps/ingestion/admin.py:602` `@admin.register(ReviewItem)` — reachable by staff in Django admin |
| FR-58 | Personal Event Conflict Detection | FULL | `components/conflicts/conflict-pair-card.tsx`, `conflict-side.tsx`; the conflict dot on `timeline-block.tsx` and `ConflictIndicator` on the Pulse Card |
| FR-59 | User-Reported Event Quality | FULL | `components/detail/event-report-control.tsx` → `POST /api/personal/event-reports` |
| FR-60 | Timezone Source of Truth | FULL | `components/settings/digest-timezone.tsx` @ `app/settings/general/page.tsx` (commit `86e78c5`) — the zone the digest is composed in is shown and changeable; the storage-truth policy itself is backend |

### Open Implementation gaps

**One, found by a user on 2026-11-20 and not by this matrix — and it is a gap in the
matrix's method, not only in the product.**

**F-1 — a scored-`FULL` row whose link 404'd.** FR-8's empty Pulse Digest carried a
"Suggest an event" link to `/suggest`, a route that has never existed in any layer: no FR,
no model, no endpoint, no table, no admin. Both the 2026-11-13 and 2026-11-17 matrices
scored FR-8 `FULL` in Sections A and C, and **by FR-8's letter both were right** — the PRD
asks for a link, and a link was there.

**Section C checks that a component has a real importer rooted in a route. It has never
followed an `href` to the other end.** That is the gap class, and FR-8 is not the only place
it could hide. Closed by **Amendment A-26** (link withdrawn, not deferred) in
`run-eventpulse24-055`.

**Three further dangling destinations were found, and two of them are worse than FR-8's.**

`/terms` and `/privacy` are linked from `components/auth/signup-form.tsx` and
`app/signin/page.tsx` beneath *"By creating an account, you agree to our Terms and Privacy
Policy."*, **and again from `components/pre-auth/pre-auth-footer.tsx`**. The product asked
people to accept documents it then 404'd. **These are invisible to every section of this
matrix** — a published privacy policy is required by §10.2/§10.5 and by GDPR, CCPA/CPRA,
PIPEDA and the Privacy Act, none of which carry FR headings, and this matrix scores FR
headings only. Being built in the same run (`legal-page-routes`, `legal-copy-draft`).

`/how` is the third, and **it was missed by the first pass of the very test written to
catch this class** — a correction recorded here rather than left standing. That test
matched the JSX attribute form `href="/x"`; the pre-auth footer holds its links in an
object literal (`{ href: "/how", label: "How it works" }`), which the pattern did not see.
The matcher now accepts both forms, and `/how` is the only route the widened pass adds.
**It reaches further than any other link in this finding**: `PreAuthFooter` renders on
eight surfaces — both auth screens, `/preview`, `/pricing`, the public event and city
pages, and both not-found pages.

**`/how` has no requirement behind it.** EXPERIENCE.md §323 names the pre-auth footer's
secondary affordances as *"Log in, Privacy, Terms, social links"*; "How it works" appears
in that section only as something that must **not** be in the topbar. The footer's own
header comment records that its link list was taken from the mockups. So it is FR-8's
shape again — a link with no destination and nothing asking for one — and it is **fenced
and undecided**, not scheduled.

**The lesson is about the guard, not the links.** A source-matching test is only as good
as the forms it matches, and its first version was blind to the commonest way this
codebase stores a route: in a table. `lib/settings-sections.ts` holds exactly such a table;
every row in it resolves today, and the widened matcher now reads it.

**The method is repaired as well as the product.** `frontend/tests/internal-links.test.ts`
resolves every literal internal `href` under `app/**` and `components/**` against a real
`page.tsx` or `route.ts`. A resolving check already existed in
`tests/digest-home-boundary.test.ts` and was sound — it reached only the fifteen files of
the digest home, which is precisely why the auth surfaces' links were never seen. **A future
regeneration should treat a green `internal-links` run as evidence for the "reachable"
half of Section C**, rather than re-deriving it by reading imports.

### Previously (2026-11-17)

**None.** Every MVP FR with a user surface is reachable in the running product. This is the
first regeneration in which all three sections read clean at once.

**FR-29 is closed, and it is worth saying what it was.** `AICostRow` had been written on
every LLM call since the gateway shipped, with no admin, no API and no page — a complete,
tested backend with no reachable surface, scored `N/A` by Section A (correctly: an internal
admin tool is outside the design system) and `FULL` by Section B (correctly: the Capability
row names the module). Neither section asks whether the admin was built. That is the gap
Section C exists for, and it is the gap it found.

### Open items that are decisions, not work

- **`timeline-why-this-tag`** — **DECIDED 2026-11-19, Amendment A-24: location only.**
  `EXPERIENCE.md` §13 promised a desktop Timeline block adds location **and one Why-this
  Tag** on hover. The location shipped; the tag is withdrawn.

  **Two claims in the original finding were wrong, and are corrected here rather than
  left to mislead a later reader.** (1) It is *not* four extra reads — `why_this_tags`
  reads only `inputs.city_match` from `RankingInputs`, the user's city rides on the
  `DigestPreference` row the Timeline already fetches, and `chip_keys_for` is pure text
  over columns the batched catalog read already selects, so the true cost is **one**
  extra query. (2) AD-10 does *not* bar the route — the contract forbids
  `apps.ingestion.event_fit`, and the Relevance Pulse path (`why_this_tags`) never
  reaches it; `personalization` already imports `catalog_read`. AD-10 remains correct and
  remains load-bearing: substituting one explanation kind for the other is the
  trust-collapse failure PRD Risk 11 calls company-ending. It simply is not what stopped
  this.

  **What actually stopped it is that the tag says nothing here.** Every public block on
  the Timeline *is* a saved event, so `is_saved` is universally true; `discovery` needs a
  digest slot and never fires; the time tags are relative to `now`, so none fire on any
  week but the current one. The single tag §13 asked for therefore resolves to `nearby` on
  every block in the user's city, or to `saved` — which, on a surface showing only saved
  events, answers *"why is this here?"* with *"because you saved it."* The one informative
  tag, `matches_<chip_key>`, sorts last in `RANKING_TAG_ORDER` and is unreachable whenever
  any fixed tag applies. Revisitable if FR-25's preference graph ever makes it meaningful.
- **`fr22-published-formula`** — **DECIDED 2026-11-19, Amendment A-25: the five-term
  as-built formula is canonical.** FR-22 publishes four components; the product computes
  five terms. The divergence is deliberate and well-argued in `domain/ranking.py` (the two
  dropped terms depend on FR-25's preference graph, which did not exist) and is pinned to
  `ADR-0025`.

  **The original finding's premise was wrong, and it is corrected here.** It said the PRD
  "still publishes the four-term version … the document FR-22 names as the source of the
  published formula is the one that does not know it changed." **It knew.** `prd.md:751`
  carried the amendment, dated 2026-11-11 and citing ADR-0025, and it predates the
  2026-11-17 pass that raised this finding.

  **What was actually wrong was the amendment's ID**: it reused **A-10**, which already
  belonged to the Browse surface amendment (2026-09-06), so two amendments shared one ID
  and this ledger read clean over the collision. Alongside it, FR-22 contradicted itself —
  the locked table published `w1 = 0.40` while the amendment implemented `interest_overlap`
  at 0.35 and asserted the weights were unchanged — and `[ASSUMPTION-11]` still cited A-3.
  All three are fixed under A-25. **No weight moved**; `shared/constants.py` is untouched.

  **One consequence remains open, and it is not a filing matter.** EXPERIENCE.md §2 row 9
  commits `/settings/privacy` to showing users the formula, weights table, bucket
  boundaries, amendment history and pledge, and FR-22's own consequences require it. **That
  route does not exist** — no surface in `frontend/` renders a formula at all. So no user
  is being shown a wrong formula, but FR-22's transparency promise is unkept. Tracked as
  `settings-privacy-ranking-transparency`.

### The test suite, for the record

The backend suite ran **6 failed** across the first three runs of this intent and is now
**7314 passed, 0 failed**. None of the six was a regression: each pinned an absolute date
the wall clock had passed. They are repaired by anchoring the fixtures to the calendar, and
the repair was proved non-vacuous by mutation rather than by assertion. **Twenty further
test files combine a pinned date with a real-clock HTTP path**; all pass today and are
listed in `run-eventpulse24-039`'s test report rather than touched.

### Retired findings from the 2026-11-13 Section C

| FR | Then | Now | What closed it |
|---|---|---|---|
| FR-25 | MISSING — *"No endpoint, no model, no column, no UI"* | **FULL** | `c114f33` (vocabulary + embedding adapter), `bf80b41` (event vectors), `a179070` (swipe → mute, reversible), `bf141f0` (the loop + reversal surface), 2026-11-14 |
| FR-13 | MISSING — registry built, no user-reachable surface | **FULL** | `fe307b6` (2026-11-13) — `/settings/sources` |
| FR-16 | MISSING — score computed, nothing exposed it | **FULL** | `fe307b6` (2026-11-13) — trust dots + legend on `/settings/sources` |

---

## Amendment Ledger

One row per distinct `Amendment A-N` found anywhere. `Consistent?` is **No** when an amendment
appears in one document but is plausibly relevant to another that does not mention it.

| Amendment | Found in | Consistent? |
|---|---|---|
| A-1 (FR-15 dedup revision) | PRD; Architecture via the `sources_as_of: 'PRD amendments A-1..A-9'` range, AD-4 implementing the substance | Consistent |
| A-2 (FR-5 revision) | PRD, DESIGN.md (`component.card.pulse.digest.category.discovery`) | **Consistent — closed 2026-11-17** by `f754c3e`. The entry already described A-2's rule (slate stripe at 0.85 plus a `discovery` micro-tag); it now cites the amendment that made it |
| A-3 (FR-22 revision) | PRD only (4 citations) | **Resolved 2026-11-19 — superseded by A-25.** A-3 locked FR-22's four published weights. A-25 records which term the implementation evaluates for each, and at what weight; the PRD's FR-22 table now carries that mapping, so the published formula and the computed one are the same formula. A-3 is **not** tagged onto the as-built UX sections — tagging it would assert a revision they do not implement — it is superseded, which is the honest close |
| A-4 (FR-59 added) | PRD, `report-event-modal-desktop.html` | Consistent |
| A-5 (FR-58 revision) | PRD, EXPERIENCE.md (3 citations) | **Consistent — corrected.** The previous ledger scored this `No`; EXPERIENCE.md cites "Amendment A-5" three times, including the Surface Coverage row and the conflict-prompt spec |
| A-6 (FR-60 added) | PRD | Consistent — backend-only, no UX impact expected |
| A-7 (FR-3 calendar OAuth→ICS) | PRD, EXPERIENCE.md, 2 mockups | **Consistent — corrected.** The previous ledger scored this `No`; EXPERIENCE.md does carry the tag |
| A-8 (FR-32/FR-33 lifted to MVP) | PRD, Architecture (AD-21 binds and cites it), DESIGN, EXPERIENCE, 17 mockups | Consistent |
| A-9 (Calendar Connect via ICS) | PRD, Architecture, DESIGN, EXPERIENCE, 3 mockups | Consistent |
| A-10 (Browse, 6th authed route) | PRD, DESIGN, EXPERIENCE, 3 mockups | Consistent. **Scope note (2026-11-19):** this ID means the Browse surface and nothing else. From 2026-11-11 to 2026-11-19 the FR-22 ranking-formula amendment was *also* recorded as A-10, and this row scored `Consistent` on the Browse propagation while reading over it. The ranking amendment is now **A-25** |
| A-11 – A-20 (UX-originated reconciliation + shell migrations) | DESIGN, EXPERIENCE, mockups | **No** — absent from the PRD. Per EXPERIENCE.md's own frontmatter these exist specifically to close PRD-coverage gaps, so the PRD arguably should record that the reconciliation happened. Unchanged since September |
| A-21 (reminder-picker shell migration) | DESIGN, EXPERIENCE | Consistent — a mockup migration with no PRD or Architecture surface |
| A-22 (Pulse Card state treatment) | DESIGN (3 citations) | Consistent — a component treatment with no PRD or Architecture surface |
| A-23 (traceability design-gap closure) | PRD (amendment list, line 18), DESIGN, EXPERIENCE | Consistent — propagated deliberately; absent from Architecture, correctly, since it changes no requirement and no system |
| A-24 (Timeline block's Why-this Tag withdrawn) | EXPERIENCE (§13 row, §13 anti-pattern scope note, `updated_note`) | Consistent — a surface-density decision with no PRD or Architecture surface. Closes O-2 |
| A-25 (FR-22 implemented formula) | PRD (FR-22 block + weights table + `[ASSUMPTION-11]` + frontmatter), `docs/adr/ADR-0025.md`, EXPERIENCE (2 as-built notes) | Consistent — re-minted from the colliding `A-10` on 2026-11-19. Changes no weight: `shared/constants.py` is untouched and `RANKING_WEIGHT_SUM == 1.00` still holds. Supersedes A-3 |

**Inconsistent amendments: 1** (the A-11–A-20 block, counted as one) — **down from 6 at the
start of 2026-11-12, from 3 at the previous regeneration, and from 2 before 2026-11-19.**
A-5 and A-7 were corrections of earlier mis-scores; A-2 is genuinely closed; **A-3 closed
2026-11-19.**

- **A-3 — CLOSED 2026-11-19, superseded by A-25.** This note previously said the right
  close "is probably a *new* amendment ID rather than stretching A-3 to cover a change it
  never made." **That is what happened.** `fr22-published-formula` ratified the five-term
  as-built formula as canonical and re-minted the ranking amendment as **A-25**, which now
  appears in the PRD's FR-22 block, its weights table, `[ASSUMPTION-11]`, the PRD
  frontmatter, `docs/adr/ADR-0025.md` and EXPERIENCE.md's two as-built notes. A-3's
  four-weight lock is superseded, not tagged.

  **A second defect was found while closing it, and it was the more serious one:** the
  ranking amendment had been recorded as **A-10**, an ID already belonging to the Browse
  surface amendment (2026-09-06). This ledger scored A-10 `Consistent` on the strength of
  the Browse propagation while reading straight over the ranking one — **a reused ID is
  worse than a missing tag, because a missing tag reads as a gap and a reused one makes
  the ledger confidently wrong.** Both rows are now corrected.
- **A-11 – A-20** — UX-originated amendments the PRD never absorbed. A *convention* question,
  not a defect: if UX-originated reconciliation is not expected to flow back into the PRD, the
  convention should say so and these rows should stop being re-flagged every regeneration.
  **Recommend deciding this once rather than re-flagging it indefinitely.** Unchanged.

---

## Deferred / Out-of-MVP FRs (listed, not scored)

15 FRs are Phase 2, Phase 3 or Year 2+ and are **not** scored in any section above.

| FR | Title | Phase |
|---|---|---|
| FR-31 | Two-Way Calendar Sync + Recurring Event Expansion | Phase 2 |
| FR-34 | Pulse the Group | Phase 2 |
| FR-35 | Pro Tier — Phase 2 Augmentation | Phase 2 |
| FR-36 | Voice Quick-Add | Phase 3 |
| FR-37 | Email-to-Event Forwarding | Phase 3 |
| FR-38 | Why Now? | Phase 3 |
| FR-39 | On-Device Personal AI | Phase 3 |
| FR-40 | Travel Mode | Phase 3 |
| FR-41 | Group Availability Heatmap | Phase 3 |
| FR-42 | White-Label B2B2C | Year 2+ |
| FR-43 | B2B Insights API | Year 2+ |
| FR-44 | Already-Handled Reminder Suppression | Phase 2 |
| FR-45 | Adaptive Pulse Digest Card Count | Phase 3 |
| FR-46 | Pulse Streak | Year 2+ |
| FR-47 | Year in Pulse Recap | Year 2+ |

The Architecture Spine's own **Deferred** table independently names FR-31, FR-34, FR-41 and
FR-39 with revisit triggers, so the deferral is architectural as well as product-side.

---

## Epic/Story Coverage

**— not yet created.** No BMad epics or stories document exists; globs over
`_bmad-output/planning-artifacts/epics*/**/*.md`, `**/epic*.md` and `**/story*.md` return
nothing. This is expected pre-epics and is not scored as a gap.

The closest equivalent remains the FIRE work items under `.specs-fire/intents/*/work-items/`,
which are intent-scoped rather than FR-scoped — they say what a run changed, not which
requirement is covered. That is why Section C reads the code directly rather than reading
them.
