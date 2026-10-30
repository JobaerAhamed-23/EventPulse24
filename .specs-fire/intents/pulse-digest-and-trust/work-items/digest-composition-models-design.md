---
id: digest-composition-models
title: PULSE_DIGEST and DIGEST_COMPOSITION models — design
intent: pulse-digest-and-trust
mode: validate
created: 2026-10-30
---

# Design: `PulseDigest` and `DigestComposition`

Two models in `apps/personalization/models.py`, in the `personal` schema, written only by
`personalization` (AD-16).

`PulseDigest` is one user's digest for one local day. `DigestComposition` is one
event's persisted explanation within it. The card, the detail screen and (later) the
email all read the same `DigestComposition` row — AD-10's "never recomputed at render",
and the reason three surfaces cannot give three answers to "why this?".

## The spine's own words

AD-10: "the persisted Why-this Tags, Confidence Pulse, and Source Badge for one Event in
one user's digest at one composition time. A **Pulse Card is a projection of it**, never a
stored entity."

AD-10: "A `DIGEST_COMPOSITION` row is **immutable** and retained per AD-15. The Detail
Screen is reachable for an Event that is not in today's digest; it reads the **most recent
composition** for that `(user, event)` pair, and renders no explanation rather than
recomputing one if none exists."

That last sentence is the constraint that decides the retention category, and it is
picked apart in D4.

## Decisions

### D1 — Two models, and the parent row is what makes the empty state expressible

FR-8's empty digest is "a real digest with zero compositions" — a fact the user is shown
("nothing near you today"), which is different from "we never composed for this user
today", which is a job that has not run. A single model with nullable columns cannot
tell those apart: the empty digest and the uncomposed day look identical.

A parent row with zero children can. `PulseDigest` exists; it has no compositions; that
is the empty state. No `PulseDigest` at all means the job has not run.

The work item asks for this reasoning to be confirmed rather than inherited. It is
confirmed, with one addition: `PulseDigest.is_empty` is a **stored flag**, not a derived
one, so a reader does not have to count children to know whether this was a deliberate
empty digest or a composition that happened to fail. The flag is set at composition time.

**The flag is not immutable, because the row is not append-only.** `DigestComposition`
is immutable (D3); `PulseDigest` is not — it is a fact about a day, and the runtime role
keeps `UPDATE` on it so a correction can land. "Set at composition time" is the
composition service's discipline, not a database guarantee, and the model says so
rather than claiming a guarantee it does not have.

### D2 — Every relation is held by value, including the parent

OQ-8: "the project holds every relation by value." The precedent is
`PersonalEvent.calendar_connection_id` — a `UUIDField`, not a foreign key, even though
`CalendarConnection` is in the *same* schema:

> `CalendarConnection` is in the same schema (`personal`), so this does not cross the
> AD-3 wall, but the project holds every relation by value (OQ-8), and a foreign key
> would couple the purge of a connection to the purge of its events.

The same reasoning applies with more force here. A foreign key from `DigestComposition`
to `PulseDigest` would make the digest's deletion cascade into its children — and
AD-10 says a composition is immutable and must outlive its day. Holding `digest_id` by
value means the retention sweep can purge a digest's compositions in an order the
application chose, rather than in an order the database chose.

**Both** the user and the event are held by value as well:

- `user_id = models.UUIDField()` — the OQ-8 pattern, identical to every model in the
  file.
- `event_id = models.UUIDField()` — the catalog Event's id by value, no foreign key,
  because AD-3 forbids a relation across the wall. Same treatment `SavedEvent.event_id`
  already uses.

**Consequence for the architecture tests.** `tests/personalization/test_model_structure.py`
asserts that no model in the app declares any relation field, over a hardcoded `MODELS`
list. `PulseDigest` and `DigestComposition` are added to that list — and they will pass,
because by-value holding means there is no relation field at all.

### D3 — `DigestComposition` is append-only, with no mutable field

`DigestComposition` extends `AppendOnlyModel`. The migration installs the
`forbid_history_mutation()` trigger on the table and the runtime grants.

**`append_only_mutable = frozenset()`** — the inherited default. Nothing is settable
after insert. This is different from `EventStateChange`, the other append-only table,
whose `propagated_at` goes from NULL to a value exactly once; a composition has no such
field, because nothing about a composition becomes known later.

The `personal` schema already has `personal.forbid_history_mutation()` — installed by
`personalization/migrations/0001_initial.py` — and **it has no `TG_ARGV[0]` branch**,
which is exactly right for a fully immutable table. The new migration reuses that
function and adds only the trigger.

This makes `DigestComposition` the first non-audit `AppendOnlyModel` in the `personal`
schema, and the first table in the app that needs `Meta.base_manager_name = "objects"`
so that related-object paths use the guarded queryset too.

**The consequence for the immutability test.** `AppendOnlyModel.save()` raises
`AppendOnlyViolation` (a `RuntimeError`), **not** an `IntegrityError`. A test that
asserts immutability by expecting `IntegrityError` would pass against a table with no
trigger at all, because the Python guard fires first. The test therefore asserts
`AppendOnlyViolation` at the ORM level *and* `RestrictViolation` at the SQL level, in
the style of `tests/personalization/test_triggers.py`.

### D4 — The retention category: `ACCOUNT_CONTENT`, and the gap is named

**No source states a retention window for digest compositions.** PRD §10.2 covers
preference signals (12 months rolling), email events (90 days) and audit logs (24
months). It says nothing about this table. The brief names this as a gap that must be
recorded rather than papered over.

Two categories are plausible and the choice matters:

| Category | Window | Effect on AD-10's "most recent composition" promise |
| --- | --- | --- |
| `PREFERENCE_SIGNALS` | 12 months rolling | **Breaks it.** A composition is deleted 12 months after it is written, so an event's most recent composition can vanish while the event is still upcoming, or while the user is still looking at it. The Detail Screen would render no explanation for an event it explained yesterday. |
| `ACCOUNT_CONTENT` | While the account is active; purged ≤30 days after deletion | **Keeps it.** A composition lives as long as the account does, so the most recent composition for a `(user, event)` pair exists for as long as the user exists. |

**`ACCOUNT_CONTENT` is chosen.** A digest composition is user content: it is a record of
what this user was shown and why, it is rendered to them, and it is the per-user half of
a product surface. It is not a preference *signal* — `PREFERENCE_SIGNALS` is for the
inputs to the preference graph (dwell, swipes, dismissals), and a composition is an
*output*. `Interest`, `OnboardingProgress` and `DigestPreference` are inputs and sit
correctly in `PREFERENCE_SIGNALS`; a composition is not an input to anything yet.

**The gap is recorded, not resolved.** The category is a declaration, and the retention
sweep that would enforce a window is not built. The category chosen here is the
*semantic* one — "this is the user's content, it lives as long as they do" — and when a
sweep is built it must treat `ACCOUNT_CONTENT` as "while the account is active", which
is the only reading under which AD-10's promise holds.

**`PulseDigest` takes the same category.** A digest row without its compositions is
meaningless, and the two must be purged together; `ACCOUNT_CONTENT` puts them in the
same bucket.

### D5 — The score is `numeric(3,2)` and the bucket is a small integer

The raw score is a `Decimal` in [0, 1] with two decimal places — the precision
`domain/ranking.py` produces (`SCORE_PRECISION = Decimal("0.01")`).

**`numeric(3,2)`** is the column type: precision 3, scale 2, so the value is
`0.00`–`1.00`. It is stored as an exact decimal, never a float, because the score is
the thing the user sees and the bucket boundaries in FR-22 are exact.

The bucket is a `PositiveSmallIntegerField` with a check constraint `1 <= bucket <= 5`.
The five values are FR-22's, and a check constraint is what makes a sixth one
impossible at the database.

### D6 — The slot is a `TextChoices`; the tag keys are a `JSONField` of ordered strings

**The slot** is a nested `models.TextChoices`, in the house style
(`ConflictPair.Kind`, `CalendarConnection.Provider`): uppercase member names, lowercase
string values, a docstring on the class, and `choices=Slot.choices` on the field.

The three values are FR-5's three slots: must-know, nearby, serendipity. The work item
names them in prose; the values are the slugs the rest of the codebase uses.

**The tag keys** are a `JSONField(default=list)` holding the ordered keys — the same
storage shape `EventFit.tags` uses. Keeping the two explanation kinds structurally
parallel is what lets a reader compare them, and it means the Why-this Tag order is
**the list order**, not an alphabetical accident.

The keys are the *server's* statement, not display strings: `nearby`, `tonight`,
`tomorrow`, `weekend`, `saved`, `discovery`, `matches_<chip_key>`. The frontend renders
them; `domain/ranking.py` produces them.

**The Source Badge** is a `CharField` holding the badge *type* — `official_site`,
`community`, `aggregator`, `crawled_html` — and those constants already exist in
`apps/ingestion/services/preview_read.py`. The badge is a type, not a label and not an
icon (EXPERIENCE.md §4); the server names the type and the client owns the label and
the glyph.

A digest composition for a **personal** event has no source badge: a personal event did
not come from a source at all. The field is nullable, and a check constraint says so —
a personal composition must have no badge, and a public one must have one.

### D7 — The event kind is stored, because a personal event has no badge and no catalog row

`event_kind` distinguishes **public** from **personal**. This is not decoration: a
personal event is a row in `personal`, not in `catalog`, so it has no catalog id, no
source, and no `event_version` in the catalog sense.

For a **public** composition, `event_id` is the catalog Event's id and `event_version` is
that Event's version at composition time. For a **personal** composition, `event_id` is
the `PersonalEvent`'s id — still held by value, still a `UUIDField`, and the two live in
the same schema so the id space does not collide in a way that matters.

`event_version` is nullable for a personal composition, and a check constraint ties
nullability to `event_kind`: a public composition must carry a version and a personal
one must not.

### D8 — The indexes the Detail Screen and the digest read need

**The Detail Screen** looks up "the most recent composition for this `(user_id,
event_id)` pair". One indexed lookup, not a scan:

```python
models.Index(fields=["user_id", "event_id", "-composed_at"], name="digest_comp_user_event_idx")
```

The `composed_at` is descending, so the most recent row is the first one the index
yields — the lookup does not sort a result set to find the newest.

**The digest read** gets "all compositions of one user's current digest, in slot order":
the `digest_id` index, plus a slot ordering.

```python
models.Index(fields=["digest_id", "slot"], name="digest_comp_digest_slot_idx")
```

**Two unique constraints**, both required by the work item:

1. `PulseDigest` — `(user_id, local_date)`. One digest per user per local calendar day.
   This is the constraint that makes "deterministic per user per day" true at the
   database rather than in application code.
2. `DigestComposition` — `(digest_id, event_id)`. No duplicate event within one digest,
   which is FR-5's "a Pulse Card in the digest is not a duplicate of another" held at
   the database.

**`local_date` is a `DateField`, and the timezone is stored beside it.** The local day is
not UTC — it is the user's day, and the digest's `timezone` says which zone it was
computed in. A `DateField` rather than a `DateTimeField`, because the day is the unit.

### D9 — `composed_at` is a `DateTimeField`, and the digest's `local_date` is its day

`composed_at` is the instant the composition was made. `local_date` is the user's local
calendar day the digest belongs to. They are different things: a digest composed at
00:30 in Tokyo belongs to the *previous* local day if the composition is for that day.

The digest's `timezone` records the zone the local date was computed in, as an IANA
name — the same convention as `DigestPreference.timezone`.

`PulseDigest` does **not** carry `updated_at`. A digest is a fact about a day, not a
mutable record, and a row whose `updated_at` can change invites the question of what
changed. It carries `created_at` only.

### D10 — `__str__` names the slot and the bucket, and nothing else

AD-13: no PII in what a log line or an admin list column shows.

```python
def __str__(self) -> str:
    return f"{self.slot} digest composition, bucket {self.bucket}"
```

**No event title, no venue, no tag labels.** The event's *content* is the thing the
composition explains, and putting it in `__str__` would put untrusted source text into
every log line that mentions the row — which is exactly the leak AD-9 and AD-13 exist
to prevent. The composition's identity is its slot and its bucket, which is enough to
find it.

Django's `Model.__repr__` delegates to `__str__`, so `repr()` is safe for free. This is
the same one-lever pattern `CalendarConnection` uses to keep its credential out of
`repr`.

`PulseDigest.__str__` names the local date and whether it is empty:

```python
def __str__(self) -> str:
    return f"digest {self.local_date} ({'empty' if self.is_empty else 'composed'})"
```

A local date is not PII — it is the user's own day, and it is already on the row.

### D11 — The table names, and what the migration must do

Django's default table names:

- `personal.personalization_pulsedigest`
- `personal.personalization_digestcomposition`

The migration (`0007_…`) is `CreateModel` × 2, then:

1. `RunSQL` installing the append-only trigger on `digestcomposition`.
2. `RunSQL` installing the runtime grants and the privilege assertion.

**The `personal` schema's `forbid_history_mutation()` is reused as-is.** It has no
`TG_ARGV[0]` branch, which is correct for a table where nothing is settable after
insert.

**The grants.** The runtime role is `ep_personal`. The append-only table gets
`REVOKE UPDATE, DELETE`, and the `DO $$ … has_table_privilege … RAISE EXCEPTION`
block, so a REVOKE that merely warned fails the migration instead of shipping a table
the runtime role can still rewrite. The `GRANTS` constant is module-level and named, so
`tests/personalization/test_grants.py` can import it and assert the block fails when
the REVOKE is missing — the pattern that file already uses for the audit table.

### D12 — The `slot` ordering is a database concern, not a Python one

The digest read returns compositions "in slot order" — must-know, nearby, serendipity.
That is a **fixed order of three values**, and it is not alphabetical, not numeric, and
not the order they were written in.

The index `(digest_id, slot)` gives the database its own order for `slot`, which is the
*alphabetical* order of the slugs — not the slot order. So the read must sort by slot
explicitly, and the enum's declaration order is the source of truth for that sort.

**The design decision:** the slot order is defined **once**, as the declaration order of
the `Slot` `TextChoices` class, and it is exposed as a module-level constant so the read
can sort by it without re-deriving the order from a string comparison. The database
index on `(digest_id, slot)` is for *lookup*, not for *ordering* — the read sorts the
three rows in Python, where three rows cost nothing to sort and the order is then
defined by one constant rather than by a collation.

This is the same decision `apps/ingestion/services/preview_read.py` made for the city
list: "A database's `ORDER BY` on text is a **locale collation**", so the sort that
decides is the one in Python. Here the stakes are smaller — three rows — but the
principle is the same, and the alternative (ordering by a `CASE` expression or a
`PositiveSmallIntegerField` that shadows the enum) is a second place the slot order
lives.

**Consequence:** `DigestComposition.slot` is a `CharField` with `choices=Slot.choices`,
and the *order* comes from `Slot.ORDER`. The `slot` values are stored as their slugs,
so a reader can see "must_know" in the database without a join.

## The models

### `PulseDigest`

| Field | Type | Notes |
|---|---|---|
| `id` | `UUIDField` (pk, UUIDv7) | from `UUIDv7Model` |
| `user_id` | `UUIDField` | by value (OQ-8) |
| `local_date` | `DateField` | the user's local calendar day |
| `timezone` | `CharField(max_length=64)` | the IANA zone the local date was computed in |
| `composed_at` | `DateTimeField` | when the digest was composed |
| `is_empty` | `BooleanField(default=False)` | FR-8's empty state, stored not derived |
| `created_at` | `DateTimeField(auto_now_add=True)` | no `updated_at` — a digest is a fact about a day |

Constraints: unique `(user_id, local_date)`; index `(user_id, local_date)`.

### `DigestComposition`

| Field | Type | Notes |
|---|---|---|
| `id` | `UUIDField` (pk, UUIDv7) | from `UUIDv7Model` |
| `digest_id` | `UUIDField` | the parent `PulseDigest`'s id, by value (OQ-8) |
| `user_id` | `UUIDField` | by value (OQ-8) — denormalised so the Detail Screen lookup is one index |
| `event_id` | `UUIDField` | by value — a catalog Event's id, or a `PersonalEvent`'s id |
| `event_kind` | `CharField(choices=EventKind.choices)` | public vs personal |
| `slot` | `CharField(choices=Slot.choices)` | must-know / nearby / serendipity |
| `score` | `DecimalField(max_digits=3, decimal_places=2)` | the raw Relevance Pulse, exact decimal |
| `bucket` | `PositiveSmallIntegerField` | FR-22's 1–5 |
| `tags` | `JSONField(default=list)` | the ordered Why-this Tag keys |
| `source_badge` | `CharField(max_length=32, null=True, blank=True)` | the badge *type*; null for a personal event |
| `event_version` | `PositiveIntegerField(null=True, blank=True)` | the catalog Event's version; null for a personal event |
| `composed_at` | `DateTimeField` | when this composition was made |

Constraints:

- unique `(digest_id, event_id)` — no duplicate event in one digest.
- check `1 <= bucket <= 5`.
- check `event_kind`/`event_version`/`source_badge` agree: a public composition has a
  version and a badge; a personal one has neither.

Indexes:

- `(user_id, event_id, -composed_at)` — the Detail Screen's "most recent composition for
  this `(user, event)` pair", in one lookup.
- `(digest_id, slot)` — the digest read's lookup.

## What this item does not decide

- **How a composition is written.** The composition service owns the write: it reads
  both sides of the wall, scores with `domain/ranking.py`, assigns the slots and writes
  the rows. This item ships the tables it writes into and the rules the database holds.
- **How the previous day's bucket is found for the hysteresis comparison.** It is the
  previous day's composition row for the same `(user, event)` — which is why these rows
  outlive their day. The lookup is the composition service's; this item makes it
  possible, with the index above and the retention category that keeps the rows around.
- **The digest's card count.** "Exactly 3 cards" is the composition service's rule.
- **The source badge for a personal event**, which does not exist — the field is null and
  the check constraint says so.

## Decisions summary

| # | Decision | Why |
|---|---|---|
| D1 | Two models; `is_empty` stored on the parent | FR-8's empty digest is a fact shown to the user; "we never composed" is a job that has not run. One model with nullable columns cannot tell them apart. |
| D2 | Every relation by value, including `digest_id` | OQ-8; and a FK would cascade a digest's deletion into its children, when AD-10 says compositions are immutable and outlive their day |
| D3 | `DigestComposition` is `AppendOnlyModel`, `append_only_mutable = frozenset()` | AD-10's "immutable". The `personal` schema's existing `forbid_history_mutation()` needs no argument for a fully immutable table |
| D4 | `ACCOUNT_CONTENT`, and the gap is named | The only category under which AD-10's "most recent composition" promise holds. `PREFERENCE_SIGNALS`'s 12-month window would delete the explanation for an event the user is still looking at. No source states a window; the category is a declaration and the sweep is not built |
| D5 | `numeric(3,2)` for the score, `1..5` check for the bucket | The score is exact decimal because FR-22's boundaries are exact; the bucket cannot have a sixth value |
| D6 | `TextChoices` slot; `JSONField` ordered tag keys; the badge is a type | House style; `EventFit.tags` parallel; the server names the type and the client owns the label and the glyph |
| D7 | `event_kind` stored, and it governs `event_version` and `source_badge` | A personal event is not in `catalog`: it has no source and no catalog version |
| D8 | Two unique constraints; three indexes | One digest per user per day; no duplicate event in a digest; the Detail Screen's lookup and the digest read are both indexed |
| D9 | `local_date` is a `DateField` with the zone beside it; the digest has no `updated_at` | The local day is the user's day, not UTC's; a digest is a fact about a day, not a mutable record |
| D10 | `__str__` names the slot and the bucket only | AD-09/AD-13: the event's content is untrusted source text and must not reach a log line |
| D11 | Reuse `personal.forbid_history_mutation()`; revoke and assert the grants | The function already exists and is exactly right for a fully immutable table; a REVOKE that merely warned must fail the migration |
| D12 | The slot order lives once, as the `TextChoices` declaration order | The index's alphabetical order is not the slot order, and three rows are cheaper to sort in Python than to define the order in two places |
