---
id: run-eventpulse24-057
scope: wide
work_items:
  - id: city-catalog-dataset
    intent: city-picker-and-auto-collection
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: source-city-timezone
    intent: city-picker-and-auto-collection
    mode: validate
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: api-source-parser
    intent: city-picker-and-auto-collection
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: city-choices-endpoint
    intent: city-picker-and-auto-collection
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: stored-city-is-the-picked-city
    intent: city-picker-and-auto-collection
    mode: validate
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: city-provider-templates
    intent: city-picker-and-auto-collection
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: city-provisioning-service
    intent: city-picker-and-auto-collection
    mode: validate
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: provisioning-probation
    intent: city-picker-and-auto-collection
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: browse-collecting-states
    intent: city-picker-and-auto-collection
    mode: confirm
    status: in_progress
    current_phase: plan
    checkpoint_state: none
    current_checkpoint: plan
  - id: city-coverage-request
    intent: city-picker-and-auto-collection
    mode: confirm
    status: pending
    current_phase: null
    checkpoint_state: none
    current_checkpoint: null
  - id: home-city-dropdown-catalog
    intent: city-picker-and-auto-collection
    mode: confirm
    status: pending
    current_phase: null
    checkpoint_state: none
    current_checkpoint: null
current_item: browse-collecting-states
status: in_progress
started: 2026-11-20T13:36:37.657Z
completed: null
---

# Run: run-eventpulse24-057

## Scope
wide (11 work items)

## Work Items
1. **city-catalog-dataset** (confirm) — completed
2. **source-city-timezone** (validate) — completed
3. **api-source-parser** (confirm) — completed
4. **city-choices-endpoint** (confirm) — completed
5. **stored-city-is-the-picked-city** (validate) — completed
6. **city-provider-templates** (confirm) — completed
7. **city-provisioning-service** (validate) — completed
8. **provisioning-probation** (confirm) — completed
9. **browse-collecting-states** (confirm) — in_progress
10. **city-coverage-request** (confirm) — pending
11. **home-city-dropdown-catalog** (confirm) — pending


## Current Item
browse-collecting-states (confirm)

## Files Created
- `backend/tests/personalization/test_stored_city_is_the_picked_city.py` — 682 cases: the
  whole-dataset proof that a catalog city is stored exactly as picked and a city outside
  it is refused
- `backend/tests/api/test_digest_preference_api.py` — 11 tests: the endpoint answers 422
  for a city outside the catalog and stores nothing
- `backend/apps/personalization/migrations/0018_digestpreference_city_source_seed.py` —
  `AlterField` adding the seed city source; moves no rows
- `backend/apps/ingestion/services/city_probation.py` — NEW: the probation — the pure
  `classify_run`, the zero-yield counter's three effects, the pause at the threshold, and
  the city's four honest statuses
- `backend/apps/ingestion/migrations/0016_source_city_ref_and_probation.py` — NEW: three
  `AddField`s on `source` — `city_ref`, `consecutive_zero_yield_runs`, `paused_reason`;
  additive and nullable, so no data migration and no backfill
- `backend/tests/ingestion/test_city_probation.py` — NEW: 75 tests, 100% coverage of the
  service, including the four "cannot happen" guards
- `.specs-fire/runs/run-eventpulse24-057/mutation/mutation_probe.py` — NEW: the mutation
  check, 14 mutations, all caught. Outside `tests/` on purpose — it is a verification tool,
  not a test, and pytest would collect it

## Files Modified
- `backend/domain/errors.py` — `UnknownHomeCityError(ValidationError)`, the refusal
- `backend/domain/city_catalog.py` — added the project's own seed city, "Montgomery"
- `backend/apps/personalization/services/digest_preferences.py` — the coverage rule
  replaced by the catalog rule; `_canonical` deleted
- `backend/apps/personalization/services/onboarding.py` — `set_digest_preference` takes a
  `city_source`, defaulting to `choice`
- `backend/apps/personalization/models.py` — `CitySource` gained `SEED`
- `backend/apps/personalization/{api,schemas}.py` — descriptions that promised the rewrite
- `backend/apps/identity/{api,schemas}.py` — the same, on the sign-up path
- `backend/config/management/commands/seed_browse_catalog.py` — the seed's city is now the
  server's own
- `backend/tests/personalization/test_digest_preferences.py` — rewritten; the old
  coverage-rule tests inverted
- `backend/tests/personalization/test_onboarding_api.py` — two assertions that asserted the
  rewrite
- `backend/tests/personalization/test_digest_preference_model.py` — the source vocabulary
  is five, not four
- `backend/tests/config/test_seed_browse_catalog.py` — the seeded city is labelled `seed`
- `frontend/lib/api/{openapi.json,schema.ts}` — regenerated by `make client`, description-only
- `backend/domain/city_providers.py` — NEW: `SourceSpec`, `ProviderTemplate`, the ordered
  `PROVIDER_TEMPLATES` registry, and `resolve(city)`
- `backend/tests/domain/test_city_providers.py` — NEW: 45 tests, over the full
  catalog × templates cross-product
- `backend/apps/ingestion/services/city_provisioning.py` — NEW: the provisioning service —
  the catalog gate, the city's advisory lock, the credential filter, and the `on_commit`
  seam
- `backend/apps/ingestion/migrations/0015_cityprovisioning.py` — NEW: `CreateModel
  CityProvisioning`
- `backend/tests/ingestion/test_city_provisioning.py` — NEW: 235 tests, whole-dataset
- `backend/apps/ingestion/models.py` — `CityProvisioning` added after `City`
- `backend/apps/personalization/services/digest_preferences.py` — the trigger:
  `provision_city_on_commit` in `set_home_city`
- `backend/tests/ingestion/test_models.py` — three model enumerations
- `backend/tests/wall/test_schema_placement.py` — the catalog table set
- `backend/tests/architecture/test_write_ownership.py` — `TABLE_OWNERS`
- `backend/tests/personalization/test_digest_recompose_triggers.py` — the callback
  assertion, relaxed from an exact count to "every callback is on `PERSONAL` and robust"
- `backend/apps/ingestion/models.py` — `Source` gained `city_ref`, `consecutive_zero_yield_runs`
  and `paused_reason`, plus `Source.PausedReason`
- `backend/apps/ingestion/services/ingest_source.py` — `_close` classifies the run and moves
  the counter inside its own transaction; the probation runs *after* the commit, wrapped so
  a probation failure never fails a successful ingest
- `backend/apps/ingestion/services/source_registry.py` — `pause_source(reason=…)`,
  `resume_source` clears the reason *and* the counter, `register_source(city_ref=…)`, and a
  `_reprobate_city` hook after a status change (a lazy import — the module-level cycle is
  `city_probation → source_registry → city_probation`)
- `backend/apps/ingestion/services/city_provisioning.py` — `city_ref=city` on registration (the
  load-bearing link), the `yielded_nothing` re-open, and `_resume_choice`
- `backend/apps/ingestion/admin.py` — the two new display fields, and the `pause_sources`
  action now records `reason=Source.PausedReason.MANUAL`
- `backend/shared/constants.py` — `ZERO_YIELD_RUN_THRESHOLD`, `PUBLISHED_COUNT_KEYS`,
  `YIELDED_COUNT_KEYS`
- `backend/tests/ingestion/test_city_provisioning.py` — 10 tests added for the resume path
- `backend/tests/ingestion/test_source_registry.py` — 5 tests added for the pause reason
- `backend/tests/ingestion/test_migrations.py` — the `constraint_dropped()` fixture now
  flushes pending deferred-FK trigger events before its `ALTER TABLE`
- `backend/tests/architecture/test_write_ownership.py` — the `ingestion_cityprovisioning`
  comment names both writers now; the ownership entry itself is unchanged

## Decisions
- **The refusal's status** — 422 (`ValidationError`). A bad value is a bad request, and
  `ValidationError` already maps there, so no error-handler wiring changed.
- **Echo the refused city?** — In `details["rejected_city"]`, not in the message. The
  client needs to know which value was refused to re-select it; the person reading the
  message does not need it echoed.
- **Migrate the existing `fallback` rows?** — No. Nulling them would push a surprise empty
  Browse onto people who never asked for one.
- **Branch on `source` or on the city?** — On `source`. A choice outside the catalog is a
  client bug and deserves a loud 422; a geo guess is not the reader's fault and must not
  become a 4xx on a path they never asked for.
- **The seed's fictional city** — A third writer, `SOURCE_SEED`, stored verbatim.
  "Fixtureville" cannot be a pickable city, and bending it into a real one would make the
  seed's venues and events disagree.
- **The Eventbrite JSON-LD template** — In the registry, `enabled=False`; `resolve()`
  skips it whole. `seed_dhaka_live.py` already says Eventbrite's Terms restrict
  automated access and point at their API. Omitting it drops the only JSON-LD shape proven
  by running code; enabling it promotes a source the codebase has flagged. Disabled keeps
  the shape and makes it live on one constant after a person's review.
- **The source_type / acquisition_method / tz_coverage vocabularies** — Restated as
  constants in `domain/`, with a test holding each to the model's. `domain` may not
  import `apps.ingestion.models` (AD-3) and is stdlib-only besides.
- **`ACQUISITION_METHODS` shape** — A tuple, with `ACQUISITION_METHOD_SET` as the set
  view. FR-17's order *is* the meaning, and `ensure_can_ingest` refuses a crawl source
  without an approved ToS review; a set throws the order away.
- **Ticketmaster's country set** — 19 countries as a module constant, not the provider's
  prose coverage. The official page states coverage in prose and says more countries are
  added continuously; we hold the list that is true today for countries the catalog has
  cities in, and widening it is a reviewed commit.
- **"Disabled" means** — Cannot be registered, not merely quiet. A disabled template that
  only hid itself would be settled by whoever was paying attention.
- **The provisioning's audit row** — Carries the city id and never the city name; the
  `Source` rows' own audit rows keep their city, because a source's city is a public
  fact about a place while a person's city is weak location data about a real person.
- **A retry** — No. The `CityProvisioning` row's existence means "provisioned", whatever its
  status says. A reader's pick is not a retry request: they did not know anything failed,
  and a retry would be invisible to them. A retry belongs to a person or to the scheduler
  (item 8's probation job).
- **A city the catalog does not hold** — Nothing happens at all. The stored preference
  still says whatever the reader picked; it is simply not provisioned. Minting a `City`
  would put a place into the registry that no reader chose.
- **The service's arguments** — The name only, never the country. A country supplied from
  the caller is a second source of truth, and a country that disagrees with the catalog row
  mints a *second* `City` for the same place — the exact split `domain.cities` exists to
  prevent, happening silently.
- **The lock** — `pg_advisory_xact_lock` on the city id, in its own key space
  (`b"eventpulse24-cty"`, separate from the personal path's `b"eventpulse24-onb"`). A row
  lock cannot lock a row that does not exist, and the interesting case is exactly that one.
- **The credential filter** — Driven by `provider_keys.PROVIDER_KEYS`; one table of "hosts
  that need a key", not two. Exact hosts, never suffixes.
- **The status** — `collecting`, not `live`. The city has no events until the scheduler has
  run and a source has answered. `live` is the ingest path's word; `yielded_nothing` and
  `paused` are item 8's.
- **The zero-yield counter** — On `Source`, beside `consecutive_failures`, and moved inside
  `ingest_source._close`'s existing transaction. A source is what actually goes quiet; a
  city-level counter would condemn a city with one dead source and one healthy one.
- **The threshold** — Three runs, in `shared/constants.py` alone (AD-8). Three, not one:
  at a four-hour cadence that is about twelve hours of doing nothing, which is long enough
  to be sure and short enough to matter. The threshold is in *runs*, not hours, so a cadence
  change does not silently change the policy.
- **A 304** — **Leaves** the counter alone. It proves neither emptiness nor content;
  resetting would let a source alternate "empty" / "304" forever and never be condemned.
  Only a move on evidence counts.
- **`unchanged` is yield** — The most consequential line in item 8. It is what a *healthy*
  source returns on every poll after the first; without it every healthy source would accrue
  a zero-yield run per poll and be paused after twelve hours of doing its job perfectly.
- **Publication is narrow** — Only `new` and `superseded` move a city to `live`. Yield is
  not publication: a city that re-affirms old events forever is covered and producing, but
  it never *published* anything, and "live" must mean "there are events in this city's
  catalogue".
- **`live` is terminal** — A drought may pause a `live` city's source; it cannot un-publish
  the city. State B (covered, quiet) and state C (never produced anything) are different
  facts.
- **The pause reason** — A column on the row, not the audit trail. The probation needs "is
  it paused, and by whom, *right now*"; the audit log is for accountability, the column is
  for state, and `IngestionAuditEntry` is retained 24 months. The audit `details` stay
  exactly `{"from", "to"}`. An empty reason is read conservatively, as a hand-pause.
- **The city link** — A nullable `PROTECT` FK (`Source.city_ref`), mirroring
  `Venue.city_ref`. A text join on `Source.city` would miss rows ("Portland, Oregon"
  against a catalog row of "Portland, OR"). The registry never resolves the name — it
  stores the row the provisioning service already resolved, because a second resolver would
  mint a second `City` for the same place.
- **When the probation runs** — In the ingest path, after the run's transaction commits.
  Not on a scheduler tick: the `tick()` enqueue list is pinned by exact equality, and a city
  that yields nothing should say so the moment it is known. The counter moves *inside* the
  run's transaction; the city-wide consequence runs *after* it, in its own transaction —
  running it inside would deadlock two concurrent runs of one city's two sources.
- **Two transactions, never nested** — `pause_source` opens its own atomic block and writes
  its own audit row; the city's re-decision opens another. Nesting them would invert the
  lock order against a concurrent hand-pause.
- **A probation failure** — Does not fail a successful ingest. The run's outcome is already
  recorded; the city is one step behind until the next run, which is a smaller harm than a
  failed ingest.
- **What a re-pick re-opens** — Only `yielded_nothing`. A `live` city stays `live`; a
  `paused` city stays `paused`, because **an editor's pause is not undone by a reader picking
  the city**. A `yielded_nothing` city resumes: the sources are looked up first (a duplicate
  URL *raises*, it never updates), paused ones are resumed, missing ones are registered, the
  `city_ref` is backfilled, and the counter is reset.

