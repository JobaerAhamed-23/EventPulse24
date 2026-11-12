# EventPulse24 — Traceability Matrix

Generated: 2026-11-12 (produced by the project's own `doc-trace` skill — `.agents/skills/doc-trace/SKILL.md`)

**Supersedes the 2026-09-08 matrix**, which was a September snapshot of a November codebase.
That version was generated **seven weeks before the first FIRE intent ran** (2026-10-27) and
was never regenerated across eleven intents and twenty-eight runs. Three of its findings had
expired and one was always wrong; all four are retired below, with evidence, rather than
being silently dropped by the re-scan.

**Sources scanned:**
- PRD: `_bmad-output/planning-artifacts/prds/prd-EventPulse24-2026-08-19/prd.md` — 45 MVP functional requirements (FR-1–FR-30, FR-32, FR-33, FR-48–FR-60). FR-31 and FR-34–FR-47 are Phase 2/3/Year 2+, listed separately and not scored.
- Architecture Spine: `_bmad-output/planning-artifacts/architecture/architecture-EventPulse24-2026-09-04/ARCHITECTURE-SPINE.md`
- UX Design: `_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/DESIGN.md`
- UX Experience: `_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/EXPERIENCE.md`
- Mockups: **50 HTML files** — 39 in `mockups/`, 6 in `mockups/mobile/`, 5 in `mockups/light-archive/`. Each file's **entire leading comment** was read, not its first few lines.
- Epics/Stories: no BMad epics document exists. FIRE work items under `.specs-fire/intents/*/work-items/` are the closest equivalent — see Epic/Story Coverage.

**Two scanning notes that affect the scores below**, recorded so the delta from the previous
matrix is attributable rather than mysterious:

1. **The mockup corpus has grown and was previously undercounted.** The 2026-09-08 matrix
   scanned *"all 32 files (26 desktop + 6 mobile)"*. There are now **50**, and
   `mockups/light-archive/` (5 files) is a directory that matrix never mentions. Archive
   files are **not** counted as evidence here; they are superseded light-theme variants.
2. **Full header comments were read.** A shallow read of the first few lines misses tags that
   sit lower in a header block — `onboarding-skip-all-state-desktop.html` carries **FR-10**,
   which appears nowhere in the previous matrix's evidence column. Where a status below
   differs from September purely because of better scanning, the note says so.

---

## Section A — PRD ↔ Design Alignment

For each MVP FR: does a design element exist, in enough detail to build the UI from?
`FULL` = a self-tagged mockup (tier 1) or a named DESIGN.md/EXPERIENCE.md section citing the
FR (tier 2). `PARTIAL` = inferable by adjacency only. `MISSING` = a user-facing requirement
with nothing found. `N/A` = no UI surface by nature.

**Counts: 35 FULL · 1 PARTIAL (inferred only) · 0 MISSING · 9 N/A** (45 total)

| FR-ID | Title | Design element found | Status | Note |
|---|---|---|---|---|
| FR-1 | 30-Second Onboarding Flow | `light-archive/onboarding-step1-desktop.html`, `light-archive/onboarding-step1-mobile.html`, `onboarding-skip-all-state-desktop.html`, `signup-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-2 | Pulse Preview (No-Auth First Value) | `geo-consent-banner-desktop.html`, `pulse-preview-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-3 | Calendar Connect (Optional, read-only ICS/webcal — Google / Apple / Outlook) | `light-archive/onboarding-step1-desktop.html`, `light-archive/onboarding-step1-mobile.html` | FULL | self-tagged mockup header (tier 1) |
| FR-4 | Authenticated User State | `signin-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-5 | Pulse Digest Composition | named in DESIGN.md / EXPERIENCE.md | FULL | named section citing the FR (tier 2) |
| FR-6 | Pulse Card Information Density | named in DESIGN.md / EXPERIENCE.md | FULL | named section citing the FR (tier 2) |
| FR-7 | Pulse Digest Delivery Time | named in DESIGN.md / EXPERIENCE.md | FULL | named section citing the FR (tier 2) |
| FR-8 | Empty-State Pulse Digest | `pulse-digest-empty-state-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-9 | Multi-Tier Reminder Picker | `event-detail-desktop.html`, `personal-event-reminders-desktop.html`, `reminder-picker-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-10 | Pulse Ping — Single Daily Notification | — | N/A (no design needed) | Pulse Ping is a notification channel, not an in-app screen; incidentally tagged in `onboarding-skip-all-state-desktop.html` |
| FR-11 | Email Multi-Tier Reminders | named in DESIGN.md / EXPERIENCE.md | FULL | named section citing the FR (tier 2) |
| FR-12 | Quiet Hours | named in DESIGN.md / EXPERIENCE.md | FULL | named section citing the FR (tier 2) |
| FR-13 | Source Registry | named in DESIGN.md / EXPERIENCE.md | FULL | named section citing the FR (tier 2) |
| FR-14 | Hybrid Event Extraction Pipeline | — | N/A (no design needed) | backend extraction pipeline |
| FR-15 | Event Deduplication | — | N/A (no design needed) | backend dedup |
| FR-16 | Source Reliability Score | nothing citing this FR | **PARTIAL (inferred only)** | inferable by adjacency only |
| FR-17 | Source Acquisition Hierarchy Enforcement | — | N/A (no design needed) | internal acquisition policy |
| FR-18 | Manual Personal Event Creation | `personal-event-create-desktop.html`, `personal-event-edit-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-19 | Personal Event in Pulse Digest | `personal-event-reminders-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-20 | Personal Event Reminder Defaults | `collections-desktop.html`, `personal-event-reminders-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-21 | Why-this Tags | named in DESIGN.md / EXPERIENCE.md | FULL | named section citing the FR (tier 2) |
| FR-22 | Confidence Pulse | `light-archive/ranking-algorithm-transparency-desktop.html`, `ranking-algorithm-transparency-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-23 | Source Badge | named in DESIGN.md / EXPERIENCE.md | FULL | named section citing the FR (tier 2) |
| FR-24 | "Why this?" Detail Screen | `event-detail-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-25 | "Less like this" Adjustment | `less-like-this-mute-prompt-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-26 | Public Event Pages with Structured Data | `public-event-page-desktop.html`, `share-affordance-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-27 | SEO City Pages | `city-page-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-28 | Share-Card Public Link | `share-affordance-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-29 | AI Cost Dashboard (Internal) | — | N/A (no design needed) | internal Django admin tool, outside this design system |
| FR-30 | Caching & Batching Defaults | — | N/A (no design needed) | backend caching/batching policy |
| FR-32 | Unified Personal+Public Timeline — MVP | `mobile/timeline-mobile.html`, `timeline-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-33 | Conflict-Aware Scheduling — MVP | `conflicts-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-48 | Pro Tier with MVP-Only Features | `export-request-modal-desktop.html`, `pricing-page-desktop.html`, `pro-upgrade-cta-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-49 | Unlimited Saves + Saved Collections (Pro) | `collections-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-50 | Calendar Provider Read-Only Sync (Free + Pro) | named in DESIGN.md / EXPERIENCE.md | FULL | named section citing the FR (tier 2) |
| FR-51 | Per-Day-of-Week Custom Quiet Hours (Pro) | named in DESIGN.md / EXPERIENCE.md | FULL | named section citing the FR (tier 2) |
| FR-52 | JSON + ICS Data Export (Pro) | `export-request-modal-desktop.html`, `share-affordance-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-53 | Event State Polling + Webhooks | `sold-out-card-state-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-54 | User-Facing State-Change Notifications | `sold-out-card-state-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-55 | Conflict Resolution on State Change | `conflict-indicator-card-state-desktop.html`, `conflict-prompt-desktop.html`, `event-state-conflict-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-56 | RSS / Email-ICS Source Acquisition (MVP) | — | N/A (no design needed) | backend source acquisition |
| FR-57 | Editorial Review Queue (Internal) | — | N/A (no design needed) | internal Django admin tool |
| FR-58 | Personal Event Conflict Detection | `conflict-indicator-card-state-desktop.html`, `conflict-prompt-desktop.html`, `event-state-conflict-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-59 | User-Reported Event Quality | `report-event-modal-desktop.html` | FULL | self-tagged mockup header (tier 1) |
| FR-60 | Timezone Source of Truth | — | N/A (no design needed) | backend stored-timestamp truth policy |

**Open Design gaps:** **FR-16** only.

- **FR-16 Source Reliability Score — `PARTIAL (inferred only)`, and this is a *downgrade* from the previous matrix, not a regression in the product.** September scored it `FULL` on the evidence *"Reliability dots; `settings-sources-desktop.html`"*. That is adjacency: `FR-16` is cited **nowhere** — not in DESIGN.md, not in EXPERIENCE.md, not in any mockup header (verified by search, 0 hits in all three). This skill's own rule 3 says a plausible-but-unnamed component with no direct FR tag *"is **PARTIAL (inferred only)** — never FULL"*. The reliability dots are real and designed; what is missing is any statement that they are FR-16's design. **One line in EXPERIENCE.md's `settings-sources` row or a tag in that mockup's header closes it.**

**The four September gaps are closed.** FR-20, FR-28, FR-49 and FR-55 each now have a
self-tagged mockup *and* named DESIGN.md entries, added 2026-11-12 under **Amendment A-23**:

| FR | September | Now | Evidence |
|---|---|---|---|
| FR-20 | PARTIAL (inferred only) | **FULL** | `personal-event-reminders-desktop.html`; `component.reminders.personal.plan`, `component.emptystate.chosen` |
| FR-28 | PARTIAL (inferred only) | **FULL** | `share-affordance-desktop.html`; `component.control.share`, `component.feedback.share` |
| FR-49 | **MISSING** | **FULL** | `collections-desktop.html`; `component.manager.collections` |
| FR-55 | PARTIAL (inferred only) | **FULL** | `event-state-conflict-desktop.html` + `conflict-prompt-desktop.html` and `conflict-indicator-card-state-desktop.html`, both re-tagged `FR-55` beside `FR-58`; `component.control.notice-mute`, `component.banner.state-notice`, `component.indicator.conflict.cleared` |

**Three errors found in EXPERIENCE.md's Surface Coverage Map and corrected.** The FR column
is hand-maintained and had drifted; every row's filename was checked against `ls` and every
FR claim against the named file's content:

| Row | Error | Correction |
|---|---|---|
| 9 | Named `empty-pulse-digest-desktop.html`, **which does not exist and never has** | Corrected to `pulse-digest-empty-state-desktop.html`, which self-tags `FR-8`. The design was always there; only the reference was wrong. |
| 10 | Claimed FR-49 coverage; the file contains **zero** collection content (`collection` ×0, against `quiet` ×10, `Pro` ×7, `export` ×4) | FR-49 struck, with the counts recorded inline. This false claim is *why* FR-49 shipped undesigned — nobody looks for a design the table says exists. |
| 11 | `share-link-desktop.html` reads as FR-28's design; it is tagged `UJ-5`, the **recipient's** landing page | Scope stated inline. The sender's affordance is row 22. |

Rows 3 and 4 reference two mobile mockups that do not exist, but both rows declare them
`(pending — see coverage gaps)`, so they are correctly-flagged backlog, not errors.

---

## Section B — PRD ↔ Architecture Alignment

Does the Architecture Spine's `Capability → Architecture Map` have a row naming this FR (or a
range covering it), with a module and at least one `AD-N`?

**Counts: 45 FULL · 0 PARTIAL · 0 MISSING · 0 N/A** (45 total)

| FR-ID | Title | Architecture (module · AD-N) | Status | Note |
|---|---|---|---|---|
| FR-1 | 30-Second Onboarding Flow | `identity`, `personalization`, frontend, `adapters/calendar` · AD-5, AD-12, AD-15, AD-18 | FULL | Capability-Map row “FR-1–4 Onboarding & account” |
| FR-2 | Pulse Preview (No-Auth First Value) | `identity`, `personalization`, frontend, `adapters/calendar` · AD-5, AD-12, AD-15, AD-18 | FULL | Capability-Map row “FR-1–4 Onboarding & account” |
| FR-3 | Calendar Connect (Optional, read-only ICS/webcal — Google / Apple / Outlook) | `identity`, `personalization`, frontend, `adapters/calendar` · AD-5, AD-12, AD-15, AD-18 | FULL | Capability-Map row “FR-1–4 Onboarding & account” |
| FR-4 | Authenticated User State | `identity`, `personalization`, frontend, `adapters/calendar` · AD-5, AD-12, AD-15, AD-18 | FULL | Capability-Map row “FR-1–4 Onboarding & account” |
| FR-5 | Pulse Digest Composition | `personalization`, frontend · AD-3, AD-10, AD-11 | FULL | Capability-Map row “FR-5–8 Pulse Digest” |
| FR-6 | Pulse Card Information Density | `personalization`, frontend · AD-3, AD-10, AD-11 | FULL | Capability-Map row “FR-5–8 Pulse Digest” |
| FR-7 | Pulse Digest Delivery Time | `personalization`, frontend · AD-3, AD-10, AD-11 | FULL | Capability-Map row “FR-5–8 Pulse Digest” |
| FR-8 | Empty-State Pulse Digest | `personalization`, frontend · AD-3, AD-10, AD-11 | FULL | Capability-Map row “FR-5–8 Pulse Digest” |
| FR-9 | Multi-Tier Reminder Picker | `delivery`, `worker` · AD-6, AD-7, AD-16, AD-17 | FULL | Capability-Map row “FR-9–12 Reminders & Pulse Ping” |
| FR-10 | Pulse Ping — Single Daily Notification | `delivery`, `worker` · AD-6, AD-7, AD-16, AD-17 | FULL | Capability-Map row “FR-9–12 Reminders & Pulse Ping” |
| FR-11 | Email Multi-Tier Reminders | `delivery`, `worker` · AD-6, AD-7, AD-16, AD-17 | FULL | Capability-Map row “FR-9–12 Reminders & Pulse Ping” |
| FR-12 | Quiet Hours | `delivery`, `worker` · AD-6, AD-7, AD-16, AD-17 | FULL | Capability-Map row “FR-9–12 Reminders & Pulse Ping” |
| FR-13 | Source Registry | `ingestion`, `worker`, `adapters/crawl` · AD-4, AD-6, AD-8, AD-9 | FULL | Capability-Map row “FR-13–17, FR-56, FR-60 Ingestion & sources” |
| FR-14 | Hybrid Event Extraction Pipeline | `ingestion`, `worker`, `adapters/crawl` · AD-4, AD-6, AD-8, AD-9 | FULL | Capability-Map row “FR-13–17, FR-56, FR-60 Ingestion & sources” |
| FR-15 | Event Deduplication | `ingestion`, `worker`, `adapters/crawl` · AD-4, AD-6, AD-8, AD-9 | FULL | Capability-Map row “FR-13–17, FR-56, FR-60 Ingestion & sources” |
| FR-16 | Source Reliability Score | `ingestion`, `worker`, `adapters/crawl` · AD-4, AD-6, AD-8, AD-9 | FULL | Capability-Map row “FR-13–17, FR-56, FR-60 Ingestion & sources” |
| FR-17 | Source Acquisition Hierarchy Enforcement | `ingestion`, `worker`, `adapters/crawl` · AD-4, AD-6, AD-8, AD-9 | FULL | Capability-Map row “FR-13–17, FR-56, FR-60 Ingestion & sources” |
| FR-18 | Manual Personal Event Creation | `personalization` · AD-3, AD-6, AD-16, AD-21 | FULL | Capability-Map row “FR-18–20, FR-58 Personal events & conflict” |
| FR-19 | Personal Event in Pulse Digest | `personalization` · AD-3, AD-6, AD-16, AD-21 | FULL | Capability-Map row “FR-18–20, FR-58 Personal events & conflict” |
| FR-20 | Personal Event Reminder Defaults | `personalization` · AD-3, AD-6, AD-16, AD-21 | FULL | Capability-Map row “FR-18–20, FR-58 Personal events & conflict” |
| FR-21 | Why-this Tags | `personalization` · AD-9, AD-10 | FULL | Capability-Map row “FR-21–25 Explainability & trust” |
| FR-22 | Confidence Pulse | `personalization` · AD-9, AD-10 | FULL | Capability-Map row “FR-21–25 Explainability & trust” |
| FR-23 | Source Badge | `personalization` · AD-9, AD-10 | FULL | Capability-Map row “FR-21–25 Explainability & trust” |
| FR-24 | "Why this?" Detail Screen | `personalization` · AD-9, AD-10 | FULL | Capability-Map row “FR-21–25 Explainability & trust” |
| FR-25 | "Less like this" Adjustment | `personalization` · AD-9, AD-10 | FULL | Capability-Map row “FR-21–25 Explainability & trust” |
| FR-26 | Public Event Pages with Structured Data | `catalog`, frontend · AD-12, AD-19 | FULL | Capability-Map row “FR-26–28 Sharing & SEO” |
| FR-27 | SEO City Pages | `catalog`, frontend · AD-12, AD-19 | FULL | Capability-Map row “FR-26–28 Sharing & SEO” |
| FR-28 | Share-Card Public Link | `catalog`, frontend · AD-12, AD-19 | FULL | Capability-Map row “FR-26–28 Sharing & SEO” |
| FR-29 | AI Cost Dashboard (Internal) | `adapters/llm`, `editorial` (Django admin) · AD-8, AD-14 | FULL | Capability-Map row “FR-29 AI Cost Dashboard” |
| FR-30 | Caching & Batching Defaults | `adapters/llm` · AD-8 | FULL | Capability-Map row “FR-30 Caching & batching” |
| FR-32 | Unified Personal+Public Timeline — MVP | `personalization`, frontend · AD-3, AD-6, AD-21 | FULL | Capability-Map row “FR-32 Unified Timeline (Week view, read-only)” |
| FR-33 | Conflict-Aware Scheduling — MVP | `personalization`, `delivery`, frontend · AD-6, AD-17, AD-21 | FULL | Capability-Map row “FR-33 Conflict-aware scheduling, `/conflicts`” |
| FR-48 | Pro Tier with MVP-Only Features | `identity`, `adapters/billing`, `adapters/calendar` · AD-5, AD-15, AD-18 | FULL | Capability-Map row “FR-48–52 Pro tier” |
| FR-49 | Unlimited Saves + Saved Collections (Pro) | `identity`, `adapters/billing`, `adapters/calendar` · AD-5, AD-15, AD-18 | FULL | Capability-Map row “FR-48–52 Pro tier” |
| FR-50 | Calendar Provider Read-Only Sync (Free + Pro) | `identity`, `adapters/billing`, `adapters/calendar` · AD-5, AD-15, AD-18 | FULL | Capability-Map row “FR-48–52 Pro tier” |
| FR-51 | Per-Day-of-Week Custom Quiet Hours (Pro) | `identity`, `adapters/billing`, `adapters/calendar` · AD-5, AD-15, AD-18 | FULL | Capability-Map row “FR-48–52 Pro tier” |
| FR-52 | JSON + ICS Data Export (Pro) | `identity`, `adapters/billing`, `adapters/calendar` · AD-5, AD-15, AD-18 | FULL | Capability-Map row “FR-48–52 Pro tier” |
| FR-53 | Event State Polling + Webhooks | `ingestion`, `delivery`, `personalization` · AD-4, AD-7, AD-17, AD-21 | FULL | Capability-Map row “FR-53–55 Event state sync” |
| FR-54 | User-Facing State-Change Notifications | `ingestion`, `delivery`, `personalization` · AD-4, AD-7, AD-17, AD-21 | FULL | Capability-Map row “FR-53–55 Event state sync” |
| FR-55 | Conflict Resolution on State Change | `ingestion`, `delivery`, `personalization` · AD-4, AD-7, AD-17, AD-21 | FULL | Capability-Map row “FR-53–55 Event state sync” |
| FR-56 | RSS / Email-ICS Source Acquisition (MVP) | `ingestion`, `worker`, `adapters/crawl` · AD-4, AD-6, AD-8, AD-9 | FULL | Capability-Map row “FR-13–17, FR-56, FR-60 Ingestion & sources” |
| FR-57 | Editorial Review Queue (Internal) | `editorial` (Django admin) · AD-4, AD-8, AD-14 | FULL | Capability-Map row “FR-57 Editorial review queue” |
| FR-58 | Personal Event Conflict Detection | `personalization` · AD-3, AD-6, AD-16, AD-21 | FULL | Capability-Map row “FR-18–20, FR-58 Personal events & conflict” |
| FR-59 | User-Reported Event Quality | `personalization`, `editorial` · AD-3, AD-14 | FULL | Capability-Map row “FR-59 User event reports” |
| FR-60 | Timezone Source of Truth | `ingestion`, `worker`, `adapters/crawl` · AD-4, AD-6, AD-8, AD-9 | FULL | Capability-Map row “FR-13–17, FR-56, FR-60 Ingestion & sources” |

**Open Architecture gaps: none.**

**The previous matrix's "single highest-value finding" is retired as false.** It stated that
FR-32 and FR-33 — lifted to MVP by Amendment A-8 — had *"no row for either"* in the
Capability Map, and that *"the word 'Amendment' appears nowhere in `ARCHITECTURE-SPINE.md`"*.
Both claims are contradicted by the current spine:

- **`AD-21 — Timeline and conflicts read personal-side snapshots, never `catalog` joins`** exists, and its `**Binds:**` line reads `FR-32, FR-33, FR-58, FR-53–55; PRD Amendment A-8`.
- The Capability Map carries **two dedicated rows**: *"FR-32 Unified Timeline (Week view, read-only)"* and *"FR-33 Conflict-aware scheduling, `/conflicts`"*.
- "Amendment" appears in the spine at **lines 11, 218 and 282**.

It is not recorded whether the spine changed after 2026-09-08 or whether the finding was
wrong when written. Either way it is wrong now, and leaving it to be dropped silently by a
re-scan would lose the fact that it was ever claimed.

---

## Amendment Ledger

One row per distinct `Amendment A-N` found anywhere. `Consistent?` is **No** when an
amendment appears in one document but is plausibly relevant to another that does not mention
it.

| Amendment | Found in | Consistent? |
|---|---|---|
| A-1 (FR-15 dedup revision) | PRD, Architecture, DESIGN, mockups | Consistent — Architecture's AD-4 implements the substance and now carries the tag. |
| A-2 (FR-5 revision) | PRD, mockups | **No** — FR-5 is core UX real estate (`Card.PulseDigest`); neither DESIGN.md nor EXPERIENCE.md carries a matching tag. |
| A-3 (FR-22 revision) | PRD, mockups | **No** — UX references FR-22 directly but never cites "Amendment A-3". |
| A-4 (FR-59 added) | PRD, mockups | Consistent — Architecture has an FR-59 Capability-Map row and `report-event-modal-desktop.html` is tagged "FR-59 / Amendment A-4". |
| A-5 (FR-58 revision) | PRD, EXPERIENCE, mockups | **No** — UX covers FR-58 extensively but under its own tags, never citing "Amendment A-5". |
| A-6 (FR-60 added) | PRD, mockups | Consistent — backend-only, no UX impact expected. |
| A-7 (FR-3 calendar OAuth→ICS) | PRD, EXPERIENCE, mockups | **No** — UX's calendar-parity guidance carries no A-7 tag. |
| A-8 (FR-32/FR-33 lifted to MVP) | PRD, Architecture, DESIGN, EXPERIENCE, mockups | **Consistent — resolved since September.** This was the previous matrix's headline gap; AD-21 now binds both FRs and cites A-8 by name. |
| A-9 (Calendar Connect via ICS) | PRD, Architecture, DESIGN, EXPERIENCE, mockups | Consistent across all four. |
| A-10 (Browse, 6th authed route) | PRD, DESIGN, EXPERIENCE, mockups | Consistent. |
| A-11 – A-20 (UX-originated reconciliation + shell migrations) | DESIGN, EXPERIENCE, mockups | **No** — absent from the PRD. Per EXPERIENCE.md's own frontmatter these exist specifically to close PRD-coverage gaps, so the PRD arguably should record that the reconciliation happened. Unchanged since September. |
| A-21 (reminder-picker shell migration) | DESIGN, EXPERIENCE | Consistent — a mockup migration with no PRD or Architecture surface. |
| A-22 (Pulse Card state treatment) | DESIGN, EXPERIENCE | Consistent — a component treatment with no PRD or Architecture surface. |
| **A-23 (traceability design-gap closure)** | **PRD, DESIGN, EXPERIENCE** | **Consistent — propagated deliberately.** Absent from Architecture, correctly: it changes no requirement and no system, only adds the design artifacts for four FRs that shipped without them. Recorded in the PRD specifically because the convention requires an ID in every document the change touches, and it touched two UX documents. |

**Inconsistent amendments: 6** (A-2, A-3, A-5, A-7, and the A-11–A-20 block, counted as one).
**All predate this run and are unchanged since September** — none is new debt. They fall into
two kinds, and the distinction is worth making before anyone "fixes" them:

- **A-2, A-3, A-5, A-7** — the PRD amended an FR whose UX surface exists, and the UX docs cover that FR without ever citing the amendment ID. These are genuine tag-propagation misses and are cheap to close.
- **A-11 – A-20** — UX-originated amendments the PRD never absorbed. These are a *convention* question, not a defect: if UX-originated reconciliation is not expected to flow back into the PRD, the convention should say so and these rows should stop being reported as inconsistent every regeneration. **Recommend deciding this once rather than re-flagging it indefinitely.**

---

## Deferred (Phase 2 / Phase 3 / Year 2+, correctly out of MVP — not scored)

FR-31 (in Architecture's own Deferred table), FR-34–FR-47 (14 FRs, all Phase 2/3/Year 2+ per
PRD headings). Note that FR-44, FR-46 and FR-47 are *mentioned* in the UX documents; those
are forward references, not MVP coverage, and are not scored here.

---

## Epic/Story Coverage

**No BMad epics document exists**, and none is expected — this project plans with FIRE, not
with BMad epics. The previous matrix's line *"none found yet — expected pre-epics"* was
written before any of that work existed and is now misleading rather than merely stale.

The equivalent artifacts are **FIRE work items**: 126 across 12 intents under
`.specs-fire/intents/*/work-items/`, with execution history in `.specs-fire/state.yaml`
(28 runs). They are not scored in this matrix because they decompose *delivery*, not
requirements — a single FR may span several work items and a work item may serve several FRs.
**Whether FIRE work items should be traced against FRs is an open question**, and would be a
third section rather than a reinterpretation of this one.

---

## Open items carried out of this regeneration

1. **FR-16 needs one line** — a tag in `settings-sources-desktop.html`'s header or an FR-16 citation in EXPERIENCE.md's row 15 moves it from PARTIAL to FULL. Deliberately **not** done here: this regeneration reports what it found, and editing a document to improve the score in the same pass that measures it is how a matrix stops being trustworthy.
2. **The postponed-into-conflict end-to-end test (FR-55)** is uncovered. Its natural home, `tests/e2e/test_timeline_and_conflict_proof.py`, is currently red from expired hardcoded fixture dates; the test should land with that fix, in a green suite.
3. **17 backend tests fail on `main`**, all from hardcoded absolute datetimes that have passed. The count rose from 16 to 17 *during* run 028 — `test_reminder_plan_api.py`'s `AFTERNOON_START` (2026-11-12 02:00 UTC) expired between run 027's suite and run 028's. This is a defect class — many instances of one pattern — and the fix is a clock port or `freezegun`, not logic changes. Recommended by run 027 and still not actioned.
4. **The A-11–A-20 convention question** above.
5. **`DESIGN.md`'s YAML frontmatter does not parse** — its `updated_note` is a double-quoted scalar containing unescaped `"` characters, introduced by Amendment A-22 on 2026-11-10. Harmless to human readers, fatal to any tool that parses the frontmatter. Found while adding A-23 (whose own quotes are escaped); not fixed here, because it is unrelated to traceability and deserves its own change.
