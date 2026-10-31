---
id: digest-composition-models
title: PULSE_DIGEST and DIGEST_COMPOSITION models
intent: pulse-digest-and-trust
complexity: high
mode: validate
status: completed
depends_on: []
created: 2026-10-30
---

# Work Item: PULSE_DIGEST and DIGEST_COMPOSITION models

## Description

Builds the two entities AD-16's ownership table assigns to `personalization` and that nothing has created yet: **`PULSE_DIGEST`** (one user's digest for one local day) and **`DIGEST_COMPOSITION`** (one event's persisted explanation within it).

`DIGEST_COMPOSITION` is the per-user half of AD-10. The spine says exactly what it holds: "the persisted Why-this Tags, Confidence Pulse, and Source Badge for one Event in one user's digest at one composition time. A **Pulse Card is a projection of it**, never a stored entity." It is the row the card reads, the row the Detail Screen reads, and — in the delivery intent — the row the email reads. All three must read the same row, or three surfaces give three answers to "why this?".

AD-10 adds the durability rule that makes this model load-bearing beyond today: "A `DIGEST_COMPOSITION` row is **immutable** and retained per AD-15. The Detail Screen is reachable for an Event that is not in today's digest; it reads the **most recent composition** for that `(user, event)` pair, and renders no explanation rather than recomputing one if none exists."

## Acceptance Criteria

- [ ] Both models live in `apps/personalization/models.py`, in the **`personal` schema**, written **only** by `personalization` (AD-16). The existing `AD-2 only apps.personalization imports apps.personalization.models` protected contract covers them.
- [ ] **The user is held by value** — a `UUIDField`, no relation to `User` — following OQ-8 and every other model in this file.
- [ ] **The event is held by value.** `event_id` is a catalog `Event`'s id with **no foreign key**, because AD-3 forbids a relation across the wall. The same treatment `SavedEvent.event_id` already uses.
- [ ] **`PulseDigest`** is keyed uniquely by **`(user_id, local_date)`** — one digest per user per local calendar day. It records the `timezone` the local date was computed in, `composed_at`, and whether it is the **empty-state** digest (FR-8), which is a real digest with zero compositions, not an absent row.
- [ ] **`DigestComposition`** records, per event in that digest: the **slot** (must-know / nearby / serendipity, as `TextChoices`), the **raw score** as `numeric(3,2)` `Decimal`, the **bucket** 1–5, the ordered **Why-this Tag keys**, the **Source Badge** variant, the event's **`event_version`** at composition time, the event kind (**public** vs **personal**), and `composed_at`.
- [ ] **A composition is immutable.** It follows the `AppendOnlyModel` pattern already in `shared/models.py` (as `EventStateChange` does): an update raises rather than silently rewriting history. A re-composition for the same `(user, local_date)` is not an update — see the composition-service item, which treats an existing digest as already done.
- [ ] **No duplicate event within one digest:** a unique constraint on `(digest, event_id)` holds FR-5's "a Pulse Card in the digest is not a duplicate of another" at the database, not in application code.
- [ ] **Both models declare a retention category** (AD-15), or `manage.py check` fails and they cannot ship. **No source states a retention window for digest compositions** — PRD §10.2 covers preference signals (12 months rolling), email events (90 days) and audit logs (24 months), but says nothing about this one. The design doc must choose a category, state the reasoning, and record that the sources are silent, because AD-10's "most recent composition for that `(user, event)` pair" promise fails the moment the sweep deletes the only composition an event ever had.
- [ ] **The index the Detail Screen needs exists:** finding the most recent composition for one `(user_id, event_id)` pair is a single indexed lookup, not a scan. The digest read (all compositions of one user's current digest, in slot order) is likewise indexed.
- [ ] A **`str`/`repr`** that names the slot and bucket without leaking event content, consistent with how `CalendarConnection` keeps its credential out of `repr`.
- [ ] Migrations are generated against the **`personal`** database alias and the router sends them there; `manage.py check` and the migration test pass on both aliases.
- [ ] Tests cover the uniqueness constraints (both of them, by asserting the `IntegrityError`), immutability refusing an update, the retention category being declared, `Decimal` round-tripping at two decimal places, and the most-recent-composition lookup returning the newest row when several exist for one `(user, event)`.

## Technical Notes

**Why two models and not one.** A digest with zero cards is FR-8's empty state and must be distinguishable from "we never composed for this user today" — the first is a fact the user is shown, the second is a job that has not run. One model with nullable everything cannot express that difference; a parent row with zero children can. The design doc should confirm this reasoning or replace it with a better one, not inherit it unexamined.

**Confidence Pulse persistence is a live conflict between sources, already settled.** PRD Glossary §3 says the Confidence Pulse is "Persisted on the Event record" — which AD-3 makes impossible, since it is per-user data and `Event` lives in `catalog`. AD-10 and AD-16 put it on `DIGEST_COMPOSITION` in `personal`. The architecture governs; the PRD amendment is owed and recorded in the brief.

**The bucket is persisted, not derived at read.** AD-10 says explanations are never recomputed at render, and EXPERIENCE.md's hysteresis is "per-event-per-day … no persistent bucket is stored between days" — meaning the bucket is stored *on the composition* (which is itself per-day) and not in a separate carry-over table. The design doc should state how yesterday's bucket is found for the hysteresis comparison: it is the previous day's composition row, which is exactly why these rows outlive their day.

Mind the storage shape of the tag keys. `EventFit.tags` is a `JSONField(default=list)` holding ordered keys; matching it keeps the two explanation kinds structurally parallel, which is useful for a reader comparing them and harmless otherwise.

## Dependencies

(none)
