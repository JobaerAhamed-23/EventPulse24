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
    status: pending
    current_phase: null
    checkpoint_state: none
    current_checkpoint: null
  - id: digest-read-api
    intent: pulse-digest-and-trust
    mode: confirm
    status: pending
    current_phase: null
    checkpoint_state: none
    current_checkpoint: null
  - id: event-detail-api
    intent: pulse-digest-and-trust
    mode: confirm
    status: pending
    current_phase: null
    checkpoint_state: none
    current_checkpoint: null
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
current_item: digest-composition-service
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
5. **digest-composition-service** (validate) — pending
6. **digest-read-api** (confirm) — pending
7. **event-detail-api** (confirm) — pending
8. **digest-scheduling** (confirm) — pending
9. **frontend-pulse-card** (confirm) — pending
10. **frontend-digest-home** (confirm) — pending
11. **frontend-event-detail** (confirm) — pending
12. **e2e-proof-and-contract-tests** (confirm) — pending


## Current Item
digest-composition-service (validate)

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
