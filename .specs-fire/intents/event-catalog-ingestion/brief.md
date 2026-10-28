---
id: event-catalog-ingestion
title: Event Catalog & Structured Ingestion
status: completed
created: 2026-10-28
completed_at: 2026-10-28T16:59:11.161Z
---

# Intent: Event Catalog & Structured Ingestion

## Goal

A structured-first ingestion pipeline that fills the `catalog` schema with deduplicated, timezone-correct Events from registered sources. It is the corpus every later feature reads from: the digest, browse, reminders and sharing.

## Users

- The operator/editor, who registers and manages sources in Django admin and watches events land.
- Indirectly, every later feature intent, which reads the catalog as its input.

## Problem

The scaffold is in place, but `catalog` is empty, so no user-facing feature can be built or demoed on real data. The ingestion invariants are the easiest to get wrong when bolted on later:

- structural Event Identity, never cosine (AD-4)
- `ingestion` as the sole catalog writer (AD-16)
- an explicit timezone or a reject (FR-60, AD-6)
- source content treated as untrusted (AD-9)
- append-only state history with an outbox (AD-17)

## Success Criteria

- **Source Registry (FR-13):** sources are managed in Django admin. Every write goes through a named `ingestion` command with an audit row (AD-5, AD-14). A `crawl` source without an approved ToS review is refused, and the acquisition-hierarchy guard holds (FR-17).
- **Structured acquisition:** JSON-LD pages, RSS feeds and ICS-by-URL ingest with no LLM call (FR-14 structured path, FR-56). Fetching goes through a port with a fake adapter, and all source content is treated as untrusted (AD-9).
- **Scheduling:** sources ingest on their declared cadence (RSS defaults to 4h). Due sources are picked up from the existing single 60s beat tick, and the work runs as Celery pipeline jobs, never inside a request (AD-7, AD-11).
- **Dedup (FR-15):** Event Identity is computed in pure `domain/dedup.py` and applies the three structural match rules. Re-ingesting the same feed is idempotent. Recurring instances stay distinct `event_id`s sharing a `series_id`.
- **Timezone (FR-60, AD-6):** Events are stored as UTC `timestamptz` with an IANA `start_time_tz` and a `tz_inference_confidence`. Tiers resolve as follows:
  - `full`: the offset comes from the source.
  - `partial`: the timezone is resolved through a venue registry. 0.90 and above publishes. 0.70–0.89 publishes but is flagged for review, with a "venue time approximated" note. Below 0.70 is held `in_review` and is not digest-eligible until editorial review (AD-6, FR-60 consequence 3).
  - `none` (no resolvable tz): auto-rejected. It never becomes an Event.

  Each Source carries a `tz_coverage` value.
- **Lifecycle:** re-ingesting a changed event bumps `event_version` and appends an `EVENT_STATE_CHANGE` with `propagated_at = NULL` in the same catalog transaction. A postponement beyond ±30 days creates a new Event, and the old one receives a terminal `superseded_by` change. Nothing writes to `personal`.
- **Freshness:** a source with no ingestion within 2× its expected cadence is flagged.
- **Read API:** a public, session-free read-only catalog endpoint exists (AD-12) and is exposed through the generated TS client (AD-19).
- **Proof:** recorded fixtures for each acquisition method (JSON-LD, RSS, ICS) drive the tests. Two or three real, ToS-safe public feeds are registered and ingest successfully on the local stack. CI stays green, coverage gates included.

## Constraints

- Builds on the `project-scaffold` intent:
  - `apps/ingestion` is the sole writer of `catalog` entities (AD-16).
  - Pure logic lives in `backend/domain/` (stdlib only).
  - Fetching happens behind `ports/` and `adapters/`.
  - The `import-linter` contracts must keep passing.
- `beat_schedule` stays exactly one 60s tick, which `backend/tests/worker/test_tick.py` enforces. Source scheduling hangs off that tick and adds no beat entries.
- Every new model declares a retention category (AD-15).
- No `catalog` model may FK to `User` or `ContentType` (OQ-8). Audit rows store the actor by id, in a catalog-side audit table.
- The confidence thresholds live in one shared module (AD-8).
- No LLM is called anywhere in this intent, and fake adapters stay the local default.
- Binding sources:
  - `_bmad-output/planning-artifacts/architecture/architecture-EventPulse24-2026-09-04/ARCHITECTURE-SPINE.md`
  - `_bmad-output/planning-artifacts/prds/prd-EventPulse24-2026-08-19/prd.md` §4.4
  - `.specs-fire/standards/`

## Notes

**Out of scope:**
- LLM/HTML extraction (the FR-14 LLM path), embeddings, the Source Reliability Score (FR-16) and the editorial review queue (FR-57). These are follow-up intents.
- The inbound email-ICS mailbox adapter. The ICS parser is built so that the mailbox path can reuse it later.
- Official-API and partnership source adapters.
- Propagation of state changes into `personal` (the FR-53–55 / AD-17 consumer side). There are no saved events yet.
- Any frontend page. Browse and city pages are their own intent.

**Still open:**
- **PRD amendment needed:** the FR-60 tier table (`prd.md:556`) says partial-tier "<0.7 → auto-reject", but FR-60 consequence 3 (`prd.md:576`) and AD-6 say "not eligible until editorial review". This intent follows AD-6 (`catalog-data-model-design.md` D6), so the table should be amended to match.
- The 40-source / 15-per-city launch floor (FR-13).
- OQ-5: the real source list and ToS reviews.
- The beachhead city.
- **Automatic re-gating vs editorial decisions** (run-eventpulse24-015, plan P1): every ingest from an Event's origin source recomputes `publication_status`, `tz_review_pending` and the confidences from the new data. When the editorial review queue (FR-57) lands, an editorial publish or hold must override that, for example with an editorial-lock flag the pipeline respects.
- **Venue renames** (run-eventpulse24-014, plan R7): a venue's name, city and country are fixed once it is registered, because they make its identity fingerprint. Only `tz` can be set later (`set_venue_timezone`). The editorial intent decides how a rename works: whether the fingerprint changes and what happens to Events already copied from it (D14).

**Work happens on branch `event-catalog-ingestion`.**
