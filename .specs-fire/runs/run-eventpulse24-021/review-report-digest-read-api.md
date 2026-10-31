# Review report: `digest-read-api`

**Work item**: `digest-read-api`
**Intent**: `pulse-digest-and-trust`
**Mode**: confirm
**Date**: 2026-10-30

---

## The verdict

**Approved.** The endpoint does what the item asked, and it does it by reading persisted
rows and nothing else — which is the whole point of the item.

The review changed two substantive things: the **conflict flag** moved onto the card
(D10), and the **card's display facts became optional** (D5). Both were corrections the
design had to make after the implementation showed it was wrong.

---

## What the review checked

| Property | How | Result |
|---|---|---|
| the read computes nothing | the ranking is monkeypatched to raise; the endpoint is exercised against a composed digest | green |
| the read writes nothing | every table in both schemas is counted before and after | green |
| the query count is bounded | the SQL is recorded on **both** connections | green — six at worst |
| the count does not grow with the card count | one-card and three-card digests cost the same | green |
| the endpoint never imports the models | the `models-personalization` contract | green |
| the endpoint never reaches the Event Fit | the `event-fit-separation` architecture test | green |
| the wall holds | the catalog read is `get_public_events`, a lookup on the `catalog` alias | green |
| the three states are distinct | three separate tests, and one that compares the two empties | green |
| the local date is the user's | a test in a second zone, and one for another day | green |
| the contract is regenerated | `make client`, and the diff is in the commit | green |

---

## The two changes the review made

### 1. The conflict flag is on the card (D10)

**The design said no.** Its argument was good: a conflict is a *live* condition of the
user's own calendar, while the composition is a *fact about a day*. A conflict that
arises at 3pm on a digest composed at 7am did not exist when the digest was composed, and
a conflict resolved at noon is gone — so a flag persisted at 7am would be stale in one
direction or the other. The design's answer was that the flag should come from the
Timeline.

**The review says the flag is on the card, read live.** Three reasons:

1. **FR-58's indicator renders on a card.** The brief says it in as many words: "The
   conflict indicator (FR-58, already built) renders on a card whose event is in a
   `CONFLICT_PAIR`". A card that could not show it would be a card missing one of the
   six trust signals, and "adaptive density never hides a trust signal" is the locked
   rule. The work item's acceptance criteria ask for the flag too.

2. **There is no other source for it.** The design assumed the frontend already holds
   the user's conflict state from the Timeline. It does not: **there is no conflict read
   endpoint.** `list_conflict_pairs` exists as a service, but nothing publishes it. So
   the design's answer pointed at a surface that does not exist, and the card would have
   had no indicator at all.

3. **The staleness argument survives the change.** The flag is read from the **persisted
   `ConflictPair` rows** at request time and is **never computed** (AD-21). It is live in
   the same sense `tz_review_pending` is live — read now, not stored on the composition.
   The composition row is untouched.

**What it cost.** Two queries: the open pairs, and the user's saves of the public cards.
The second is a **bridge** — a pair's sides are the `personal` rows (a `PersonalEvent`'s
id and a `SavedEvent`'s id), while a public card names the *catalog* event's id, so the
save is what connects them. A personal card's `event_id` **is** the `PersonalEvent`'s
id and matches directly.

The bound moved from four to six. It is still a constant, and the save lookup is only
reached once a pair exists to look for — a user with no conflicts pays five.

**What did not change.** The `saved` flag is still **not** a separate field: it travels
as the persisted `saved` Why-this tag. The save lookup exists for the *conflict*, not
for the flag, and recomputing the flag would be recomputing an explanation.

### 2. The card's display facts are optional (D5)

**The design had them required**, with a required `title: str` and a required
`start_time_utc`. The first draft of the implementation papered over the gap with a
sentinel: an epoch instant and an empty title for a card whose catalog event had been
dropped.

**That is a lie about a day.** A card showing an empty title at 1970-01-01 tells the
user something that is not true, and the sentinel would have been invisible in the
schema — every consumer would have had to know that the epoch means "gone".

The display facts are now **optional**: `title`, `canonical_url`, `start_time_utc`,
`end_time_utc` and `start_time_tz` are all `None` when the facts are gone, and
`catalog_event_missing=True` says why. The card still appears, still carries its
bucket, its tags and its badge, and the client marks it rather than hiding it.

**The required fields are now exactly the ones the composition holds** — `event_id`,
`slot`, `event_kind`, `tags`, `bucket` — plus the flags. That is the right shape: AD-10
guarantees the *explanation* is persisted, so it can never be missing; the *display
facts* live elsewhere and may have moved on.

**The same rule was applied to a personal card whose agenda row is gone** — the user may
delete the event after the composition. The same flag marks it.

---

## The three things the review checked and found correct

**The local date really is shared.** `_local_date` was promoted out of
`digest_composition.py` into `apps/personalization/services/digest_dates.py` and both
sides import it. The failure this prevents is silent and nasty: a read that computed a
different day would report `not_composed` on a day that has three cards on it. The
boundary is exactly what the DST test pins, so it is the last place for two rules to
drift.

**The response's `timezone` is the digest's, not the preference's.** The read resolves
*today's* day from the **current** preference's zone — a user who moved may now be on a
different day — but the response reports the **digest row's** stored zone. A mismatch is
then visible rather than silent: the client can see that the digest it was given was
composed in a different zone from the one it would have resolved today.

**The `not_composed` state does not compose.** The read says so; it does not compose
one. AD-11 makes composition worker work, and a read that composes would be a write
from a request path. The `test_the_endpoint_never_writes_a_row` test is what holds that
line, and it counts every table in both schemas.

---

## The one thing the review would still change, and did not

**The digest read duplicates the composition's preference read.** Both
`digest_composition.py` and `digest_read.py` have a `_read_preference` that asks the same
question of the same row.

It is two lines each, and the composition's version carries a comment explaining why it
does not reuse `digest_preferences.py`'s (that module is a command module and its
`_read_preference` is private to it). So the duplication is *already* the established
answer to "how do two modules read the preference?" — and the alternative, a shared
read module for a single-row lookup, would be a module that exists for one function.

**It was left alone, deliberately.** A change here would touch the composition service,
which is not this item's subject, and the two copies cannot disagree: they ask the same
question of the same row with the same ordering. The duplication is recorded rather than
removed, so the next reader knows it was seen.

---

## A note on the test file's `NOW`

The composition service's tests pin `NOW = 2026-11-04`; this file's `NOW` is **the wall
clock**, pinned at import time. The difference is not an inconsistency — it is forced by
the surface. The composition service takes `now` as a parameter, so its tests choose it.
The endpoint resolves `now` itself, so the test has to write the digest for *today's*
local date.

The first run answered `not_composed` for a digest that existed, and the fix was in the
test. Worth recording, because the symptom — a read that cannot find a digest it wrote —
is exactly the failure the shared date helper exists to prevent, and here it was the test
that was wrong rather than the code.

---

## The gate, one more time

```
3730 passed · 99.15% coverage · 19/19 import contracts · domain 100% · no migrations
ruff check clean · ruff format clean · frontend typecheck, lint and format clean
```
