---
id: digest-read-api
title: The digest read API
intent: pulse-digest-and-trust
complexity: medium
mode: confirm
status: pending
depends_on: [digest-composition-service]
created: 2026-10-30
---

# Work Item: The digest read API

## Description

The endpoint `/` reads: today's persisted digest for the signed-in user, as the card payload FR-6 specifies. It is a **read of persisted rows and nothing else** — no scoring, no ranking, no tag generation, no fallback that computes anything. AD-10's rule is that explanations are never recomputed at render, and this endpoint is where that rule either holds or is quietly broken.

It is also where the <500ms p95 budget is met. PRD §11.1 sets digest composition at <500ms p95 cached and <3s p95 cold, and EXPERIENCE.md states the consequence plainly: "Performance is a behavioral contract: a slow digest is a broken digest." A breach is a SEV-1.

## Acceptance Criteria

- [ ] **A session-authenticated endpoint** returning the current user's digest for their local date, with auth resolved at the API edge and an explicit actor passed to the service — never a `request` — following the seam `auth-api-and-session-seam` established. An anonymous request gets 401, not a preview.
- [ ] **The payload carries all six of FR-6's elements per card**: event name, time, location, up to 3 Why-this Tags, the 1–5 Confidence Pulse bucket, and the Source Badge variant. Plus: the slot, the personal/public kind, the conflict flag, `tz_review_pending`, and whether the event is already saved.
- [ ] **Time is carried as an instant plus the IANA zone**, and converted at the presentation edge (AD-6: "display-time conversion happens at the presentation edge, never in domain logic"). The API does not send a pre-formatted local string.
- [ ] **The empty state is a distinct, explicit response** — a digest that exists with zero cards — never an empty list that the frontend has to interpret, and never a 404. It carries the city, because FR-8's copy is "No qualifying events in **{city}**."
- [ ] **A digest that has not been composed yet is distinguishable from an empty one.** These are different facts and the frontend shows different things; collapsing them is the bug this AC exists to prevent.
- [ ] **Nothing is computed.** A test asserts the endpoint path never calls `domain/ranking.py` and never writes a row — the read is a read. If no composition exists, it says so; it does not compose one on demand.
- [ ] **Request and response are Pydantic schemas in `apps/personalization/schemas.py`** (AD-19: never ad-hoc dicts), and the endpoint appears in the OpenAPI schema with the generated TypeScript client regenerated in CI. No hand-written client.
- [ ] **The query count is bounded and asserted.** Three cards must not become three-plus queries per card; a test pins the count so an N+1 cannot land silently inside a 500ms budget.
- [ ] **No `personal` data leaks into any public surface**, and this endpoint is never reachable without a session (AD-12's wall runs the other way here, but the separation is the same one).
- [ ] **Rate limiting** follows the per-user pattern the existing endpoints use.
- [ ] Tests cover: a composed digest returning three cards in slot order; the empty-state response; the not-yet-composed response; a 401 for anonymous; the query-count bound; the saved and conflicted flags; and `tz_review_pending` surviving to the payload.

## Technical Notes

**The Relevance Pulse is sent as a bucket, not as a score.** FR-22's raw `relevance_score` is an internal number; the card shows 1–5 dots. Sending the raw score would invite the frontend to re-bucket it — which is the "recomputed at render" failure wearing a different hat, and would also break hysteresis, since the bucket the user saw this morning is a persisted fact about their day. Send the bucket. If the tooltip's contributing-factor lines need more, they come from the persisted tags, not from the score.

**Source Badge variant, not a rendered label.** The five variants map to labels and tooltip copy in the design system; the API sends the variant key. Same reasoning as the tag keys in `domain/ranking.py`.

Check whether `apps/personalization/api.py` or a new router is the right home, given that the digest is a different concern from personal events and saved events. Either is defensible; what matters is that the schemas live with the surface that owns the contract, as `catalog_read.py`'s docstring already establishes.

## Dependencies

- digest-composition-service
