---
work_item: ingest-pipeline-and-lifecycle
intent: event-catalog-ingestion
created: 2026-10-28
mode: validate
checkpoint_1: approved
revision: 1 (approved as drafted)
---

# Design: Ingest Pipeline & Event Lifecycle

## Summary

`ingest_source(source_id)` is the one command that turns a registered Source into catalog rows. A run has four steps:

1. Take a **run lock** for the source and re-check the FR-17 guard on a fresh, locked read.
2. Fetch through `SourceFetchPort`, using conditional headers.
3. Parse with the method's parser.
4. Process each candidate in **its own transaction**, under the identity advisory locks: resolve the timezone, resolve identity, then create, update, supersede or reject.

Lifecycle changes bump `event_version` and append one `EventStateChange` per kind. They go in the same transaction as the Event write, with an `on_commit` enqueue of a placeholder propagation job. Each run ends with one audit row of counts. Nothing touches `personal`.

All the decisions are made by the existing pure modules: `domain.timezones.resolve_tz`, `domain.dedup.resolve` and `identity_lock_keys`, `domain.lifecycle.classify_change`, and `domain.confidence`. This item is the orchestration and the writes. The resolve-and-write stage takes a `ParsedCandidate`, so the later LLM/HTML path can feed it unchanged.

This design departs from the work item twice: it moves the reconciler's **tick wiring** to `ingestion-scheduling` (D15), and it makes title, description and URL changes silent (D9). Both are listed under [Departures](#departures-from-the-work-item-acs).

## Scope

**In scope:**
- `apps/ingestion/services/ingest_source.py`: the run, plus the `IngestReport` it returns
- `ingest_item.py`: one candidate, from resolution to write
- `event_writes.py`: create, update with state changes, and supersede (D7 order)
- `outbox.py`: the enqueue seam, `mark_propagated` (D23 form) and `reconcile_outbox`
- `slugs.py`
- Migration `ingestion/0002`:
  - `Event.original_start_utc`
  - the `reinstated` kind
  - `ExtractedRecord.match_notes`
  - `Source.fetched_url`
  - `guard_event_write` extended so `original_start_utc` can't change
- `worker/tasks.py`: `propagate_state_change` (a no-op consumer) and `reconcile_outbox`, both tasks that only call the command
- Constants: `EXTRACTION_CONFIDENCE_STRUCTURED`, `OUTBOX_RECONCILE_AFTER`, `OUTBOX_RECONCILE_BATCH`
- Log allowlist: the run-count fields
- Tests driven by the recorded fixtures and a scripted fetch port

**Out of scope:**
- Choosing due sources, the claim/lock against double *enqueue*, the `ingest_source` Celery task and management command, stale flagging, and wiring the tick: all `ingestion-scheduling`
- The real propagation consumer (FR-53–55)
- The editorial review queue and editorial kinds
- Cross-source "best facts" merging
- Detecting items that disappear from a feed (D12)

## Key Decisions

### Run shape and concurrency

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D1. Transaction granularity** | **One transaction per candidate.** The run's opening and closing source-state writes get their own short transactions. Nothing is held open across the network fetch. | `identity_lock_keys` is specified for one transaction per item, so its sorted-key locking is deadlock-free only that way. One bad item rolls back alone, which meets the "savepoint per item" AC more simply than a savepoint inside a long per-source transaction. A per-source transaction would also hold row locks for the whole fetch and parse. |
| **D2. Two runs of one source** | A **session-level** `pg_try_advisory_lock(source_run_key(source_id))` held for the whole run and released in `finally`. If another run holds it, the command returns `IngestReport(outcome="already_running")` and writes nothing. The key is blake2b with its own `person`, so it can't collide with identity keys. | A row lock or transaction would span the fetch (D1). A session lock is released by Postgres if the worker dies, because the connection closes. Preventing double *enqueue* stays with `ingestion-scheduling`; this is the backstop for "two workers never ingest one source at once". |
| **D3. FR-13/FR-17 guard** | After taking the run lock, a short `atomic`: `select_for_update()` the Source, call `ensure_can_ingest(source)`, set `last_attempted_at`, and commit. A refusal raises `SourcePausedError` or `CrawlNeedsTosReviewError` to the caller and writes no audit row. | This meets the handed-on AC: the check runs on a locked, fresh read, never a stale copy. A pause committed *after* this point applies from the next run, and a run already fetching finishes. |
| **D4. Cross-source identity races** | Per item: `pg_advisory_xact_lock(k)` for each `k` in `identity_lock_keys(candidate)`, in order, then match-then-write in the same transaction. | Two sources ingesting the same happening at once serialize on the rule (b)/(c) keys, so neither inserts a duplicate between the other's match and write. |

### Per-item resolution

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D5. Venue lookup** | The pipeline **never creates Venues**; the registry is curated (run-014). Lookup: `venue_fingerprint(name, city or source.city, country)`, matched exactly. When the candidate has no country, the fingerprint is computed for each distinct `country_code` in the registry, and a **single** match is used (two or more: none). On a match, `Event.venue` is set and the venue's fingerprint and `tz` are used. Otherwise `venue` is NULL and the candidate's own fingerprint is kept for rule (b). | Feeds are untrusted (AD-9). Auto-created venues would pollute the tz source of the `partial` tier. Many feeds omit the country, and the registry has few countries, so the fallback is cheap and only unambiguous matches count. |
| **D6. Timezone outcome** | `resolve_tz(c.start, source_zone=c.start_zone, venue_tz=venue.tz, end=c.end)`.<br>• A `TzRejection` gives `ExtractedRecord(resolution=rejected, reject_reason=<RejectReason>)` and no Event.<br>• Otherwise, publication is `combine_gates(tz_gate(conf), extraction_gate(EXTRACTION_CONFIDENCE_STRUCTURED))`: `PUBLISH` → published; `PUBLISH_FLAGGED` → published with `tz_review_pending`; `IN_REVIEW` → `in_review`.<br>• Structured extraction is `Decimal("1.00")`, a new constant. | These are the FR-60 tiers exactly as `domain.confidence` defines them (design D6). The gates are never re-implemented inline (coding standards). |
| **D7. When `content_hash` says unchanged** | `content_hash = sha256` of canonical JSON (sorted keys) of the normalized payload **plus the resolution inputs** (`venue_tz` and the matched venue ID). If the hash is unchanged and the record is `resolved` or `rejected`, the item is **unchanged**. Its `last_seen_at` is updated in one bulk statement at the end of the run, with no locks and no Event write. An `ambiguous` record is always re-resolved. | This makes "re-ingest is a no-op" cheap and exact. Hashing the venue tz means a tz an editor adds later (`set_venue_timezone`) causes re-resolution on the next run, so a rejected `none`-tier item can recover. Ambiguity depends on the *other* live Events, so it can't be cached. |
| **D8. Identity and fact ownership** | `resolve(candidate, bound_event_id, live)`:<br>• **Live set:** non-superseded Events matching `(venue_fingerprint, start_time_utc)` or `(canonical_url, start_time_utc)`, with `bound_source_ids` taken from their ExtractedRecords.<br>• **A bound record pointing at a superseded Event** follows `superseded_by` to the live end of the chain and rebinds there.<br>• **Who updates facts:** only the Event's **origin source** (`Event.source`). An item bound by rule (b) or (c) from another source is recorded and bound but never changes the Event.<br>• **`Ambiguous`:** the record is unbound, with the IDs in `match_notes`.<br>• **`Matched.review_signals`:** go to `match_notes`. | Without a single owner, two sources that disagree on a title would flip the Event on every run, and each flip would be a state change. Owner-wins is the simplest stable rule; cross-source "best facts" belong to a later intent. Following the chain keeps a secondary item attached to the happening it described. `match_notes` is where the future review queue gets its signals without re-deriving them. |
| **D9. Lifecycle vs silent changes** | `classify_change(stored, incoming, original_start_utc)`.<br>• **`change.is_lifecycle`** (start, end, tz, status, sold out, or venue changed): apply the facts and append **one `EventStateChange` per kind** in `change.kinds`. The first UPDATE writes all the facts at `version + 1`; each further kind is a bump-only UPDATE (`version + 1`). The trigger allows "stay or +1" per UPDATE.<br>• **Otherwise**, if only the title, description or canonical URL changed: a **silent update** of those fields and `title_fingerprint`, with no version bump and no state change. The slug never changes (design D15). | The trigger permits +1 per statement (design D10, amended at checkpoint 2), so k kinds take k statements; there are at most 4 in practice, all in one transaction. A state change is something a saved event's owner must hear about (AD-17). A typo fix in a title isn't, and live reads show the new title anyway. *(Departure 1.)* |
| **D10. Supersede** | When `ChangeKind.SUPERSEDED` is in the kinds, the design D7 order runs in the item's transaction:<br>1. mint the ID<br>2. one UPDATE to `superseded`, setting `superseded_by` and `version + 1`<br>3. INSERT the new Event (version 1, `original_start_utc` = its own start, same `series_id`, new slug)<br>4. repoint the ExtractedRecord<br>5. append the `superseded` state change on the old Event<br><br>The other kinds in the same change are **not** recorded on the old Event, which is now terminal. The new Event starts clean. | D7 is fixed by the data model, and the partial unique index makes the order necessary. Recording `sold_out` on a superseded row would be meaningless. |
| **D11. `original_start_utc`** | A new **`Event.original_start_utc`** column (NOT NULL), set on insert and never changed. `guard_event_write` now requires `original_start_utc = start_time_utc` on INSERT and rejects any change to it on UPDATE. Migration 0002 adds it as nullable, backfills it from `start_time_utc`, then sets it NOT NULL. | The handed-on AC requires the original start, never the current one. A column is one indexed read. Deriving it from `state_history` would mean scanning a growing log on every update, and it would break for Events with no history. |
| **D12. Reverse transitions and missing items** | **Reverse transitions:** `cancelled → scheduled` and `postponed → scheduled` (same start) are allowed, recorded as the new stored kind **`reinstated`** (the `Kind` choice is added, and `NOT_YET_STORED` becomes empty). The source is the authority on its own events.<br>**Missing items:** an item missing from a feed changes **nothing**; its `ExtractedRecord.last_seen_at` simply stops advancing. | A refused un-cancel would leave the catalog wrong while the venue says the event is on. Feeds drop past and paginated-out items all the time, so inferring a cancellation from absence would invent cancellations (the work item says "never infer a cancellation silently"). A later job can act on `last_seen_at`. |
| **D13. Rejections and failures on an existing binding** | A previously **resolved** item that now fails timezone resolution keeps its binding and its Event untouched, counted as `rejected_update:<reason>`. The `resolved` row can't carry a `reject_reason` (D21 check). A previously **rejected** item that now resolves is created normally. Any other exception in an item rolls back that item only, and is counted as `failed:<ExceptionType>`. | Dropping or freezing a live Event because one fetch lost its zone would be worse than keeping the last good facts. Failure isolation is an AC. |

### Writes, outbox, fetch state

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D14. Enqueueing from `ingestion`** | `apps/ingestion/services/outbox.py::enqueue_propagation(state_change_id)` is called through `transaction.on_commit(..., using=CATALOG)`, and calls `celery.current_app.send_task("worker.tasks.propagate_state_change", args=[str(id)])`. Tests replace that one function with an autouse recorder fixture. **Alternative:** a `JobQueuePort` plus adapters, which would be more ceremony for one call site. | `apps` can't import `worker` or `config` (layers), so a task is reached by name. `config/__init__` already loads the Celery app "so the API runtime can enqueue jobs". One function is one seam to fake. A port can replace it if a second caller appears. |
| **D15. Placeholder consumer and reconciler** | `worker.tasks.propagate_state_change(id)` is a **no-op** that logs `DEBUG` and **leaves `propagated_at` NULL**: setting it would claim a propagation that never happened, and the real consumer would then skip the row. `reconcile_outbox(limit=OUTBOX_RECONCILE_BATCH)` re-enqueues the oldest rows unpropagated for longer than `OUTBOX_RECONCILE_AFTER` (5 minutes). It ships as a command plus a `worker.tasks.reconcile_outbox` task. **Wiring it into the tick moves to `ingestion-scheduling`.** `mark_propagated(id)` is the D23 conditional update, for the real consumer to use. | The tick wiring breaks the scaffold test that `ingestion-scheduling` must keep unchanged: `tests/worker/test_tick.py` calls `tick()` with no database access and asserts exactly one `worker.tasks` log record. That item restructures the tick anyway, for due sources. The batch cap keeps re-enqueueing bounded while no consumer exists. *(Departure 2.)* |
| **D16. Fetch outcomes → source state** | Written in the run's closing transaction:<br>• **Success (200):** `last_ingested_at`, `consecutive_failures = 0`, `last_error_code = ""`, `etag` and `last_modified` from the response, `fetched_url = final_url`, `stale_since = NULL`.<br>• **304:** the same, with no parse.<br>• **`FetchError`:** `consecutive_failures + 1`, `last_error_code = error.code`. **`fetch_blocked` with `reason = cross_host_redirect`** stores `source_moved`, so the source is flagged for re-registration, which resets the ToS review through `update_source` (run-014 R4). It is never followed.<br>• **`ParseResult.error`:** a failure with `parse_<error>`, and `last_ingested_at` unchanged.<br>The parse base URL is `final_url`. | These are the handed-on ACs. Clearing `stale_since` on success meets scheduling's "clears on the next success" from the side that knows of the success. Scheduling only sets it. |
| **D17. Audit and logs** | **One audit row per run:** `write_audit(actor, "ingest_source", "source", id, details={outcome, error_code?, counts})` in the closing transaction. Counts:<br>• `new`, `updated`, `silent_updated`, `superseded`, `unchanged`<br>• `bound_other_source`, `ambiguous`, `in_review`, `tz_review_pending`<br>• `rejected:{reason}`, `rejected_update:{reason}`, `failed:{type}`<br>• `skipped:{parser reason}`<br><br>There is no per-Event audit row: the Event's `created_at` and origin plus its `EventStateChange` rows (which carry the actor) are its history. **Log:** `INFO "Ingest finished"` with `source_id` and integer count fields, which are added to `ALLOWED_FIELDS` as `new_count`, `updated_count`, `unchanged_count`, `rejected_count`, `ambiguous_count` and `failed_count`. | AD-5 and the "audit entry with counts" AC. A row per Event would put thousands of rows a day in the audit log and duplicate `state_history`. Counts only, never content (AD-13). |
| **D18. Slugs** | `slugify(title)[:80]`, or `event` if that's empty (non-Latin titles), then `-YYYY-MM-DD` (venue-local date, from `start_time_local`), then `-` and the last 6 hex characters of the Event's UUIDv7. A collision (unique `event_slug_uq`, under a savepoint) is retried once with 12 hex characters, then raises. | The random tail of a UUIDv7 makes a collision practically impossible, and the retry covers the rest without a loop. ASCII slugs keep public URLs plain (AD-12). |
| **D19. Long canonical URLs** | `Event.canonical_url` stores `domain.dedup.canonical_url(c.canonical_url)` (the normalized form that rule (c) looks up through `event_canonical_url_idx`). If the normalized form is over 2,048 characters it is stored as `""`, so rule (c) is off for that item. The as-written link stays in the payload. | That bounds the btree key well under the ~2.7 KB row limit: `canonical_url` emits ASCII (escapes percent-encoded, IDNA hosts). Storing the normalized form means the index serves rule (c) directly. The trade-off, accepted: the public link is the https/no-`www.` form. |

## Departures from the Work Item ACs

| # | AC | Design | Why |
|---|---|---|---|
| 1 | "Kinds: time moved, cancelled, sold out, venue or detail" (every fact change appends a state change) | A title, description or URL change on its own is a **silent update**, with no version bump. When a lifecycle change happens, `detail_changed` is still recorded alongside it. | A state change notifies saved-event owners (AD-17), and a typo fix shouldn't. Reads are live, so the new text shows anyway. (D9) |
| 2 | "The 5-minute reconciler ... wired to the tick" | The reconciler command and task ship here. **Wiring it into the tick** is added to `ingestion-scheduling`'s ACs. | `test_tick.py` (no database, exactly one log record) must stay unchanged there, and that item restructures the tick. (D15) |

## Data Model Changes (migration `ingestion/0002`, forward-only)

- **`Event.original_start_utc`** `timestamptz NOT NULL`: added nullable, backfilled `= start_time_utc`, then set NOT NULL. `catalog.guard_event_write()` is `CREATE OR REPLACE`d. On INSERT it requires `NEW.original_start_utc = NEW.start_time_utc`. On UPDATE it rejects `NEW.original_start_utc IS DISTINCT FROM OLD.original_start_utc`. Every other rule stays the same, and the existing trigger-parity test is extended.
- **`EventStateChange.Kind`** gains `reinstated`. This is state-only (`AlterField` choices); there is no DB check on `kind`.
- **`ExtractedRecord.match_notes`** `jsonb NOT NULL DEFAULT '{}'`: `{"rule": "a|b|c", "review_signals": [...], "ambiguous": [...]}`.
- **`Source.fetched_url`** `varchar(2048)`, blank allowed: the last `final_url`.
- **`shared/constants.py`:** `EXTRACTION_CONFIDENCE_STRUCTURED = Decimal("1.00")`, `OUTBOX_RECONCILE_AFTER = timedelta(minutes=5)`, `OUTBOX_RECONCILE_BATCH = 500`.

## Technical Approach

```
ingest_source(source_id, *, actor=Actor.system("ingest_pipeline"), fetch_port=None) -> IngestReport
 │ session advisory lock (D2) ── held? → IngestReport("already_running")
 │ atomic: select_for_update Source → ensure_can_ingest → last_attempted_at          (D3)
 │ fetch_port.fetch(url, etag, last_modified, source_id) ── FetchError → close(failure)
 │   304 → close(success, not_modified)
 │ parse(method, body, SourceContext(source.id, final_url)) ── error → close(parse failure)
 │ for candidate in result.candidates:                                     one atomic each (D1)
 │   payload + content_hash (D7) ── unchanged? → mark for bulk last_seen_at
 │   venue lookup (D5) → resolve_tz (D6) ── TzRejection → record rejected / rejected_update (D13)
 │   pg_advisory_xact_lock(identity_lock_keys)                                             (D4)
 │   live set + bound_event_id → dedup.resolve (D8)
 │     New        → create Event (slug D18, original_start_utc) + record resolved
 │     Matched    → origin source? classify_change → lifecycle (D9) | supersede (D10) | silent
 │                  else bind only (bound_other_source)
 │     Ambiguous  → record ambiguous + match_notes
 │   each EventStateChange → on_commit(enqueue_propagation)                               (D14)
 │ atomic: bulk last_seen_at; source success state (D16); write_audit(counts) (D17)
 └ release session lock (finally) · log "Ingest finished"
```

`IngestReport(outcome: "ok" | "not_modified" | "fetch_failed" | "parse_failed" | "already_running", error_code: str, counts: Counter)` is returned to callers and tests. Celery tasks still return `None`.

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Kinds applied in the wrong order or with the wrong version breaks the trigger mid-item | High | The item rolls back alone (D1). Tests cover one item that changes status, time and sold-out at once, and assert versions v+1..v+k in `PRECEDENCE` order. |
| A deadlock between two sources' items | Medium | Keys are taken in the sorted order from `identity_lock_keys`, with one item per transaction. A concurrency test runs two threads with `transaction=True` against one happening and asserts a single Event. |
| The session advisory lock leaks if `finally` doesn't run | Medium | Postgres releases it when the connection closes (worker death). A test asserts the lock is released after a forced exception mid-run. |
| The owner-wins rule hides a real cancellation that only a secondary source reports | Medium | It's recorded in `match_notes` and the counts. Cross-source authority is named as a later intent. A test pins the behavior so a later change is deliberate. |
| The country fallback matches the wrong venue | Low | Only a *single* match across countries counts, and a test covers two same-named venues in different countries. |
| The reconciler re-enqueues the same rows every 5 minutes while no consumer exists | Low | The batch cap is 500, and the job is a no-op. Scheduling wires it, and the consumer intent replaces the no-op. |
| A normalized https link that the site doesn't serve | Low | The as-written URL stays in the payload. It is accepted and named (D19). |
| Migration 0002 backfill on a large table | Low | There is no production data yet. Add, backfill, then set NOT NULL, forward-only. |

## Test Plan (fixture-driven; scripted fetch port for sequences)

Two fetch sources drive the tests:
- `FakeFetchAdapter` with the recorded fixtures (JSON-LD, RSS, Atom, ICS), for first-ingest and error paths through `simulate`
- a `ScriptedFetchPort` (tests only), which serves a different body on each call, for lifecycle sequences

The tests:
- **First ingest:** creates the expected Events for every method, with tz fields, publication status and slugs. All-day and overnight ICS events arrive normalized; this is asserted here.
- **Idempotency:** re-ingesting the same fixture gives no new Event, no version bump and no state change. Only `last_seen_at` moves.
- **Lifecycle:**
  - cancelled → v+1 and one `cancelled` change
  - a move within 30 days keeps the ID (`time_moved`)
  - a move beyond 30 days supersedes in the D7 order, with both Events and the repointed record asserted
  - several moves under 30 days each but more than 30 days in total are measured from `original_start_utc` and supersede
  - un-cancel → `reinstated`
  - a status, time and sold-out change together gives k rows in order
  - a title-only change is silent
- **Timezone gates:** none → rejected with its reason; 0.65 → `in_review`; 0.80 → published with `tz_review_pending`; exactly 0.90 → published unflagged; `set_venue_timezone` later lets a `none` item resolve on the next run (D7).
- **Identity:**
  - rule (b) across two sources: the second binds, and doesn't update (owner-wins)
  - rule (c) by canonical URL
  - recurring instances get distinct IDs sharing `series_id`
  - an ambiguous match leaves the record unbound with `match_notes`
  - a secondary item bound to a superseded Event rebinds to the live one
- **Outbox:**
  - Forcing an error after the Event write rolls back both the Event and the state change (`transaction=True`).
  - `on_commit` enqueues once per state change.
  - `reconcile_outbox` respects the 5-minute age and the batch cap.
  - `mark_propagated` is idempotent.
  - No `personal` table is written.
- **Fetch and parse outcomes:**
  - each `simulate` error maps onto `last_error_code` and `consecutive_failures`
  - a 304 → `not_modified` with `last_ingested_at` updated
  - a cross-host redirect → `source_moved`
  - a parse error → `parse_<error>`
  - `final_url` is stored and used as the base URL
- **Guards and concurrency:**
  - a paused source and a crawl source without ToS are refused before the fetch
  - a second run while one is in progress gets `already_running`
  - two sources racing on one happening give one Event
  - the session lock is released after an exception
- **Audit and logs:** one audit row per run with exact counts. The JSON log line contains counts and IDs only, with no title text.
- **Parity:** `NOT_YET_STORED` is empty, and the trigger rejects a change to `original_start_utc`.

## Integration Points

| System | Type | Purpose |
|--------|------|---------|
| `source_registry.ensure_can_ingest` | Guard | FR-13/FR-17, on the locked row (D3) |
| `domain.timezones` / `dedup` / `lifecycle` / `confidence` | Pure decisions | Every timezone, identity, change and gate decision |
| `ports.fetch` via `ports.registry.get_fetch_port()` | Port | Fetching; tests inject `fetch_port` |
| `apps.ingestion.parsers.parse` | Pure | Candidates |
| `ingestion-scheduling` | Consumer | Calls `ingest_source` from its task and management command; wires `reconcile_outbox` into the tick; sets `stale_since` |
| `public-catalog-read-api` | Reader | Lists `published`, non-superseded Events |
| The future propagation consumer | Consumer | Replaces the no-op task and calls `mark_propagated` |

## Implementation Checklist

- [ ] Migration 0002: the four columns and choices, plus `CREATE OR REPLACE` of `guard_event_write`. Update the models, factories (`original_start_utc`) and `NOT_YET_STORED`.
- [ ] The constants and the log-allowlist count fields
- [ ] `slugs.py` and `outbox.py` (enqueue seam, `mark_propagated`, `reconcile_outbox`)
- [ ] `event_writes.py`: create, lifecycle update (k statements), supersede (D7), silent update
- [ ] `ingest_item.py`: payload and hash, venue lookup, `resolve_tz`, locks, live set, resolve, dispatch, record upsert
- [ ] `ingest_source.py`: run lock, guard, fetch, parse, item loop, close-out, audit, log, `IngestReport`
- [ ] `worker/tasks.py`: `propagate_state_change` (no-op) and `reconcile_outbox`
- [ ] Tests per the test plan, plus a `ScriptedFetchPort` and any new fixtures (in `index.json`)
- [ ] `ingestion-scheduling.md`: add the reconciler tick wiring and the note that `stale_since` is cleared by the pipeline
- [ ] `coding-standards.md`: the pipeline rules (one transaction per item, owner-wins, silent detail updates, `original_start_utc`, enqueue by task name)
- [ ] Gates: lint, check, makemigrations, coverage

---
*Generated by specs.md - fabriqa.ai FIRE Flow | Checkpoint 1 approved: 2026-10-28T12:00:04Z*
