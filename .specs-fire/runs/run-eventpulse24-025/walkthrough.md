---
run: run-eventpulse24-025
work_item: digest-card-state-fields
intent: event-state-sync
generated: 2026-11-10
mode: confirm
---

# Implementation Walkthrough: The card that could not say an event was cancelled

## Summary

FR-53's testable consequence is that *"a sold-out event is marked with a 'Sold Out' tag on
the Pulse Card and Detail Screen."* The Detail Screen half was already done. The Pulse Card
half was not — and could not be, because `DigestCardOut` carried neither the lifecycle status
nor the sold-out flag. The card had no vocabulary for saying an event was no longer what it
was.

This item gives the card that vocabulary: two fields, read live, joined in.

**The design's central claim is what it does *not* add.** No column on the composition, no
migration, no cache. The status is not *stored* — it is *read*, at request time, from the same
catalog row the read was already fetching. The obvious implementation — a `status` column on
`DigestComposition` — would have passed every acceptance criterion's letter and failed its
third one, because a card composed at 09:00 would keep saying `scheduled` for an event
cancelled at 10:00.

## Structure Overview

The change touches four files, all of them in existing seams:

```text
┌──────────────────────────────────────────────┐
│  ingestion · catalog_read                    │
│  PublicEvent += is_sold_out                  │
│  (the same fact PublicEventDetail had)       │
└───────────────────┬──────────────────────────┘
                    │ get_public_events — ONE batched read
                    │ (already there; the card already joined it)
┌───────────────────▼──────────────────────────┐
│  personalization · digest_read               │
│  DigestCard += status, is_sold_out           │
│  _card_for_public  → the catalog's facts     │
│  _card_for_personal → None, None             │
└───────────────────┬──────────────────────────┘
                    │
┌───────────────────▼──────────────────────────┐
│  personalization · schemas + api             │
│  DigestCardOut += status, is_sold_out        │
│  → OpenAPI → the TypeScript client           │
└──────────────────────────────────────────────┘
```

The read already did the hard part. `_public_display_facts` batches `get_public_events` into
one map, and `_card_for_public` already received the joined `PublicEvent`. **`status` was
already on the object.** The card simply did not hand it over.

## Architecture

### Pattern Used

A **live-fact join**, distinct from the **persisted explanation** that AD-10 governs. The
composition holds the *why* — bucket, tags, badge — and those are frozen at composition time
on purpose, because the bucket the user saw this morning must not change while they look at
it. The lifecycle status is a *what*, and a what has to be current.

The card already carried two live facts of exactly this kind: `tz_review_pending` (read from
the catalog at request time) and `conflict` (read from the persisted pairs at request time).
The new fields are a third and fourth of the same species, not a new kind of thing.

### The three facts that settled the design

1. **`DigestComposition` cannot hold it.** Append-only, `append_only_mutable = frozenset()` —
   *"Nothing about a composition becomes known after it is written."* A status stored there
   would be written at composition time, and frozen.
2. **AD-10 says the composition explains *why*, not *what*.** The bucket, the tags and the
   badge are a fact about the user's day. The event's lifecycle is a fact about the event.
3. **The read already joins the catalog's current facts.** The status was *already on the
   object* the card was built from. This is plumbing, not a new read.

### Data flow

1. The user requests the digest.
2. `_public_display_facts` makes **one** batched `get_public_events` call — unchanged.
3. `_card_for_public` hands `public.status` and `public.is_sold_out` to the card.
4. The endpoint passes both to `DigestCardOut`; the OpenAPI schema carries them; the
   TypeScript client is regenerated from it.

## Files Changed

### Created

| File | Purpose |
|------|---------|
| (none) | — |

### Modified

| File | Changes |
|------|---------|
| `backend/apps/ingestion/services/catalog_read.py` | `PublicEvent` gains `is_sold_out`; `_to_public_event` fills it |
| `backend/apps/personalization/services/digest_read.py` | `DigestCard` gains `status` and `is_sold_out`; the four construction sites fill them |
| `backend/apps/personalization/schemas.py` | `DigestCardOut` gains the same two |
| `backend/apps/personalization/api.py` | The endpoint passes them through; the OpenAPI description was updated |
| `backend/tests/personalization/test_digest_api.py` | 9 tests |
| `backend/tests/api/test_catalog_read_service.py` | 3 tests |
| `frontend/lib/api/openapi.json` | Regenerated |
| `frontend/lib/api/schema.ts` | Regenerated |

## Domain Model

**No new entities. No new fields on any model. No migration.** `makemigrations --check` reports
no changes detected — which is the design's claim, held.

| Entity | Change | Business Rules |
|--------|--------|----------------|
| `DigestComposition` | **none** | Its `append_only_mutable = frozenset()` is the reason this item is a read and not a write |
| `Event` | **none** | `status` and `is_sold_out` already exist on the catalog row; this item only makes them reachable from the read the digest already makes |
| `PublicEvent` | `is_sold_out` added | Plain data across the wall (AD-3). Required, not defaulted |
| `DigestCard` | `status`, `is_sold_out` added | Both `| None`. `None` means "not applicable", not "fine" |
| `DigestCardOut` | `status`, `is_sold_out` added | The wire shape |

## Key Implementation Details

### 1. `is_sold_out` had to travel; `status` did not

`PublicEvent` carried `status` but not `is_sold_out`. `PublicEventDetail` carried both. So the
one field that had to move was the one the digest's read happened to be missing — and adding it
is the same one-line change `PublicEventDetail` already made, in the same module, for the same
reason.

**This is not widening the public contract.** The docstring on `PublicEventCandidate` warns
that *"widening `PublicEvent` would put digest-only fields on the public catalog's contract."*
`is_sold_out` is **not** digest-only — it is already on the public contract, via
`PublicEventDetail` and `apps/catalog/schemas.py`. This makes an existing fact reachable from
the one read that lacked it.

### 2. `None` is a fact; `"scheduled"` is a claim

Both fields are `str | None` / `bool | None`, and every personal or missing branch says
`None`. The alternative — defaulting a personal card to `"scheduled"` — would claim the
catalog had an opinion about a row it has never seen, and the client could not tell "no
lifecycle here" from "a live event that happens to be fine".

**Mutations 3 and 4 pin this.** Each of the two `None` branches was mutated to `"scheduled"`
and each was caught.

### 3. The two facts stay apart

An event can be `scheduled` **and** sold out at the same time. A collapsed "state" enum
could not say both, and the acceptance criterion forbids it. The backend's existing vocabulary
is unchanged: `Event.Status` for the lifecycle, a separate flag for the tickets —
`EventDetailFactsOut` already sets this precedent with the same two fields in the same shape.

### 4. The FR-55 question was settled elsewhere, and the two answers agree

FR-55 says *"event is removed from the digest"*, and `saved-event-lifecycle-state` settled it
at the **candidate** stage: `digest_candidates.py:336` drops a save the catalog says is
cancelled, before it can become a candidate.

**So a newly cancelled event never enters a composition at all.** A *newly* cancelled event is
never a card. But a card composed *before* the cancellation is still on the digest — and that
card must say `status="cancelled"`.

Removing it at read time would be a **second, different removal** with a different trigger
than FR-55's, and it would break AD-10's rule that digest rows are served as stored. It would
also make the digest flicker: a card the user was looking at would vanish.

**Both answers agree.** FR-55 removes at the door. This item marks what is already on the
digest. The card tells the truth; tomorrow's composition will not contain the event at all.

### 5. A cancelled card keeps its explanation

The state changed; the *why* did not. `test_a_cancelled_card_says_cancelled_and_stays_on_the_digest`
asserts the bucket and the tags are untouched alongside the status — AD-10's rule, made
executable.

## Security Considerations

| Concern | Approach |
|---|---|
| PII | None. Two booleans and a status word — no title, no address, no name (AD-13) |
| New attack surface | None. No new endpoint, no new parameter, no new credential, no new external input |
| New query | None. The read reuses the batch it already made — the query-count tests pass unchanged |
| The `status` value on the wire | The catalog's own `Event.Status`: one of four fixed strings chosen by the server. A client meeting an unknown value is no worse off than one meeting `null` |
| Writes | None. No transaction, no migration, no wall crossing |

## Performance Considerations

| Requirement | Implementation |
|-------------|----------------|
| **No new query** | `_public_display_facts` already batched `get_public_events`; the status rides on the `PublicEvent` that was already joined. `test_the_query_count_does_not_grow_with_the_number_of_cards` passes unchanged |
| **No per-card catalog read** | The join happens once per card from an in-memory map, not a query |
| **No recomputation at render** | Nothing is scored, ranked, or derived. AD-10's own architecture test still passes |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Where the state lives | **Read at read time, not stored on the composition** | The composition is append-only and AD-10 says it explains *why*. A stored status would be frozen — and the wrong design would have passed every criterion's letter |
| The personal card | **`None` for both fields** | "Not applicable" and "fine" are different facts. `"scheduled"` would claim the catalog had an opinion about a row it has never seen |
| The vocabulary | **The backend's own, unchanged** | `Event.Status` plus a separate flag. A collapsed "state" enum could not say "scheduled and sold out" |
| `is_sold_out` on `PublicEvent` | **Required, not defaulted** | No field on that dataclass has a default, so a new construction site cannot forget the flag and get a silently wrong `False` |
| A cancelled card | **Stays on the digest, marked `cancelled`** | FR-55's removal is at the candidate stage and already shipped. Removing at read time would be a second removal, would break AD-10, and would make the digest flicker |
| `status` as `str`, not `Literal` | **`str`** | `Event.Status` includes `superseded`, which the read cannot produce, so a `Literal` would be a narrower claim than the data model supports — and widening it later breaks the contract. `DigestCardOut`'s other vocabulary fields are `str` for the same reason |
| The frontend | **Not touched** | `frontend-pulse-card-state` is the item that renders it, and it depends on this one. This item gives the API the facts |

## Deviations from Plan

**One, and it was found in review.** The endpoint's OpenAPI `description` enumerated what a
card carries and was silent about the two new fields. The description is the document the
frontend client is generated from, so an omission there is an omission in the *contract* — a
client author reading the contract, not the source, would not learn that a card can say an
event is cancelled, nor that both fields are `null` for a personal event. The description now
states both fields, that they are read at request time, and the two reasons they are `null`.

Nothing else changed from the plan.

## Dependencies Added

None. No new package, no new library, no new service, no new model field.

## How to Verify

1. **The item's own tests**

   ```bash
   cd backend && uv run pytest tests/personalization/test_digest_api.py tests/api/test_catalog_read_service.py -q
   ```

   Expected: `67 passed`.

2. **The whole backend suite**

   ```bash
   cd backend && uv run pytest tests/ -q
   ```

   Expected: `5440 passed, 16 failed` — the 16 are pre-existing date-expired fixtures,
   reproduced identically on stashed code. They belong to `timeline-and-conflicts` and block CI
   on any branch.

3. **The architecture contracts**

   ```bash
   cd backend && uv run lint-imports && uv run ruff check . && uv run ruff format --check .
   ```

   Expected: `19 kept, 0 broken` · `All checks passed!` · `524 files already formatted`.

4. **No migration was needed**

   ```bash
   cd backend && uv run python manage.py makemigrations --check --dry-run
   ```

   Expected: `No changes detected` — the design's central claim, held.

5. **The design's proof, by hand**

   ```python
   # backend/apps/personalization/services/digest_read.py, in _card_for_public
   status="scheduled",   # was: public.status
   ```

   Expected: `4 failed`. The card now says "scheduled" for an event the catalog has cancelled
   — which is exactly the failure this item exists to prevent.

6. **The contract, by hand**

   ```bash
   cd /path/to/EventPulse24 && make client && git diff --stat frontend/lib/api
   ```

   Expected: `openapi.json` and `schema.ts` both change, and `schema.ts` gains
   `status?: string | null` and `is_sold_out?: boolean | null` on `DigestCardOut`.

## Test Coverage

- Tests added: **12** (9 in `test_digest_api.py`, 3 in `test_catalog_read_service.py`)
- Mutations proven able to fail: **5**, each applied, run, and reverted
- Status: **passing**

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues
- [x] Documentation updated (the OpenAPI endpoint description)
- [x] Developer notes captured

## Developer Notes

- **Do not move the status onto the composition.** It is read live because the composition is
  append-only and because a frozen status is the whole bug. The test
  `test_a_state_change_after_the_composition_is_reflected` writes the composition *before* the
  cancellation and reads it *after* — it is the test that would catch the wrong design.
- **The two `None` branches are load-bearing.** A personal card and a card whose catalog event
  is gone both say `None`, not `"scheduled"`. A client cannot otherwise tell "no lifecycle
  here" from "a live event". Mutations 3 and 4 pin each branch separately.
- **`is_sold_out` was required, not defaulted**, on `PublicEvent`. Every other field on that
  dataclass is required for the same reason: a new construction site should fail loudly rather
  than produce a silently wrong `False`.
- **`status` is `str`, not a `Literal`.** `Event.Status` contains `superseded`, which
  `get_public_events` filters out — so a `Literal` over the three producible values would be a
  narrower claim than the model supports, and widening it later would break the contract.
- **A cancelled card stays on the digest.** That is not an oversight and not an FR-55
  conflict. FR-55's removal is at the candidate stage and already shipped
  (`digest_candidates.py:336`). This item marks what is already composed.
- **The frontend does not render either field yet.** `frontend-pulse-card-state` is next, and
  it depends on this item. The API now carries the facts; nothing displays them.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-025*
