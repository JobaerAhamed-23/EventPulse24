---
id: source-registry-commands-admin
title: Source Registry Commands & Admin
intent: event-catalog-ingestion
complexity: medium
mode: confirm
status: completed
depends_on:
  - catalog-data-model
created: 2026-10-28
run_id: run-eventpulse24-014
completed_at: 2026-10-28T11:47:26.363Z
---

# Work Item: Source Registry Commands & Admin

## Description

The operator-facing Source Registry (FR-13). It provides named `ingestion` commands for every source mutation, enforces the acquisition hierarchy (FR-17), and exposes a Django admin that writes only through those commands, with an audit row on each change (AD-5, AD-14).

## Acceptance Criteria

- [ ] `apps/ingestion/services/` provides these commands: `register_source`, `update_source`, `pause_source`, `resume_source`, `record_tos_review` and `register_venue`. Each one:
  - validates its input
  - runs in `transaction.atomic(using=CATALOG)`
  - writes an `IngestionAuditEntry` with the actor id
- [ ] FR-17 hierarchy guard: registering or switching a source to `crawl` without an approved ToS review raises a domain error, and so does ingesting one. Changing to a higher-priority method is always allowed.
- [ ] Per-method defaults apply when no cadence is given (RSS: 4 hours). The model has no default (`catalog-data-model-design.md` D16).
- [ ] When `update_source` changes `acquisition_method`, it resets `tos_status` to `not_reviewed` in the same transaction, because a ToS review approves a method (design D13). A test asserts that `tos_status` always equals the latest `TosReview` for the current method.
- [ ] Audit actors: admin passes `Actor.user(staff_user_id)`, which carries no label. A username or email never reaches `catalog` (design D17).
- [ ] Django admin, under the editorial placement:
  - list and search sources with method, status, `tz_coverage`, `last_ingested_at` and the stale flag
  - list venues
  - read-only lists of events and state changes
  - `save_model` and delete paths call the commands, never `obj.save()` directly
  - deleting a source is disabled; pause it instead
- [ ] The admin actor (staff user id) is passed by value into the audit row, with no FK (OQ-8).
- [ ] Every source change is auditable: the audit list shows who, what and when.
- [ ] Tests cover:
  - each command's happy path and audit row
  - crawl without ToS refused
  - an admin save going through the command
  - an admin delete being blocked
  - no direct writes: a grep or architecture test confirms admin and API modules don't call `.save()` or `.create()` on ingestion models

## Technical Notes

- **Spine references:** AD-5 (named commands), AD-14 (editorial acts only through `ingestion` commands), AD-16 (`ingestion` owns `SOURCE`, `VENUE`).
- **Spine placement:** the editorial surface is "Django admin". The admin classes may live in `apps/editorial/admin.py` and call `ingestion` services. Decide at plan time under the import contracts.
- **Out of scope:** the 40-source floor launch check (OQ-5), the reliability score (FR-16) and the review queue (FR-57).

## Dependencies

- catalog-data-model
