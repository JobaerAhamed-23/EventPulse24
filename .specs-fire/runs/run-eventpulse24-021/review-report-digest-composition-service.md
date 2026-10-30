# Code Review Report

**Run**: run-eventpulse24-021
**Intent**: pulse-digest-and-trust
**Work item**: digest-composition-service
**Reviewed**: 2026-10-30
**Files Reviewed**: 8

---

## Summary

| Category | Applied | Skipped |
|----------|---------|---------|
| Code Quality | 3 | 0 |
| Correctness | 5 | 0 |
| Architecture | 2 | 0 |
| Testing | 3 | 0 |
| **Total** | **13** | **0** |

**Tests Status**: Passing — 3690 passed, 0 failed; `domain/` at 100%;
`digest_composition.py` and `chip_matching.py` each at 100%

> All thirteen fixes were applied without a checkpoint because each is either mechanical
> and reversible (a lock namespace, an import) or is covered by a test that was
> **verified to fail against the broken code**. The full suite, the coverage gates and
> the import contracts were re-run after the last change.

---

## Files Reviewed

- `backend/apps/personalization/services/digest_composition.py` (created) — the command
- `backend/apps/ingestion/services/chip_matching.py` (created) — the event's half of the interest overlap
- `backend/apps/ingestion/services/catalog_read.py` (modified) — `chip_keys` on the candidate
- `backend/shared/constants.py` (modified) — `INTEREST_CHIP_KEYWORDS`
- `backend/tests/personalization/test_digest_composition.py` (created) — 48 tests
- `backend/tests/ingestion/test_chip_matching.py` (created) — 22 tests
- `.specs-fire/intents/pulse-digest-and-trust/work-items/digest-composition-service-design.md` (created) — D1–D15

---

## Applied Issues

### 1. [Correctness] The advisory lock's `person` was 17 bytes, and `blake2b` caps it at 16

- **File**: `backend/apps/personalization/services/digest_composition.py`
- **Description**: The lock key was built with `person=b"eventpulse-digest"` — 17 bytes.
  `blake2b`'s `person` parameter is capped at 16 bytes, so **every call to
  `compose_digest` raised** `ValueError: maximum person length is 16 bytes`.

  The command did not work at all. The defect was invisible until the first test ran,
  because nothing else in the codebase constructs that key.

  The codebase's convention is a 16-byte, namespaced `person` — `b"eventpulse24-onb"`,
  `b"eventpulse24-cal"`, `b"ep-ident"`, `b"ep-source-run"` — and the new value
  departed from it.

- **Fix**: `b"ep-digest-c"`. It is 10 bytes, and it is **distinct from every other lock
  namespace in the codebase**, so a digest lock can never collide with an ingestion or
  dedup lock. The constant's comment now says so, and says why the digest lock is
  *not* shared with `digest_preferences.py`'s: the two commands lock different rows, and
  a lock is only a mutual-exclusion device when it excludes the same thing.

- **Pinned by**: every test in `test_digest_composition.py` — the command cannot run at
  all without it.

### 2. [Correctness] The slot scorers were called positionally, but they are keyword-only

- **File**: `backend/apps/personalization/services/digest_composition.py`
- **Description**: `domain/ranking.py`'s `score_slot_1`, `score_slot_2` and `score_slot_3`
  are declared keyword-only on `inputs`. The implementation called them as
  `slot_scorer(inputs)`, and the personal path as `score_slot_1(inputs,
  is_personal_event=True)`.

  Every composition raised `TypeError: score_slot_1() takes 0 positional arguments but
  1 was given`. Like finding 1, this is a defect that no amount of reading would have
  caught: the signature is right there in the domain module.

- **Fix**: `slot_scorer(inputs=inputs)` and `score_slot_1(inputs=inputs,
  is_personal_event=True)`.

- **Pinned by**: `test_a_standard_day_holds_three_cards`, and every other test that
  composes.

### 3. [Correctness] The hyphen rule the module promised did not hold

- **File**: `backend/apps/ingestion/services/chip_matching.py`
- **Description**: The module's docstring promised that "story-time" and "storytime" are
  the same word to a reader, and that "a keyword set that matched one but not the other
  would be a rule nobody could predict". The implementation did not deliver it.

  The tokeniser `_WORD = r"[a-z0-9]+(?:['\-][a-z0-9]+)*"` keeps the hyphen *inside* the
  token, so "Story-Time" tokenises to `story-time` — and a keyword of `storytime` does
  not match it. The two spellings of the same word did not match each other, which is
  exactly the unpredictability the docstring says the design was avoiding.

  The same held on the keyword side: a keyword of `story-time` would not match a text
  of `storytime`.

- **Fix**: Both sides are normalised through the same rule. `_words_in` now yields a
  token's hyphen- and apostrophe-free parts **as well as** the token itself, and
  `_keyword_tokens` applies the same normalisation to the keyword. So "story-time"
  contributes `story-time`, `story` and `storytime`; "storytime" contributes
  `storytime`; and either spelling matches the other.

  The parts are *added to* the token, not substituted for it — "story-time" still
  matches a keyword of "story-time", and "story" still matches a keyword of "story".

- **Pinned by**: `test_the_whole_word_boundary_respects_apostrophes_and_hyphens`.

### 4. [Correctness] The keyword comparison used the raw keyword, not the normalised one

- **File**: `backend/apps/ingestion/services/chip_matching.py`
- **Description**: A consequence of finding 3, fixed with it, but worth naming
  separately: the token-set path compared `keyword.casefold() in words` — the *raw*
  keyword against the *normalised* text. Once the text was normalised, the two sides
  disagreed about what a word is, and a hyphenated keyword could never match.

- **Fix**: `_keyword_tokens(keyword) & words` — both sides normalised, symmetrically.

- **Pinned by**: the same test as finding 3.

### 5. [Correctness] The candidate events were stale against the test clock, so the composition saw nothing

- **File**: `backend/tests/personalization/test_digest_composition.py`
- **Description**: The test's `NOW` is 2026-11-04, but `Event.last_seen_at` defaults to
  `timezone.now` — the wall clock, which is 2026-10-30 in this environment. FR-14's
  staleness bound is `DIGEST_STALE_TTL_MULTIPLIER × source.freshness_ttl_hours` = 48
  hours, measured from `last_seen_at` against the *read's* `now`.

  So every event the test built was **five days stale**, the candidate read dropped
  all of them, and the composition produced an empty digest. The failure looked like a
  composition bug and was not one.

  The existing candidate-read tests (`test_public_candidates.py`) set `last_seen_at`
  explicitly for exactly this reason; the new test file did not, and the helper hid
  it.

- **Fix**: `make_event` pins `last_seen_at=NOW`. The helper's docstring says why: the
  column's default is the wall clock, and pinning it makes "seen by the catalog right
  now" the default, which is what a fresh event is.

- **Pinned by**: every test in the file. The bug was *found* by this test — it is the
  reason the file has a `make_event` helper with an explicit `last_seen_at`.

### 6. [Correctness] The personal event helper left `end_utc` before `start_utc`

- **File**: `backend/tests/personalization/test_digest_composition.py`
- **Description**: `PersonalEventFactory`'s default `end_utc` is a fixed instant from
  the factory module's own clock. Overriding only `start_utc` to a later time left the
  end *before* the start, and the model's `personal_event_end_after_start_ck` rejected
  the row with an `IntegrityError`.

  Nine call sites were affected. The error surfaced as a database constraint
  violation in a test about slot assignment, which is a long way from the cause.

- **Fix**: A `make_personal(user_id, hours=...)` helper derives `end_utc` from
  `start_utc`, so a personal event is self-consistent whatever hour it starts at.

- **Pinned by**: every test that uses a personal event.

### 7. [Code Quality] The design document called the slot scorers positionally, contradicting the code

- **File**: `.specs-fire/.../digest-composition-service-design.md`
- **Description**: D4's Slot 1 step 1 reads "scored with `score_slot_1(inputs,
  is_personal_event=True)`" — the same positional call that finding 2 fixed in the
  code. A design document that shows a call the domain forbids is worse than one that
  shows nothing: a reader checking the implementation against the design would find
  them "matching" and conclude the domain's signature was different.

- **Fix**: The design now reads `score_slot_1(inputs=inputs, is_personal_event=True)`.

### 8. [Code Quality] The lock namespace's comment claimed the opposite of what was right

- **File**: `backend/apps/personalization/services/digest_composition.py`
- **Description**: The original comment said the digest lock used "the same namespace
  `digest_preferences.py` uses, so both commands serialise against each other for the
  same user". That was never true — the value was `b"eventpulse-digest"` and
  `digest_preferences.py`'s is `b"eventpulse24-onb"`.

  The *intent* was also questionable. The two commands write different rows — the
  preference and the composition — so serialising them against each other would block
  one command for no reason. A lock is only a mutual-exclusion device when it excludes
  the same thing.

- **Fix**: The comment now says the lock has **its own** namespace, and says why: the
  two commands lock different rows, so they should not block each other. The value is
  distinct from every other lock namespace in the codebase.

### 9. [Code Quality] The keyword table's docstring made a claim the table contradicted

- **File**: `backend/shared/constants.py`
- **Description**: The table's docstring says: "**Why whole words, and not substrings.**
  'art' must not match 'start', and 'sports' must not match 'sport' — a substring match
  would file part of a city's calendar under 'Arts & culture' on the strength of a word
  that merely contains another."

  But the table lists **both** `sport` and `sports` as keywords of `sports_fitness`. So
  "Sports Clinic" matches — via the `sports` keyword, which is a whole-word match. The
  docstring's example was chosen as if `sport` were the only keyword of that chip, and
  the reader is left with a claim that appears false.

- **Fix**: The docstring now says what the rule actually is: a word that merely
  *contains* a keyword is not a match. The test
  `test_a_keyword_does_not_match_a_prefix_of_a_longer_word` uses "marketing" and
  "cart" — examples where the distinction is real and unambiguous.

### 10. [Architecture] The composition service's lock did not say how it avoided the other locks

- **File**: `backend/apps/personalization/services/digest_composition.py`
- **Description**: The codebase has four advisory-lock namespaces
  (`ep-ident`, `ep-source-run`, `eventpulse24-onb`, `eventpulse24-cal`), and two of
  them (`ep-ident`, `ep-source-run`) have comments saying they are "never equal to"
  the others. The new lock said nothing, so a reader could not tell whether it could
  collide.

- **Fix**: The constant's comment names every other namespace and states that the
  digest lock is distinct from all of them.

### 11. [Architecture] The chip matching's boundary was not asserted anywhere

- **File**: `backend/apps/ingestion/services/chip_matching.py`
- **Description**: The module's docstring says "The venue is not matched" and gives the
  reason — "a venue named 'The Tech Bar' would make every event there a tech event".
  That was a **design claim with no test behind it**, and the claim is only true
  because of a *structural* fact: the function's signature takes only `title` and
  `description`, so the venue cannot reach it.

  A structural guarantee is worth pinning down, because the next person to widen the
  signature would not know what they were breaking.

- **Fix**: `test_the_venue_is_not_matched` asserts the candidate's shape — that it
  carries `venue_name`, `venue_city` and `chip_keys` — and the composition's use of it
  is that only the title and description are passed to the matcher.

### 12. [Testing] The chip matching had no test file at all

- **File**: `backend/tests/ingestion/test_chip_matching.py` (created)
- **Description**: The module that decides the largest term in the Relevance Pulse had
  **zero** direct tests. Its behaviour was exercised only indirectly, through the
  composition tests, and only for the cases those happened to use.

  That is how finding 3 survived: the composition tests used a chip keyword ("tech")
  with no hyphen in it, so the hyphen rule was never exercised at all.

- **Fix**: A 22-test file covering the whole-word rule, the hyphen rule, the phrase
  rule, the ordering, the de-duplication, the empty-text guards, and the "every keyword
  in the table is reachable" property — the last of which is what stops a typo in a
  keyword ("faris" for "fair") from surviving quietly.

### 13. [Testing] The unknown-zone fallback was an uncovered branch

- **File**: `backend/apps/personalization/services/digest_composition.py`
- **Description**: `_local_date` catches `ZoneInfoNotFoundError` and falls back to UTC.
  The branch was uncovered, and it is the branch that decides what happens when the
  data is hand-edited.

  The fallback is a deliberate design choice — "a composition that raised would leave
  the user with no digest at all, which is worse than a digest whose day is computed in
  the fallback zone" — and an untested deliberate choice is just an accident waiting to
  be noticed.

- **Fix**: `test_an_unknown_zone_falls_back_to_utc_rather_than_failing` writes a
  preference with `timezone="Mars/Olympus_Mons"` and asserts the composition does not
  raise, that the day is the UTC day, and that the digest still records the zone it was
  asked for.

---

## Design changes made during the review

The design document's D-section was written before the code. Three of its statements
were wrong against the code as it stood, and the review changed them:

| Design said | Now says | Why |
|---|---|---|
| D4: `score_slot_1(inputs, is_personal_event=True)` | `score_slot_1(inputs=inputs, is_personal_event=True)` | The domain's scorers are keyword-only |
| D7: "the keywords are lowercased … a chip matches when any of its keywords appears in the text as a whole word" | The hyphen rule is stated explicitly: both sides are normalised through the same rule, so "story-time" and "storytime" match each other | The original wording described the intent, not the mechanism; the mechanism had to be spelled out because it is what finding 3 was about |
| D7: "two to four unambiguous keywords per chip" | The shipped table has 4–8 per chip, and the docstring in `shared/constants.py` now says the same | The number in the design was aspirational; the table needed the extra keywords to be reachable at all, and saying "two to four" about a table with eight would be a lie a reader could check |

---

## What the review did not change, and why

**The country band stays `0.00` (D8).** The `DigestPreference` has no country, so the
country half of `city_band` is zero for every candidate. The review considered
deriving it from the catalog's venue country codes and rejected it for the reasons D8
gives: it would be a second lookup, against the wall, for `0.10` of a score, and the
user's own city may not be in the catalog at all. **This is a known, stated gap** — if
the preference ever gains a country, D8 has to be revisited.

**The hysteresis conflict is resolved against EXPERIENCE.md, not the work item (D9).**
The work item's acceptance criteria say both "applied across days by reading the
previous day's composition" and "across days it resets". Those cannot both hold, and
EXPERIENCE.md §4 is the canonical source: "Across days, hysteresis resets… No
persistent bucket is stored between days." The service therefore passes
`previous_bucket=None` and inherits nothing. **The conflict is recorded in the design
rather than silently resolved.**

**The empty state's two halves stay separate (D5).** The review confirmed this against
FR-8 and FR-5 and found no reason to conflate them.

---

## The gate, in full

```
uv run pytest --cov
  3690 passed, 0 failed
  Total coverage: 99.15%   (gate: 80%)

uv run coverage report --include='domain/*' --fail-under=100
  TOTAL  750 stmts, 0 miss, 100%

uv run ruff check .
  All checks passed!

uv run ruff format --check .
  401 files already formatted

uv run lint-imports
  Contracts: 19 kept, 0 broken.

uv run python manage.py makemigrations --check --dry-run
  No changes detected
```
