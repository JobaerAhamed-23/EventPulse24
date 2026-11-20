---
run: run-eventpulse24-057
work_item: stored-city-is-the-picked-city
intent: city-picker-and-auto-collection
mode: validate
checkpoint: plan-approval
status: awaiting_approval
---

# Implementation Plan: The stored city is the picked city

## Approach

Delete the silent rewrite. `resolve_home_city()` currently replaces **any** city outside
`list_supported_cities()` with `PREVIEW_FALLBACK_CITY` and marks it `fallback`. That
function's question changes here: from *"can the preview serve this city today?"* to
*"is this a city a person may pick?"*.

The answer to the new question is `domain.city_catalog` — item 1's frozen 165-row table,
which is the same answer whether or not one event has ever been ingested in that city.

**The re-based rule, in one place:**

| The city is… | What happens | Why |
|---|---|---|
| `None` | stores nothing, clears an existing one | unchanged — "we do not know" is a real state |
| in the catalog, `source="choice"` | stored **exactly as picked**, `city_source="choice"` | the user's choice is authoritative |
| in the catalog, `source="geo"` | stored in the catalog's spelling, `city_source="geo"` | unchanged |
| **not** in the catalog, `source="choice"` | **refused** — a validation error, nothing written | a client bug, refused loudly |
| **not** in the catalog, `source="geo"` | `PREVIEW_FALLBACK_CITY`, `city_source="fallback"` | nobody chose it; an edge's guess must not become a 4xx |
| over-long (> `GEO_CITY_MAX_LENGTH`) | **refused** on a choice; fallback on a geo | an over-long value is an attempt to put a value somewhere it should not go |

### The geo-versus-choice distinction is the subtle part

Two callers reach this function and they are **not** the same kind of caller:

- **the user picking from the dropdown** (`source="choice"`) — their choice is
  authoritative. A city outside the catalog is a *client bug*, so it is refused loudly.
- **the geo header** (`source="geo"`) — nobody chose it. An uncoverable value falls back
  silently exactly as it does today, because refusing it would turn an edge's guess into a
  4xx on a path the user never asked for.

So the branch is on **`source`**, not on the city alone. This is the one place where
"geo" and "choice" must not be collapsed, and it is why the refusal lives *inside*
`resolve_home_city` rather than at the API edge: the service knows which caller it is
serving, and the API edge does not.

**`SOURCE_FALLBACK` and `SOURCE_BACKFILL` never reach `resolve_home_city`** — they go
through `store_fallback_city()`, which stores the fallback without asking. That is
unchanged, and it stays unchanged: those are server-chosen cities, not user-chosen ones.

### Where the refusal lives, and what it carries

`resolve_home_city()` raises a new `domain.errors.ValidationError` subclass —
`UnknownHomeCityError` — carrying the **rejected city** in `details`.

AD-13 is the reason this is a narrow channel and not a log line:

- the refused city **is** in the API error, because the caller sent it and needs to be
  told which value was refused;
- the refused city is **not** in any audit `details`, and **not** in any log line.

The error is raised **before** the transaction opens, so a refusal writes **no**
`DigestPreference` row and **no** audit row. That is the whole of AC 9.

The refusal is a `ValidationError`, so `config/errors.py` maps it to a **422** with the
project's own error shape `{code, message, details}` — which satisfies "the API returns
4xx" without touching the error-handler wiring.

### `_canonical()` now resolves against the catalog

`_canonical(cities, city)` currently takes the *list of covered cities* and scans it. It
now resolves against `domain.city_catalog` instead: `lookup(name)` returns the row, and
the row's `.name` is the catalog's spelling.

**Its `raise ValueError` invariant guard stays.** The caller checks membership first
(`lookup(...) is not None`), and the raise is still the type-checker's proof that the
check happened. The guard's message changes to name the catalog rather than "the catalog"
in the old sense, because "the catalog" now means two different things in this codebase
and the sentence should not be ambiguous.

**`list_supported_cities` is no longer imported here.** That removes this module's only
dependency on `apps.ingestion.services.preview_read` — and with it the "two rules for
which cities may a user be in" hazard the module's own docstring describes at length.
`preview_read` is untouched; it still answers the preview's question.

### What does *not* change

- **`store_fallback_city()`** — unchanged. The server chose the fallback; it is not
  coverage-checked.
- **`backfill_home_cities()`** — unchanged, and still idempotent.
- **Existing `city_source="fallback"` rows** — left exactly as they are. **No migration
  touches them.** A user whose city reads `fallback` is told honestly what happened, and
  nulling those rows would push a surprise empty Browse onto people who never asked for
  one.
- **`home-city.tsx`** — no change is needed for this item to be observable. It already
  replaces its optimistic value with the server's answer, so the user sees their city
  stick immediately. Its stale docstring (which still claims the choices come from
  `preview/cities`) belongs to **item 11**, where the claim actually stops being true.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/tests/personalization/test_stored_city_is_the_picked_city.py` | The whole-dataset test, the refusal test, and the geo/choice distinction — this item's proof, kept separate from the older coverage-rule tests it partly supersedes |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/domain/errors.py` | `UnknownHomeCityError(ValidationError)` — the refusal, carrying the rejected city |
| `backend/apps/personalization/services/digest_preferences.py` | The re-based `resolve_home_city`; `_canonical` resolves against the catalog; the module docstring rewritten to describe the new rule and to stop claiming the coverage rule is "reused" |
| `backend/apps/personalization/schemas.py` | `DigestPreferenceIn.city` docstring — a city outside the catalog is refused, not stored as the fallback |
| `backend/apps/personalization/api.py` | The `PUT /onboarding/digest-preference` description — it currently promises the fallback behaviour that this item deletes |
| `backend/tests/personalization/test_digest_preferences.py` | The coverage-rule tests that this item inverts are rewritten to the new rule |

## Technical Details

### The refusal error

```python
class UnknownHomeCityError(ValidationError):
    """A city the reader chose that is not in the curated catalog."""

    code = "unknown_home_city"
    default_message = "We don't have that city yet. Pick one from the list."
```

`details` carries the rejected city under a stable key, so the caller can name it:

```python
details={"errors": [{"loc": ["city"], "msg": "..."}], "rejected_city": "<the city>"}
```

**Why `details` and not the message.** The message is for a person and must stay calm
and quotable. The rejected value is machine-readable data the client needs in order to
re-select. The two go in different places because they have different jobs.

**Why the rejected city is safe here.** AD-13 protects the city from the *audit log* and
the *log sink* — a city is weak location data about a real person, and a log crosses
into `catalog`. The API response goes back to the person who sent it, over their own
authenticated session, having just sent it themselves. Echoing a value back to its sender
is not disclosure. The audit row is a different audience entirely, which is why it stays
silent.

### `resolve_home_city`, rewritten

The signature is unchanged — `city: str | None, source: str, now: datetime` — so every
caller and every test that uses it keeps working. `now` is no longer needed by the
function (the catalog does not change with the clock), but it stays in the signature
because removing it would churn every call site for no gain, and `set_home_city` has a
`now` it needs anyway.

```python
if city is None:
    return None, None

wanted = city.strip()
if not wanted or len(wanted) > GEO_CITY_MAX_LENGTH:
    # A geo guess may fall back; a choice is refused.
    if source == SOURCE_CHOICE:
        raise UnknownHomeCityError(...)
    return PREVIEW_FALLBACK_CITY, SOURCE_FALLBACK

row = lookup(wanted)
if row is None:
    if source == SOURCE_CHOICE:
        raise UnknownHomeCityError(...)
    return PREVIEW_FALLBACK_CITY, SOURCE_FALLBACK

return row.name, source
```

**Why `row.name` and not the caller's spelling.** The catalog's spelling is what the
events are filed under, and `lookup` folds case and spacing — "  portland, or " finds
"Portland, OR". The stored value is always the catalog's, exactly as today.

**Why `lookup` and not `is_known` + a second lookup.** `is_known` is the question most
callers have, but this one needs the row anyway (for its `.name`), so it asks for the row
directly. One dict hit, not two.

**A note on the empty string.** `city=""` or `city="   "` is not a city a person could
have picked from a `<select>`, so on a choice it is refused with the same error. On geo
it falls back, as today.

### The API edge

No change to the endpoint's *shape* — the refusal is an ordinary `ValidationError` and
`config/errors.py` already maps it to 422. What changes is the **description**, which
currently tells the client the opposite of what now happens:

> "`city` is the user's home city, in the catalog's own spelling. A city the catalog does
> not cover is stored as the fallback and reported back with `city_source` set to
> `fallback`, so the client can say 'we don't have your city yet' rather than implying
> it is the user's city."

That paragraph is the item's bug, written down. It becomes: a city outside the catalog is
**refused** with a 422 and nothing is stored; a city inside it is stored exactly as sent.

**The 422 body.** `{"code": "unknown_home_city", "message": ..., "details": {...}}`.

### The `city_source="fallback"` rows that already exist

**No migration.** The brief is explicit and the reasoning is good: nulling them would
push a surprise empty Browse onto people who never asked for one, and `citySourceNote()`
already labels them honestly. They repick whenever they like — and now the pick sticks.

There is one consequence worth naming: a user whose stored city is `fallback` will, on
their next pick, get the catalog's spelling of their city rather than the fallback.
That is the point.

## Tests

| Test File | Coverage |
|-----------|----------|
| `tests/personalization/test_stored_city_is_the_picked_city.py` | **The whole-dataset test (AC 8)**: parameterised over all 165 `WORLD_CITIES` rows — `resolve_home_city(city=row.name, source="choice")` returns `(row.name, "choice")` for every row, so a future catalog row cannot regress it. Also: the case-folded spelling of every row returns the catalog's own spelling; a city outside the catalog is refused; the refusal carries the city; the refusal writes **no** preference row and **no** audit row; the geo path keeps its fallback for a city outside the catalog; `city=None` still clears and is distinct from a refusal; an over-long city is refused on a choice and falls back on geo; `store_fallback_city` and `backfill_home_cities` are unchanged; the refused city appears in the API error and in **no** audit `details` |
| `tests/personalization/test_digest_preferences.py` | The coverage-rule tests this item inverts, rewritten: an uncovered city on a **choice** is refused rather than stored as the fallback; the fallback is still what `store_fallback_city` and the backfill write; the audit rows still say *that* the city changed and never *which* |
| `tests/api/test_digest_preference_api.py` | The endpoint answers **422** for a city outside the catalog, with the project's error shape, and **stores nothing**; a city inside it answers 200 and stores exactly what was sent |

**The mutation check.** Every whole-dataset invariant is mutation-checked before the
test report is written — the rule that a test must be able to fail. The
parameterised-over-the-catalog test is the one that most needs it: it is checked against
a deliberately broken `lookup` and against a deliberately blanked `row.name`, and both
must fail the test.

**A test that could pass for the wrong reason.** The old suite's own docstring names
this pattern: *"the fallback is recorded as a fallback"* passes if *every* city were the
fallback. The new tests keep that discipline — the refusal test asserts **both** that the
call raised **and** that nothing was written, so a `resolve_home_city` that raised after
writing would fail.

## Risks

| Risk | Mitigation |
|---|---|
| A city the reader can pick is refused | The refusal is scoped to `source="choice"` only, and the catalog is the *same* table the picker is populated from (`GET /api/public/cities`, item 4). A city on offer is a city that resolves. The whole-dataset test proves it for all 165 |
| The sign-up path now 500s on a bad city | `sign_up.py` calls `set_home_city(source=SOURCE_CHOICE)` **after** the account commits, so a refusal there raises `UnknownHomeCityError` → a 422 with the account created and no city. The account stands; the city is missing. That is the same bargain the module's docstring already makes ("the account is the thing that must not be half-made") |
| An existing test asserts the fallback for an uncovered choice | Those tests are inverted by this item — that is the item. They are rewritten, not deleted, and the rewrite is what proves the behaviour changed |
| A geo path that does not exist yet gets the wrong behaviour | `SOURCE_GEO` is currently reachable only from a test. The branch is written and tested anyway, because the AC requires it and because the next item to write a geo path will get it right by default rather than by accident |
| `home-city.tsx` shows a raw error | The frontend already handles `response.error` verbatim (`saveFailureMessage`), so a 422 renders its message and reverts the optimistic value. No frontend change is needed for this item |

## Notes for the checkpoint

**Two things I decided rather than asked, and would change on request.**

1. **The refusal is a 422, not a 400.** `ValidationError` already maps to 422 in
   `config/errors.py`, and the refusal is "input breaks a rule" — the same shape as every
   other validation failure in this codebase. A 400 would need a new mapping and would
   say "your request was wrong" about a request that was well-formed and offered a city
   the server does not have.

2. **The refused city is echoed in the error body.** AD-13 keeps it out of the audit log
   and out of the logs; the AC requires it in the API error, and the two are consistent
   because the caller sent it.

**One thing I did *not* do, on purpose.** I did not add a `city_source="choice"` check
for cities already stored as `fallback` — no migration, no rewriting of existing rows.
The brief forbids it and the reasoning holds.

---

*Plan written for the validate-mode checkpoint (checkpoint 2 of 2; the design doc was
the Planner's checkpoint 1). Execution follows approval.*
