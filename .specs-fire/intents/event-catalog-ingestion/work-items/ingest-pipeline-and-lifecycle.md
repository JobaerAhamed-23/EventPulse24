---
id: ingest-pipeline-and-lifecycle
title: Ingest Pipeline & Event Lifecycle
intent: event-catalog-ingestion
complexity: high
mode: validate
status: pending
depends_on: [catalog-data-model, event-identity-and-tz-domain, source-fetch-port, structured-parsers, source-registry-commands-admin]
created: 2026-10-28
---

# Work Item: Ingest Pipeline & Event Lifecycle

## Description

The core `ingest_source` command. It fetches a source, parses it, resolves timezone and identity, and writes the result into `catalog` idempotently. It also detects lifecycle changes, bumps `event_version` and appends the `EventStateChange` outbox row in the same transaction. This is where AD-4, AD-6, AD-9 and AD-17 meet, and `ingestion` stays the sole writer of `catalog`.

## Acceptance Criteria

- [ ] `ingest_source(source_id)` is a named command:
  1. It refuses paused sources and crawl sources without approved ToS.
  2. It fetches through `SourceFetchPort`, passing the etag and last-modified values. A 304 is a cheap no-op that still updates `last_ingested_at`.
  3. It parses with the method's parser.
  4. For each candidate, it resolves the timezone tier, then resolves identity, then creates or updates the `Event` and records an `ExtractedRecord`.
- [ ] Timezone outcomes (FR-60):
  - `none` (no resolvable tz): rejected. It is recorded on `ExtractedRecord` with a reason and never becomes an Event.
  - Below 0.70 with a resolved tz: the Event is created `in_review`. It is not digest-eligible and not publicly listed (AD-6).
  - 0.70–0.89: published and digest-eligible, with `tz_review_pending` set for the "venue time approximated" note and the later editorial queue (FR-60 consequence 2).
  - 0.90 or above: published, no flag.
- [ ] Identity: the three structural rules decide whether a candidate is new or existing. No cosine is used (AD-4). Ambiguous matches against more than one candidate are recorded as unresolved, and nothing is auto-merged.
- [ ] Idempotency: ingesting the same fixture twice produces no new Events, no version bump and no state change. An unchanged item is detected by `content_hash`.
- [ ] Lifecycle: when a stored Event's normalized facts change, `event_version` is incremented and one `EventStateChange` is appended with `propagated_at = NULL`, in the **same** `atomic(using=CATALOG)` block as the Event update. Kinds: time moved, cancelled, sold out, venue or detail.
- [ ] A start-time move beyond ±30 days creates a new Event, in exactly the `catalog-data-model-design.md` D7 order inside one transaction:
  1. Mint the new ID.
  2. Mark the old Event `superseded`, setting `superseded_by` and `event_version + 1` in one UPDATE.
  3. Insert the new Event.
  4. Repoint `ExtractedRecord`.
  5. Append the `superseded` state change.

  A superseded Event is terminal. History is never rewritten.
- [ ] `propagated_at` is only ever set with the conditional `filter(propagated_at__isnull=True).update(...)` form (design D23).
- [ ] A `transaction.on_commit` hook enqueues a placeholder propagation job for each state change (no-op consumer). The 5-minute reconciler that re-finds unpropagated rows is wired to the tick and also has no consumer yet. Nothing is written to `personal`, and the test asserts this.
- [ ] Failure isolation: one bad item doesn't abort the source. Fetch failures update the source's error state.
- [ ] Each run writes an audit entry with counts: new, updated, unchanged, rejected (by reason), ambiguous, tz-review-pending.
- [ ] Logs are structured with counts and ids only, never source content (AD-13).
- [ ] Tests (fixture-driven, fake fetch adapter):
  - first ingest creates events
  - re-ingest is a no-op
  - a cancelled update produces a version bump and one state change
  - a move within 30 days keeps the same id
  - a move beyond 30 days supersedes
  - a recurring series gives distinct ids sharing `series_id`
  - a tz-none event is rejected, a 0.65 confidence event is `in_review`, a 0.80 confidence event is published with `tz_review_pending`, and exactly 0.90 is published unflagged
  - rule-2 dedup across two sources, and rule-3 dedup by canonical URL
  - the outbox row is in the same transaction: an error forced after the Event write rolls back both

- [ ] **Original start for the ±30-day rule:** `domain.lifecycle.classify_change` takes `original_start_utc`. Supply it from a new `Event.original_start_utc` column (decided in the design doc), or derive it from `state_history`. Never use the current start. This was handed on from run-eventpulse24-011.
- [ ] **Advisory locks:** call `domain.dedup.identity_lock_keys(candidate)` and `pg_advisory_xact_lock` each key in order, with **one transaction per item**. If items are ever batched in one transaction, lock the union of their keys in global sorted order first.
- [ ] **Rule (a) comes from the `ExtractedRecord` binding:** pass the bound `event_id` to `domain.dedup.resolve()`. Pass in live Events with their `bound_source_ids`, superseded ones excluded. Record `Matched.review_signals` and `Ambiguous` for the later review queue; never merge them.
- [ ] **One state change per kind:** append one `EventStateChange` for each kind in `Change.kinds`, in order, each bumping `event_version` by 1. Decide how to store `ChangeKind.REINSTATED` (a new model choice or a refusal). `tests/ingestion/test_domain_parity.py` fails until `NOT_YET_STORED` is updated to match.
- [ ] **Publication** comes from `domain.confidence.combine_gates(tz_gate(...), extraction_gate(...))`, where the strictest wins. `PUBLISH_FLAGGED` sets `tz_review_pending`.

- [ ] **Fetch outcomes** (handed on from run-eventpulse24-012):
  - Store `FetchResult.final_url`.
  - Map each `FetchError.code` onto the source's `last_error_code` and `consecutive_failures`, and record a success as `last_ingested_at`. A 304 counts as a success with no change.
  - Treat `fetch_blocked` with reason `cross_host_redirect` as "the source moved": flag it for re-registration, which re-triggers the FR-17 ToS review. Never follow it automatically.
  - Test every error path with the fake adapter's `simulate` entries.

## Technical Notes

- **Spine references:**
  - AD-4: sole writer, identity, `state_history`, supersede
  - AD-5: named command plus audit
  - AD-6: UTC truth
  - AD-9: untrusted input
  - AD-11: never inside a request
  - AD-17: outbox in the same transaction, `on_commit` enqueue, reconciler
- **Design doc first:** this item runs in validate mode, so `ingest-pipeline-and-lifecycle-design.md` must be approved first. It decides:
  - transaction granularity (per item or per source)
  - concurrency (two runs of one source; Postgres advisory lock or row lock on `Source`)
  - which field changes count as lifecycle changes and which count as a silent detail update
  - the handling of ambiguous identity matches before the review queue exists
- **Pipeline shape:** it should leave a clean seam for the later LLM/HTML extraction path: a different producer of candidates feeding the same resolve-and-write stage.
- **Deferred here from the `catalog-data-model` design review.** The design doc must decide each of these:
  - **Reverse transitions:** un-cancel, and a postponed event that gets a date. Which `kind` they record, and whether `cancelled → scheduled` is allowed. Editorial kinds (editorial reject or publish) belong to the editorial intent.
  - **Items that disappear from a feed:** do nothing, mark stale, or treat as cancelled? Never infer a cancellation silently.
  - **A savepoint per item**, so one bad item rolls back alone inside a per-source run.
  - **Slug minting:** collision retry, and a fallback for titles that slugify to an empty string.
  - **Long canonical URLs:** normalization and a length cap, or a hashed lookup column if the btree index row limit (~2.7 KB) can be exceeded.
  - **Advisory lock** on the domain's candidate lock key around match-then-write, for concurrent cross-source ingest.
  - **Overnight end-before-start and all-day ICS events** reach this stage already normalized by `structured-parsers`. Assert that here.

## Dependencies

- catalog-data-model
- event-identity-and-tz-domain
- source-fetch-port
- structured-parsers
- source-registry-commands-admin
