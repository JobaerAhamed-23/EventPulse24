---
id: run-eventpulse24-021
scope: wide
work_items:
  - id: digest-ranking-domain
    intent: pulse-digest-and-trust
    mode: validate
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: digest-composition-models
    intent: pulse-digest-and-trust
    mode: validate
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: digest-user-preferences
    intent: pulse-digest-and-trust
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: digest-candidate-reads
    intent: pulse-digest-and-trust
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: digest-composition-service
    intent: pulse-digest-and-trust
    mode: validate
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: digest-read-api
    intent: pulse-digest-and-trust
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: event-detail-api
    intent: pulse-digest-and-trust
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: digest-scheduling
    intent: pulse-digest-and-trust
    mode: confirm
    status: pending
    current_phase: null
    checkpoint_state: none
    current_checkpoint: null
  - id: frontend-pulse-card
    intent: pulse-digest-and-trust
    mode: confirm
    status: pending
    current_phase: null
    checkpoint_state: none
    current_checkpoint: null
  - id: frontend-digest-home
    intent: pulse-digest-and-trust
    mode: confirm
    status: pending
    current_phase: null
    checkpoint_state: none
    current_checkpoint: null
  - id: frontend-event-detail
    intent: pulse-digest-and-trust
    mode: confirm
    status: pending
    current_phase: null
    checkpoint_state: none
    current_checkpoint: null
  - id: e2e-proof-and-contract-tests
    intent: pulse-digest-and-trust
    mode: confirm
    status: pending
    current_phase: null
    checkpoint_state: none
    current_checkpoint: null
current_item: digest-scheduling
status: in_progress
started: 2026-10-30T12:40:28.978Z
completed: null
---

# Run: run-eventpulse24-021

## Scope
wide (12 work items)

## Work Items
1. **digest-ranking-domain** (validate) — completed
2. **digest-composition-models** (validate) — completed
3. **digest-user-preferences** (confirm) — completed
4. **digest-candidate-reads** (confirm) — completed
5. **digest-composition-service** (validate) — completed
6. **digest-read-api** (confirm) — completed
7. **event-detail-api** (confirm) — completed
8. **digest-scheduling** (confirm) — pending
9. **frontend-pulse-card** (confirm) — pending
10. **frontend-digest-home** (confirm) — pending
11. **frontend-event-detail** (confirm) — pending
12. **e2e-proof-and-contract-tests** (confirm) — pending


## Current Item
digest-scheduling (confirm)

## Files Created
- `backend/apps/personalization/migrations/0007_digestcomposition_pulsedigest.py`
- `backend/apps/personalization/migrations/0008_digestcomposition_digest_composition_slot_ck.py`
- `backend/tests/personalization/test_digest_models.py`
- `backend/apps/personalization/services/digest_preferences.py` — the home-city and
  opt-out commands, the coverage rule, the backfill
- `backend/config/management/commands/backfill_digest_cities.py` — the idempotent
  backfill, with `--dry-run`
- `backend/tests/personalization/test_digest_preferences.py` — 33 tests
- `backend/tests/personalization/test_digest_preference_model.py` — 11 tests
- `backend/apps/ingestion/services/source_badges.py` — the Source Badge leaf module:
  the mapping from a source's type and acquisition method to a badge type, imported by
  both the Preview's read and the Digest's candidate read
- `backend/apps/personalization/services/digest_candidates.py` — the personal-side
  reads: the user's own events in the 48-hour window, their saves, and the conflict
  ids that come with them
- `backend/tests/ingestion/test_public_candidates.py` — 35 tests
- `backend/tests/personalization/test_digest_candidates.py` — 32 tests
- `.specs-fire/intents/pulse-digest-and-trust/work-items/digest-candidate-reads-design.md`
  — D1–D15 plus D5a, and what the code review changed
- `.specs-fire/runs/run-eventpulse24-021/test-report-digest-candidate-reads.md`
- `.specs-fire/runs/run-eventpulse24-021/review-report-digest-candidate-reads.md`
- `backend/apps/personalization/services/digest_composition.py` — the composition
  command: it reads the three pools, scores them, assigns the three slots, and writes
  one `PulseDigest` with its `DigestComposition` rows
- `backend/apps/ingestion/services/chip_matching.py` — the **event's** half of the
  interest overlap: the title and description matched against the keyword table,
  whole-word, in the layer that owns the content (AD-9)
- `backend/tests/personalization/test_digest_composition.py` — 48 tests
- `backend/tests/ingestion/test_chip_matching.py` — 22 tests
- `.specs-fire/intents/pulse-digest-and-trust/work-items/digest-composition-service-design.md`
  — D1–D15 plus D8b, and what the code review changed
- `.specs-fire/runs/run-eventpulse24-021/test-report-digest-composition-service.md`
- `.specs-fire/runs/run-eventpulse24-021/review-report-digest-composition-service.md`
- `backend/apps/personalization/services/digest_dates.py` — the shared local-date rule:
  `local_date_for(*, now, zone_name)` — the one place that decides which calendar day
  `now` falls on for the user
- `backend/apps/personalization/services/digest_read.py` — the read of the persisted
  rows: `read_digest(*, user_id, now) -> DigestRead`, with the three states, the card
  projection and the live conflict flag
- `backend/tests/personalization/test_digest_api.py` — 30 tests
- `.specs-fire/intents/pulse-digest-and-trust/work-items/digest-read-api-design.md`
  — D1–D12 plus D4b, and what the code review changed
- `.specs-fire/runs/run-eventpulse24-021/test-report-digest-read-api.md`
- `.specs-fire/runs/run-eventpulse24-021/review-report-digest-read-api.md`
- `backend/apps/personalization/detail_api.py` — the Detail Screen's two endpoints:
  `GET /api/events/{id}` and `POST /api/events/{id}/opened`. The router has **no**
  `auth=`, because the route serves two audiences and a router's `auth=` is
  all-or-nothing: the read calls `unauthenticated_user` and branches, the write calls
  `current_user`
- `backend/apps/personalization/services/detail_read.py` — the read of the persisted
  rows: `read_event_detail(*, event_id, user_id, now) -> EventDetail`, with the public
  facts, the persisted breakdown, the saved state and the bucketed neighbour count
- `backend/apps/personalization/services/neighbor_count.py` — the k-anonymous count,
  suppressed **before** the number is formed: `NeighborCount` holds a bucket key and
  **no count field**, so there is nothing for a later change to leak
- `backend/apps/personalization/services/detail_opens.py` — the named command that
  records the detail-open signal, with its audit row in the same transaction (AD-5)
- `backend/apps/personalization/migrations/0010_eventdetailopen.py`
- `backend/tests/personalization/test_event_detail_api.py` — 52 tests
- `.specs-fire/intents/pulse-digest-and-trust/work-items/event-detail-api-design.md`
  — D1–D13, and what the code review changed
- `.specs-fire/runs/run-eventpulse24-021/test-report-event-detail-api.md`
- `.specs-fire/runs/run-eventpulse24-021/review-report-event-detail-api.md`

## Files Modified
- `backend/apps/personalization/models.py` — `PulseDigest`, `DigestComposition`, `DIGEST_SLOT_ORDER`
- `backend/tests/personalization/factories.py` — the two factories
- `backend/tests/personalization/test_model_structure.py`
- `backend/tests/personalization/test_grants.py`
- `backend/apps/personalization/models.py` — `DigestPreference`'s three columns, the
  `CitySource` enum, the city/source agreement constraint
- `backend/apps/personalization/services/onboarding.py` — `set_digest_preference` gains
  the city and the flag; `OnboardingState` carries them
- `backend/apps/personalization/schemas.py` — `DigestPreferenceIn`/`Out`
- `backend/apps/personalization/api.py` — the endpoint carries the new fields
- `backend/apps/identity/services/sign_up.py` — the sign-up carry
- `backend/apps/identity/schemas.py` — `SignUpIn.city`
- `backend/apps/identity/api.py` — the endpoint passes the city through
- `backend/tests/personalization/test_onboarding_api.py` — 4 added tests
- `backend/tests/personalization/factories.py` — `DigestPreferenceFactory`
- `frontend/lib/api/openapi.json`, `frontend/lib/api/schema.ts` — the regenerated contract
- `frontend/components/onboarding/onboarding-flow.test.tsx` — the fixture's new fields
- `backend/apps/ingestion/services/catalog_read.py` — the public candidate read, the
  batched `get_public_events` lookup, the pool constants
- `backend/apps/ingestion/services/preview_read.py` — the badge wrapper over
  `source_badges`; the badge constants are no longer re-exported here
- `backend/shared/constants.py` — `DIGEST_STALE_TTL_MULTIPLIER`
- `backend/tests/ingestion/test_preview_read.py` — the badge imports move to
  `source_badges`
- `backend/tests/architecture/test_event_fit_separation.py` — two added tests: the
  candidate read reaches no Event Fit, and the badge leaf reaches neither the Event
  Fit nor `personalization`
- `backend/apps/ingestion/services/catalog_read.py` — `PublicEventCandidate` gains
  `chip_keys`, computed from the event's title and description
- `backend/shared/constants.py` — `INTEREST_CHIP_KEYWORDS`, the table that gives an
  **event** its interest chips; the interest term is the largest weight in the
  Relevance Pulse and was pinned to `0.0` without it
- `backend/apps/personalization/schemas.py` — `DigestStatus`, `DigestCardOut`,
  `DigestOut`
- `backend/apps/personalization/api.py` — `GET /api/personal/digest`
- `backend/apps/personalization/services/digest_composition.py` — `_local_date` replaced
  by the shared `local_date_for`
- `backend/apps/ingestion/services/catalog_read.py` — `PublicEventDetail` and
  `get_public_event_detail`: a **new** published read, because widening `PublicEvent`
  would have silently changed the public catalog's wire shape
- `backend/apps/personalization/models.py` — `EventDetailOpen`, the qualifying-signal
  model: one row per `(user, event)`, `PREFERENCE_SIGNALS`
- `backend/apps/personalization/schemas.py` — `WhyThisOut`, `DetailPersonalOut`,
  `EventDetailFactsOut`, `EventDetailOut`
- `backend/config/api.py` — the `/events` router mounted, with the two-audience rule
  written down
- `backend/tests/architecture/test_write_ownership.py` —
  `personalization_eventdetailopen` added to `TABLE_OWNERS`
- `backend/tests/personalization/factories.py` — `EventDetailOpenFactory`
- `frontend/lib/api/openapi.json`, `frontend/lib/api/schema.ts` — the regenerated contract

## Decisions
- **D4 — retention category `ACCOUNT_CONTENT`** for both tables. It is the only category
  under which AD-10's "most recent composition for that `(user, event)` pair" promise
  holds: `PREFERENCE_SIGNALS`' 12-month rolling window would delete an event's only
  explanation while the user is still looking at it. **No source states a window for
  this table** — the gap is recorded, not resolved.
- **The `slot` check constraint** (added by the code review). Django's `choices` are not
  a database constraint, so a row with a fourth slot was writable; the read sorts
  against `DIGEST_SLOT_ORDER`, and a slot outside it would silently vanish from the
  digest.
- **The slot order lives once**, as the module-level `DIGEST_SLOT_ORDER` — a
  `TextChoices` member holds a scalar, so a tuple inside the enum class would be read
  as an enum member and fail at import.
- **D1 — the home city joins `DigestPreference`** as three columns, not a new table.
  The city is a third coordinate of the same question the row already answers — where
  and when the digest arrives — and the opt-out says what goes *into* this user's
  digest. A separate table would mean an owner, a retention category, a backfill and a
  second lookup for information that belongs in the same row.
- **D3 — the coverage rule and the NYC fallback are reused, not reimplemented.**
  `list_supported_cities()` and `PREVIEW_FALLBACK_CITY` already exist and are already
  tested. Two rules for "which cities may a user be in" would be two rules that could
  disagree, and the disagreement would surface as a digest ranking on a city the
  preview says is not served.
- **D15 — the transaction boundaries differ, and both are argued.**
  The digest-preference endpoint writes the delivery time and the city in **one**
  transaction: a half-applied decision is worse than a failed one. The sign-up path
  writes the city **outside** the account's: an account that exists without its audit
  row is a hole, while an account that exists without a city is a state the digest
  already handles and the backfill fills.
- **The fallback is not coverage-checked.** The server chose it, so there is nothing to
  check — and checking it would rewrite the backfill's source from `backfill` to
  `fallback`, making a backfilled city indistinguishable from a rejected one.
- **The endpoint cannot clear the city.** A `null` city and an omitted city are the
  same value in Pydantic, so the shape cannot say which one it means. It must not
  guess: guessing "clear" would wipe the city of every client that sends `null`. So
  `null` means "leave it alone", and clearing is reached through the service.
- **D2 — the pool is bounded in SQL as well as in Python.** The staleness filter runs
  in Python (the per-source bound is not expressible in SQL in this Django version —
  six routes were tried and refused), so an unbounded fetch would hand every row to
  Python before the first candidate was found. The fetch over-fetches by
  `CANDIDATE_OVERFETCH_FACTOR = 4` and the SQL carries a `LIMIT`. The trade is
  stated: a catalog that is mostly stale may fill the pool with fewer than `limit`
  rows.
- **A `limit` of zero or less returns nothing.** `max(1, ...)` — the usual dodge for a
  `LIMIT 0` — quietly turns "none" into "one", and a caller that asks for no
  candidates must not be handed one.
- **D5/D5a — the Source Badge is resolved on the catalog side, and the mapping
  needed a leaf module of its own.** The mapping already existed in `preview_read`,
  but that module imports the Event Fit, and `personalization` imports
  `catalog_read` — so importing it from there would have put the Event Fit inside
  `personalization` by another name, and the `event-fit-separation` contract could
  not have caught it (`allow_indirect_imports = true`). `source_badges` is now a leaf
  that imports the `Source` choices and nothing else; two architecture tests pin it.
  The badge constants are **not** re-exported from `preview_read` — one rule, one
  home.
- **D6 — `superseded_by` is not filtered on separately.** The database constraint
  `event_superseded_consistent_ck` already makes the two states mutually exclusive,
  so a second filter would be unreachable code and a false comfort.
- **A cancelled or postponed event is a candidate.** Dropping it would hide the
  cancellation rather than report it, and the user would see an event that is not
  happening as though it were.
- **The confidences are carried as `Decimal`, not as strings.** The gates are exact
  comparisons, and a string compared against a `Decimal` is not exact — which would
  make the boundary tests meaningless.
- **D8b — the saved read is bounded but not windowed.** The 48-hour window bounds how
  far ahead the digest *looks*; a save is a fact about the user's own present, and
  bounding it by the window dropped saves for an event later that week. The saved
  read bounds on `start_utc >= now` and nothing above, and its catalog lookup is
  batched into one query.
- **The staleness comparison is inclusive at the bound.** "Older than" is exclusive,
  and an event exactly at the bound is not older than it. The bound is measured from
  `Event.last_seen_at` — when the catalog last saw the event at the source — and not
  from `updated_at`, which moves whenever *we* touch the row.
- **The wall is asserted on the alias, not on the table names.** The public read's
  test wraps both connections and asserts the personal alias was never queried. The
  personal read's test asserts on table names instead, because there the catalog side
  is legitimately reached through a published service (AD-2 forbids importing
  `apps.ingestion.models` from `apps.personalization`).
- **The interest term was inert, and this item built the missing half.** The
  Relevance Pulse's interest term is `0.45 × interest_overlap`, and `interest_overlap`
  needs the **event's** chip keys as well as the user's. The event's half existed
  nowhere: `Event` has no category field and no read produced one. So the term was
  pinned to `0.0` for every candidate — which the ranking domain calls an *inert
  weight*: "the published formula would stay arithmetically checkable and still produce
  a different number from the one on the card, which is a worse trust failure than a
  reduced formula because it looks verifiable." With it inert the score could never
  exceed `0.55`, so no card could reach bucket 4 or 5, and `score_slot_3`'s inverted
  term (`1 − 0.0`) was identical to the plain score — the serendipity slot inverted
  nothing. The matching is now a pure function in the layer that owns the content
  (AD-9), and the acceptance criteria could not have been met without it.
- **The chip matching is a pure function, not a stored column.** A `chip_keys` column
  on `Event` would need a migration, a write-time computation and a backfill for every
  existing event — and it would be *wrong* the moment the keyword table changed. A new
  keyword improves the matching for every event at once, with no migration.
- **Hyphens and apostrophes are normalised on both sides of the match.** "story-time"
  and "storytime" are the same word to a reader, so either spelling of a keyword
  matches either spelling of the text. The first implementation kept the hyphen inside
  the token and so did not deliver what its own docstring promised; the test found it.
- **The personal event *is* Slot 1, and the public event is a fallback.** FR-5 puts
  "Personal Events eligible" first and makes the public event conditional on "if no
  Personal Event is eligible", so a personal event takes Slot 1 even when a public
  event would have outscored it. This is the opposite of what a "highest score wins"
  implementation does, and it is the point of the slot.
- **The empty state needs both halves.** "No qualifying public event" is not enough:
  a user with a personal event tomorrow and nothing else in the catalog has a card to
  show, and a digest saying "nothing today" would be wrong.
- **A short digest is not padded.** A two-card day is composed with two cards.
  Padding would mean relaxing a gate — the staleness bound or a confidence threshold —
  and publishing a card the rules forbid, with the user having no way to know it was
  filler. And the empty state would lie: two events *is* something happening near you.
- **Hysteresis is within-day only, and nothing is inherited across days.** The work
  item's criteria said both "applied across days by reading the previous day's
  composition" and "across days it resets" — two clauses that cannot both hold.
  EXPERIENCE.md §4 is the canonical source: "**Across days, hysteresis resets** …
  **No persistent bucket is stored between days.**" So the service passes
  `previous_bucket=None`. The conflict is recorded rather than silently resolved.
- **The re-run is a no-op under a per-user advisory lock, not a constraint violation.**
  `pulse_digest_user_date_uq` would catch a race as an `IntegrityError` that reaches
  the caller as a 500. The lock makes the second worker *wait*, see the row the first
  wrote, and return it — and it is transaction-scoped, so a crashed worker cannot
  leave a user's digest wedged.
- **The lock has its own namespace, distinct from every other lock in the codebase.**
  It does not share `digest_preferences.py`'s: the two commands write different rows —
  the preference and the composition — and a lock is only a mutual-exclusion device
  when it excludes the same thing.
- **The user's country is empty, and the country band is `0.00`.** The
  `DigestPreference` has a city and a zone and no country. The trade is `0.10` of a
  score, and it is **stated** rather than papered over with a catalog lookup that
  would be a second read across the wall, for the *user's* city as well as the
  event's. **If the preference ever gains a country, D8 has to be revisited.**
- **The saves mark a card; they are not a candidate pool.** A saved event in another
  city is not "nearby" — a save is not a statement that the event is nearby — and a
  save the catalog dropped has no badge, so it cannot be a public composition at all.
- **The catalog reads happen outside the transaction.** AD-3 forbids a transaction
  spanning both schemas, and a catalog read inside a `personal` transaction would be
  reading across the wall even though the write is only to `personal`.
- **The audit row carries the count, the date and the emptiness — and nothing else.**
  AD-13 forbids PII and untrusted content in logs, and the audit table is a log. A
  title or a URL would be untrusted source content in a log; the event ids are already
  one indexed read away.
- **An unknown timezone falls back to UTC rather than failing.** The zone is validated
  at write time, so an unknown name means hand-edited data. A composition that raised
  would leave the user with **no digest at all**, which is worse than a digest whose
  day is computed in the fallback zone: the failure mode is a wrong day, not a missing
  card.
- **D10 was reversed — the conflict flag is on the card, read live.** The design
  originally said the card must not carry it, on the argument that a conflict is a
  *live* condition while the composition is a *fact about a day*. The reasoning is
  sound but the conclusion pointed at a surface that does not exist: there is **no
  conflict read endpoint** — `list_conflict_pairs` is a service that nothing publishes.
  And FR-58's indicator renders *on a card*, so a card that could not show it would be
  missing one of the six trust signals, and "adaptive density never hides a trust
  signal" is a locked rule. So the flag is read from the **persisted `ConflictPair`
  rows at request time** and is **never computed** (AD-21) — live in the same sense
  `tz_review_pending` is live. The composition row is untouched.
- **The conflict lookup costs two queries, and one of them is a bridge.** The open
  pairs, and the user's saves of the public cards: a pair's sides are the *personal*
  rows (a `PersonalEvent`'s id and a `SavedEvent`'s id), while a public card names the
  *catalog* event's id — so the save is what connects them. A personal card's
  `event_id` **is** the `PersonalEvent`'s id and matches directly. The bound moved
  from four to six; it is still a constant, and the save lookup is only reached once a
  pair exists to look for.
- **The `saved` flag is not a separate field.** It travels as the persisted `saved`
  Why-this tag. The save lookup exists for the *conflict*, not for the flag, and
  recomputing the flag would be recomputing an explanation.
- **D5 was reversed — the card's display facts are optional.** The first draft had a
  required `title: str` and an epoch `start_time_utc` for a card whose catalog event
  had been dropped. A card showing an empty title at 1970-01-01 tells the user
  something that is not true, and the sentinel would have been invisible in the schema
  — every consumer would have had to know that the epoch means "gone". So `title`,
  `canonical_url`, `start_time_utc`, `end_time_utc` and `start_time_tz` are all
  `None` when the facts are gone, and `catalog_event_missing=True` says why. The card
  still appears, still carries its bucket, its tags and its badge.
- **The required fields are exactly the ones the composition holds.** `event_id`,
  `slot`, `event_kind`, `tags`, `bucket`, plus the flags. AD-10 guarantees the
  *explanation* is persisted, so it can never be missing; the *display facts* live
  elsewhere and may have moved on.
- **The local-date rule is shared, not copied.** `_local_date` was promoted out of
  `digest_composition.py` into `digest_dates.py`, and both sides import it. The
  failure this prevents is silent and nasty: a read that computed a different day
  would report `not_composed` on a day that has three cards on it.
- **The response's `timezone` is the digest's, not the preference's.** The read
  resolves *today's* day from the **current** preference's zone — a user who moved may
  now be on a different day — but the response reports the **digest row's** stored
  zone. A mismatch is then visible rather than silent.
- **The three states are three distinct 200 responses.** `composed`, `empty` and
  `not_composed`. A 404 would be true of one and false of the other, and `not_composed`
  is not an error: the digest is composed by a worker (AD-11), so a read that
  composed one would be a write from a request path.
- **The query bound is on the read, and the read is counted directly.** The first
  bound was four and the read measured five — the extra two were the framework's auth
  seam (the session row and the user row), paid by every endpoint on the router and
  not the read's. The bound moved onto the service, where it means something, and the
  endpoint path got its own test: the count must not grow with the number of cards.
- **The duplicated `_read_preference` was left alone, deliberately.** Both
  `digest_composition.py` and `digest_read.py` ask the same question of the same row.
  The duplication is *already* the established answer to "how do two modules read the
  preference?" — the alternative, a shared read module for a single-row lookup, would
  be a module that exists for one function. It is recorded rather than removed.
- **The endpoint's test `NOW` is the wall clock, and that is not an inconsistency.** The
  composition service takes `now` as a parameter, so its tests choose it; the endpoint
  resolves `now` itself, so the test has to write the digest for *today's* local date.
  The first run answered `not_composed` for a digest that existed — and the fix was in
  the test, not the code.

---

## The `event-detail-api` item's decisions

- **The detail-open signal is a separate `POST`, because a `GET` that writes is
  forgeable.** Django's `require_csrf` returns early on **safe** methods, so a `GET`
  that recorded the signal would carry no CSRF check at all — and any third-party page
  can make a browser issue a `GET`. The neighbor count says "other people near you are
  interested in this"; a forgeable signal inflates it, and the count is a *trust*
  signal. So the read writes **nothing** (a test pins it) and the signal is
  `POST /api/events/{id}/opened` — session required, CSRF checked, 401 for an
  anonymous caller. The cost is a second round trip, and the trade is stated rather
  than hidden.
- **The router has no `auth=`, and that is deliberate.** The route serves two audiences
  with different rights — a signed-in user may see their own explanation, an anonymous
  visitor may see the event and nothing personal (AD-12). A router's `auth=` is
  all-or-nothing, so the two rules live in the two handlers: the read calls
  `unauthenticated_user` and branches, the write calls `current_user`.
- **`PublicEvent` was not widened.** `EventOut.from_public_event` does
  `cls(**vars(event))`, so adding a field to `PublicEvent` would have **silently
  changed the public catalog's wire shape** — and the catalog's contract is not this
  item's to change. `catalog_read` grew a **new** published read,
  `get_public_event_detail`, carrying `PublicEvent`'s fields plus `is_sold_out` and
  `description`. The design's heading said the opposite of its body; the body was
  right and the heading was corrected.
- **The description is served but never logged.** `Event.description` is *already* the
  stripped field — the ingestion pipeline strips it before storing — so it is not raw
  payload (AD-9). It is untrusted source text that is **display content**: the Detail
  Screen has to show it. It may never reach a log line, an audit row or a sort key —
  the same rule the catalog's own `EventOut` follows for the title.
- **The count is suppressed before the number is formed.** `NeighborCount` holds a
  bucket key and **no count field**; the schema has `neighbor_bucket` and no count.
  There is nothing for a later change to log, cache or leak, because there is nothing
  to leak. The test asserts the whole `personal` key set is exactly
  `{"why_this", "saved", "neighbor_bucket"}`, so a later `neighbor_count` field fails
  the test rather than shipping.
- **The threshold is 5, and the reason is stated.** FR-24's body says "≥5 qualifying
  users"; the PRD's glossary says "at least 1". The stricter rule governs, and not out
  of deference to the body text: **k-anonymity at k=1 is not anonymity**. A count of
  exactly one is the identity of one person, and the whole point of the signal is that
  it says "other people near you are interested in this" rather than "one specific
  person is".
- **The count is two reads unioned in Python, not one `COUNT(DISTINCT)` aggregate.**
  *(Revised by the code review — the design said one aggregate.)* The two signals
  live in two tables with two shapes, and a single aggregate across them needs a
  `UNION` subquery — raw SQL in an otherwise pure-ORM service. The union is also the
  shape that **cannot multiply** a user who both saved and opened: the ids go into a
  set, so a user qualifies once. The cost is one extra query, and it is a constant —
  the signed-in read is five queries, not four.
- **"Same area" is city equality, and the deviation is named.** FR-24 defines it as
  "≤2 km or same city-zip-cluster", and neither is computable — `Venue` has no
  coordinates and there is no zip data anywhere in the schema. The clause filters on
  the **event side**: a user qualifies for *this* event by saving *this* event, so
  there is no per-user city to compare against, and the event's own city is the area.
  The event's city is still read, for one reason: **an event with no venue has no area,
  and therefore no neighbours.**
- **The three states are three independent facts.** "There is no explanation" and "you
  have not saved this" are different claims, and a client that cannot tell them apart
  renders the wrong thing. `why_this`, `saved` and `neighbor_bucket` are three separate
  fields, each carried explicitly.
- **The signal stores one row per `(user, event)`, holding the most recent open.** A
  user who opened the screen ten times is still one row, so the row count is bounded
  by the number of events a user opened and not by the number of times. The 30-day
  query window is therefore exact.
- **The signal's retention category is `PREFERENCE_SIGNALS`, and a gap is recorded.**
  The count looks back 30 days; `PREFERENCE_SIGNALS`' policy is 12 months. A row can
  outlive the window that made it relevant, holding a record of what a named person
  looked at. The shape is right and the deletion job is a separate concern, so the gap
  is **recorded rather than closed** — a 30-day deletion policy on this table would
  match the window exactly, and that is a one-line change to a policy table.
- **Reviews and similar-events are absent, not present-and-empty.** Reviews are
  ASSUM-6, deferred to Phase 3+; similar-events needs attendance data that does not
  exist. A key that is always null is a promise the backend cannot keep.
- **The neighbouring sources contradict each other on the count, and the bucketed
  prose governs.** `EXPERIENCE.md` §12's own example breakdown line says "12 of your
  neighbors saved this", and `event-detail-desktop.html` renders "12 neighbors tracking
  this in Brooklyn" — both exposing an exact count that FR-24 and §12's "Neighbor Count
  Privacy" subsection explicitly forbid ("Exact counts are never exposed"). Both
  examples are wrong. Recorded because the mockup is the more persuasive artifact, and
  a later reader looking at it will find an exact count and think the implementation is
  missing it.
- **The window's boundary is pinned at the service, not at the endpoint.** The
  endpoint resolves `now` from the wall clock, so a timestamp pinned at import time is
  a few milliseconds older than the service's own `now` — and an **inclusive** boundary
  that should have qualified was one hair outside the window. `count_neighbors` takes
  `now` as a parameter, so the instant is exactly expressible there. The same lesson
  the `digest-read-api` item learned about its own `NOW`: the surface decides whether
  "now" is a parameter or a wall clock, and the test has to follow it.
- **The tier-agnostic test asserts on the SQL, not on the prose.** The first version
  read the module's source and asserted the word "pro" was absent — and the module's
  own docstring says "Pro and Free users count identically", so it failed on its own
  explanation. The assertion is now on the SQL that actually runs: the two signal
  queries are located in the captured query log and asserted to carry no tier
  predicate. A prose grep was never a meaningful test of a query's shape.
- **The anonymous path's zero-query assertion is genuine.** An anonymous request has
  no session row, so the session middleware never touches `personal` — the count of
  personal queries really is zero, not zero-after-filtering. The strongest statement
  about a leak is that the query never happened.
- **The read's query bound excludes the framework's auth seam.** Django's session
  middleware reads the session row and the user row on every request; those belong to
  the request, not to the Detail Screen's read. What is counted is the read's own work
  — the composition, the save and the count's two signal reads — and that is at most
  four, whatever the neighbour count is.
