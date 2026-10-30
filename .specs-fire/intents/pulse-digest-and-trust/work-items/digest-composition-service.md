---
id: digest-composition-service
title: The composition command (slots, determinism, the empty state)
intent: pulse-digest-and-trust
complexity: high
mode: validate
status: completed
depends_on: [digest-ranking-domain, digest-composition-models, digest-user-preferences, digest-candidate-reads]
created: 2026-10-30
---

# Work Item: The composition command (slots, determinism, the empty state)

## Description

The command that turns candidates into a persisted digest: it reads both sides of the wall, scores with `domain/ranking.py`, assigns A-2's three slots, and writes one `PULSE_DIGEST` with its `DIGEST_COMPOSITION` rows. It is the application-layer join AD-3 forces, and the place where "exactly 3 cards" and "deterministic per user per day" become true or stop being true.

It runs in the **worker**, never in a request (AD-11), and it is the only writer of these rows (AD-16, AD-5: every mutation is a named command that owns its validation and its audit-log write).

## Acceptance Criteria

- [x] **A named command** in `apps/personalization/services/`, taking an explicit actor and an explicit `now` — never a `request` — following the shape of the existing services in that package.
- [x] **Exactly 3 compositions on a standard day**, one per slot, in A-2's order:
  1. **must-know** — an eligible personal event within 48 hours if one exists and the user has not opted out; otherwise the highest-scoring eligible public event;
  2. **nearby** — the highest-scoring remaining public event;
  3. **serendipity** — the highest scorer under the **inverted** preference term.
- [x] **No duplicate `event_id` across the three slots.** The model's unique constraint is the backstop; the service must not rely on an `IntegrityError` to notice. A test composes against a candidate pool where the same event would win two slots and asserts three distinct events.
- [x] **Determinism (FR-30, `[ASSUMPTION-2]`):** composing for the same `(user, local_date)` twice returns **the identical persisted rows** — the second call is a no-op that returns the existing digest, not a second composition and not an update to an immutable row. Ties in scoring break on a **stable, documented key** (an explicit ordering, never database order), so two runs over the same candidates cannot disagree.
- [x] **The local date is the user's, in their stored timezone** (AD-6), not UTC and not the server's. A user at 23:00 local on the 1st and a user at 01:00 local on the 2nd get different digests even if both run in the same UTC minute. A DST-transition day is tested.
- [x] **Hysteresis is applied across days** by reading the previous day's composition for the same `(user, event)` and passing its bucket and score into `domain/ranking.py`'s hysteresis function. A card whose score drifted by less than 0.10 within a day keeps its bucket; across days it resets.
- [x] **The empty state (FR-8) is a real digest with zero compositions**, written when there are **no qualifying public events *and* no eligible personal events** — FR-5 widens FR-8's own trigger, and both halves are tested separately.
- [x] **The personal-events opt-out is honored:** an opted-out user's digest contains no personal event in any slot, and Slot 1 falls back to the highest-scoring public event.
- [x] **Conflicted events still appear.** A conflict is an indicator on a card (FR-58), not an exclusion — the card carries the flag and the user decides. `/conflicts` and the resolution sheet are out of scope.
- [x] **The whole composition is written in one transaction on the `personal` alias.** AD-3's accepted cost is that no transaction spans both schemas, so the catalog reads happen first, outside it, and the write is atomic on its own side.
- [x] **An audit entry is written** through `personalization`'s existing `write_audit` (AD-5), recording that a digest was composed for a user on a date — never the event content or anything about the user beyond the ids the audit log already carries (AD-13).
- [x] **No LLM call, no embedding call, no network call** anywhere in the path.
- [x] Tests cover: the three slots filled from a realistic pool; Slot 1's personal-event preference and its public fallback; Slot 1 with the opt-out set; the duplicate-suppression case; determinism across two runs; the re-run no-op; both halves of the empty-state trigger; the local-date boundary across DST; hysteresis holding and releasing across days; a user with no interest chips at all (the skip-everything onboarding path); and a user whose candidate pool has fewer than 3 events, which must produce a short digest or an empty one by a stated rule rather than by accident.

### Two criteria that were resolved against a conflicting source

**The hysteresis criterion is internally contradictory, and the canonical source won.**
The criterion says hysteresis "is applied across days by reading the previous day's
composition for the same `(user, event)`" *and* that "across days it resets". Those
cannot both hold. EXPERIENCE.md §4 — the canonical source, as the ranking domain
itself says — is explicit: "**Across days, hysteresis resets** … **No persistent bucket
is stored between days.**" So the service passes `previous_bucket=None` and inherits
nothing across the day boundary. The conflict is recorded in the design (D9) rather
than silently resolved; see also D9's note that the *within-day* hold is unreachable
here, because the composed rows are append-only and a mid-day recomposition could not
update one.

**The interest term needed an addition to the item's scope.** The criterion for Slot 3
requires "the highest scorer under the **inverted** preference term", and the criteria
include "a user with no interest chips at all" — but with no *event-side* chips, the
inverted term is provably identical to the plain term (`1 − 0.0`), so the criteria
cannot be met without building the event→chip matching. That matching is now
`apps/ingestion/services/chip_matching.py` plus `INTEREST_CHIP_KEYWORDS` in
`shared/constants.py` (design D7).

## Technical Notes

**The fewer-than-3 case needs an explicit decision and has no source.** FR-5 says "exactly 3 cards on a standard day. Exception: a 'No pulse for today' empty state" — a two-card day is neither. The design doc must choose: pad from a relaxed pool, show two cards, or fall to the empty state. "Exactly 3 or nothing" is defensible and so is "show what there is"; what is not defensible is discovering the answer from whatever the code happens to do at 2 candidates.

**Determinism is a property of the ordering, not of the scorer.** `domain/ranking.py` is deterministic by construction, but two events with identical scores leave the choice to whatever order the queryset returned, which Postgres does not promise. The tie-break key must be explicit and stated in the docstring.

**Watch the cost shape.** This is per-user work on a daily cadence; at MVP scale it is trivial and at 100K MAU it is 100K compositions a day, each reading a candidate pool. The design should say how the job is batched and bounded, the way `schedule_sources` already bounds its claims. AD-1 exists precisely so this cannot compete with a crawl for the same process.

**AD-10's durability promise is made here, not on the Detail Screen.** The Detail Screen can only show an explanation for an event this service once composed. That means the set of events a user can ever ask "why this?" about is exactly the set this service wrote rows for — worth stating in the docstring, because it is the kind of constraint that looks like a bug later.

## Dependencies

- digest-ranking-domain
- digest-composition-models
- digest-user-preferences
- digest-candidate-reads
