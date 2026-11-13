---
work_item: browse-read-api
intent: browse-surface
complexity: high
mode: validate
checkpoint: 1
status: approved
approved_at: 2026-11-12
created: 2026-11-12
---

# Design: The Browse Read API

## The decision this document exists for

Browse needs ranked, city-scoped, upcoming events with an explanation on every card. Two
reads in this codebase already produce almost exactly that, and **choosing the wrong one is a
trust bug, not a performance one.**

`apps/ingestion/event_fit/reads.py` offers `list_city_event_fits(city_ref_id, now, offset,
limit)`. Mechanically it is a near-perfect fit: canonical-city key, offset paging with a total
order so *"a row cannot move between pages"*, the staleness skip, the publication filters and
the upcoming bound all shared with the preview. It is what the city page uses.

**Browse must not use it.** AD-10 is an import contract enforced in both directions:

```toml
name = "AD-10 personalization never reaches the Event Fit"
source_modules    = ["apps.personalization"]
forbidden_modules = ["apps.ingestion.event_fit", "apps.ingestion.event_fit.*"]

name = "AD-10 the Event Fit is computed on the catalog side, from catalog facts"
source_modules    = ["apps.ingestion"]
forbidden_modules = ["apps.personalization"]
```

and its stated reason is precisely Browse's hazard:

> Two indicators that look identical must never be silently substituted for one another —
> that is the trust-collapse failure PRD Risk 11 calls company-ending.

**Event Fit is the explanation for a stranger**: per `(event, city)`, on `catalog`, computed
from the event's start time, extraction confidence and venue city, deliberately blind to who
is looking. **The Relevance Pulse is per user**: on `personal`, owned by `personalization`.

Browse is an authed surface whose cards carry why-tags and a confidence row, and whose first
section head reads **"3 worth your attention today"**. *Your* attention. If those cards showed
Event Fit's tags and score, a signed-in user would see a stranger's explanation wearing the
personal one's clothes, on a surface one click from the Digest — which shows the real personal
one, in the same card vocabulary. That is the substitution AD-10 forbids, and the import
linter would reject the code anyway.

So Browse ranks with the **Relevance Pulse**, reading its candidates from the published
catalog interface, exactly as the Digest does.

## Key decisions

| # | Decision | Choice | Rationale |
|---|---|---|---|
| D1 | Candidate source | `catalog_read.list_public_candidates(now, city, limit)` | The digest's own pool read. City-filtered, every publish/confidence/tz gate applied in the database against shared constants (AD-8), `source_badge` resolved catalog-side, returns frozen `PublicEventCandidate` — no model reference crosses the wall. Using Event Fit instead would breach AD-10. |
| D2 | Ranking | `domain/ranking.py` — `relevance_score`, `why_this_tags`, `score_bucket` | Pure stdlib, no Django, `now` already a parameter. The same functions the Digest ranks with, so the two surfaces explain an event the same way. |
| D3 | Service location | new `apps/personalization/services/browse_read.py` | Mirrors `digest_candidates.py` + `digest_composition.py`: the public facts arrive as plain data and the personal join happens on the personalization side, because `apps.ingestion` may not import `apps.personalization`. |
| D4 | The 7-day bound | add `starts_before: datetime \| None = None` to `list_public_candidates` | The read already bounds the *lower* end ("starting in the future") and takes `city`; it has no upper bound because a digest does not need one. Defaulting to `None` leaves digest behaviour byte-identical. |
| D5 | Paging | explicit `offset` + `limit` on the Browse read, total order `(score desc, start_time asc, id asc)` | The 24-card soft cap loads more in place. The city-page read documents the hazard — a non-total order lets a row move between pages and be shown twice or skipped. `id` is the tiebreaker that makes the order total. |
| D6 | `is_saved` | per card, resolved in one batch query | **Approved at checkpoint 1.** See below. |
| D7 | Tier boundary | in the response, not inferred client-side | **Approved at checkpoint 1.** See below. |
| D8 | Quota state | read through `save_cap` + `entitlement.is_pro` | Never a `SavedEvent` row count. `save_cap.py` is explicit: a row count would let unsaving hand the allowance back. |
| D9 | The city | the user's digest preference (`DigestPreferenceOut.city`) | One meaning of "your city" across Digest and Browse, and the reason "Change city" routes to `/settings/account`. |

### D6 — `is_saved`: per card, or a set in the envelope?

**Recommendation: per card.**

The alternative is one `saved_event_ids` set in the response envelope and the client marking
its own cards. That is marginally smaller on the wire and it is how a cache-friendly API might
do it.

Per card wins here because the Save button's *initial* state is a property of the card, and
the acceptance criteria say an already-saved event must render "Saved ✓" **on first paint
rather than flashing "Save"**. A set in the envelope is the same information, but it makes
every card's initial state a client-side join — which is one more place for the flash to
reappear when a later refactor renders a card before the envelope is read.

Cost: one extra query per request. `SavedEvent` rows for this user, filtered to the candidate
ids — an `IN` clause, the same shape `get_public_events` uses and for the same stated reason
("the batch is the same query with an `IN` clause instead of five queries with an `=`").

### D7 — where the tier boundary is decided

**Recommendation: the server names the tiers.**

The design splits cards into "3 worth your attention today" and "More this week". A client
could take the first three of a score-ordered list and call it tier 1. That works until the
rule changes — if tier 1 ever becomes "score above a threshold, at most 3" or "at most 3, but
never a cancelled event", every client re-implements it, and the Digest's and Browse's idea of
"worth your attention" drift apart silently.

The response carries an explicit tier per card, or an index where tier 2 begins. The client
renders section heads from what it is told.

**Note for implementation:** the second section head's meta is "144 events · scroll for more",
so the response also needs a **total count** for the window — distinct from the number of
cards in this page.

## Domain model

No new models, no migration. Browse is a read.

```
  catalog (apps.ingestion)                personal (apps.personalization)
  ────────────────────────                ───────────────────────────────
  Event, Venue, Source                    SavedEvent        DigestPreference
        │                                       │                  │
        │ list_public_candidates(               │                  │
        │   now, city, starts_before, …)        │                  │
        ▼                                       │                  │
  PublicEventCandidate  ─── plain frozen data ──┼──────────────────┘
  (id, slug, title, start_time_utc/tz,          │
   venue_*, status, event_version,              │
   source_name, source_badge, confidences)      │
                         │                      │
                         ▼                      ▼
              apps/personalization/services/browse_read.py
                 · rank   → domain.ranking.relevance_score
                 · explain→ domain.ranking.why_this_tags
                 · confide→ domain.confidence
                 · join   → SavedEvent (one IN query)  → is_saved
                 · gate   → save_cap + entitlement.is_pro → quota
                 · split  → tier 1 (top 3) / tier 2 (rest)
                         │
                         ▼
                 GET /api/personal/browse
```

**AD-3 holds**: no transaction spans the two aliases and no query joins them. Two reads, joined
in Python, exactly as `digest_candidates.py` documents.

## API contract

```
GET /api/personal/browse?offset=0&limit=24
```

Session required. Response sketch:

```jsonc
{
  "city": "Brooklyn",
  "city_source": "onboarding",
  "timezone": "America/New_York",
  "window": { "from": "...", "to": "..." },     // tonight → +7 days, user's zone
  "total": 147,                                  // for "144 events · scroll for more"
  "tier_2_starts_at": 3,                         // D7
  "quota": { "used": 0, "cap": 1, "resets_at": "...", "is_pro": false },
  "cards": [
    {
      "event_id": "...", "slug": "...", "title": "...",
      "start_time_utc": "...", "start_time_tz": "...",
      "venue_name": "...", "venue_city": "...",
      "source_badge": "...", "status": "...",
      "tags": ["..."],                           // why_this_tags — the PERSONAL explanation
      "confidence": 3,
      "stripe": "public" | "must_know",          // server-capped, see below
      "is_saved": false
    }
  ],
  "has_more": true
}
```

**The must-know stripe is capped server-side.** The acceptance criteria say at most one card
per response may carry it, enforcing the existing <10% rule. A client-side cap would let two
pages each show their own "one", so the page as a whole floods.

**Zero events is not an error.** An empty `cards` with `total: 0` is the "Nothing nearby
tonight" state. A failure is a non-200. The frontend must be able to tell them apart, and this
is where that distinction starts.

## Risks

| # | Risk | Mitigation |
|---|---|---|
| 1 | **Changing `list_public_candidates` changes the Digest.** It is the digest's pool read. | `starts_before` defaults to `None`, preserving current behaviour exactly. A test asserts the digest's pool is unchanged when the parameter is omitted. |
| 2 | **`CANDIDATE_POOL_SIZE` is a digest-shaped bound.** A digest ranks a pool and picks 3; Browse pages through 24 at a time and claims a `total` of 147. | Decide the Browse limit explicitly rather than inheriting the digest's constant, and measure the cost of the `total` count. If counting the window is expensive, it is one `COUNT(*)` with the same filters, not a second fetch. |
| 3 | **Ranking cost.** `relevance_score` is per event in Python, not in the database. A 147-event window scores 147 rows per request. | Measure. The Digest already does this for its pool. If it is too slow, the answer is a bounded pool per page, not moving the score into SQL — the score is domain logic and `domain/` is where it is allowed to live. |
| 4 | **Ordering must be total or paging lies.** | `(score desc, start_time asc, id asc)`. A test pages through a window twice and asserts no event appears in two pages and none is skipped. |
| 5 | **The user may have no city set.** Onboarding can be skipped. | Decide the behaviour explicitly: most likely the same "Nothing nearby / Change city" empty state rather than an error. It must be a stated decision, not an accidental 500. |
| 6 | **The import linter will reject an AD-10 breach at review time, not at design time.** | `make lint-imports` runs in the test gate for this item, and the design above keeps `browse_read.py` on the personalization side with only `catalog_read` imported. |

## Implementation checklist

- [ ] `starts_before` added to `list_public_candidates`, defaulting to `None`; digest behaviour test
- [ ] `apps/personalization/services/browse_read.py` — candidates → rank → explain → join → split
- [ ] `is_saved` batch query (one `IN`, not per card)
- [ ] Quota state via `save_cap` + `entitlement.is_pro`
- [ ] Must-know stripe capped at one per response
- [ ] `GET /api/personal/browse` with session requirement matching the other `/api/personal/*` routes
- [ ] Total-order paging test: two passes, no duplicates, no gaps
- [ ] Window boundary test: 11pm local on day 7 in, 1am local on day 8 out
- [ ] Zero-events response distinguishable from a failure
- [ ] Pro user's quota state reports no cap
- [ ] OpenAPI regenerates; `make client` produces types with no manual edits
- [ ] `make lint-imports` green — 19 contracts kept

## Checkpoint 1 — resolved

All four open questions were decided by Jobaer on 2026-11-12, each the recommended option.

| # | Question | Decision |
|---|---|---|
| D6 | per-card `is_saved` vs a set in the envelope | **Per card.** The initial Save state is a property of the card, and the criteria require "Saved ✓" on first paint rather than a flash. |
| D7 | who names the tiers | **The server.** An explicit tier boundary in the response, so the rule lives in one place and Browse cannot drift from the Digest's idea of "worth your attention". |
| Risk 5 | a user with no city set | **The designed empty state** — "Nothing nearby tonight. Try a wider city?" with "Change city" to `/settings/account`. No geo-IP guess: Browse must not show a city the user never chose. No new prompt surface, because the design does not contain one. |
| Risk 2 | `total` for the second section head | **Yes, one `COUNT(*)` per request**, same filters as the candidate query. The cost is to be **measured and reported**, not assumed free. |

### One tension to carry into implementation

The anti-pattern list bans **count badges** ("No count badges anywhere. No 'saved 7' or '47
nearby' or any numeric tag"), and the second section head's own copy is "144 events · scroll
for more". These are not the same thing — a section head's meta line is layout scaffolding,
and a count badge is a decoration attached to a card or a nav item — but they are close
enough that the implementation should not let the number migrate anywhere else on the surface.
The count appears in the section head meta and nowhere else.
