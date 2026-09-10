# EventPulse24 — Traceability Matrix

Generated: 2026-09-10

**Sources scanned:**
- PRD: `_bmad-output/planning-artifacts/prds/prd-EventPulse24-2026-08-19/prd.md` — 60 total FRs; 45 in MVP scope (FR-1–FR-30, FR-32, FR-33, FR-48–FR-60). FR-31 and FR-34–FR-47 (15 FRs) are Phase 2/3/Year 2+, listed separately below and not scored.
- Architecture Spine: `_bmad-output/planning-artifacts/architecture/architecture-EventPulse24-2026-09-04/ARCHITECTURE-SPINE.md`
- UX Design (components/visual system): `_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/DESIGN.md`
- UX Experience (flows/journeys): `_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/EXPERIENCE.md`
- Mockups: **48 files** under `.../mockups/` (35 root + 6 `mobile/` + 4 `light-archive/` + 3 `superseded/`), verified via `find`, each checked for a self-tagged `FR-N` / `Amendment A-N` in its own header comment. EXPERIENCE.md's own "Surface Coverage Map" table has a documented history of undercounting (41→42→43→48 across amendments) and an explicit "rows not yet listed" section — it was cross-checked against the filesystem rather than trusted alone. Note: `22-app-conflicts.html` and `22-app-reminder-picker.html` share the numeral "22" (a filename collision, not a duplicate file).
- Epics/Stories: none found yet — expected pre-epics. Not scored below.
- Prior matrix: this run supersedes `TRACEABILITY.md` generated 2026-09-08 (32-mockup snapshot). Two gaps flagged there are now closed (FR-49, FR-55 — see notes below); everything else was re-verified independently against current sources.

---

## Section A — PRD ↔ Design Alignment

For each MVP FR: does a design element exist, in enough detail to build the UI from, in DESIGN.md, EXPERIENCE.md, or a mockup? `FULL` = a self-tagged mockup or a named section/component names the FR directly. `PARTIAL (inferred only)` = only inferable by adjacency, no direct tag anywhere. `MISSING` = a user-facing requirement with nothing found. `N/A` = the FR has no UI surface by nature (backend/internal/policy).

**Counts: 36 FULL · 0 PARTIAL · 0 MISSING · 9 N/A** (45 total)

> **Updated 2026-09-10 after Amendment A-25.** The two open gaps this matrix found (FR-20, FR-28) were closed the same day by UX Amendment A-25; both rows below are updated and the counts above reflect the post-amendment state. Section A now has no non-FULL, non-N/A rows.

| FR-ID | Title | Design element found (source) | Status | Note |
|---|---|---|---|---|
| FR-1 | 30-Second Onboarding Flow | `06-auth-signup.html`, `11-onboarding-skip-all.html`, `light-archive/onboarding-step1-*.html` — self-tagged FR-1 | FULL | |
| FR-2 | Pulse Preview (No-Auth First Value) | `01-pre-login-pulse-preview.html` ("Realizes FR-2"), `02-pre-login-geo-consent.html` — self-tagged FR-2; DESIGN.md `component.control.toggle.location` (A-14) | FULL | |
| FR-3 | Calendar Connect (OAuth) | DESIGN.md "Calendar Connect Provider Parity (v1)" names FR-3/FR-50 directly; `light-archive/onboarding-step1-*.html` self-tagged FR-3 | FULL | |
| FR-4 | Authenticated User State | `07-auth-signin.html` self-tagged FR-4 (A-20) | FULL | |
| FR-5 | Pulse Digest Composition (rev. A-2) | EXPERIENCE.md §9/§13 name FR-5 directly ("3-card cap — FR-5 Out of Scope"; "not reordered by engagement — FR-5") | FULL | Primary mockup `12-app-pulse-digest.html` itself carries no FR-N header tag — worth adding one for consistency even though coverage is otherwise real. |
| FR-6 | Pulse Card Information Density | EXPERIENCE.md `Card.PulseDigest — FR-6 (Source Badge)` | FULL | |
| FR-7 | Pulse Digest Delivery Time | EXPERIENCE.md Surface Coverage row for onboarding step 3 names FR-1/FR-7 (time presets + AM/PM control) | FULL | |
| FR-8 | Empty-State Pulse Digest | `13-app-pulse-digest-empty.html` self-tagged FR-8; EXPERIENCE.md Empty Patterns cites FR-8 | FULL | |
| FR-9 | Multi-Tier Reminder Picker | `16-app-event-detail.html` ("FR-9/FR-24"), `22-app-reminder-picker.html` — self-tagged FR-9; EXPERIENCE.md `Input.ReminderSlot — FR-9` | FULL | |
| FR-10 | Pulse Ping — Single Daily Notification | No custom in-app screen — `11-onboarding-skip-all.html`'s header explicitly documents the topbar Notifications button "is removed entirely... per PRD FR-10 there is no in-app notifications inbox" | N/A (no design needed) | Rendered via the browser's native Web Notification API; the deliberate absence of an in-app inbox is itself a documented design decision, not a gap. |
| FR-11 | Email Multi-Tier Reminders | Same reminder-picker UI as FR-9 configures both channels' tiers together; no separate email-template mockup exists | FULL | The configuration surface is designed; the transactional email's own visual template is not mocked up, but FR-11's UI-relevant requirement (tier configuration) is covered by FR-9's surface. |
| FR-12 | Quiet Hours | EXPERIENCE.md `Input.ReminderSlot — FR-9, FR-12 (Quiet Hours interaction)` | FULL | |
| FR-13 | Source Registry | `32-app-settings-sources.html` (A-18); EXPERIENCE.md `Component.Settings.Sources — FR-13` | FULL | |
| FR-14 | Hybrid Event Extraction Pipeline | — | N/A (no design needed) | Backend JSON-LD/API/LLM extraction pipeline, no user-facing surface. |
| FR-15 | Event Deduplication (rev. A-1) | — | N/A (no design needed) | Backend structural-identity matching, no user-facing surface. |
| FR-16 | Source Reliability Score | `32-app-settings-sources.html`'s reliability-dot display (same FR-13-tagged surface) | FULL | Realized via the source-registry page's reliability dots rather than its own distinct FR-16 tag. |
| FR-17 | Source Acquisition Hierarchy Enforcement | — | N/A (no design needed) | Internal crawl/API acquisition-priority policy, no user-facing surface. |
| FR-18 | Manual Personal Event Creation | `14-app-personal-event-create.html` self-tagged FR-18 | FULL | |
| FR-19 | Personal Event in Pulse Digest | DESIGN.md warm-tone personal-event token/label spec | FULL | |
| FR-20 | Personal Event Reminder Defaults | EXPERIENCE.md `Input.ReminderSlot` now cites FR-9 · FR-12 · FR-20 with an explicit "Default plan on a new event" bullet (Amendment A-25); FR-20 header citations added to `14-app-personal-event-create.html`, `15-app-personal-event-edit.html`, `22-app-reminder-picker.html` | FULL | **Closed by Amendment A-25 (2026-09-10) as a tracing gap, not a design gap.** The 1d + 1hr default was already rendered unanimously in all three mockups; no design changed, only the citation. Worth recording as a lesson: an implemented-but-uncited requirement is indistinguishable from an unbuilt one when the only evidence audited is the spine. |
| FR-21 | Why-this Tags | EXPERIENCE.md §3/§12 cite FR-21 directly | FULL | |
| FR-22 | Confidence Pulse (rev. A-3) | `superseded/ranking-algorithm-transparency-desktop.html` (FR-22, now deprecated/inlined); `31-app-settings.html` (A-13, "Amendment-history timeline inlined... FR-22") | FULL | |
| FR-23 | Source Badge | EXPERIENCE.md `Badge.Source — FR-23`; §12 | FULL | |
| FR-24 | "Why this?" Detail Screen | `16-app-event-detail.html` self-tagged FR-24 | FULL | |
| FR-25 | "Less like this" Adjustment | `29-app-less-like-this-mute.html` self-tagged FR-25 | FULL | |
| FR-26 | Public Event Pages with Structured Data | `04-pre-login-public-event-page.html` self-tagged FR-26 | FULL | |
| FR-27 | SEO City Pages | `03-pre-login-city-page.html` self-tagged FR-27 | FULL | |
| FR-28 | Share-Card Public Link | EXPERIENCE.md §4 `Component.Action.Share` (behavioral contract) + DESIGN.md §Components → Share action `component.action.share` (visual spec), both Amendment A-25; states matrix in `16-app-event-detail.html`, `copied` morph in `mobile/event-detail-mobile.html`, Open Graph on `27-app-share-link.html` | FULL | **Closed by Amendment A-25 (2026-09-10).** Both halves were unmet: the sender-side affordance had a button rendered on two mockups with its behavior specified nowhere, and the recipient landing served **none** of `og:title`/`og:description`/`og:type`/`og:url` while the public event page served all four plus JSON-LD — so a shared link unfurled blank in the one place FR-28 must work. Now specified as `idle → copied → idle` (morph-as-confirmation reused from `Save.Inline`, no toast, no overlay) with Open Graph written into the component's contract. ASSUM-17 locks it. |
| FR-29 | AI Cost Dashboard (Internal) | — | N/A (no design needed) | EXPERIENCE.md explicitly places this outside the user-facing surface map (internal-only). |
| FR-30 | Caching & Batching Defaults | — | N/A (no design needed) | Backend performance/cost policy, no user-facing surface. |
| FR-32 | Unified Personal+Public Timeline (lifted A-8) | `23-app-timeline.html`, `mobile/timeline-mobile.html` self-tagged FR-32 | FULL | |
| FR-33 | Conflict-Aware Scheduling (lifted A-8) | `22-app-conflicts.html` self-tagged FR-33 | FULL | |
| FR-48 | Pro Tier with MVP-Only Features | `05-pre-login-pricing-page.html`, `34-app-pro-upgrade-cta.html` self-tagged FR-48 | FULL | |
| FR-49 | Unlimited Saves + Saved Collections (Pro) | `26-app-saved-collections.html` self-tagged FR-49 (A-22) | FULL | **Closes a previously-flagged MISSING gap** — the prior (2026-09-08) matrix found nothing but a marketing bullet; Amendment A-22 has since added a real Saved Collections surface. |
| FR-50 | Calendar Provider Read-Only Sync | DESIGN.md "Calendar Connect Provider Parity (v1)" names FR-3/FR-50 directly | FULL | |
| FR-51 | Per-Day-of-Week Custom Quiet Hours (Pro) | `33-app-settings-quiet-hours-pro.html`; DESIGN.md `component.control.day-picker` (A-19) names FR-51 directly | FULL | |
| FR-52 | JSON + ICS Data Export (Pro) | `28-app-export-request-modal.html` self-tagged FR-52 (A-17) | FULL | |
| FR-53 | Event State Polling + Webhooks | `38-app-event-state-change.html` self-tagged FR-53 (A-23) | FULL | |
| FR-54 | User-Facing State-Change Notifications | `38-app-event-state-change.html` self-tagged FR-54 (A-23) | FULL | |
| FR-55 | Conflict Resolution on State Change | `38-app-event-state-change.html` self-tagged FR-55 (A-23) | FULL | **Closes a previously-flagged PARTIAL gap** — the prior matrix found only unacknowledged overlap with FR-58's conflict UI; Amendment A-23's event-state-change mockup now names FR-55 directly. |
| FR-56 | RSS/Email-ICS Source Acquisition (MVP) | — | N/A (no design needed) | Backend acquisition-method policy; users see resulting events, not how they were acquired. |
| FR-57 | Editorial Review Queue (Internal) | — | N/A (no design needed) | EXPERIENCE.md explicitly places this outside the user-facing surface map (internal-only). |
| FR-58 | Personal Event Conflict Detection (rev. A-5) | `20-app-conflict-prompt.html`, `21-app-conflict-indicator-card.html` self-tagged FR-58 | FULL | |
| FR-59 | User-Reported Event Quality (added A-4) | `30-app-report-event-modal.html` self-tagged "FR-59 / Amendment A-4" | FULL | |
| FR-60 | Timezone Source of Truth (added A-6) | — | N/A (no design needed) | Backend data-integrity/launch-gating policy (which events get accepted); correct time display is a byproduct already covered under FR-6/FR-9's card and reminder surfaces, not a distinct screen. |

**Open Design gaps: none.** FR-20 and FR-28 were the two open rows when this matrix was generated; both were closed by UX Amendment A-25 on 2026-09-10 (see their rows above). Section A is now entirely FULL or N/A.

**New item recorded during A-25, not a Design-coverage gap:** both UX spines carry **164 mockup filename references pointing at the pre-renumbering names** (`event-detail-desktop.html` rather than `16-app-event-detail.html`) and zero pointing at a file that currently exists, so every mockup link in DESIGN.md and EXPERIENCE.md is presently dead. This does not change any FR's coverage status — the designs exist and were verified against the real files — but it will mislead any future reader or audit that trusts a spine link. Queued as Amendment A-26 as its own mechanical sweep.

---

## Section B — PRD ↔ Architecture Alignment

For each MVP FR: does the Architecture Spine's `Capability → Architecture Map` have an explicit row naming this FR (or a covering range), with a module and at least one `AD-N`?

**Counts: 43 FULL · 2 MISSING · 0 PARTIAL · 0 N/A** (45 total)

| FR-ID | Title | Architecture (module · AD-N) | Status | Note |
|---|---|---|---|---|
| FR-1 – FR-4 | Onboarding / Preview / Calendar Connect / Auth State | `identity`, `web`, `adapters/calendar` · AD-5, AD-12, AD-15, AD-18 | FULL | |
| FR-5 – FR-8 | Pulse Digest group | `personalization`, `web` · AD-3, AD-10, AD-11 | FULL | |
| FR-9 – FR-12 | Reminders & Pulse Ping group | `delivery`, `worker` · AD-6, AD-7, AD-16, AD-17 | FULL | |
| FR-13 – FR-17, FR-56 | Source Registry / Extraction / Dedup / Reliability / Hierarchy / RSS-ICS | `ingestion`, `worker`, `adapters/crawl` · AD-4, AD-6, AD-8, AD-9 | FULL | |
| FR-18 – FR-20, FR-58 | Personal Event group + Conflict Detection | `personalization` · AD-3, AD-6, AD-16 | FULL | |
| FR-21 – FR-25 | Explainability & Trust group | `personalization` · AD-9, AD-10 | FULL | |
| FR-26 – FR-28 | Sharing & SEO group | `catalog`, `frontend` · AD-12, AD-19 | FULL | |
| FR-29 | AI Cost Dashboard (Internal) | `adapters/llm`, `editorial` (Django admin) · AD-8, AD-14 | FULL | |
| FR-30 | Caching & Batching Defaults | `adapters/llm` · AD-8 | FULL | |
| **FR-32** | **Unified Personal+Public Timeline — lifted to MVP by Amendment A-8** | **none — no Capability Map row** | **MISSING** | Architecture Spine is dated 2026-09-04; Amendment A-8 merged 2026-09-06. Spine has not been updated since the amendment lifted this FR into MVP. |
| **FR-33** | **Conflict-Aware Scheduling — lifted to MVP by Amendment A-8** | **none — no Capability Map row** | **MISSING** | Same cause as FR-32 — both lifted by the same amendment, both absent from the same map. |
| FR-48 – FR-52 | Pro tier group (incl. Saved Collections, Quiet Hours Pro, Export) | `identity`, `adapters/billing`, `adapters/calendar` · AD-5, AD-15, AD-18 | FULL | |
| FR-53 – FR-55 | Event state sync group | `ingestion`, `delivery` · AD-4, AD-7, AD-17 | FULL | |
| FR-57 | Editorial Review Queue (Internal) | `editorial` (Django admin) · AD-4, AD-8, AD-14 | FULL | |
| FR-59 | User Event Reports | `personalization`, `editorial` · AD-3, AD-14 | FULL | |

(FR-60, Timezone Source of Truth, is covered by the same Capability Map row as FR-13–17/FR-56 — `ingestion`/`worker`/`adapters/crawl` · AD-4, AD-6, AD-8, AD-9 — and is FULL, folded into that row above per the row's own listed FR range.)

**Open Architecture gaps: FR-32 and FR-33** — this is the single highest-value finding in this matrix. Both are fully designed (Section A: FULL, self-tagged mockups) and both are explicitly PRD MVP scope via Amendment A-8, but the Architecture Spine's Capability Map has no row for either, and the word "Amendment" never appears in `ARCHITECTURE-SPINE.md` at all (see Amendment Ledger below). Two of the three source docs treat this as real, shipped MVP scope; Architecture has not caught up.

---

## Amendment Ledger

Cross-cutting across PRD, Architecture, Design, Experience, and mockups — one row per distinct `Amendment A-N` found anywhere. `ARCHITECTURE-SPINE.md` does not use the "Amendment A-N" ID convention anywhere in the document (confirmed by full-text scan) — it is noted below only where a specific amendment has a concrete, unreflected architectural consequence; its general absence is not scored as a separate defect per amendment.

| Amendment | Found in | Consistent? |
|---|---|---|
| A-1 (FR-15 dedup revision) | PRD | Consistent — FR-15 is backend-only (N/A design); Architecture's AD-4/AD-9 implement the substance without citing the tag by ID, which is expected since the Spine doesn't use the convention. |
| A-2 (FR-5/FR-25 serendipity slot & diversity floor) | PRD only | **No** — neither DESIGN.md nor EXPERIENCE.md cites "Amendment A-2" anywhere, despite FR-5 and FR-25 both being FULL, real design surfaces (`Card.PulseDigest`, `29-app-less-like-this-mute.html`). |
| A-3 (FR-22 static weights lock) | PRD only | **No** — neither DESIGN.md nor EXPERIENCE.md cites "Amendment A-3" anywhere, despite FR-22 having extensive design coverage (`Indicator.Confidence`, the A-13 amendment-history timeline). |
| A-4 (FR-59 added) | PRD, mockup (`30-app-report-event-modal.html`), Architecture (FR-59 capability-map row) | Consistent |
| A-5 (FR-58 conflict resolution) | PRD, EXPERIENCE.md (§4, §8, §13 — `Sheet.ConflictResolution`) | Consistent |
| A-6 (FR-60 timezone added) | PRD only | Consistent — FR-60 is backend-only (N/A design); no design citation expected. |
| A-7 (FR-3/FR-50 calendar parity at MVP) | PRD, Design (mockup headers on `08-onboarding-step1.html` and siblings, DESIGN.md updated_note) | Consistent |
| A-8 (FR-32/FR-33 lifted to MVP) | PRD, Design (pervasive across ~12 mockup headers) | Consistent between PRD and Design. **Inconsistent with Architecture** — see Section B gap; this is the same finding, cross-referenced here because it is the ledger's most material entry. |
| A-9 – A-24 (16 Design-layer amendments: pre-auth chrome, Browse route, Browse×city merge, inline search, geo-IP toggle, Sold Out badge, delete-account modal, export modal, source-mute control, Pro quiet-hours picker, signin/signup routes, reminder-picker relocation, Saved Collections, Event-State generalization, mockup alignment sweep) | Design/mockups only | Consistent — each realizes an FR requirement that the PRD already specifies (e.g. A-22 implements FR-49's existing "reorderable collections" text via explicit buttons; A-19 implements FR-51's existing 7-window spec) rather than changing the FR's normative text, so no PRD-side tag is expected under the convention. |
| A-25 (share action + FR-20 tracing — 2026-09-10) | DESIGN.md, EXPERIENCE.md, and 6 mockup headers (`16-app-event-detail`, `27-app-share-link`, `mobile/event-detail-mobile`, `14-app-personal-event-create`, `15-app-personal-event-edit`, `22-app-reminder-picker`) | Consistent — specifies PRD FR-28's previously-unspecified share behavior and Open Graph contract, and adds the missing FR-20 citation, without changing either FR's normative text, so no PRD-side amendment tag is expected. Both spines carry the ID, as does every mockup it touches. |

**Net finding:** the Amendment convention is being followed faithfully between PRD and Design/mockups from A-4 onward (A-2 and A-3 are the two lingering exceptions from earlier in the log). It is not being followed by Architecture at all — the document never uses the ID scheme, and the one amendment with unambiguous architectural stakes (A-8) has a real, unresolved gap rather than just a missing citation.

---

## Deferred (Phase 2 / Phase 3 / Year 2+ — out of MVP, not scored)

- **Phase 2:** FR-31 (Two-Way Calendar Sync + RRULE Expansion), FR-34 (Pulse the Group), FR-35 (Pro Tier — Phase 2 Augmentation), FR-44 (Already-Handled Reminder Suppression)
- **Phase 3:** FR-36 (Voice Quick-Add), FR-37 (Email-to-Event Forwarding), FR-38 (Why Now?), FR-39 (On-Device Personal AI), FR-40 (Travel Mode), FR-41 (Group Availability Heatmap), FR-45 (Adaptive Pulse Digest Card Count)
- **Year 2+:** FR-42 (White-Label B2B2C), FR-43 (B2B Insights API), FR-46 (Pulse Streak), FR-47 (Year in Pulse Recap)

All 15 are correctly absent from the Architecture Capability Map and from UX design coverage — none is in MVP scope, consistent with the PRD's own §6.2 "Out of Scope for MVP" table.

## Epic/Story Coverage

No epics or stories exist yet anywhere under `_bmad-output/planning-artifacts/` — not yet created. This section will populate once they exist.
