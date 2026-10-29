---
id: personal-events-and-saved-catalog
title: Personal Events, Saved Catalog & Conflict Detection
status: completed
created: 2026-10-29
completed_at: 2026-10-29T05:31:24.902Z
---

# Intent: Personal Events, Saved Catalog & Conflict Detection

## Goal

Populate the empty `personal` schema with the user-owned records that every later feature reads: `PERSONAL_EVENT`, `SAVED_EVENT` and `CONFLICT_PAIR`. This is the write side of `personalization` and the first consumer of the ingested catalog.

It delivers FR-18 (manual personal event creation), FR-20 (personal event reminder defaults), FR-58 (conflict detection) and the AD-21 `SAVED_EVENT` record, and it establishes the `personalization` write-ownership contract that the Pulse Digest, the Timeline and `/conflicts` all depend on.

## Users

- **The signed-in user**, who creates personal events (a birthday, a dinner, a meeting), saves public events from the catalog, and is protected from double-booking.
- **The operator/editor**, indirectly: personal events never enter `catalog`, so no editorial surface is affected.

## Problem

The scaffold and the ingestion pipeline are done, so `catalog` is populated and readable. But `personal` is empty and `personalization` has no models, no API and no writer:

- `apps/personalization/models.py` is empty; `apps/personalization/api.py` is a bare `Router()`.
- `apps/delivery/models.py` is empty too, and AD-16 assigns `REMINDER_PLAN` to `delivery`, not `personalization`.

Three consequences follow:

1. **No user can own a single event.** FR-18 is the entry point to the whole product, and it does not exist.
2. **AD-21 has no source of truth.** AD-21 says the Timeline and conflict detection read *personal-side snapshots*, never `catalog` joins. With no `SAVED_EVENT` row, there is nothing to read, so FR-32, FR-33 and FR-58 are all blocked on this.
3. **The `personal` write boundary is undefined.** AD-16 requires every entity in either schema to have exactly one owning module. `personalization` owns `PERSONAL_EVENT`, `SAVED_EVENT` and `CONFLICT_PAIR`, but nothing has been written by it yet, so the contract is untested. AD-16's own rule notes that `delivery` owns `REMINDER_PLAN` and that `personalization` must call `delivery`'s published service for FR-20's default plan — a boundary crossing that must be built deliberately, not discovered later.

The single personal event is also where the app's calm promise is first tested: the PRD requires a forced three-way choice on a conflict, with no dismiss and no red.

## Success Criteria

- **`PERSONAL_EVENT` (FR-18):** a user creates a personal event with name, start time, optional end time, location and optional notes. It is stored in `personal` with `source = user_created`, and the user can edit and delete it. Start time requires an explicit IANA timezone; a floating or ambiguous local time is refused, and UTC `timestamptz` is the stored truth (AD-6).
- **`SAVED_EVENT` (AD-21):** a user saves a public event from the catalog. The row holds `event_id` **by value, never as a FK**, plus a snapshot (`start_utc`, `end_utc`, `event_version`) read from `catalog` at save time. A save re-reads the event's version after commit and requests re-propagation if it moved meanwhile, so a save racing a postponement cannot keep a stale snapshot. Saving is idempotent; the same event saved twice is one row.
- **`CONFLICT_PAIR` (AD-21, FR-58):** each detected conflict is one persisted row linking two sides (each a `SAVED_EVENT` or a `PERSONAL_EVENT`), with status `active` or `resolved`. The user's choice is recorded on the pair as a `ConflictResolution`. A resolved pair is immutable and is never re-prompted.
- **One overlap function (AD-21):** conflict detection is a single pure function in `domain/conflict.py`. Two UTC intervals conflict when they overlap by **strictly more than 15 minutes**. It runs on save, on personal event create and edit, and never at render time. Public-vs-public pairs are out of scope at MVP.
- **Duplicate detection (FR-58):** on personal event creation, a likely duplicate is flagged when another personal event has the same name (case-insensitive, token-overlap ≥ 80%) and starts within 24 hours. This is a separate rule from the interval-overlap rule and is not a conflict by itself.
- **Forced choice (FR-58):** a conflict prompt presents exactly three actions — "Keep both — I'll manage", "Edit the new one" (relabelled "Update the existing one" for duplicates) and "Delete the new one". There is **no dismiss and no X**. The creation flow cannot complete until one of the three is chosen. A `ConflictResolution` is recorded for **every** prompt, including those resolved by editing or deleting.
- **Conflict indicator:** an 8–10px filled circle in desaturated amber at the top-right of the Pulse Card, with `aria-label="Schedule conflict"`. It is **never red**, it is symmetric across the pair, it is distinct from the Source Badge and the Confidence Pulse by shape and position, and it **persists permanently** after "Keep both". The Pulse Card and the Timeline event-block read the same `CONFLICT_PAIR` rows, so the indicator is symmetric by construction.
- **Reminder default (FR-20):** a new personal event inherits a reminder plan of **1d + 1hr**, and the user can remove all reminders. The default lives as **one named constant in `shared/`**, beside the confidence thresholds (AD-16's rule: the default is a constant, not state). `personalization` does not own `REMINDER_PLAN`; it calls `delivery`'s published service to attach the default plan, and `delivery` owns the entity.
- **Write ownership (AD-16):** `personalization` writes `PERSONAL_EVENT`, `SAVED_EVENT` and `CONFLICT_PAIR` and nothing else. `delivery` writes `REMINDER_PLAN` and nothing else. Every cross-module write goes through the owner's published interface. The `import-linter` contracts keep passing.
- **Schema separation (AD-3):** no `personal` model FKs to `User` or `ContentType`, and no model in either schema FKs across the wall. Audit rows store the actor by id in a catalog-side or personal-side audit table. Every new model declares a retention category (AD-15).
- **Frontend:** the `Sheet.PersonalEventCreate` / `Sheet.PersonalEventEdit` and `Sheet.ConflictResolution` surfaces exist, following the UX spine exactly, with the `color.warm.personal` tone (`#C8967A` dark / `#A8765C` light) always paired with the visible text label "Personal" so colour is never the sole carrier of meaning (WCAG 1.4.1).
- **Proof:** the conflict rules are pinned by tests, including the "strictly more than 15 minutes" boundary (exactly 15 minutes is **not** a conflict), the 80% duplicate threshold, the "keep both" non-re-prompt, the immutable resolved pair, and a test proving a `SAVED_EVENT` snapshot survives a catalog postponement unchanged. CI stays green with the coverage gates.

## Constraints

- Builds on the two completed intents:
  - `project-scaffold` — the `personal` schema, the two-`DATABASES` router (AD-3), the shared foundations, and the `import-linter` contracts.
  - `event-catalog-ingestion` — `catalog` is populated and read through `ingestion`'s published read interface (`apps/ingestion/services/catalog_read.py`). `ingestion` remains the sole writer of `catalog` (AD-16).
- **Pure logic lives in `backend/domain/`** (stdlib only). `domain/conflict.py` is new and holds the one overlap function. `domain/` must not import Django or I/O.
- **Reading `catalog` from `personalization` goes through `ingestion`'s published read interface**, never by importing `apps.ingestion.models` and never by a cross-schema join (AD-3, AD-21).
- **`beat_schedule` stays exactly one 60s tick**, enforced by `backend/tests/worker/test_tick.py`. Conflict detection on write adds no beat entry.
- **No LLM call anywhere in this intent.** Duplicate detection is token-overlap, not semantic similarity (AD-4's discipline extends to personal events: embeddings never decide an identity).
- **`delivery` is built minimally here.** It arrives only far enough to own `REMINDER_PLAN` and expose the published service that `personalization` calls. The rest of `delivery` (scheduled sends, quiet hours, FR-9–FR-12) is a later intent.
- The UX spine already specifies this feature in detail: `EXPERIENCE.md` §`Sheet.ConflictResolution`, §`Surface.Timeline`; `DESIGN.md` §`component.card.pulse.digest.category.personal`, §`component.indicator.conflict`, §`component.timeline.event-block`. Mockups `personal-event-create-desktop.html`, `personal-event-edit-desktop.html`, `conflict-prompt-desktop.html` and `conflict-indicator-card-state-desktop.html` exist. This intent implements them; it does not re-design them.
- Binding sources:
  - `_bmad-output/planning-artifacts/architecture/architecture-EventPulse24-2026-09-04/ARCHITECTURE-SPINE.md` (AD-3, AD-6, AD-12, AD-15, AD-16, AD-21)
  - `_bmad-output/planning-artifacts/prds/prd-EventPulse24-2026-08-19/prd.md` §4.5, §3 Glossary
  - `_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/`
  - `.specs-fire/standards/`

## Notes

**Out of scope:**
- **FR-19 (personal event in the Pulse Digest).** Deferred wholesale to the Pulse Digest intent, where the digest composition engine (FR-5–FR-8) lives. Building a partial projection here would be a second, divergent implementation of the digest card.
- **FR-32 (Timeline) and FR-33 (`/conflicts` route).** The `CONFLICT_PAIR` records and the personal-side snapshots this intent produces are their data foundation, but the surfaces themselves are their own intents. FR-58's *detection and prompt* is in scope; FR-33's *cross-event review route* is not.
- **The Pulse Card's own rendering.** The conflict indicator must be correct on the card, but the card is the Pulse Digest intent's work.
- **Calendar import (FR-3, FR-50).** `CALENDAR_CONNECTION` is `personalization`-owned but arrives with the onboarding intent. The ICS parser built during ingestion is reused later.
- **Auto-rebook, alternatives and conflict suggestions (Phase 3).** FR-58's three-action pattern is the minimum viable guard; there is no auto-resolve.
- **Public-vs-public conflicts** at MVP (Phase 3).
- **A "Hide conflict indicators" toggle** (Phase 2 candidate — it would conflict with the calm permanent-reminder design).
- **Saved Collections (FR-49).** It is Pro-tier scope and has **no UX design at all** (the traceability matrix marks it MISSING). Keeping it out of this intent avoids building an undesigned feature.

**Still open:**
- **PRD amendment needed:** the PRD Glossary does not yet contain `SavedEvent`, `ConflictPair` or `ExtractedRecord`. The Architecture Spine's naming convention requires these new nouns be added to PRD §3 before build. This intent follows the Spine's terms.
- **The 15-minute overlap threshold is strict.** "Strictly more than 15 minutes" means exactly 15 minutes is *not* a conflict. This is a wireframe-locked constant from AD-21 and FR-33, and it needs a pinned boundary test.
- **OQ-7 (Google ICS cache freshness)** still blocks a fixed calendar-poll interval. It does not block this intent, but it will surface when calendar import lands.
- **Editorial vs. automatic re-gating** remains open from `event-catalog-ingestion` (run-eventpulse24-015). A `SAVED_EVENT` snapshot is updated only by AD-17 propagation; if propagation is ever corrected manually by an editor, the snapshot must be re-derived rather than hand-edited.
- **Venue renames** remain open from `event-catalog-ingestion` (run-eventpulse24-014). Not in scope here, but a saved event's display name resolves through `catalog` at read time, so a rename is visible immediately even though the snapshot's times are not.

**Decisions taken during capture (2026-10-29):**

1. **FR-20 ships in this intent, with a minimal `delivery` owner.** `delivery` gets a `REMINDER_PLAN` model and a published service that `personalization` calls for the default plan. This keeps AD-16 intact rather than deferring FR-20.
2. **FR-19 is deferred entirely** to the Pulse Digest intent. No partial digest projection is built here.
3. **`SAVED_EVENT` ships in full** — model, snapshot semantics, and save/unsave API. It is not optional: conflict detection against public events depends on it.

**Work happens on branch `personal-events-and-saved-catalog`.**

**Housekeeping:** the repository root carries ~30 Finder duplicate files (`Makefile 2.py`, `README 2.md`, `docker-compose 2.yml`, and duplicates under `backend/` and `frontend/`). These are collected by formatters, linters and test collectors and risk misleading test runs. They should be removed in a separate cleanup commit before this intent's implementation starts.
