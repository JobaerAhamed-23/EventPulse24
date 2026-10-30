# Test report: `digest-read-api`

**Work item**: `digest-read-api`
**Intent**: `pulse-digest-and-trust`
**Mode**: confirm
**Date**: 2026-10-30

---

## What was built

| File | Kind | What it is |
|---|---|---|
| `backend/apps/personalization/services/digest_dates.py` | new | `local_date_for(*, now, zone_name) -> date` — the user's local day, one shared rule |
| `backend/apps/personalization/services/digest_read.py` | new | `read_digest(*, user_id, now) -> DigestRead` — the read of the persisted rows |
| `backend/apps/personalization/schemas.py` | modified | `DigestStatus` (a `Literal`), `DigestCardOut`, `DigestOut` |
| `backend/apps/personalization/api.py` | modified | `GET /api/personal/digest` |
| `backend/apps/personalization/services/digest_composition.py` | modified | `_local_date` replaced by the shared `local_date_for` |
| `backend/tests/personalization/test_digest_api.py` | new | 30 tests |
| `frontend/lib/api/openapi.json` | modified | the regenerated contract |
| `frontend/lib/api/schema.ts` | modified | the regenerated TypeScript client |

## The test file

**30 tests**, in six groups:

| Group | Tests | What it pins |
|---|---|---|
| the three states | 5 | `composed`, `empty` and `not_composed` are three distinct bodies; the two empties do not collapse |
| auth and scoping | 3 | an anonymous request is a 401; another user's digest is invisible; a `user_id` query parameter reaches nothing |
| the card | 10 | the slot order; the bucket and not the score; the persisted tags in the persisted order; the saved tag; a personal card's free-text place and null badge; the instant plus the zone; `tz_review_pending`; a gone catalog event; a gone agenda row |
| the conflict flag | 3 | a personal card in a pair; a public card in a pair, through the save; a resolved pair is not a flag |
| nothing is computed | 2 | the endpoint path never calls `domain/ranking.py`; the endpoint path never writes a row |
| the query bound and the contract | 7 | the read's query count is bounded; it does not grow with the card count; the endpoint path's does not either; the user's day; another day is not the user's digest; the path is in the OpenAPI schema |

## The acceptance criteria, one by one

| Criterion | How it is met | Test |
|---|---|---|
| a session-authenticated endpoint, no `request` in the service | the router's one `auth=current_user`; the service takes `user_id` and `now` | `test_the_endpoint_requires_a_session` |
| FR-6's six elements per card | name, time, place, tags, bucket, badge — all on the shape | `test_a_composed_digest_returns_its_cards` |
| plus the slot, the kind, the conflict flag, `tz_review_pending`, the saved flag | all five are on the card; the saved flag travels as the persisted `saved` tag | `test_the_saved_flag_travels_as_a_tag`, `test_a_public_card_in_a_conflict_carries_the_flag` |
| time as an instant plus the IANA zone | `start_time_utc` + `start_time_tz`, never a formatted string | `test_the_card_carries_the_time_as_an_instant_plus_the_zone` |
| the empty state is a distinct, explicit response, with the city, never a 404 | `status: "empty"`, `cards: []`, and `city` on the body | `test_an_empty_digest_is_a_digest_with_no_cards`, `test_the_empty_state_carries_the_city` |
| not-yet-composed is distinguishable from empty | `status: "not_composed"` | `test_a_digest_that_was_never_composed_is_distinguishable`, `test_the_empty_state_and_the_not_composed_state_are_different_bodies` |
| nothing is computed | the ranking is monkeypatched to raise; the row counts are compared before and after | `test_the_endpoint_never_calls_the_ranking`, `test_the_endpoint_never_writes_a_row` |
| Pydantic schemas in `schemas.py`, the endpoint in the OpenAPI schema, the client regenerated | `DigestCardOut` and `DigestOut`; `make client` run and the diff committed | `test_the_endpoint_is_in_the_openapi_schema` |
| the query count is bounded and asserted | the SQL is recorded on **both** connections and the count asserted | `test_the_query_count_is_bounded`, `test_the_query_count_is_bounded_with_an_open_conflict`, `test_the_query_count_does_not_grow_with_the_number_of_cards` |
| no `personal` data on a public surface | the endpoint is on the personal router, which is session-authed | `test_the_endpoint_requires_a_session` |
| rate limiting follows the per-user pattern | there is **no** rate limiter on the personal router, and none was added — D1 argues why | (a design decision, not a test) |

## The gate

```
uv run pytest --cov --cov-report=term-missing -q
→ 3730 passed, 99.15% total coverage

uv run ruff check .
→ All checks passed!

uv run ruff format --check .
→ 404 files already formatted

uv run lint-imports
→ Contracts: 19 kept, 0 broken.

uv run coverage report --include='domain/*' --fail-under=100
→ TOTAL 750 0 100%

uv run python manage.py makemigrations --check --dry-run
→ No changes detected

pnpm --dir frontend typecheck
→ Types generated successfully

pnpm --dir frontend lint
→ (clean)

pnpm --dir frontend format:check
→ All matched files use Prettier code style!
```

**Both new modules are at 100% coverage** — `digest_read.py` and `digest_dates.py` do not appear in the coverage report, which lists only files with a miss.

## The failures the tests found

Five, and every one of them was a real defect — in the implementation, in the test, or in
the design.

1. **The endpoint resolved the wrong day.** The first run answered `not_composed` for a
   digest that existed. The cause was the test, not the code: the composition service's
   own tests pin `NOW = 2026-11-04`, but **the endpoint resolves `now` itself** from the
   wall clock, and the wall clock was `2026-10-30`. The digest had to be written for
   *today's* local date. The test's `NOW` is now the wall clock, pinned at import time so
   every instant in a test is measured from the same "today".

2. **The query bound counted the auth seam.** The first bound was four, and the read
   measured five. Two of the five were the session row and the user row — the framework's
   cost, paid by every endpoint on the router, and not the read's. The bound was moved
   onto the service, where it means something, and the endpoint path got its own test:
   the count must not grow with the number of cards.

3. **The query bound was four and became six.** The review changed the answer on the
   conflict flag (D10): the flag **is** on the card, because FR-58's indicator renders
   on a card and the work item asks for it. Reading it costs two queries — the open
   pairs, and the user's saves of the public cards (the bridge from a catalog event id
   to a pair's side). The save lookup is only reached once a pair exists to look for, so
   a user with no conflicts pays five.

4. **A card with no title needed a shape, not a sentinel.** The first draft of the card
   carried a required `title: str` and an epoch `start_time_utc` for the case where the
   catalog had dropped the event. A card showing "Untitled event" at the epoch is a lie
   about a day. The display facts are now **optional** — `None`, with
   `catalog_event_missing=True` saying why — and the required fields are the ones the
   composition itself holds.

5. **Two fixture collisions.** The venue fingerprint is unique per call, and a
   `RESOLVED` conflict pair needs its `resolution` and `resolved_at` — the
   `conflict_pair_status_ck` constraint says so. Both were the test's problem, and both
   are now the test's statement of the rule.

## What the tests do **not** cover

- **The composition itself.** `test_digest_composition.py` owns it. This item reads what
  it wrote.
- **The Detail Screen's read.** `event-detail-api` is a different query with a different
  contract, and it *does* need the score the card does not carry.
- **The frontend's rendering of the three states.** `frontend-digest-home` owns it.
- **The conflict *detection*.** The flag is read from the persisted pairs; the detection
  that writes them is `conflicts.py`'s job and is already tested there.
