---
work_item: catalog-data-model
intent: event-catalog-ingestion
created: 2026-10-28
mode: validate
checkpoint_1: approved
revision: 2 (design review: 10 must-fix + 9 should-fix applied; deferrals recorded in later items)
---

# Design: Catalog Data Model

## Summary

This item creates the `ingestion`-owned tables in the `catalog` schema that every later item writes through:

- `Source` and `TosReview`
- `Venue`
- `Event`
- `ExtractedRecord`
- `EventStateChange` (the AD-17 outbox)
- `IngestionAuditEntry`

The schema makes the AD-4 and AD-6 invariants structural where a database can hold them. Where it can't, it leaves a single obvious application seam:

- **Identity:** one live Event per source item.
- **Time:** UTC plus an explicit IANA tz, with NOT NULL confidence ranges.
- **Lifecycle:** monotonic `event_version`, append-only `state_history`, terminal `superseded`, and a fixed supersede order.

It also lands the abstract `AuditEntry` base, an `Actor` value object, and `write_audit()`, because `coding-standards.md` says the audit log is built "with the first named command". No commands, parsers, or API are written here. Factories and constraint tests prove the model.

The design departs from six of the work item's original acceptance criteria. Each departure is listed, with its reason, under [Departures from the Work Item ACs](#departures-from-the-work-item-acs), and `catalog-data-model.md` has been updated to match.

## Scope

**In Scope:**
- Seven concrete models in `apps/ingestion/models.py`
- The abstract `AuditEntry` in `shared/models.py` and `Actor` in `shared/actor.py`
- `write_audit()` in `apps/ingestion/services/audit.py`
- Migration `ingestion/0001_initial`: tables, constraints, the append-only and event-guard triggers, and the column-level grants
- New constants in `shared/constants.py`: `TZ_INFERENCE_CONFIDENCE_AUTO_PUBLISH` and `SERIES_ID_NAMESPACE`
- factory_boy factories, plus model, constraint, trigger, and grant tests

**Out of Scope:**
- Source commands and admin (`source-registry-commands-admin`)
- Identity and tz logic (`event-identity-and-tz-domain`)
- The pipeline (`ingest-pipeline-and-lifecycle`), including the supersede *command*. This item fixes only its order (D7).
- Scheduling claim and lock fields (`ingestion-scheduling` adds them)
- Reverse transitions and editorial kinds (un-cancel, editorial reject, editorial publish): `ingest-pipeline-and-lifecycle` and the editorial intent
- Retention purge order across supersede chains under `PROTECT`: the future AD-15 sweep
- `EVENT_FIT`, `REVIEW_ITEM`, reliability score fields, and embeddings (follow-up intents)

## Key Decisions

### Placement and identity

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D1. Home** | All seven tables live in `apps/ingestion/models.py`, with the app routed to `catalog`. `apps/catalog` stays model-less. | AD-16 gives every one of these entities to `ingestion`. `apps/catalog` is the public read surface and reads through `ingestion`'s interface (`system-architecture.md`). |
| **D2. Where rule (a) lives** | `ExtractedRecord` is **one row per `(source, source_event_id)`**, upserted on every ingest, with a unique constraint on `(source_id, source_event_id)`. It binds that source item to its current Event. | An Event has 1..n Sources (Glossary), so "this source item is that Event" belongs to the source item, not to the Event. A row per parse would add the full feed every 4 hours with no reader: change history is `EventStateChange`'s job. *(Departure 2.)* |
| **D3. Event uniqueness** | `UniqueConstraint(fields=["source", "source_event_id"], condition=~Q(status="superseded"), name="event_live_source_item_uq")`. Django creates this as a **partial unique index**, and a conditional unique constraint **cannot be deferrable** (D7 depends on this). `canonical_url` gets an index but **no unique constraint**. | A supersede beyond ±30 days creates a second Event from the *same* source item and usually the same URL. Recurring instances often share one series URL. A plain unique constraint on either would forbid both legal cases. *(Departure 1.)* |
| **D4. Rule (c) vs recurring series** | Carried to `event-identity-and-tz-domain` as an acceptance criterion: rule (c) (same canonical URL) never matches two candidates whose start times differ when either has a `series_id`. | FR-15 rule (c) contradicts "recurring instances are never dedup-merged" for a series that shares one URL. This is the narrowest reading that satisfies both. |
| **D5. Rejected candidates** | A candidate rejected by a gate **never becomes an Event**. The rejection is stored on `ExtractedRecord` (`resolution = rejected` plus a `reject_reason`). | Rejected rows must never take part in identity matching or appear in a read path. The source item is still remembered, so re-ingest stays idempotent and the rejection stays auditable. |
| **D22. Non-empty source item ID** | `source_event_id` is NOT NULL, `CheckConstraint(~Q(source_event_id=""))`, on both Event and ExtractedRecord. | A NULL or empty ID would slip past both unique constraints: NULLs never collide, and an empty string collapses every item into one. Deriving a stable ID for feeds that lack one (an RSS item without a `guid`) is the parser's job (`structured-parsers`). |

### Event state, time, and versioning

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D6. Publication and the timezone gates** | `Event.publication_status ∈ {published, in_review}` plus `Event.tz_review_pending: bool`. **Gates, inclusive at the lower bound:**<br>• `tz_inference_confidence ≥ 0.90`: `published`, not flagged. **Exactly 0.90 auto-publishes.**<br>• `0.70 ≤ c < 0.90`: `published` **and** `tz_review_pending = true`. It stays digest-eligible, with a "venue time approximated" note.<br>• `c < 0.70` with a resolved tz: the Event is created as **`in_review`**. It is not digest-eligible and not publicly listed until editorial review.<br>• tz not resolvable at all (`none` tier): **rejected** (D5). There is no UTC instant to store. | **AD-6 binds:** "<0.7 is not eligible for any Pulse Digest until editorial review completes", which means review, not rejection. **Recorded conflict:** the PRD contradicts itself. The FR-60 tier table says "<0.7 → auto-reject" (`prd.md:556`), while FR-60 consequence 3 says "does not appear … until editorial review completes" (`prd.md:576`). The spine and consequence 3 win, and the tier table needs a PRD amendment (logged in the intent brief). **0.90:** the tier table's "≥0.9 → proceed" is the specific rule, and consequence 2's closed interval "[0.7, 0.9]" is read as descriptive. Constant: `TZ_INFERENCE_CONFIDENCE_AUTO_PUBLISH = Decimal("0.90")`. The `in_review` state is also the AD-8 extraction gate (0.5–0.7) that the LLM intent will use. |
| **D7. Lifecycle status and supersede** | `Event.status ∈ {scheduled, postponed, cancelled, superseded}`, plus a separate `is_sold_out: bool`. Checks: `(status = 'superseded') = (superseded_by_id IS NOT NULL)`, and `superseded_by_id <> id`.<br><br>**`superseded` is terminal:** the event-guard trigger (D12) rejects any UPDATE to a row whose `OLD.status = 'superseded'`.<br><br>**Fixed supersede order**, all inside one `atomic(using=CATALOG)`:<br>1. Mint the new Event's UUIDv7.<br>2. In one UPDATE, mark the old Event `status = superseded`, `superseded_by = <new id>`, `event_version = old + 1`.<br>3. Insert the new Event (`event_version = 1`).<br>4. Repoint `ExtractedRecord.event` to the new Event.<br>5. Append the `EventStateChange(kind = superseded, event = old, event_version = old + 1)`. | Sold out is orthogonal: a postponed event can also be sold out. A move with a known new date stays `scheduled`, because the move is a state change, not a status. `postponed` is schema.org's "date TBD".<br><br>**Order:** the partial unique index (D3) is not deferrable, so the old Event must leave the live set (step 2) before the new one enters it (step 3). Step 2 can name a row that doesn't exist yet because Django creates every FK as `DEFERRABLE INITIALLY DEFERRED` on Postgres. The version bump goes in the same UPDATE as the status change, because after it the row is frozen. |
| **D8. Time fields** | `start_time_utc` (NOT NULL) and `end_time_utc` (NULL) as `timestamptz`, with check `end_time_utc IS NULL OR end_time_utc >= start_time_utc`.<br><br>`start_time_tz` is `varchar(64)`, an IANA name.<br><br>`start_time_local` is the **normalized ISO 8601 wall-clock time without an offset**, at second precision (`YYYY-MM-DDTHH:MM:SS`), as `varchar(19)` with a regex check. The raw text exactly as the source wrote it stays in `ExtractedRecord.payload`. | AD-6: UTC is the truth and the tz is explicit and IANA, never an offset. With `USE_TZ = True` Django has no clean naive-timestamp column. A fixed normalized form is checkable and sized exactly. Raw text would be unbounded and unvalidatable, and it is already kept as evidence in the payload. IANA validity is checked in the command via `zoneinfo`, because a DB check can't see the tz database. Overnight events (an end before the start in local time) and all-day ICS events are normalized by the parser and pipeline before they reach this check. |
| **D9. Confidence columns** | `tz_inference_confidence` and `extraction_confidence` are `numeric(3,2)` with check `0 ≤ x ≤ 1`.<br>• **On Event:** both are NOT NULL, because a NULL passes a check.<br>• **On ExtractedRecord:** `tz_inference_confidence` is nullable (a `none`-tier rejection has none), and `extraction_confidence` is NOT NULL.<br>Structured sources write `extraction_confidence = 1.00`. | Spine Consistency Conventions: both are `numeric(3,2)` in `[0, 1]` on Event. Thresholds stay in `shared/constants.py` (AD-8). |
| **D10. Versioning** | `Event.event_version` is a positive integer defaulting to 1. The event-guard trigger (D12) rejects `NEW.event_version < OLD.event_version`. `EventStateChange` has a unique constraint on `(event_id, event_version)`. | AD-17 needs a monotonically increasing version per Event. The trigger stops a stale writer from moving it backwards, and the unique constraint stops two state changes from claiming one version, even under concurrent ingest. |
| **D11. Series** | `Event.series_id` is a nullable, indexed UUID. There is **no Series table**: the ID is `uuid5(SERIES_ID_NAMESPACE, f"{source_id}:{series_key}")`, minted by domain code, with `SERIES_ID_NAMESPACE = UUID("cbd88e48-d511-4f1b-a595-2f31c0067ad4")` pinned in `shared/constants.py`. | AD-4 only needs a shared key for recurring instances. A deterministic ID means re-ingest yields the same ID with no lookup and no extra table. The namespace is a pinned constant because changing it would silently split every existing series. |

### Integrity enforcement

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D12. Append-only history, audit, and event guards** | Three layers.<br><br>**(1) Grants** (in the migration): `REVOKE UPDATE, DELETE ON ingestion_eventstatechange, ingestion_ingestionauditentry FROM ep_catalog;` then `GRANT UPDATE (propagated_at) ON ingestion_eventstatechange TO ep_catalog;`.<br><br>**(2) Triggers**, which also bind the owner role:<br>• `catalog.forbid_history_mutation()` is `BEFORE UPDATE OR DELETE` on both tables. DELETE is allowed only under `SET LOCAL eventpulse.retention_purge = 'on'`. UPDATE on the audit table is never allowed. UPDATE on state changes is allowed only when `OLD.propagated_at IS NULL AND NEW.propagated_at IS NOT NULL AND (to_jsonb(NEW) - 'propagated_at') IS NOT DISTINCT FROM (to_jsonb(OLD) - 'propagated_at')`.<br>• `catalog.guard_event_update()` is `BEFORE UPDATE` on `ingestion_event`. It rejects any update when `OLD.status = 'superseded'` (D7) and any `NEW.event_version < OLD.event_version` (D10).<br><br>**(3) Model guard:** `save()` raises when `not self._state.adding`, unless `update_fields == ["propagated_at"]`. `delete()` raises. A custom QuerySet blocks `delete()`, blocks `update()` unless its only keyword is `propagated_at`, and blocks `bulk_update()` unless `fields == ["propagated_at"]`. | **Grants** stop the runtime role at the privilege layer, the role the application actually uses. This is testable because `tests/wall/test_role_isolation.py` already runs statements as `ep_catalog`, and the same `run_as` helper covers the new tests. Default privileges grant full DML on new tables, so the revoke must come after the create, in the same migration.<br><br>**Triggers** cover the owner role (migrations, the shell, admin under owner settings) and NULL→value semantics, which a grant can't express. `to_jsonb(NEW) - 'propagated_at'` compares the whole row, so a column added later is covered automatically.<br><br>**The model guard** fails fast in Python, with a readable error before the round trip. The role name `ep_catalog` matches `docker/postgres/init/01-schemas-and-roles.sh`. The deployment intent must create the same role. |
| **D23. Outbox update form** | `propagated_at` is set **only** with the conditional form `EventStateChange.objects.filter(pk=…, propagated_at__isnull=True).update(propagated_at=now)`, through an `ingestion` command. A zero-row result means the change was already propagated, which is not an error. | It is idempotent under the AD-17 retry and reconciler, and it matches what both the trigger and the QuerySet guard allow. |
| **D21. Resolution consistency** | `ExtractedRecord.resolution ∈ {resolved, rejected, ambiguous}`, with one `CheckConstraint`:<br>• `resolved`: `event_id IS NOT NULL AND reject_reason = ''`<br>• `rejected`: `event_id IS NULL AND reject_reason <> ''`<br>• `ambiguous`: `event_id IS NULL AND reject_reason = ''`<br><br>**Ambiguous** means the candidate satisfies an identity rule against **more than one** live Event, or different rules point to different Events. It is never auto-merged and stays unbound until editorial resolves it. An `in_review` Event (D6) counts as `resolved`: the record is bound to it. | It makes the three states impossible to mix up in the data. "Ambiguous" follows FR-15's out-of-scope line ("auto-merge across >2 ambiguous candidates (always routed to editorial review)"). |

### Registry

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D13. ToS reviews** | `TosReview` is its own table (retention `TOS_REVIEW_RECORDS`) and is the record. `Source.tos_status` (`not_reviewed`, `approved`, `rejected`) is a denormalized cache, written **only** by `record_tos_review` in the same transaction. Whenever `acquisition_method` changes, `update_source` resets it to `not_reviewed` in that transaction. | AD-15 makes retention a table property: ToS records live 7 years, while source data lives for the event range plus 12 months, so they can't share a table. A review approves *a method*, so a method change invalidates it. The cache keeps the FR-17 guard to a one-row read. *(Departure 3: the name is `tos_status`.)* |
| **D14. Venue** | `Venue(name, city, country_code, venue_fingerprint unique, tz NULL)`. `Event.venue` is a nullable FK (`PROTECT`), and `Event.venue_fingerprint` is copied onto the Event at ingest. | The registry serves the FR-60 `partial` tier (it needs `tz`) and the identity tuple. Copying the fingerprint means an editorial rename never changes an existing Event's identity. A venue without `tz` may exist but can't rescue a `partial`-tier event. *(Departure 4: `tz` is nullable.)* |
| **D15. Public slug** | `Event.slug` has a unique constraint and is minted by the create command from the title, the venue-local date, and a short ID suffix. | Spine Ids convention: public URLs use a slug, never the PK. Minting it at creation keeps it stable when the title changes. Collisions and empty slugs are the create command's concern (`ingest-pipeline-and-lifecycle`). |
| **D16. Source fields owned by later items** | Included now: `etag`, `last_modified`, `last_ingested_at`, `last_attempted_at`, `consecutive_failures`, `last_error_code`, and `stale_since`. **`ingestion_cadence` has no model default:** `register_source` applies a per-method default (RSS: 4 hours). Scheduling claim and lock fields are not included. | The pipeline needs conditional-fetch and error state, and freshness (FR-13) needs `stale_since`. A per-method default can't be one model default, so it belongs to the command that knows the method. Double-run prevention is `ingestion-scheduling`'s decision, in its own forward-only migration. *(Departure 5.)* |

### Audit, retention, and migration

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D17. Audit** | The abstract `AuditEntry(UUIDv7Model)` lives in `shared/models.py`. The concrete `IngestionAuditEntry` has category `AUDIT_LOG`. `write_audit(actor, action, target, details)` **raises** unless `connections[CATALOG].in_atomic_block`.<br><br>**Actor check:**<br>• `actor_kind = 'user'`: `actor_id IS NOT NULL AND actor_label = ''`<br>• `actor_kind = 'system'`: `actor_id IS NULL AND actor_label <> ''`<br><br>`actor_label` holds **only** a system job name, such as `scheduler` or `ingest_pipeline`, and **never** a username, email, or any other personal data. | It follows `coding-standards.md` and OQ-8: one table per owning app, actor by value, and no FK, so E002 can't trip. Refusing to write outside a catalog transaction makes AD-5's "same transaction" mechanical. The check makes it structurally impossible for a user's name to cross into `catalog` (AD-3, AD-13). |
| **D18. Actor** | `shared/actor.py` defines a frozen dataclass `Actor(kind, id, label)`, with `Actor.system("scheduler")` and `Actor.user(user_id)`. It is stdlib only, and `Actor.user` takes no label. | Services receive an explicit actor and never a `request` (Consistency Conventions). Admin passes the staff user's UUIDv7, which E005 already guarantees. |
| **D19. Retention** | `SOURCE_REGISTRY` for Source, Venue, Event, ExtractedRecord, and EventStateChange. `TOS_REVIEW_RECORDS` for TosReview. `AUDIT_LOG` for IngestionAuditEntry. | These are PRD §10.2 categories. No table stores a user reference except the audit actor and `TosReview.reviewed_by_id`, both stored by value. |
| **D20. Deletes and migration** | Every FK is `on_delete=PROTECT`. There is a single forward-only migration, `ingestion/0001_initial`, which includes the trigger and grant `RunSQL`. Its `reverse_sql` is for local rollback only. | Sources are paused, never deleted (FR-13 auditability). Spine: migrations are forward-only, one per PR. |

## Departures from the Work Item ACs

Each departure below has been applied to `catalog-data-model.md`.

| # | Original AC | Design | Why |
|---|---|---|---|
| 1 | Unique constraint on the canonical URL | Index only, no unique constraint (D3) | Superseded events and recurring series legally share a URL |
| 2 | `ExtractedRecord` records each raw parse | One row per source item, upserted (D2) | It binds the item to its Event; change history is `EventStateChange` |
| 3 | `tos_review_status` | `tos_status`, a cache of `TosReview` (D13) | The ToS record needs its own table and retention category |
| 4 | `Venue` has an IANA `tz` | `tz` is nullable (D14) | A venue can be known before its timezone is |
| 5 | `ingestion_cadence` defaults per method | No model default; the command applies it (D16) | A per-method default needs the method |
| 6 | Kinds `postpone, cancel, move, sold_out, supersede, detail` | `time_moved, postponed, cancelled, sold_out, detail_changed, superseded` (past tense) | The rows record facts that happened; `time_moved` and `postponed` (date TBD) are distinct |

## Data Models Affected

### Creates

- **Source**:
  - `name`, `source_type` (`venue | promoter | ticketing | community | government | media | other`)
  - `url`, `city` (blank allowed)
  - `acquisition_method` (`api | partnership | jsonld | rss | ics | email_ics | crawl`)
  - `tos_status`, `status` (`active | paused`)
  - `ingestion_cadence` (interval, no default), `freshness_ttl_hours` (default 24), `tz_coverage` (`full | partial | none`)
  - `etag`, `last_modified`, `last_ingested_at`, `last_attempted_at`, `consecutive_failures`, `last_error_code`, `stale_since`
  - `created_at`, `updated_at`

  This is the FR-13 registry.
- **TosReview**:
  - `source` (FK), `decision` (`approved | rejected`)
  - `reviewed_by_id` (UUID by value), `reviewed_at`
  - `acquisition_method` at review time, `evidence_url`, `notes`

  These are the FR-17 ToS records, kept 7 years.
- **Venue**: `name`, `city`, `country_code`, `venue_fingerprint` (unique constraint), `tz` (IANA, nullable), `created_at`, `updated_at`. It is the FR-60 `partial` tier's tz source and the identity tuple's venue key.
- **Event**:
  - origin: `source` (FK), `source_event_id` (non-empty), `slug` (unique constraint)
  - content: `title`, `description` (plain text), `canonical_url` (indexed)
  - venue: `venue` (FK, nullable), `venue_fingerprint`, `title_fingerprint`
  - time: `start_time_utc`, `end_time_utc`, `start_time_local` (`varchar(19)`), `start_time_tz`
  - confidence: `tz_inference_confidence` and `extraction_confidence` (both NOT NULL), `tz_review_pending`
  - state: `publication_status`, `status`, `is_sold_out`, `event_version`
  - lineage: `series_id`, `superseded_by` (self FK)
  - timestamps: `first_seen_at`, `last_seen_at`, `created_at`, `updated_at`

  It is the canonical public event.
- **ExtractedRecord**:
  - `source` (FK), `source_event_id` (non-empty)
  - `payload` (JSON: the normalized, text-only candidate plus the raw as-written time), `content_hash` (SHA-256 hex)
  - `extraction_confidence` (NOT NULL), `tz_inference_confidence` (nullable)
  - `resolution`, `reject_reason`
  - `event` (FK, nullable)
  - `first_seen_at`, `last_seen_at`, `last_changed_at`

  It binds a source item to an Event and is the rule (a) authority.
- **EventStateChange**: `event` (FK), `kind` (`time_moved | postponed | cancelled | sold_out | detail_changed | superseded`), `event_version`, `before` (JSON), `after` (JSON), `occurred_at`, `propagated_at` (nullable), `actor_kind`, `actor_id`. It is `state_history` plus the AD-17 outbox. Append-only (D12).
- **AuditEntry** (abstract, `shared/models.py`): UUIDv7 `id`, `at`, `actor_kind` (`user | system`), `actor_id` (UUID by value, nullable), `actor_label` (system job name only), `action`, `target_type`, `target_id`, `details` (JSON). It is AD-5's audit shape, with one concrete table per owning app.
- **IngestionAuditEntry**: concrete `AuditEntry`, `AUDIT_LOG`, append-only (D12). It is the `ingestion` audit log.

### Modifies

- **`shared/constants.py`**: adds two constants:
  - `TZ_INFERENCE_CONFIDENCE_AUTO_PUBLISH = Decimal("0.90")`, the FR-60 upper gate (D6)
  - `SERIES_ID_NAMESPACE = UUID("cbd88e48-d511-4f1b-a595-2f31c0067ad4")` (D11)

  The module stays stdlib only.

## Technical Approach

### Architecture

```
                    catalog schema (alias CATALOG), all owned by apps.ingestion
 ┌──────────┐ n   1 ┌────────────┐
 │ TosReview├──────►│   Source   │◄──────────────┐
 └──────────┘       └─────┬──────┘               │ source (origin)
                          │ 1                    │
                          │ n                    │
                ┌─────────▼────────┐  event   ┌──┴──────────┐ superseded_by (terminal)
                │ ExtractedRecord  ├────────► │    Event    ├────────┐
                │ UQ(source,       │ n   0..1 │ partial UQ  │◄───────┘
                │  source_event_id)│          │ (source,    │
                │ CHECK resolution │          │  src_ev_id) │ n  0..1 ┌───────┐
                └──────────────────┘          │ live only   ├────────►│ Venue │
                                              │ guard trig. │  venue  └───────┘
                                              └─────┬───────┘
                                                    │ 1
                                                    │ n   UQ(event, event_version)
                                         ┌──────────▼──────────┐
                                         │  EventStateChange   │ append-only: grant + trigger + model
                                         │  propagated_at NULL │──► AD-17 outbox (conditional update)
                                         └─────────────────────┘
 ┌──────────────────────┐
 │ IngestionAuditEntry  │  append-only; actor by value, no FK, no personal data in actor_label
 └──────────────────────┘
```

### Database Changes

```python
# Django Meta.constraints (key ones)
UniqueConstraint(fields=["source", "source_event_id"],
                 condition=~Q(status="superseded"), name="event_live_source_item_uq")  # partial, not deferrable
CheckConstraint(condition=~Q(source_event_id=""), name="event_source_event_id_nonempty")
CheckConstraint(condition=Q(tz_inference_confidence__gte=0, tz_inference_confidence__lte=1), ...)
CheckConstraint(condition=Q(extraction_confidence__gte=0, extraction_confidence__lte=1), ...)
CheckConstraint(condition=Q(end_time_utc__isnull=True) | Q(end_time_utc__gte=F("start_time_utc")), ...)
CheckConstraint(condition=Q(status="superseded") == Q(superseded_by__isnull=False), ...)  # as two ORed branches
CheckConstraint(condition=Q(superseded_by__isnull=True) | ~Q(superseded_by=F("id")), ...)
CheckConstraint(condition=Q(event_version__gte=1), ...)
CheckConstraint(condition=Q(start_time_local__regex=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$"), ...)
Index(fields=["venue_fingerprint", "start_time_utc"])            # rule (b)
Index(fields=["canonical_url"])                                  # rule (c); long-URL handling → pipeline
Index(fields=["publication_status", "status", "start_time_utc"]) # public listing
Index(fields=["series_id"])

# ExtractedRecord
UniqueConstraint(fields=["source", "source_event_id"], name="extracted_record_source_item_uq")  # rule (a)
CheckConstraint(condition=~Q(source_event_id=""), ...)
CheckConstraint(condition=(Q(resolution="resolved") & Q(event__isnull=False) & Q(reject_reason=""))
                        | (Q(resolution="rejected") & Q(event__isnull=True) & ~Q(reject_reason=""))
                        | (Q(resolution="ambiguous") & Q(event__isnull=True) & Q(reject_reason="")), ...)

# EventStateChange
UniqueConstraint(fields=["event", "event_version"], name="state_change_version_uq")
Index(fields=["occurred_at"], condition=Q(propagated_at__isnull=True), name="state_change_unpropagated_idx")

# IngestionAuditEntry
CheckConstraint(condition=(Q(actor_kind="user") & Q(actor_id__isnull=False) & Q(actor_label=""))
                        | (Q(actor_kind="system") & Q(actor_id__isnull=True) & ~Q(actor_label="")), ...)
```

```sql
-- RunSQL in 0001_initial
CREATE FUNCTION catalog.forbid_history_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF current_setting('eventpulse.retention_purge', true) = 'on' THEN RETURN OLD; END IF;
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME USING ERRCODE = 'restrict_violation';
  END IF;
  IF TG_TABLE_NAME = 'ingestion_eventstatechange'
     AND OLD.propagated_at IS NULL AND NEW.propagated_at IS NOT NULL
     AND (to_jsonb(NEW) - 'propagated_at') IS NOT DISTINCT FROM (to_jsonb(OLD) - 'propagated_at') THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION '% is append-only', TG_TABLE_NAME USING ERRCODE = 'restrict_violation';
END $$;

CREATE FUNCTION catalog.guard_event_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status = 'superseded' THEN
    RAISE EXCEPTION 'superseded Event % is terminal', OLD.id USING ERRCODE = 'restrict_violation';
  END IF;
  IF NEW.event_version < OLD.event_version THEN
    RAISE EXCEPTION 'event_version may not decrease (% -> %)', OLD.event_version, NEW.event_version
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER eventstatechange_append_only BEFORE UPDATE OR DELETE ON ingestion_eventstatechange
  FOR EACH ROW EXECUTE FUNCTION catalog.forbid_history_mutation();
CREATE TRIGGER ingestionauditentry_append_only BEFORE UPDATE OR DELETE ON ingestion_ingestionauditentry
  FOR EACH ROW EXECUTE FUNCTION catalog.forbid_history_mutation();
CREATE TRIGGER event_guard BEFORE UPDATE ON ingestion_event
  FOR EACH ROW EXECUTE FUNCTION catalog.guard_event_update();

REVOKE UPDATE, DELETE ON ingestion_eventstatechange, ingestion_ingestionauditentry FROM ep_catalog;
GRANT UPDATE (propagated_at) ON ingestion_eventstatechange TO ep_catalog;
```

## Dependencies

- `shared.models.UUIDv7Model`, `shared.retention`, `shared.db.CATALOG`, and `config/checks.py` (E001–E005) all already exist.
- `tests/wall/test_role_isolation.py::run_as` is reused for the grant tests.
- The `ep_catalog` role comes from `docker/postgres/init/01-schemas-and-roles.sh`.
- No new third-party packages.

## Affected Files

| File | Action | Purpose |
|------|--------|---------|
| `backend/apps/ingestion/models.py` | Modify | The seven models, constraints, indexes, and model and QuerySet guards |
| `backend/apps/ingestion/migrations/0001_initial.py` | Create | Tables, triggers, and grants (`RunSQL`) |
| `backend/apps/ingestion/services/audit.py` | Create | `write_audit()`, which refuses to run outside `atomic(using=CATALOG)` |
| `backend/shared/models.py` | Modify | Abstract `AuditEntry` |
| `backend/shared/actor.py` | Create | `Actor` value object (stdlib only) |
| `backend/shared/constants.py` | Modify | `TZ_INFERENCE_CONFIDENCE_AUTO_PUBLISH`, `SERIES_ID_NAMESPACE` |
| `backend/tests/ingestion/factories.py` | Create | factory_boy factories, with explicit UTC and IANA tz |
| `backend/tests/ingestion/test_models.py` | Create | Constraints, triggers, guards, routing, retention |
| `backend/tests/ingestion/test_grants.py` | Create | `ep_catalog` privilege tests via `run_as` |
| `backend/tests/ingestion/test_audit.py` | Create | `write_audit` inside and outside a transaction (`transaction=True`) |
| `.specs-fire/standards/coding-standards.md` | Modify | `Actor`, `write_audit`, the append-only convention, and the conditional outbox update |

## Security Considerations

- **Untrusted content (AD-9):** `ExtractedRecord.payload` and `Event.description` hold parser-stripped plain text and are never rendered as HTML. This item adds no template or admin view that marks them safe.
- **No personal data across the wall (AD-3, OQ-8):** the only person references are `actor_id` and `reviewed_by_id`, both stored by value with no FK. `actor_label` is check-constrained so it can't hold one.
- **Tamper resistance, and its exact coverage:**
  - The **runtime role `ep_catalog`** can't UPDATE (except `propagated_at`) or DELETE state changes, and can't UPDATE or DELETE audit rows (grant layer).
  - **Every role**, the owner included, is stopped by the triggers for row-level UPDATE and DELETE.
  - **Not covered:**
    - The owner role can `TRUNCATE` (no row trigger fires) or `ALTER TABLE … DISABLE TRIGGER`.
    - **Any role** can `SET LOCAL eventpulse.retention_purge = 'on'`, which re-enables DELETE where the role also holds the DELETE privilege. That means the owner only, since `ep_catalog` has had DELETE revoked.

  The owner credential is a migration-time secret that is never present in a production runtime environment (schema-router-spike D8), so these gaps are accepted and named. `TRUNCATE` is left open deliberately, because Django's `transaction=True` test flush uses it.

## Integration Points

| System | Type | Purpose |
|--------|------|---------|
| `config/checks.py` E001–E005 | System check | Routing, retention, UUIDv7: every new model must pass |
| `event-identity-and-tz-domain` | Producer of values | Fingerprints, `series_id` (via `SERIES_ID_NAMESPACE`), and tz tier and confidence. Rule (c) honors D4. |
| `ingest-pipeline-and-lifecycle` | Consumer | Writes Event, ExtractedRecord, and EventStateChange in one `atomic(using=CATALOG)`, follows the D7 supersede order and the D23 outbox form |
| `source-registry-commands-admin` | Consumer | Writes Source, TosReview, Venue, and audit rows. Resets `tos_status` on a method change (D13). Applies the cadence default (D16). |
| `public-catalog-read-api` | Reader | Lists `published`, non-superseded Events via the listing index, exposing `tz_review_pending` |
| Future AD-15 sweep | Consumer | Purges under `SET LOCAL eventpulse.retention_purge = 'on'` as a role holding DELETE. Order across supersede chains under `PROTECT` is its concern. |
| Deployment intent | Environment | Must create the `ep_catalog` role, or the grant `RunSQL` fails loudly |

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Rule (c) (same URL) merges recurring instances that share a series page | High | D4 is in the `event-identity-and-tz-domain` acceptance criteria. There is no unique constraint on the URL (D3), so a domain bug can't hide behind a constraint error, and item 6's recurring-series fixture test catches it. |
| A supersede run out of order violates the non-deferrable partial unique index | High | D7 fixes the order. Item 6's acceptance criteria require it, and a test runs the supersede path and asserts both Events and the repointed record. |
| The PRD's FR-60 tier table still says "<0.7 → auto-reject" | Medium | D6 follows AD-6 and FR-60 consequence 3, and the conflict is logged in the intent brief for a PRD amendment. Item 6's tests pin the behavior. |
| The `ep_catalog` role is missing in some environment, so the migration fails | Medium | That failure is loud and intended. CI already provisions the role for `test_role_isolation.py`, and the deployment intent is told (Integration Points). |
| The `tos_status` cache drifts from `TosReview` | Medium | Only `record_tos_review` and `update_source` write it, in the same transaction. A test asserts the cache equals the latest review, and that it resets on a method change. |
| `in_review` and `extraction_confidence` look speculative | Low | `in_review` is now used by D6, and `extraction_confidence` is spine-mandated on Event. |
| The partial unique index lets two live Events from *different* sources describe one happening | Medium | By design: cross-source merging is rules (b) and (c) in the domain, with a review queue later. Concurrency between two sources matching the same Event is handled by an advisory lock (`event-identity-and-tz-domain` and `ingest-pipeline-and-lifecycle`). |

## Implementation Checklist

- [ ] Add `Actor` in `shared/actor.py`, the abstract `AuditEntry` in `shared/models.py`, and `TZ_INFERENCE_CONFIDENCE_AUTO_PUBLISH` and `SERIES_ID_NAMESPACE` in `shared/constants.py`
- [ ] Write the models in `apps/ingestion/models.py`: TextChoices, `retention_category`, `Meta.constraints` and indexes, model and QuerySet guards (D12), and docstrings citing the ADs
- [ ] Run `make makemigrations`, then append the trigger and grant `RunSQL` (with `reverse_sql`) to `0001_initial`, then run `migrate --database=catalog`. Confirm nothing lands in `personal`.
- [ ] Add `apps/ingestion/services/audit.py::write_audit`
- [ ] Add factories in `tests/ingestion/factories.py`
- [ ] Tests (`@pytest.mark.django_db(databases=[PERSONAL, CATALOG])`):
  - **Constraints:** every check and unique constraint, including a superseded duplicate allowed by the partial index, an empty `source_event_id` rejected, every invalid resolution, actor, and `start_time_local` shape rejected, and a NULL confidence on Event rejected.
  - **Supersede:** the D7 order succeeds inside one transaction, and the reverse order (insert the new Event first) fails on the partial unique index.
  - **Triggers:** state-change UPDATE and DELETE rejected; `propagated_at` NULL→value allowed and value→other rejected; changing another column together with `propagated_at` rejected; purge setting allows DELETE (owner); any UPDATE of a superseded Event rejected; `event_version` decrease rejected.
  - **Grants (`run_as` as `ep_catalog`):** UPDATE of a non-`propagated_at` column denied, UPDATE of `propagated_at` allowed, DELETE denied, and audit UPDATE and DELETE denied.
  - **Model and QuerySet guards:** `save()` on an existing row raises, `save(update_fields=["propagated_at"])` is allowed, `qs.delete()` raises, `qs.update(kind=…)` raises, and `qs.filter(propagated_at__isnull=True).update(propagated_at=…)` is allowed.
  - **`write_audit`** uses `@pytest.mark.django_db(transaction=True, databases=[PERSONAL, CATALOG])`: it raises with no catalog atomic block (and so can actually fail) and writes inside one.
  - **System:** `manage.py check` passes, and the router places every table in `catalog`.
- [ ] Update `coding-standards.md`: `Actor`, `write_audit`, the append-only convention (grant + trigger + guard), and the conditional outbox update
- [ ] Run lint, types, import-linter, and the full test suite with coverage gates


## Amendments at Checkpoint 2

These were approved with the implementation plan (run-eventpulse24-010, `plan.md` "Deviations from the design" 5–10). Where they differ from a decision above, the amendment wins.

| Amends | Change |
|---|---|
| D11 | `series_id` is minted by `shared.ids.series_id(source_id, series_key)`, with a golden-value test. Domain code calls it and never mints one inline. |
| D12 | The QuerySet guard also rejects `update(propagated_at=None)`, `bulk_create(update_conflicts=True)`, and any `update_fields` or `fields` set other than `{"propagated_at"}`. `Meta.base_manager_name = "objects"`, so related-object paths are guarded too. The guard lives in `shared.models.AppendOnlyModel` / `AppendOnlyQuerySet`, so every app's audit table reuses it. The trigger function takes the settable column as a trigger argument instead of naming the table. |
| D7, D10, D12 | The Event trigger is `catalog.guard_event_write()`, renamed from `guard_event_update()`. It also fires `BEFORE INSERT`: a new Event has `event_version = 1` and is not `superseded`. On UPDATE, `event_version` may only stay the same or rise by 1, and a change to any of `Event.LIFECYCLE_FIELDS` (start, end, tz, status, sold out, venue, `superseded_by`) at an unchanged version is rejected. |
| D17 | `EventStateChange` also has `actor_label` and the same actor check (`state_change_actor_ck`). The check is `shared.models.actor_check()`. The abstract base names it `%(app_label)s_%(class)s_actor_ck`. |
| D17, D18 | `Actor.__post_init__` validates kind and ID together. A system label must match `^[a-z][a-z0-9_]+$`. |
| Data models | Every JSON field (`payload`, `before`, `after`, `details`) uses `DjangoJSONEncoder`. |
| Dependencies | Adds the dev dependency `factory-boy==3.3.3` (with `faker`), which the testing standards require. |

## Amendments from run-eventpulse24-011 (event-identity-and-tz-domain)

| Amends | Change |
|---|---|
| D8 | `start_time_local` is **derived**: `start_time_utc` read in `start_time_tz`, at second precision, with no offset. It therefore always converts back to `start_time_utc`. The text exactly as the source wrote it stays in `ExtractedRecord.payload`. Format and column are unchanged. |
| D14 | `venue_fingerprint` is `v1:` + sha256 of the normalized name, city and country code (67 characters). It is `""` when there's no venue name, and an empty fingerprint never matches. |
| D4 | Rule (c) matches only on the same normalized URL **and** the same instant. Rules (b) and (c) never match an Event that already has an item bound from the candidate's source. |

---
*Generated by specs.md - fabriqa.ai FIRE Flow | Checkpoint 1 approved: 2026-10-28T06:53:33Z*
