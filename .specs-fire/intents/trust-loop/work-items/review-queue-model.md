---
id: review-queue-model
title: Something to queue onto — the ReviewItem and the editorial group
intent: trust-loop
complexity: high
mode: validate
status: completed
depends_on: []
created: 2026-11-10
run_id: run-eventpulse24-026
completed_at: 2026-11-10T14:37:21.224Z
---

# Work Item: Something to queue onto — the ReviewItem and the editorial group

## Description

FR-57's queue has no table. `apps/ingestion/__init__.py:3` lists `ReviewItem` as owned, and the Spine places `REVIEW_ITEM` in schema `catalog`. Its ER diagram has `EVENT ||--o{ REVIEW_ITEM : flagged_as` and `EVENT_REPORT ||--o{ REVIEW_ITEM : raises`. The model does not exist.

This item builds the model, the one command that raises or bumps an item, and the editorial role that AD-14 requires. Everything else in the intent writes to or reads from it.

## Acceptance Criteria

- [ ] `ReviewItem` lives in `apps/ingestion/models.py`, schema `catalog`, and is written only by `ingestion` services (AD-4).
- [ ] **A reason** is one of `user_reported`, `in_review` or `source_reliability`. **A target** is exactly one of an Event or a Source, enforced by a `CheckConstraint`. A `source_reliability` item targets a Source, and the other two target an Event.
- [ ] **Priority and SLA.** `user_reported` items carry `due_at = created + 24h`. The other reasons carry the daily-review cadence, or none, as the design decides. Both durations live in `shared/constants.py`.
- [ ] **No user identity crosses the wall (AD-3).** The row holds no user id, email or `EventReport` foreign key. A report raises the item by event id, and only a **count** of reports and their **category tallies** are stored on it.
- [ ] **At most one open item per (target, reason)**, enforced by a partial unique constraint. A second raise **bumps** the open item's count and tallies. It never creates a duplicate.
- [ ] **Lifecycle:** `open`, then `resolved`. The resolution (`approved`, `edited` or `rejected`, plus `dismissed` for a source item with no action) is attributed to an actor (`ActorColumns`), carries a timestamp, and is immutable once closed. A guard rejects re-opening or editing a closed item, following the pattern of the existing `guard_*` triggers.
- [ ] **`raise_review_item(target, reason, ...)`** is an `ingestion` command. It is idempotent under concurrency, so two simultaneous raises yield one row, and it writes an `IngestionAuditEntry` (AD-5).
- [ ] **The editorial group.** A data migration creates the editorial reviewers group with per-model permissions: view and change on `ReviewItem`, view on `Event` and `Source`, and **no delete anywhere**. It never grants superuser. Running it twice is a no-op.
- [ ] A retention category is declared (AD-15), as for every table.
- [ ] Tests cover:
  - the target `CheckConstraint`, in both of its illegal shapes
  - a duplicate open item refused at the database level
  - a raise on an open item bumping it, and a raise on a closed item opening a new one
  - concurrent raises yielding one row
  - the closed-item guard
  - the group's exact permission set, with no delete permission and no superuser

## Technical Notes

High complexity, so this item gets a design doc. The design needs to decide:
- how a source-level item and an event-level item share one table without nullable-everything sprawl
- whether the daily-review cadence for `in_review` items is a `due_at` or only a sort order
- the shape of the stored category tallies: four integer columns, or JSON. Columns are queryable and checkable.

Follow the existing `apps/ingestion/admin.py` and `services/source_registry.py` conventions for commands and audit, and the `EventStateChange` `ActorColumns` mixin for attribution.

## Dependencies

(none)
