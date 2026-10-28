---
id: catalog-data-model
title: Catalog Data Model
intent: event-catalog-ingestion
complexity: high
mode: validate
status: completed
depends_on: []
created: 2026-10-28
run_id: run-eventpulse24-010
completed_at: 2026-10-28T08:06:49.432Z
---

# Work Item: Catalog Data Model

## Description

Create the `ingestion`-owned entities in the `catalog` schema that the rest of the intent writes to:

- `Source` and `TosReview`
- `Venue`
- `Event`
- `ExtractedRecord`
- `EventStateChange` (the AD-17 outbox)

Also create the per-app audit table, which the standards say is built "with the first named command". The schema encodes the Event Identity tuple, explicit timezone fields, versioning, and series linkage, so the later pipeline cannot store an event that violates AD-4 or AD-6.

The binding design is `catalog-data-model-design.md`. Its "Departures from the Work Item ACs" table explains each change from this item's first draft.

## Acceptance Criteria

- [ ] All seven models live in `apps/ingestion/models.py`, are routed to the `catalog` alias, extend `UUIDv7Model`, and pass `eventpulse.E001`–`E005`.
- [ ] `Source` has:
  - name and `source_type`, `url`, `city`
  - `acquisition_method`, one of `api | partnership | jsonld | rss | ics | email_ics | crawl`
  - `tos_status`, a cache of `TosReview` (D13)
  - `ingestion_cadence` with no model default; the command applies the per-method default (D16)
  - `freshness_ttl_hours` (default 24), `tz_coverage` (`full | partial | none`), `status` (`active | paused`)
  - the conditional-fetch, error, and freshness fields from D16, including `stale_since`
- [ ] `TosReview` is its own table with retention `TOS_REVIEW_RECORDS`, and `reviewed_by_id` is stored by value.
- [ ] `Venue` has a name, city, country code, a `venue_fingerprint` with a unique constraint, and a **nullable** IANA `tz` (D14).
- [ ] `Event` fields:
  - identity: `source_id`, a non-empty `source_event_id`, `venue_fingerprint`, `title_fingerprint`, and an indexed `canonical_url`
  - time: `start_time_utc` (`timestamptz`), `start_time_local` (normalized ISO wall-clock time, `varchar(19)`, regex check), IANA `start_time_tz`, an optional `end_time_utc`
  - confidence: `tz_inference_confidence` and `extraction_confidence`, both `numeric(3,2)`, NOT NULL, with a check in `[0, 1]`
  - review: `publication_status` (`published | in_review`) and `tz_review_pending` (D6). Rejected candidates never become Events; the rejection is recorded on `ExtractedRecord`.
  - lifecycle: `status` (`scheduled | postponed | cancelled | superseded`) and `is_sold_out`
  - versioning and lineage: `event_version` (≥1, never decreasing), a nullable `series_id`, `superseded_by` (self FK), and a unique `slug`
- [ ] Identity constraints (D2, D3, D22):
  - a unique constraint on `ExtractedRecord(source, source_event_id)`, which enforces rule (a)
  - a partial unique `UniqueConstraint(source, source_event_id, condition=~Q(status="superseded"))` on Event
  - **no** unique constraint on `canonical_url`, only an index
  - `source_event_id` is non-empty on both tables
- [ ] Indexes support lookup by `(venue_fingerprint, start_time_utc)` and the public listing.
- [ ] `ExtractedRecord` is **one row per source item**, upserted (D2). It has:
  - `payload`, which includes the raw as-written time
  - `content_hash`
  - `extraction_confidence` (NOT NULL) and `tz_inference_confidence` (nullable)
  - `resolution` (`resolved | rejected | ambiguous`), with a check tying it to `event_id` and `reject_reason` (D21)
- [ ] `EventStateChange`:
  - `kind` is one of `time_moved | postponed | cancelled | sold_out | detail_changed | superseded`
  - a unique constraint on `(event, event_version)`
  - a nullable `propagated_at` with a partial index on unpropagated rows
  - append-only through the grant, trigger, and model guard layers (D12)
  - `propagated_at` is set only with the conditional `filter(propagated_at__isnull=True).update(...)` form (D23)
- [ ] The Event guard trigger makes `superseded` terminal and rejects any decrease in `event_version` (D7, D10).
- [ ] The supersede order (D7) is proven by a test: the specified order succeeds, and the reverse order fails on the partial unique index.
- [ ] Audit log:
  - an abstract `AuditEntry` in `shared/models.py`
  - `Actor` in `shared/actor.py`
  - a concrete, append-only `IngestionAuditEntry` (`AUDIT_LOG`) with an actor check that keeps personal data out of `actor_label` (D17)
  - `write_audit()` raises outside `atomic(using=CATALOG)`
- [ ] `shared/constants.py` gains `TZ_INFERENCE_CONFIDENCE_AUTO_PUBLISH = Decimal("0.90")` and a pinned `SERIES_ID_NAMESPACE`.
- [ ] Retention categories: `SOURCE_REGISTRY` for Source, Venue, Event, ExtractedRecord, and EventStateChange; `TOS_REVIEW_RECORDS` for TosReview; `AUDIT_LOG` for the audit table.
- [ ] No catalog model has an FK to `User` or `ContentType`, and there is no `GenericForeignKey` (OQ-8).
- [ ] A single forward-only migration `0001_initial`, with the trigger and grant `RunSQL`, applies cleanly to `catalog`. `personal` is untouched.
- [ ] factory_boy factories exist per model, and every temporal field uses an explicit UTC value and an IANA tz.
- [ ] Tests cover everything in the design's Implementation Checklist:
  - constraints, triggers, and grants (as `ep_catalog` via `run_as`)
  - model and QuerySet guards
  - the supersede order
  - `write_audit` with `transaction=True`
  - routing and retention

## Technical Notes

- **Spine references:**
  - AD-3: the schema wall; cross by ID only
  - AD-4: identity tuple, `state_history`, `superseded_by`
  - AD-6: UTC storage, explicit IANA tz, the <0.7 review gate
  - AD-15: retention
  - AD-16: `ingestion` owns all of these
  - AD-17: outbox with `propagated_at = NULL`
- **`state_history`** is the ordered set of `EventStateChange` rows, not a JSON column on Event.
- **`EVENT_FIT` and `REVIEW_ITEM`** are out of scope (follow-up intents).
- **Validate mode:** this item may not be implemented until `catalog-data-model-design.md` is approved.

## Dependencies

(none)
