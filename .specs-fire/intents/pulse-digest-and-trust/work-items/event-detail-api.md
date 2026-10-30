---
id: event-detail-api
title: The Detail Screen API and the neighbor count
intent: pulse-digest-and-trust
complexity: medium
mode: confirm
status: pending
depends_on: [digest-composition-service]
created: 2026-10-30
---

# Work Item: The Detail Screen API and the neighbor count

## Description

The data behind `/events/:id` (FR-24): the event's public facts, the **why-this breakdown** read from the most recent `DIGEST_COMPOSITION` for that `(user, event)` pair, and the **neighbor count** under k-anonymity.

This endpoint is where AD-10's durability rule is proved. The rule is exact: the Detail Screen "is reachable for an Event that is not in today's digest; it reads the **most recent composition** for that `(user, event)` pair, and **renders no explanation rather than recomputing one if none exists**. An explanation is never generated at view time."

The IA marks `/events/:id` as **Authed + Anon (read-only)**, so this endpoint serves two callers with different rights: a signed-in user may see their own explanation; an anonymous visitor may see the event and nothing personal at all (AD-12).

## Acceptance Criteria

- [ ] **The event's public facts** come from `catalog_read`'s published interface — never from `apps.ingestion.models` directly, and never through the Event Fit package.
- [ ] **The why-this breakdown reads the most recent composition** for `(user, event)`, whatever day it was composed, and returns its persisted tags, bucket and Source Badge.
- [ ] **No composition means no explanation.** The response carries an explicit absence — not an empty breakdown, not a zero bucket, not a recomputed one. **A test asserts that requesting the detail for an event never composed for this user returns no explanation and that `domain/ranking.py` was not called.** This is the single most important test in the intent.
- [ ] **An anonymous caller gets the public facts and nothing personal**: no breakdown, no bucket, no neighbor count, no saved state. AD-12 and AD-10 together forbid substituting an Event Fit to fill the gap, and a test asserts the Event Fit read is not reached from this path.
- [ ] **The neighbor count honors k-anonymity (FR-24), as bucketed prose keys:**
  - a **qualifying user** is one who saved **or** opened the detail for this event in the last **30 days**;
  - the threshold is **≥5**; below it the count is **silently suppressed** — no row, no "0 neighbors" copy;
  - buckets are **5–9 / 10–24 / 25–99 / 100+**, returned as keys the frontend renders as "A few / Some / Many / A lot of neighbors saved this";
  - **exact counts are never exposed** in the payload, not even as a number the frontend chooses not to show;
  - the count is **tier-agnostic** — Pro and Free users count identically, so no density difference can leak.
- [ ] **"Same area" is city equality**, not haversine. FR-24 defines it as "≤2 km or same city-zip-cluster", and neither is computable: `Venue` has no coordinates and there is no zip data. The deviation is named in the response's docstring and in the brief, not silently approximated.
- [ ] **Opening the detail is recorded as a qualifying signal**, since the neighbor count depends on it. The write is a named command with its audit entry (AD-5), it does not block the read, and it stores no more than it needs.
- [ ] **"Similar events you've attended" and the reviews count do not ship.** Reviews are ASSUM-6, deferred to Phase 3+; similar-events needs attendance data that does not exist. Both are absent from the payload rather than present and empty.
- [ ] **Sold-out state** (A-15 / FR-53) flows through if the event carries it, since `Event.is_sold_out` already exists.
- [ ] Pydantic schemas, generated client, no hand-written types (AD-19).
- [ ] Tests cover: the breakdown from a composition made today and one made three days ago; **the no-composition case**; the anonymous case; neighbor counts at exactly 4 (suppressed), 5, 9, 10, 24, 25, 99, 100 and 101; the 30-day qualifying window at its boundary; and the detail-open signal being recorded once per the stated rule.

## Technical Notes

**The sources contradict each other on the neighbor count and the stricter rule governs.** EXPERIENCE.md §12's own example breakdown line says "12 of your neighbors saved this", and `event-detail-desktop.html` renders "12 neighbors tracking this in Brooklyn" — both exposing an exact count that FR-24 and §12's "Neighbor Count Privacy" subsection explicitly forbid ("Exact counts are never exposed"). The bucketed prose governs; the example line and the mockup are both wrong. Record it.

**The qualifying-signal write is a privacy decision, not just a counter.** "Opened the detail screen for this event in the last 30 days" is a record of what a named person looked at. It needs a retention category (AD-15), it must not reach a log sink (AD-13), and the design should consider whether a per-`(user, event)` row with a timestamp is the right shape or whether something coarser satisfies the count. The feature is a trust signal; building it carelessly is the opposite.

**Beware the cheap version of the k-anonymity check.** Computing the bucket and then suppressing it in the serializer means the exact count existed in the response-building code and could be logged, cached or leaked by a later change. Suppress before the number is formed.

## Dependencies

- digest-composition-service
