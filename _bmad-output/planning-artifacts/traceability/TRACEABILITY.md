# EventPulse24 — Traceability Matrix

Generated: 2026-09-07

**Sources scanned:**
- PRD: `_bmad-output/planning-artifacts/prds/prd-EventPulse24-2026-08-19/prd.md`
- Architecture: `_bmad-output/planning-artifacts/architecture/architecture-EventPulse24-2026-09-04/ARCHITECTURE-SPINE.md`
- UX: `_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/DESIGN.md`
- Epics/Stories: none found yet (expected — not created in this project as of this run). The Epic/Story column below will populate automatically once `_bmad-output/planning-artifacts/epics*` (or similar) exists.

## Findings (read this first)

1. **Architecture gap — FR-32 and FR-33 are MVP but architecturally homeless.** The PRD's own `Amendment A-8` explicitly "lifted" FR-32 (Unified Personal+Public Timeline) and FR-33 (Conflict-Aware Scheduling) from Phase 2 into MVP scope. UX has fully built for this — dedicated `Surface.Timeline`, the `/conflicts` route, `layout.timeline.grid`, and `ASSUM-7` even cites "the FR-33 three-action pattern" by name. But the Architecture Spine's **Capability → Architecture Map** has no row for FR-32 or FR-33, and the word "Amendment" does not appear anywhere in `ARCHITECTURE-SPINE.md`. Two of three docs treat this as a real, shipped-scope MVP feature; the third has never accounted for it. This is the highest-value finding from this run.
2. **Two independent "Amendment A-N" counters exist, not one shared ledger.** The PRD numbers its own amendments A-1 → A-8. `DESIGN.md`'s frontmatter separately numbers UX-originated amendments A-8 → A-21 ("PRD-coverage reconciliation" work). These are two disjoint per-doc sequences that happen to collide at `A-8` — and the UX author was clearly aware of the collision risk (see the doc's own "Numbering note" comments about not clashing with "the existing A-12 spine lock"). At `A-8` specifically the collision is benign (both docs are describing the same underlying change — the Timeline/Conflicts MVP lift). But nothing enforces that going forward, and A-9 through A-21 exist **only** in `DESIGN.md` — `prd.md` has no record that 13 more amendments happened downstream of it. There is no single, doc-agnostic amendment log.
3. **Architecture Spine never uses the Amendment convention at all.** Zero `Amendment A-N` mentions anywhere in `ARCHITECTURE-SPINE.md`, even where architecture rules clearly trace back to a numbered PRD amendment (e.g. AD-4's dedup rule ↔ PRD Amendment A-1; AD-6's UTC rule ↔ PRD Amendment A-6). Worth a decision: either Architecture adopts the tag too, or the convention is explicitly scoped as PRD+UX-only.
4. **FR-59 (User-Reported Event Quality, added by PRD Amendment A-4) has Architecture coverage but no discoverable UX section.** No "report" affordance found anywhere in `DESIGN.md`. If a report flow exists, it isn't documented in the spine.
5. Several Pro-tier and secondary FRs (FR-20, FR-28, FR-49, FR-54, FR-55) have plausible but only **inferred** UX coverage — the design system doc doesn't name them by FR number, so coverage is inferred from adjacent component descriptions rather than confirmed.

## FR ↔ Architecture ↔ UX ↔ Epic Matrix

| FR-ID | Title | PRD Amendment(s) | Architecture (module · AD-N) | UX section / Amendment | Epic/Story | Status |
|---|---|---|---|---|---|---|
| FR-1 | 30-Second Onboarding Flow | — | `identity`,`web`,`adapters/calendar` · AD-5,12,15,18 | `/onboarding` flow, `layout.container.form` (2026-09-03 onboarding audit) | — not yet created | FULL |
| FR-2 | Pulse Preview (No-Auth First Value) | — | same as FR-1–4 group | Explicit: `pulse-preview-desktop.html` | — not yet created | FULL |
| FR-3 | Calendar Connect (OAuth Google/Apple/Outlook) | A-7 (see Ledger) | same | Explicit: Do's/Don'ts calendar-provider-parity row | — not yet created | FULL (Amendment A-7 not echoed — see Ledger) |
| FR-4 | Authenticated User State | — | same | Inferred: authed shell / sidenav routing | — not yet created | PARTIAL (inferred only) |
| FR-5 | Pulse Digest Composition | A-2 | `personalization`,`web` · AD-3,10,11 | `Card.PulseDigest` vocabulary (extensive, but no A-2 tag) | — not yet created | FULL (Amendment A-2 not echoed — see Ledger) |
| FR-6 | Pulse Card Information Density | — | same | `Card.PulseDigest` stripe/density rules | — not yet created | FULL |
| FR-7 | Pulse Digest Delivery Time | — | same | none (delivery-time is backend scheduling, no UI expected) | — not yet created | FULL (N/A UX) |
| FR-8 | Empty-State Pulse Digest | — | same | Explicit: `component.emptystate.quiet` | — not yet created | FULL |
| FR-9 | Multi-Tier Reminder Picker | — | `delivery`,`worker` · AD-6,7,16,17 | Explicit: `reminder-picker-desktop.html` (Amendment A-21 shell migration) | — not yet created | FULL |
| FR-10 | Pulse Ping — Single Daily Notification | — | same | none (push/email, no in-app UI expected) | — not yet created | FULL (N/A UX) |
| FR-11 | Email Multi-Tier Reminders | — | same | covered via FR-9's reminder picker config | — not yet created | FULL |
| FR-12 | Quiet Hours | — | same | Reminder picker aside panel ("Edit quiet hours"); Pro variant explicit (Amendment A-19 → FR-51) | — not yet created | FULL |
| FR-13 | Source Registry | — | `ingestion`,`worker`,`adapters/crawl` · AD-4,6,8,9 | Explicit: `/settings/sources` (Amendment A-18) | — not yet created | FULL |
| FR-14 | Hybrid Event Extraction Pipeline | — | same | none (backend pipeline) | — not yet created | FULL (N/A UX) |
| FR-15 | Event Deduplication | A-1 | same | none (backend) | — not yet created | FULL (N/A UX) |
| FR-16 | Source Reliability Score | — | same | Explicit: reliability dots (Amendment A-18) | — not yet created | FULL |
| FR-17 | Source Acquisition Hierarchy Enforcement | — | same | none (internal policy) | — not yet created | FULL (N/A UX) |
| FR-56 | RSS/Email-ICS Source Acquisition (MVP) | — | same | none (backend) | — not yet created | FULL (N/A UX) |
| FR-60 | Timezone Source of Truth | A-6 | same (AD-6 governs this in substance) | none (backend) | — not yet created | FULL (N/A UX; A-6 not echoed in Architecture — see Finding 3) |
| FR-18 | Manual Personal Event Creation | — | `personalization` · AD-3,6,16 | Inferred: `personal-event-edit-desktop.html` mockup | — not yet created | FULL |
| FR-19 | Personal Event in Pulse Digest | — | same | `color.warm.personal` + "Personal" label | — not yet created | FULL |
| FR-20 | Personal Event Reminder Defaults | — | same | Inferred via FR-9 reminder picker | — not yet created | PARTIAL (inferred only) |
| FR-58 | Personal Event Conflict Detection | A-5 | same | Explicit: conflict indicator, `/conflicts` route (tagged UX-side as A-8/A-33, not A-5) | — not yet created | FULL (Amendment A-5 not echoed — see Ledger) |
| FR-21 | Why-this Tags | — | `personalization` · AD-9,10 | `type.scale.microtag` italic hint | — not yet created | FULL |
| FR-22 | Confidence Pulse | A-3 | same | Explicit: changelog mechanism, `Indicator.Confidence` (no A-3 tag) | — not yet created | FULL (Amendment A-3 not echoed — see Ledger) |
| FR-23 | Source Badge | — | same | `Badge.Source.verified` | — not yet created | FULL |
| FR-24 | "Why this?" Detail Screen | — | same | `Tooltip.Confidence` / `Tooltip.Source` | — not yet created | FULL |
| FR-25 | "Less like this" Adjustment | — | same | "less like this" explainer aside panel | — not yet created | FULL |
| FR-26 | Public Event Pages with Structured Data | — | `catalog`,frontend · AD-12,19 | Inferred: `/events/:id` pre-auth route | — not yet created | PARTIAL (inferred only) |
| FR-27 | SEO City Pages | — | same | Explicit: "per PRD FR-27" on `city-page-desktop.html` | — not yet created | FULL |
| FR-28 | Share-Card Public Link | — | same | Inferred: `/p/:slug` pre-auth route, no named component | — not yet created | PARTIAL (inferred only) |
| FR-29 | AI Cost Dashboard (Internal) | — | `adapters/llm`,`editorial`(Django admin) · AD-8,14 | none (internal admin tool, outside this design system) | — not yet created | FULL (N/A UX) |
| FR-30 | Caching & Batching Defaults | — | `adapters/llm` · AD-8 | none (backend) | — not yet created | FULL (N/A UX) |
| FR-32 | Unified Personal+Public Timeline — lifted to MVP | A-8 | **none — no Capability Map row** | Explicit: `Surface.Timeline`, `layout.timeline.grid` (Amendment A-8) | — not yet created | **MISSING (architecture)** |
| FR-33 | Conflict-Aware Scheduling — lifted to MVP | A-8 | **none — no Capability Map row** | Explicit: `/conflicts` route, "FR-33 three-action pattern" (ASSUM-7, Amendment A-8) | — not yet created | **MISSING (architecture)** |
| FR-48 | Pro Tier with MVP-Only Features | — | `identity`,`adapters/billing`,`adapters/calendar` · AD-5,15,18 | Explicit: Pro upsell section | — not yet created | FULL |
| FR-49 | Unlimited Saves + Saved Collections (Pro) | — | same | none found | — not yet created | **MISSING** |
| FR-50 | Calendar Provider Read-Only Sync (Free+Pro) | — | same | Explicit: parity row (shared with FR-3) | — not yet created | FULL |
| FR-51 | Per-Day-of-Week Custom Quiet Hours (Pro) | — | same | Explicit: `component.control.day-picker` (Amendment A-19) | — not yet created | FULL |
| FR-52 | JSON+ICS Data Export (Pro) | — | same | Inferred: `component.modal.export-request` (Amendment A-17) | — not yet created | FULL (inferred match, not FR-numbered in UX) |
| FR-53 | Event State Polling + Webhooks | — | `ingestion`,`delivery` · AD-4,7,17 | Explicit: `component.badge.soldout` (Amendment A-15) | — not yet created | FULL |
| FR-54 | User-Facing State-Change Notifications | — | same | Inferred: sold-out Detail Screen messaging | — not yet created | PARTIAL (inferred only) |
| FR-55 | Conflict Resolution on State Change | — | same | Inferred: overlaps FR-58 conflict UI | — not yet created | PARTIAL (inferred only) |
| FR-57 | Editorial Review Queue (Internal) | — | `editorial`(Django admin) · AD-4,8,14 | none (internal admin tool) | — not yet created | FULL (N/A UX) |
| FR-59 | User-Reported Event Quality | A-4 | `personalization`,`editorial` · AD-3,14 | **none found** | — not yet created | **MISSING (UX)** |

**Deferred (Phase 2 / Phase 3 / Year 2+, correctly out of MVP — not scored)**: FR-31 (explicitly in Architecture's own Deferred table), FR-34–FR-47 (14 FRs, all Phase 2/3/Year 2+ per PRD headings, none expected in Architecture or UX yet).

## Amendment Ledger

| Amendment | Found in | Consistent? |
|---|---|---|
| A-1 (FR-15 dedup revision) | PRD | Consistent — backend-only change, no UX impact expected; Architecture's AD-4 implements the substance but doesn't cite the tag (see Finding 3). |
| A-2 (FR-5 revision) | PRD | **No** — FR-5 is core UX real estate (`Card.PulseDigest`); DESIGN.md has no matching tag anywhere. |
| A-3 (FR-22 revision) | PRD | **No** — DESIGN.md references FR-22 directly (changelog mechanism) but never cites "Amendment A-3". |
| A-4 (FR-59 added) | PRD | Partially — Architecture picked it up (Capability Map has an FR-59 row); UX has no coverage at all (see FR-59 MISSING above). |
| A-5 (FR-58 revision) | PRD | **No** — UX covers FR-58 extensively but under its own tags (A-8, A-15), never citing "Amendment A-5". |
| A-6 (FR-60 added) | PRD | Consistent — backend-only (timezone truth), no UX impact expected. |
| A-7 (FR-3 calendar OAuth→ICS correction) | PRD | **No** — UX's calendar-parity guidance (FR-3/FR-50) carries no A-7 tag. |
| A-8 (FR-32/FR-33 lifted to MVP) | PRD, UX | Consistent between PRD and UX — both describe the same Timeline/Conflicts MVP lift. **Missing from Architecture** (see Finding 1). |
| A-9 – A-21 (UX-originated "PRD-coverage reconciliation" + shell migrations) | UX only | Not found in PRD at all. Per DESIGN.md's own frontmatter these exist specifically to close PRD-coverage gaps, so the PRD arguably should reflect that reconciliation happened — see Finding 2 for the broader "two counters" issue. |

## Epic/Story Coverage

No epics or stories exist yet in `_bmad-output/planning-artifacts/`. This section will populate automatically on the next `/doc-trace` run once they're created.
