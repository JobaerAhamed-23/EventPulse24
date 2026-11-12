---
id: browse-read-api
title: The Browse Read API — Ranked, Authed, City-Aware, Save-Aware
intent: browse-surface
complexity: high
mode: validate
status: completed
depends_on:
  - test-clock-seam
created: 2026-11-12
run_id: run-eventpulse24-029
completed_at: 2026-11-12T10:59:29.042Z
---

# Work Item: The Browse Read API — Ranked, Authed, City-Aware, Save-Aware

## Description

Browse needs a read that no existing endpoint provides. `GET /api/catalog/events` is public
by construction — its own description says *"No session is used and none is set."* It
returns published upcoming events with optional city and date filters, and nothing else: no
ranking, no why-tags, no confidence, no per-card saved state, no quota state, and no notion
of whose city it is.

This item builds `GET /api/personal/browse`: the signed-in user's city, tonight through the
next seven days, ranked by the existing relevance domain, split into the two attention tiers
the design calls for, with each card carrying everything the Browse card anatomy renders and
everything the Save button needs to decide its own initial state.

It is `validate` mode because three decisions here are hard to reverse once the frontend is
built on them: the tier split, the pagination contract for the 24-card soft cap, and whether
saved-state is embedded per card or fetched alongside.

## Acceptance Criteria

- [ ] `GET /api/personal/browse` requires a session; an anonymous request is refused, and the
      refusal matches the shape the other `/api/personal/*` endpoints already use
- [ ] The city comes from the user's existing digest preference (`DigestPreferenceOut.city`),
      not a query parameter and not geo-IP — one meaning of "your city" across both surfaces
- [ ] The window is tonight through +7 days in the **user's** timezone, not UTC midnight;
      an event at 11pm local on day 7 is included and one at 1am local on day 8 is not
- [ ] Cards are ranked with `domain.ranking.relevance_score`; no new scoring logic is
      introduced and `domain/` gains no Django import
- [ ] The response carries two tiers: the top 3 by score, and the remainder ordered by start
      time — and the tier boundary is in the response, not inferred by the client
- [ ] Each card carries: headline, kicker, venue/where line, start time (local + UTC),
      source badge, why-tags from `domain.ranking.why_this_tags`, confidence from
      `domain.confidence`, stripe kind (public | must-know), and `is_saved`
- [ ] **At most one card per response carries the must-know stripe** — the existing <10% rule
      is enforced server-side, so the client cannot flood the page by accident
- [ ] The response carries the user's quota state — saves used, cap, reset time, and whether
      the user is Pro — read through the existing entitlement and throttle services, never
      by counting `SavedEvent` rows
- [ ] Pagination serves the 24-card soft cap: the first response holds at most 24 cards and
      says whether more exist; the next chunk loads in place
- [ ] An empty window returns an explicit zero-events signal that the client can tell apart
      from a failure — "nothing nearby" and "couldn't reach Browse" are different states
- [ ] Contract test: the OpenAPI schema regenerates cleanly and `make client` produces types
      with no manual edits
- [ ] Every test can fail — including one asserting that an event outside the 7-day window is
      genuinely excluded, and one asserting a Pro user's quota state reports no cap

## Technical Notes

**Verified reuse, confirmed by reading the code at capture:**

- `backend/domain/ranking.py` — `relevance_score(inputs: RankingInputs)`, `why_this_tags(...)`,
  `score_bucket(score)`. Pure stdlib, frozen dataclass input, `now` passed in as a parameter.
  This is the seam; use it.
- `backend/domain/confidence.py` — the confidence indicator the card anatomy calls for.
- `apps/identity/services/entitlement.py` — `is_pro`, described in `save_cap.py` as *"the
  single entitlement read this project has"*. It returns a bool. Use it; do not add a second.
- `apps/personalization/services/save_cap.py` — the throttle-port-backed gate. Read quota
  state through it rather than reimplementing the count.

**The thing most likely to be got wrong:** `apps.personalization` may not import
`apps.identity.models` — `save_cap.py` says so explicitly and `make lint-imports` enforces
it. Entitlement is read through the published service, not the model.

**Open question for checkpoint 1:** whether `is_saved` belongs on each card or in a separate
set in the response envelope. Per-card is simpler for the client; a set is cheaper if the
saved list is large. Decide it in the design doc, with the reasoning written down.

## Dependencies

- test-clock-seam
