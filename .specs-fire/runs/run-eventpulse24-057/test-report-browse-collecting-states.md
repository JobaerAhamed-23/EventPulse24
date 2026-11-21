---
run: run-eventpulse24-057
work_item: browse-collecting-states
intent: city-picker-and-auto-collection
generated: 2026-11-21
status: passed
---

# Test Report: The four honest states

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| `test_city_status_read.py` (new) | 19 | 0 | 0 | 100% |
| `test_browse_read.py` (extended) | 31 | 0 | 0 | 99% |
| `test_browse_api.py` (extended) | 15 | 0 | 0 | 97% |
| `test_city_page_api.py` (extended) | 39 | 0 | 0 | 98% |
| `browse-states.test.tsx` (new) | 30 | 0 | 0 | — |
| `city-page-states.test.tsx` (new) | 11 | 0 | 0 | — |
| `city-collection-vocabulary.test.ts` (new) | 5 | 0 | 0 | — |
| Backend suite (full) | 9036 | 0 | 0 | 98.9% |
| Frontend suite (full) | 2922 | 0 | 0 | — |

`apps/ingestion/services/city_status_read.py` at **100%** — every statement, including the
"this name normalises to nothing" guard. `lint-imports` 21 contracts kept, 0 broken.
`makemigrations --check` reports no changes.

## Acceptance Criteria Validation

### The four states on Browse

- ✅ **A collecting city says we are collecting, and names the city** —
  `frontend/tests/browse-states.test.tsx` → `the collecting state` →
  `says we are collecting, and names the city`, and `carries the city's own heading`
  (the `<h1>` is "Events in Brooklyn.", not a heading that denies the city has events).
- ✅ **The collecting state is not the quiet state** —
  `is not the quiet state` asserts both that "Nothing nearby tonight" is absent and that
  `data-browse-empty` is absent, and `replaces the hero, so there is no second heading`
  asserts the page has exactly one `<h1>` and no `data-browse-hero`.
- ✅ **The collecting state announces itself politely** —
  `announces itself politely, because the reader is waiting on it` asserts
  `role="status"` and `aria-live="polite"`.
- ✅ **A covered city that is simply quiet is not told its sources failed** —
  `the quiet state` → `is not the no-sources state — a covered city must not be told its
  sources failed`. **This is the AC that the whole item turns on**, and it has its own
  mutation (§"the mutation check", #4).
- ✅ **A city with no sources says so, and names the city** —
  `the no-sources state` → `says we have no sources, and names the city`, plus
  `is not the quiet state` and `is not the collecting state`.
- ✅ **Paused renders the same honest line as "no sources"** —
  `the paused state` → `says the same honest line as no sources`, and
  `the no-providers state` and `the failed state` for the other two members of the family.
- ✅ **A reader with no city is not told collection is under way** —
  `a user with no city` → `is not the collecting state` (asserts the marker *and* the
  copy are absent) and `is not the no-sources state`.
- ✅ **The no-sources state carries the coverage-request control; the other states do
  not** — `carries the coverage-request slot` on the no-sources, paused and failed
  states; `offers no coverage request — we are already doing the thing` on the
  collecting state; `carries no coverage request either` on the quiet state.
- ✅ **Each state has a test that fails if the states are collapsed into one** —
  `the states do not collapse into one another`, four tests, and the mutation check
  proves they can fail.

### The city's own page

- ✅ **The threshold decides whether the page shows a listing; the status only adds a
  sentence** — `frontend/tests/city-page-states.test.tsx` →
  `a published city shows its listing` → `says nothing about the collection, whatever
  the status` (a published city says nothing about the collection, in *every* status),
  and `the sparse state` → `keeps the coming-soon copy whatever the collection status`
  (six statuses, the "coming soon" copy survives all of them).
- ✅ **A collecting city gains the collecting sentence** — `adds the collecting sentence
  when we are collecting`.
- ✅ **A city with no sources gains the no-sources sentence** — `adds the no-sources
  sentence when we have no sources`, over all four members of the family.
- ✅ **A `live` city below the threshold gains nothing** — `says nothing extra when the
  collection is working`.
- ✅ **A status nobody wrote reaches the surface as silence** — `says nothing extra for a
  status nobody wrote`.

### The status reaches the payload

- ✅ **The read is a read** — `backend/tests/ingestion/test_city_status_read.py` →
  `TestTheReadNeverWrites` → `reading_an_unknown_city_does_not_mint_it`,
  `reading_writes_no_audit_row`, and `reading_a_city_with_no_provisioning_row_mints_nothing`.
  **The module's own docstring says it reads and never writes**, and the mutation check
  proves the test can fail (§"the mutation check", #2).
- ✅ **Every one of the model's six statuses comes back verbatim** —
  `TestTheStatusIsRead` → `test_every_status_is_read_verbatim`, parametrised over all six.
- ✅ **An empty status is a real answer** — `TestTheEmptyStatus`: a city with no
  provisioning row, a city that does not exist, an empty name, and a name that
  normalises to nothing.
- ✅ **Two spellings of one place are one city** —
  `test_the_status_is_read_by_the_catalogs_own_name` and
  `test_the_status_is_read_by_the_identity_key_too`.
- ✅ **The status does not change the cards** —
  `test_browse_read.py` → `the status does not change the cards`.
- ✅ **The response carries it** — `test_browse_api.py` → the response carries
  `city_collection_status`; the city page's response carries it too
  (`test_city_page_api.py`).

### The vocabulary

- ✅ **The frontend's status set is exactly the backend's** —
  `frontend/tests/city-collection-vocabulary.test.ts`:
  `recognises every status the backend has`, `recognises no status the backend does not
  have`, and `the two surfaces recognise the same vocabulary`. **The set is read from
  the components' own source**, not from a list written in the test — so the test fails
  the moment the code and the backend disagree, which is the only moment it matters.
- ✅ **The guard is not vacuous** — `the backend's vocabulary` → `is read, not assumed`
  and `the frontend's vocabulary` → `is read, not assumed` both assert the regexes
  matched something, so a regex that stopped matching would fail rather than pass every
  assertion below it.

### The architecture

- ✅ **AD-3: the surfaces do not import the models** — the import-linter's 21 contracts
  are all kept, including `models-ingestion`. The seam is
  `apps/ingestion/services/city_status_read.py`, which hands over a frozen dataclass
  (`CityCollectionStatus`) and never a model — the same contract
  `apps/ingestion/services/catalog_read.py` already established and `browse_read.py`
  already imported.
- ✅ **AD-12: the public page's response is still cacheable** — the status is a fact
  about a *place*, not about a reader, so it rides in the same cacheable response.
  `city_read.py` reads it through the same service.
- ✅ **AD-16: the provisioning status has one writer** — the surface reads it; it does
  not write it, and no denormalised column was added to `DigestPreference`. **A second
  writer of one fact would go stale the moment the probation moved a city to `live`.**
- ✅ **AD-13: no reader's city reaches a log or an audit row** — the read writes
  nothing at all, so there is nothing to leak.
- ✅ **AD-10: the surface does not re-rank** — the status changes *which* state is
  rendered, never the order or the content of the cards.

### The two query-count guards

Both were raised by one, honestly, with the reason recorded in the comment:

| Guard | Before | After | Why |
|---|---|---|---|
| `test_scoring_a_full_pool_costs_a_query_and_a_bounded_amount_of_python` | 1 | **2** | The status is a *separate* fact from the pool, and it comes from a different table (`ingestion_cityprovisioning`). One query cannot serve both without a join that would multiply the pool's rows by the provisioning's. |
| `test_the_page_costs_a_bounded_number_of_queries` | 3 | **4** | The same, on the city page. |

**The status read is itself one query.** The two lookups (canonical name and identity
key) were collapsed into one `Q(name=name) | Q(normalized_key=key)`, and the
provisioning row is *joined* with `annotate(F("provisioning__status"))` rather than
fetched after — so the whole sentence costs one round trip.

## The mutation check

**The rule: a test must be able to fail.** A green suite proves the code does what it
does; it does not prove the tests *notice* when it stops doing it. Eight mutations were
applied one at a time, each reverted afterwards, and each was expected to turn the suite
red.

The probe is at
`.specs-fire/runs/run-eventpulse24-057/mutation/mutation_probe.py` — **extended, not
duplicated**, because it is the run's single mutation instrument. **It now covers both
halves of the application**: a mutation in a Python file is caught by pytest and a
mutation in a React component by vitest, and the runner is chosen by the target's own
path.

| # | Mutation | Caught by | Result |
|---|----------|-----------|--------|
| 1 | the status is never read — every city is quiet | 4 tests | ✅ |
| 2 | the status read mints a `City` | 1 test | ✅ |
| 3 | the collecting state is folded into the quiet state | 7 tests | ✅ |
| 4 | a live city with no cards is told its sources failed | 1 test | ✅ |
| 5 | a user with no city is told collection is under way | 3 tests | ✅ |
| 6 | the collecting state does not announce itself | 1 test | ✅ |
| 7 | the city page's collection note is dropped | 3 tests | ✅ |
| 8 | the frontend learns a status the backend does not have | the vocabulary test | ✅ |

**All 8 caught**, and the run's own fourteen from item 8 still catch.

**Mutation 5 was the one that found a gap — in the mutation, not in the test.** The
first version of it replaced `{noCity ? (` with `{false ? (`, on the theory that the
no-city reader would then fall through to the collecting state. **They did not**: the
fall-through is `noCards`, and a no-city reader has no cards, so they fell through to
the *quiet* state — which is what the test asserts they get. The mutation survived, and
the honest reading was that **the mutation did not express the lie it claimed**. It was
rewritten to swap the branch's body for `<BrowseCollecting city={browse.city} />`, which
*is* the lie, and that one is caught by three tests.

**A mutation that survives is a missing test — or a mutation that does not do what it
says.** Both are worth a run's attention, and this one was the latter.

**Mutations 3, 4 and 5 are the ones that carry the item's meaning.** #3 says "a
collecting city is empty"; #4 says "a covered city is a broken city"; #5 says "a reader
with no city has a collection". Each is a lie the surface used to tell, or would tell.

**Mutation 8 is the vocabulary test's reason to exist.** The frontend learned a status
the backend does not have, and the test failed — which is the failure mode that would
otherwise be *silent*: the string would simply stop matching, and every city in that
status would fall back to the quiet state, which says "there is nothing on tonight" about
a city that is in fact still being collected.

## Tests written

### `backend/tests/ingestion/test_city_status_read.py` — **19 tests, new**

| Class | Tests | What it holds |
|---|---|---|
| `TestTheStatusIsRead` | 5 | Every one of the model's six statuses comes back verbatim; the source count comes with it; the canonical name and the identity key both find the city; whitespace is ignored. |
| `TestTheEmptyStatus` | 4 | A city with no provisioning row; a city that does not exist; an empty name; a name that normalises to nothing. |
| `TestTheReadNeverWrites` | 3 | The read does not mint a `City`, writes no audit row, and does not provision. |
| `TestTheOutcomeIsPlainData` | 2 | The dataclass is frozen, and it carries no model. |

### `backend/tests/personalization/test_browse_read.py` — **5 tests added**

The status is the catalogue's own; it is read for a live city; a city that was never
provisioned has none; a user with no city has none; **the status does not change the
cards** (AD-10, on the surface's own terms).

### `backend/tests/personalization/test_browse_api.py` — **4 tests added**

`test_the_payload_carries_the_collection_status`; `test_a_live_city_says_so_even_with_nothing_on`;
`test_a_city_that_was_never_provisioned_carries_no_status`; and
`test_a_user_with_no_city_carries_no_status`.

### `backend/tests/api/test_city_page_api.py` — **4 tests added**

`test_the_city_page_carries_the_collection_status`;
`test_a_city_that_was_never_provisioned_carries_no_status`;
`test_a_live_city_below_the_threshold_is_live_and_not_published` (the threshold and the
status are different questions, and both are visible in the response); and
`test_the_status_does_not_vary_by_the_session` — **AD-12: the status is a fact about a
place, not about a reader**, so the public response is identical for everybody.

### `frontend/tests/browse-states.test.tsx` — **30 tests, new**

The per-state blocks (collecting ×6, quiet ×4, no-sources ×4, paused ×3, no-providers
×1, failed ×2, no-city ×3), the four pairwise "the states do not collapse into one
another" tests, and the two "the ordinary surface is unchanged" tests.

**The pairwise tests are the point of the file.** A test that checks each state in
isolation passes even when every state renders the same thing, so these check the
*grouping*: three treatments, and the grouping is exactly two families.

### `frontend/tests/city-page-states.test.tsx` — **11 tests, new**

The published city's listing; the sparse state under six statuses; the collecting
sentence; the no-sources sentence over four statuses; the silence for a `live` city and
for a status nobody wrote; and the two states' sentences are different sentences.

### `frontend/tests/city-collection-vocabulary.test.ts` — **5 tests, new**

The backend's six statuses are read from the Django model; the frontend's set is read
from the two components that branch on it; the two sets are equal; and the two surfaces
agree with each other.

## The commands

```bash
# backend
uv run --directory backend ruff check apps/ingestion apps/personalization apps/catalog shared tests/ingestion tests/personalization tests/api
uv run --directory backend ruff format --check apps/ingestion apps/personalization apps/catalog tests/ingestion tests/personalization tests/api
uv run --directory backend lint-imports                    # 21 kept, 0 broken
uv run --directory backend python manage.py makemigrations --check --dry-run
uv run --directory backend pytest -q                        # 9036 passed

# frontend
pnpm typecheck                                             # clean
pnpm lint                                                  # 0 errors
pnpm test                                                   # 2922 passed

# the mutation check
uv run --directory backend python ../.specs-fire/runs/run-eventpulse24-057/mutation/mutation_probe.py
#   → All 22 mutations were caught.
```

## One thing that was found along the way

**The backend has six statuses, and the plan had named five.** The plan listed
`collecting`, `live`, `no_providers`, `yielded_nothing` and `paused` — and the model has
a sixth, `failed`, which item 8's probation writes when provisioning itself errored.

**The vocabulary test caught it**, because the test reads the model's `Status.choices`
rather than a list written by hand. `failed` is a fact about *why there are no sources*
— the same family as `no_providers` — so it joins the no-sources family on both
surfaces, and the reader gets the same honest sentence.

**A hand-written list in the test would have missed it**, and the surface would have
said "Nothing nearby tonight" about a city whose provisioning had failed — which is the
exact lie this item exists to remove.
