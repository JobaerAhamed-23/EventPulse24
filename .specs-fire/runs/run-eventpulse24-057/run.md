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
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: city-coverage-request
    intent: city-picker-and-auto-collection
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: home-city-dropdown-catalog
    intent: city-picker-and-auto-collection
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
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
9. **browse-collecting-states** (confirm) — completed
10. **city-coverage-request** (confirm) — completed
11. **home-city-dropdown-catalog** (confirm) — completed


## Current Item
(all completed)

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
- `backend/apps/ingestion/services/city_status_read.py` — NEW: the read service that hands
  the provisioning status to the surfaces. It reads and never writes — a read that minted a
  `City` would put a place into the registry that no reader chose
- `backend/tests/ingestion/test_city_status_read.py` — NEW: 19 tests, 100% coverage of the
  service, including the "this name normalises to nothing" guard
- `frontend/tests/browse-states.test.tsx` — NEW: the four honest states on Browse, and the
  pairwise tests that hold the three treatments apart
- `frontend/tests/city-page-states.test.tsx` — NEW: the city page's degradation, and what
  the collection status may add to it
- `frontend/tests/city-collection-vocabulary.test.ts` — NEW: the frontend's status set, held
  exactly to the backend's — read from the model's `Status.choices` and from the two
  components that branch on it
- `backend/apps/ingestion/services/coverage_requests.py` — NEW: the command behind the ask —
  the throttle, the city lookup, the upsert and the audit row, all in one transaction
- `backend/apps/ingestion/coverage_api.py` — NEW: `POST /api/catalog/coverage-requests`, with
  `auth=current_user` on the router
- `backend/apps/ingestion/schemas.py` — NEW: `CoverageRequestIn` and `CoverageRequestOut`
- `backend/apps/ingestion/migrations/0017_citycoveragerequest.py` — NEW:
  `CreateModel CityCoverageRequest`, with the named unique constraint
- `backend/tests/ingestion/test_coverage_requests.py` — NEW: 30 tests, 100% coverage of the
  service — the one-row guarantee, the count, the never-mints refusal, AD-13, the audit and
  the throttle
- `backend/tests/api/test_coverage_request_api.py` — NEW: 12 tests — the endpoint's contract
  (401/201/422/429), the idempotence, and the body's user id being ignored
- `frontend/components/browse/coverage-request-control.tsx` — NEW: the client island — idle,
  busy, recorded, failed
- `frontend/tests/browse-coverage-request.test.tsx` — NEW: 24 tests over the control's four
  states
- `.specs-fire/runs/run-eventpulse24-057/plan-city-coverage-request.md` — the item's plan
- `.specs-fire/runs/run-eventpulse24-057/test-report-city-coverage-request.md` — the
  AC-by-AC validation and the mutation table
- `.specs-fire/runs/run-eventpulse24-057/review-report-city-coverage-request.md` — the
  findings and the architecture notes
- `.specs-fire/runs/run-eventpulse24-057/walkthrough-city-coverage-request.md` — the
  walkthrough — the decisions, the rules held, the risks
- `.specs-fire/runs/run-eventpulse24-057/plan-home-city-dropdown-catalog.md` — the item's
  plan
- `.specs-fire/runs/run-eventpulse24-057/test-report-home-city-dropdown-catalog.md` — the
  AC-by-AC validation and the mutation table
- `.specs-fire/runs/run-eventpulse24-057/review-report-home-city-dropdown-catalog.md` —
  the findings and the architecture notes
- `.specs-fire/runs/run-eventpulse24-057/walkthrough-home-city-dropdown-catalog.md` — the
  walkthrough — the decisions, the rules held, the risks

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
- `backend/apps/personalization/services/browse_read.py` — reads the collection status and
  carries it on `BrowsePage`
- `backend/apps/personalization/schemas.py` — `BrowseOut.city_collection_status`
- `backend/apps/personalization/api.py` — passes the status through to the response
- `backend/apps/ingestion/services/city_read.py` — carries the status on `CityPage`
- `backend/apps/catalog/schemas.py` — `CityPageOut.city_collection_status`
- `backend/tests/personalization/test_browse_read.py` — 5 tests added; the query-count
  bound raised from 1 to 2, with the reason recorded
- `backend/tests/personalization/test_browse_api.py` — 4 tests added
- `backend/tests/api/test_city_page_api.py` — 4 tests added; the query-count bound raised
  from 3 to 4, with the reason recorded
- `frontend/components/browse/browse-states.tsx` — `BrowseCollecting` and `BrowseNoSources`
- `frontend/app/browse/page.tsx` — the five-way branch: no city, collecting, no sources,
  quiet, ordinary
- `frontend/components/city-page/city-page.tsx` — `collectionNote`: one added sentence, in
  the sparse state only
- `frontend/components/city-page/city-page.test.tsx` — the fixture carries the new field
- `frontend/tests/endpoint-coverage.test.ts` — the `GET /api/public/cities` declaration,
  which item 11 removes when the picker calls the endpoint
- `frontend/lib/api/{openapi.json,schema.ts}` — regenerated by `make client`
- `.specs-fire/runs/run-eventpulse24-057/mutation/mutation_probe.py` — eight item-9
  mutations, and vitest support so the probe covers both halves of the application
- `backend/apps/ingestion/models.py` — `CityCoverageRequest` — the city FK, the counter, the
  named constraint, the count check
- `backend/apps/ingestion/admin.py` — `CityCoverageRequestAdmin` — read-only; editorial reads
  the queue, readers create the rows
- `backend/shared/constants.py` — `COVERAGE_REQUEST_LIMIT` and
  `COVERAGE_REQUEST_WINDOW_SECONDS`
- `backend/config/api.py` — the `/catalog` router mount
- `backend/tests/ingestion/test_models.py` — the model enumeration and the retention-category
  map
- `backend/tests/wall/test_schema_placement.py` — the catalog table enumeration
- `backend/tests/architecture/test_write_ownership.py` — `ingestion_citycoveragerequest` →
  `ingestion`
- `backend/tests/architecture/test_no_direct_writes.py` — `coverage_api.py` added to the
  surface list
- `backend/tests/architecture/test_digest_composition_separation.py` — `coverage_api.py` added
  to the request-module list
- `frontend/components/browse/browse-states.tsx` — `BrowseCollecting` gained the same
  `coverageRequest` slot — so the absence is a decision, not an accident
- `frontend/app/browse/page.tsx` — the control is built once at the page level, guarded by
  `hasNoSources`
- `frontend/tests/browse-states.test.tsx` — the partition: the control is offered in the
  no-sources family and nowhere else
- `frontend/lib/api/{openapi.json,schema.ts}` — regenerated by `make client`
- `.specs-fire/runs/run-eventpulse24-057/mutation/mutation_probe.py` — ten item-10 mutations,
  and the corrections to the mint and guard mutations
- `frontend/lib/home-city-read.ts` — the read calls `GET /api/public/cities`, and `choices`
  is `CityChoice[]` rather than `string[]`
- `frontend/components/settings/home-city.tsx` — the options render the label and submit
  the value; the stored city is matched by value and kept; the docstring's rewrite
  paragraph is replaced
- `frontend/components/settings/place-settings.tsx` — the choices prop's type
- `frontend/components/settings/home-city.test.tsx` — rewritten: 15 tests over the
  label/value boundary, the stored city, and the placeholder
- `frontend/components/settings/place-settings.test.tsx` — the fixture carries the
  catalog's pairs
- `frontend/app/settings/profile/page.test.tsx` — the fixture carries the catalog's
  pairs; two assertions use the catalog's strings
- `frontend/tests/profile-a11y.test.tsx` — the fixture carries the catalog's pairs
- `frontend/tests/endpoint-coverage.test.ts` — the `GET /api/public/cities` declaration
  comes out of `DECLARED_UNCALLED`
- `.specs-fire/runs/run-eventpulse24-057/mutation/mutation_probe.py` — seven item-11
  mutations

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
- **How the status reaches the payload** — A new ingestion service handing over a frozen
  dataclass. AD-3 forbids the surfaces importing `apps.ingestion.models`, and the contract
  protects the *models module*, not the app — `catalog_read`, `preview_read` and
  `city_read` already establish the seam.
- **How the read finds a city without creating one** — Its own lookup, never
  `resolve_city`. `resolve_city` *mints* a `City`, and a read that minted one would put a
  place into the registry that no reader chose, every time somebody opened Browse for an
  unprovisioned city.
- **The query-count guards rose by one** — Raised honestly, with the reason in the comment.
  The status is a separate fact from the pool and comes from a different table, so one
  query cannot serve both without a join that would multiply the pool's rows. A raised
  bound with a reason is not a weakened test; a raised bound without one is.
- **Which states share a treatment** — Three treatments, in two families. `quiet` and
  `noCity` share the quiet treatment; `noSources`, `paused`, `noProviders` and `failed`
  share the no-sources treatment. A collapse of the *groups* is the failure this item
  exists to catch; a collapse within a group is the design, and the AC says so for
  `paused`.
- **Where item 10's control goes** — A slot: `BrowseNoSources` takes a `coverageRequest`
  prop. The slot is empty today, so it offers the reader nothing it cannot do, and item 10
  fills it in the no-sources states only.
- **The status vocabulary is read, not written down** — The test reads the model's
  `Status.choices` and the components' own `status === "..."` comparisons. A hand-written
  list would have missed the sixth status (`failed`), and the surface would have said
  "Nothing nearby tonight" about a city whose provisioning had failed.
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
- **Where the coverage-request row lives** — On the `catalog` side, in `apps.ingestion`.
  The row is about a *place*. A per-user row would make the uniqueness constraint
  `(user, city)` — a different guarantee — force the editorial queue to aggregate across
  readers to find the count that is already the stored thing, and put a user id beside a
  city.
- **A counter, not a per-user join table** — The editorial question is "how many people want
  this city covered?", and the answer to that is a number. "Did *this* reader ask?" has no
  use and no reader who could act on it.
- **The uniqueness is a named constraint** — `city_coverage_request_city_uq` on
  `fields=["city"]`. An auto-named constraint cannot be asserted by name, and the AC asks
  for a database-level test; the repo's `violates()` helper reads the name out of the
  error. The *fields* are asserted too, because a constraint on `(city, request_count)`
  would carry the same name and would still permit a second row at a different count.
- **The endpoint's home** — An `apps.ingestion` router mounted at `/api/catalog`, with
  `auth=current_user` **on the router**, so the reader's id comes from the session and never
  from a payload. A `personalization` router would misfile a catalog row. The `/catalog`
  prefix is the public catalog's, and this one carries auth because **it is a write** — the
  public catalog's session-free rule is about its answers.
- **A request never mints a city** — The cities automatic collection cannot reach are the
  ones that already have a provisioning row, because provisioning wrote their `City` row.
  A city we have never heard of is a *pick*, and a pick provisions immediately — a better
  answer than queueing it. So the endpoint refuses with the project's own
  `UnknownHomeCityError` (422, `unknown_home_city`) and the reader is sent to the picker.
- **The throttle runs before the idempotence shortcut** — A repeat still spends an attempt;
  a limit a repeat could slip past is not a limit. The `event_reports.py` rule, for the same
  reason, and the limit is the same number for the same reason.
- **`PROTECT`, not `CASCADE`** — A city is never deleted, and a cascading delete would mean
  a coverage request could vanish without anybody deciding to.
- **The control's placement is structural** — The node is built once at the page level and
  guarded by `hasNoSources`, and every state that could hold it has the slot. "Only there"
  is then a fact about where the page places the node, not a condition inside the control
  that a later edit could widen. The mutation check forced this shape.
- **The count is on the wire and not on the screen** — A reader told "you are the 47th person
  to ask" is being told something about a crowd, and the product's voice is calm.
- **Which endpoint the picker reads** — `GET /api/public/cities`, not the preview's list.
  The catalog is a map of the world and the preview's list is a mirror of what we happen
  to have. **A reader in a city nothing has been collected for is the most important
  reader to offer it to** — and the run's guarantee is hollow without it.
- **The label is read; the value is stored** — The catalog's two forms are different
  strings on purpose, and a native `<select>` already separates an option's text from its
  value, so nothing has to translate between them. "Atlanta, Georgia" and "Tbilisi,
  Georgia" differ only in the first word — a control that showed the value would offer
  two near-identical entries, and one that submitted the label would store a string the
  server refuses.
- **The stored city is matched by its *value*, never by its label** — The stored city is
  "Portland, OR" and its label is "Portland, Oregon". A control that matched on the label
  would not find it, would synthesise a second option, and would offer the reader the
  same city twice under two spellings.
- **A stored city the catalog no longer holds shows itself as its own label** — The
  catalog's disambiguating form for a city it does not hold is unknown, and inventing one
  would be a fabrication. The alternative — dropping the option — would render the select
  blank, which is a worse lie.
- **Why the control is still a select** — The catalog's size and the catalog's canonical
  spellings. **The old reason is false**: the server no longer silently replaces a city
  with a fallback, because a *chosen* city outside the catalog is now refused. A
  docstring that explains a decision with a false reason sends the next reader looking
  for a rewrite that no longer happens.
- **The declaration's removal is the second half of a two-sided guard** — The coverage
  test is the only thing that notices the picker's source of truth changed: an endpoint
  with no caller and no declaration is an orphan, and a declaration with a caller is a
  stale exemption. **Both directions are under test**, and the removal is the half that
  is easy to undo by accident.
- **The preview's city list keeps its caller** — It answers a different question — which
  cities can the Pulse Preview serve *right now* — and the preview component is where it
  belongs.
- **The `fallback` note is not vestigial** — Only a *chosen* city outside the catalog is
  refused; a geo guess and a backfill still fall back, and their accounts still carry
  one.
