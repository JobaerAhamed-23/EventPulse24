# Design: The eligible-candidate reads, on both sides of the wall

**Work item**: `digest-candidate-reads`
**Intent**: `pulse-digest-and-trust`
**Mode**: confirm
**Date**: 2026-10-30

---

## The shape of the problem

The composition service needs two things it cannot get from one place, because they live
on opposite sides of the AD-3 wall:

- **public candidates** — the catalog events a user may legally be shown;
- **personal candidates** — the user's own events, their saves, and their conflicts.

AD-3 means no query can return both. So this item builds two reads, in two apps, and the
join happens in the application layer — in the composition service, which is a later
work item.

The one thing this item must not do is reach across the wall. `personalization` may not
import `apps.ingestion.models` (contract `models-ingestion`) and may not import
`apps.ingestion.event_fit` (contract `event-fit-separation`). The established way across
is already in the codebase: `personalization` imports a **service** from
`apps.ingestion.services` that already did the catalog query, and receives plain frozen
dataclasses. `saved_events.py` does exactly this for a save.

---

## D1 — A new frozen dataclass, not a widened `PublicEvent`

**Decision**: the candidate read returns a new `PublicEventCandidate`, and `PublicEvent`
is left exactly as it is.

`PublicEvent` is already the public catalog's wire shape: `apps/catalog/schemas.py`
projects it through `EventOut.from_public_event`, and `apps/personalization/schemas.py`
projects it for the save flow. Widening it would change the public catalog's contract to
serve the digest's needs — a coupling of two surfaces with two reasons to change.

The candidate carries **more** than the public event does, and each addition earns its
place:

| Field | Why the candidate needs it and `PublicEvent` does not |
|---|---|
| `venue_country_code` | The city band is "same city, same country, elsewhere" (D4) |
| `source_type` | The Source Badge input (D5) |
| `acquisition_method` | The other Source Badge input — a crawl outranks the type (D5) |
| `source_freshness_ttl_hours` | The staleness bound (D3) |
| `extraction_confidence` | The digest's own eligibility gate, kept visible for the audit trail |
| `tz_inference_confidence` | Likewise |
| `superseded_by_id` | Which event replaced it, for the audit trail |

`PublicEvent`'s fields are a **subset** of the candidate's. That is not duplication: the
two dataclasses answer different questions. The public event answers "what can this
surface show?"; the candidate answers "what may this digest rank, and what may it say
about why?"

**Rejected**: making `PublicEvent` a superset and using it for both. It would be fewer
types, but the public catalog would then carry digest-only fields — a `extraction_confidence`
on a wire shape that no public consumer reads is a field that will drift out of sync with
the one that matters.

**Rejected**: subclassing. A frozen dataclass that inherits another frozen dataclass
inherits its fields *and* its constructor order, and the result is a shape nobody can
predict from either parent.

---

## D2 — The candidate pool is bounded, and the bound is its own constant

**Decision**: `CANDIDATE_POOL_SIZE = 60`, `MAX_CANDIDATE_POOL_SIZE = 200`,
`CANDIDATE_OVERFETCH_FACTOR = 4`.

The work item asks for the pool size to be named, bounded, and argued. The argument:

- The digest has **three slots** (must-know, nearby, serendipity). Filling three slots
  with *distinct* events after scoring needs more than three candidates, because a
  candidate can lose on every dimension — wrong time of day, wrong bucket, a duplicate of
  a higher-scoring event.
- The page size in `catalog_read` (`DEFAULT_PAGE_SIZE = 20`) is a **page** of a paginated
  public list. A candidate pool is not a page: it has no page two, and it is not bounded
  by "one request may not ask for the whole catalog".
- 60 is roughly four times the preview's three cards (`DEFAULT_PREVIEW_SIZE = 3`) and
  three times a digest's slots. It is small enough that one user's read is cheap, and
  large enough that three slots can be filled from a crowded city without the pool
  becoming the ranking's tiebreaker.

The cost argument the work item raises: this read runs **once per user per day**. A pool
that is cheap for one user is not automatically cheap for all of them. 60 rows with
`select_related("venue", "source")` is one indexed query per user per day, and the
`personal_event_user_start_idx` / `event_fit_city_score_idx` indexes are already there to
serve it. The cap of 200 exists so a caller cannot ask for the whole catalog by
accident.

**The SQL fetch is bounded too** (`CANDIDATE_OVERFETCH_FACTOR = 4`). FR-14's staleness
bound is per source, so it cannot be expressed in SQL — those rows are dropped in
Python. Without a `LIMIT`, a catalog whose events are *mostly* stale would hand every
one of them to Python before the first candidate was found, and the read's cost would
depend on the size of the catalog rather than on the size of the pool. The over-fetch
factor buys room for the stale rows: a pool whose events are mostly fresh fills from the
first page.

**The trade is stated, not hidden**: a catalog that is mostly stale may fill the pool
with fewer than `limit` rows, even though fresher events exist further out. The
alternative — fetching the whole catalog to be sure — costs more than the pool is ever
worth.

**A `limit` of zero or less returns nothing.** `max(1, ...)` would quietly turn "no
candidates" into "one candidate", and a caller computing "how many cards can I fill?"
from a limit of zero would be handed a card it did not ask for.

**The pool is ordered by start time, then id** — the same total order `list_public_events`
uses, so the two reads cannot disagree about which event comes first. It is *not* ordered
by score: scoring happens in the composition service, which is the only place that knows
the user's preferences.

---

## D3 — Staleness is 2× the source's TTL, and the multiplier is a named constant

**Decision**: add `DIGEST_STALE_TTL_MULTIPLIER = 2` to `shared/constants.py`, and bound a
candidate by `now - event.last_seen_at > multiplier × source.freshness_ttl_hours`.

FR-14: "an event older than 2× its source's `freshness_ttl_hours` is not surfaced in a
fresh digest." The TTL is per source and defaults to 24 hours, so the default bound is
48 hours.

**Which timestamp**: `Event.last_seen_at`, not `updated_at`. `last_seen_at` is when the
catalog last saw the event at the source; `updated_at` is when the row was written, which
changes when *we* touch it — and a re-save of an unchanged event would reset the clock on
a stale event and keep it alive. `last_seen_at` is the honest reading of "how old is
this".

**The comparison is strict**: an event exactly at the bound is **included**. "Older than
2×" is exclusive at the boundary, and the digest must not flicker an event in and out of
existence on the second. Every other gate in this item is an inclusive lower bound
(`>=`), so this is the one place the direction is worth arguing: at exactly 48 hours the
event is not *older than* 48 hours, so it is eligible.

**Why a new constant and not `STALE_AFTER_CADENCES`**: `STALE_AFTER_CADENCES = 2` is a
multiplier over *ingestion cadences*, which is a different quantity with a different
meaning — a cadence is how often a source is fetched, a TTL is how long its facts are
treated as current. The number is the same by coincidence. AD-8 says a threshold lives
in one shared module; it does not say two different thresholds may share one name. The
new constant sits next to the TTL it multiplies.

**Why not reuse `RANKING_PERSONAL_EVENT_WINDOW` for the personal window**: it already
means exactly what the personal-candidate read needs — 48 hours — and it is already
named for the ranking. A second 48-hour constant for the same window would be two
constants that could disagree about a window FR-5 and FR-19 both name.

---

## D4 — City matching is equality, and an event with no city matches nothing

**Decision**: `venue__city__iexact=city`. Same city, case-insensitively. The candidate
read also returns `venue_country_code`, so the caller can tell "same city" from "same
country" — but it does not *search* the country.

`Venue` has `city` and `country_code` and no coordinates. FR-5's haversine curve is a
named deviation this codebase does not implement; the brief records it. **Do not invent a
centroid table here.** If coordinates arrive later, this read is where they land, and the
band grows from "same city" to "nearby" without a second read.

**An event with no venue, or a venue with no city, matches no city.** The city filter
is a join on `venue__city`, so a null venue produces no match. This is the same call
`event-fit` made: an event it could not place got no row rather than a guessed one. A
digest that showed a cityless event in "nearby" would be claiming a locality it does not
have.

**The city filter is optional.** With no city, the read returns every eligible event in
the catalog — which is what the "serendipity" slot wants when the user has no city yet,
and what the backfilled fallback city would otherwise over-constrain.

---

## D5 — The Source Badge is resolved on the catalog side, in a module of its own

**Decision**: the badge is resolved **on the catalog side**, in the candidate read,
before it crosses. The mapping itself lives in a new module,
`apps/ingestion/services/source_badges.py`.

`preview_read.source_badge_for(source)` takes a `Source` **model instance** — which
`personalization` may not hold. So the candidate read cannot defer the mapping to the
caller.

**Two options, and the second is chosen**:

1. Carry `source_type` and `acquisition_method` and let `personalization` map them.
   That duplicates the mapping table in the app that is *not* allowed to know about
   `Source`, and the two copies would drift.
2. Resolve the badge in the candidate read and carry `source_badge` as a plain string.

**Option 2.** The badge mapping is catalog knowledge — it maps a `Source` to a claim about
how the facts were obtained — so it belongs on the catalog side of the wall. The badge is
one of the four values `DigestComposition.source_badge` accepts (`max_length=32`), and
`preview_read` already produces exactly those four.

**The badge must come from the same read that justified the card.** The work item says
so, and it is right for a reason that is not obvious: a badge resolved by a *second*
query could disagree with the first if the source changed between them. One query, one
badge, one event.

**The badge input is `source_type` plus `acquisition_method`** — a crawled source gets
the crawled badge regardless of its type, because "how the facts were obtained" is what
the ⚠ means. This is `preview_read`'s existing rule, reused rather than restated.

### D5a — The mapping needed its own module, and that is not a detail

`preview_read` imports the Event Fit. `catalog_read` may **not**: `personalization`
imports `catalog_read`, so an Event Fit import there would put the Event Fit inside
`personalization` by another name — the exact substitution AD-10 forbids, one import hop
removed. The import contract cannot catch it (`allow_indirect_imports` is true, because
the point is that `personalization` does not import the Event Fit *directly*), so the
architecture test catches it instead.

The badge mapping was therefore moved to `apps/ingestion/services/source_badges.py`:
a leaf that imports `apps.ingestion.models` for the `Source` choices (legal from
`apps.ingestion.services`, and no heavier than `catalog_read` already is) and nothing
else. Both reads import it; neither imports the other.

**The names are not re-exported from `preview_read`.** One rule, one home: a name
exported from two modules is two homes, and a reader has to know which is current.
`preview_read` was their home before the split; `source_badges` is it now.

---

## D6 — The eligibility gates are the shared constants, applied in SQL

**Decision**: the candidate read filters on:

| Gate | Constant | Direction |
|---|---|---|
| Extraction confidence | `EXTRACTION_CONFIDENCE_PUBLISH` (0.70) | `>=` |
| TZ inference confidence | `TZ_INFERENCE_CONFIDENCE_DIGEST` (0.70) | `>=` |
| Publication status | `Event.PublicationStatus.PUBLISHED` | equality |
| Superseded | `Event.Status.SUPERSEDED` | excluded |
| Start time | `now` | `>=` |

**Every threshold is reused, never restated** (AD-8). The two confidence gates are
`Decimal`, and the model fields are `DecimalField(max_digits=3, decimal_places=2)`, so the
comparison happens in the database without a float ever appearing — `domain/confidence.py`
is explicit that "a float 0.7 is slightly below Decimal 0.70 and would land an event in
the wrong band."

**Both bounds are inclusive.** "An event one hundredth below the confidence gate is
excluded, one at it is included" — so `>=`, not `>`.

**A `tz_review_pending` event is eligible.** AD-6: "an Event with `tz_inference_confidence`
< 0.7 is **not eligible for any Pulse Digest** until editorial review completes." Between
0.70 and 0.90 the event is published *with* `tz_review_pending` set — published, eligible,
and its time is approximated. The candidate carries the flag so the frontend can mark it.
Excluding it would contradict AD-6 and would silently drop every event whose timezone was
inferred but not certain — which is most of them.

**`superseded_by` is not filtered on separately.** The database holds the supersession
consistent — `event_superseded_consistent_ck` says a superseded Event names its
replacement and a live one names none — so a row with `status != superseded` and a
`superseded_by` pointer **cannot exist**. A second filter for a state the database
forbids would be a second thing to keep true, and it could only ever be true in the same
rows the status filter already admits.

(The first draft of this design filtered on both, on the reasoning that "a row with the
status updated but the pointer not yet cleared would slip through". The constraint says
otherwise, and the filter was removed rather than kept as a false comfort.)

**A cancelled or postponed event is a candidate.** `status` is filtered for `superseded`
and nothing else, so `cancelled` and `postponed` events reach the pool. That is the same
set the public catalog lists — the two reads must not disagree about what exists — and
what happens to a cancelled event is the composition service's call. A cancelled event
is still a real event with a real place in the user's city; dropping it here would hide
the cancellation rather than report it, and the card can mark it. **This is stated here
rather than left implicit**, because a digest offering a cancelled event is the kind of
thing a user notices.

**The confidences are carried as `Decimal`, not as strings.** `shared/constants.py` is
explicit that "a float 0.8 is not exactly 4/5, and a boundary test on a float would be a
lie". A string is exact but un-typable and un-comparable; the model's own type is
`Decimal`, and the wire layer can serialise it.

---

## D7 — The public read lives in `catalog_read.py`, and it is a new function

**Decision**: `list_public_candidates(...)` in `apps/ingestion/services/catalog_read.py`.

The work item names the file, and the file's own docstring says it is "the published
read interface over the catalog" — the only legal path for another app to see an `Event`.
A second module in `apps.ingestion.services` would be legal under the import contracts,
but it would split "the published read interface" into two, and a caller would then have
to know which of the two to reach for.

**It is a new function, not a widened `list_public_events`.** The two answer different
questions and have different gates: the public list shows what a human may browse
(which does *not* apply the digest's confidence gates), while the candidate pool shows
what a digest may rank (which does). Widening `list_public_events` with optional gate
flags would give the public catalog a parameter that changes what a public surface
returns — and the preview's coverage rule depends on `list_public_events`'s meaning
staying put.

---

## D8 — The personal reads live in a new `personalization` service

**Decision**: a new `apps/personalization/services/digest_candidates.py` holding three
reads.

**Why a new module and not an extension of `personal_events.py` / `saved_events.py`**: those
two modules are *command* modules — they create, update and delete. They hold their own
audit writes, their own transaction boundaries and their own error types. A *read* for
composition is a different kind of thing: no writes, no audit, no `Actor`. Putting it in
either module would either mix reads into a command module or scatter composition's
reads across three files.

**The three reads**:

| Read | Returns | Source |
|---|---|---|
| `list_personal_candidates` | The user's personal events starting within 48 hours | `PersonalEvent` |
| `list_saved_candidates` | The user's saved events, with the public facts | `SavedEvent` + `catalog_read` |
| `list_conflict_pairs` | The user's open conflict pairs | `ConflictPair` |

### D8a — The personal window

**Decision**: `now <= start_utc <= now + RANKING_PERSONAL_EVENT_WINDOW`, inclusive at
both ends.

The window is **inclusive at the far end**: an event starting exactly 48 hours from now
is eligible. FR-5's "within the next 48 hours" includes the boundary, and the ranking
boost it carries (`RANKING_PERSONAL_EVENT_BOOST`) applies at exactly the same boundary —
so the candidate set and the boost cannot disagree about which events are "soon".

**The near end is `now`**, inclusive. An event that started a second ago is still
happening, and a digest composed at 09:00 should be able to say "you're going to that
now". An event that started an hour ago is *not* a candidate — the window is "starting
within the next 48 hours", not "running".

**Imported calendar events are included.** `PersonalEvent.source` is `user_created` or
`calendar_import`, and both are the user's own events — the digest's Slot 1 is about the
user's agenda, not about who typed the row. An imported event that the user has not
edited is still their event. (`user_modified` does not affect eligibility either; it
decides who owns the row during a re-sync, which is a sync concern.)

### D8b — Saved events read their own snapshot

**Decision**: the saved-candidate read reads `SavedEvent`'s snapshot columns and resolves
the *display* facts through `catalog_read.get_public_events` — **one batched lookup**,
never a join.

AD-21 is explicit that the Timeline and conflict detection read the snapshot and never
join `catalog`. The snapshot is what the user's calendar shows; the catalog's current time
may have moved, and AD-17's propagation is what reconciles them. A digest that showed
the catalog's *current* time for a saved event would show a time the user's own calendar
does not show — the two surfaces would disagree about the same event.

**A saved event whose catalog event has gone is still a candidate.** The save is real;
the snapshot is what the user has. It is returned with whatever the catalog still says,
and if the catalog no longer has it, the read returns it with the catalog facts absent
rather than dropping it — a user whose save would silently vanish from their digest
because the source dropped the event would have no way to know.

**`event_id` is the lookup key, by value.** `SavedEvent.event_id` holds the catalog
Event's id; the read calls `get_public_events(event_ids=...)`. That is a *lookup*, not a
join — one query against the `catalog` alias, and the ORM wall holds because no queryset
ever spans the two aliases.

**The lookup is batched.** The read runs once per user per day, so a user with five
saves would otherwise cost five round-trips to the catalog — five round-trips times every
user. `get_public_events` is the same query with an `IN` clause instead of five queries
with an `=`.

**The catalog lookup passes no `now`.** `get_public_event`'s own contract says `now=None`
skips the start-time bound, and that "a record of something the user already saved has
to stay readable after the event has started". The user's own calendar does not un-save an
event because it began. The caller's bound — on the snapshot — is the one that applies.

**The saved pool is bounded** (`MAX_SAVED_CANDIDATES = 60`), for the same reason the
public pool is: a user with thousands of saves must not cost a thousands-of-rows read on
a job that runs once per day.

**The 48-hour window does not apply to saves.** `RANKING_PERSONAL_EVENT_WINDOW` is
FR-5's *Slot 1* window — the window in which the user's own agenda is the must-know
card. A save is not the user's agenda; it is a record of a public event they took an
interest in, and a save three weeks out is still a save three weeks out. Applying the
agenda window to saves would drop a user's saves of long-planned events, and the digest's
own slots have no reason to. The saved read's bound is "has not started yet".

### D8c — Conflict state comes from the persisted rows

**Decision**: `list_conflict_pairs` reads `ConflictPair` rows with
`status == ACTIVE`. It never calls `domain.conflict.conflicts`.

AD-21: conflict detection happens "never at render", and `domain/conflict.py` is the one
overlap function. Computing an overlap here would produce a *different* answer from the
persisted pair whenever the two disagreed — and they would disagree the moment an event
moved without the propagation running. The Pulse Card indicator, the Timeline block
indicator and `/conflicts` all read the same rows; this read joins them.

**Only `ACTIVE` pairs.** A `RESOLVED` pair is answered; a `CLEARED_BY_STATE_CHANGE` pair
is over because a side went away. Neither is an open conflict, and showing either would
put a conflict prompt on a card for a conflict the user has already settled.

---

## D9 — Conflict state on a candidate, and the read's shape

**Decision**: the personal-candidate and saved-candidate reads return the candidate's
*own* facts plus a `conflict_ids: tuple[UUID, ...]`.

**Why not a boolean**: "is this event in conflict" is not a fact about the event — it is
a fact about the *pair*. Two candidates can be in conflict with each other, and the
frontend's Pulse Card indicator needs to know *which* conflict it is showing, so the
user can answer the prompt. A `has_conflict: bool` would lose the pair's id, and the
pair's id is what `/conflicts` and the resolution command take.

**Why the ids rather than a join**: the conflict pairs are read from the `personal`
alias and the candidates from the `personal` alias too — but they are still two queries,
because a conflict pair names two sides and the candidate is one side. The read
collects the pairs for the user once, then attaches the relevant pair ids to each
candidate. One extra query per user per day.

**A candidate with no conflict gets an empty tuple**, not `None`. "No conflict" and "we
did not look" must not be the same value.

---

## D10 — `now` is an explicit parameter, and the reads are pure reads

**Decision**: every read takes `now: datetime` as a keyword-only argument, and none of
them opens a transaction.

`now` is explicit throughout `catalog_read.py` and throughout `personalization`'s
services, and the reason is the same: no time-freezing library, and each boundary is
testable at the exact second. A digest composed once per day per user is a job that must
be reproducible — "the same inputs produce the same digest" is only true if the inputs
include the clock.

**No transaction.** A read that opens a transaction on `personal` and then calls into
`catalog` would span the wall. The reads are separate queries against separate aliases,
and the composition service owns the order.

---

## D11 — The alias separation is asserted, not assumed

**Decision**: a test asserts the public read runs on `catalog` and the personal reads on
`default`, and that no code path joins the two.

The ORM already raises `ValueError: Subqueries aren't allowed across different
databases` on a cross-alias subquery, and `tests/wall/test_orm_wall.py` proves it. But
that is the ORM's protection, not this item's. This item's protection is that **no
queryset in these reads touches two aliases at once**: the public read's queryset is
`.using(CATALOG)` and involves only `Event`; the personal reads' querysets are
`.using(PERSONAL)` and involve only `PersonalEvent`, `SavedEvent` and `ConflictPair`.

**The test asserts the aliases by capturing the executed queries.** `django_assert_num_queries`
does not say *which* database; `CaptureQueriesContext` does not either. The test uses
`django.db.connection.queries` against each alias and asserts the public read touched
`catalog` and not `default`, and the personal read touched `default` and not `catalog`.

---

## D12 — The event-fit wall is not weakened, and the coverage rule is not reused here

**Decision**: the candidate read does not use the Event Fit, and does not import
`apps.ingestion.event_fit` in any form.

`event-fit-separation` is a **package** contract for a reason the contract's own comment
records: a name-only wall was bypassed by a two-line re-export file. So this item does
not add a re-export, does not add an `event_fit` module to `apps.ingestion.services`, and
does not route the badge through the fit read.

The badge mapping is *not* the Event Fit — it is `preview_read`'s source→badge table,
which lives in `apps.ingestion.services` and is already importable. The candidate read
therefore borrows **that** and not the fit.

**`list_supported_cities()` is not reused here either.** The coverage rule asks "can the
preview serve this city?" — it requires a *current Event Fit*. The candidate read asks
"what may this digest rank?" — a different question, and the answer does not depend on
whether a fit exists. Reusing the coverage rule would mean a city with events but no
fits is a city with no candidates, which is not true.

**`make lint-imports` passes unchanged** and
`tests/architecture/test_event_fit_separation.py` stays green with no edit.

---

## D13 — The reads return plain frozen dataclasses

**Decision**: every read returns frozen dataclasses, never model instances.

This is the `catalog_read` discipline, and it is the mechanism by which the wall holds
"without either side knowing the other's models". The candidate read returns
`PublicEventCandidate`; the personal reads return `PersonalEventCandidate`,
`SavedEventCandidate` and `ConflictPairSnapshot`.

**The dataclasses are new, not the existing snapshots.** `PersonalEventSnapshot` and
`SavedEventSnapshot` exist and are correct — but they are the *Timeline's* shapes, and
this item's candidates need the digest's extra facts (the source of a personal event, the
badge of a saved event, the conflict ids). Reusing the Timeline's dataclass and adding
digest-only fields to it would make the Timeline's shape carry fields the Timeline never
reads.

---

## D14 — No logs, and no audit rows

**Decision**: the reads write nothing and log nothing.

A read has no actor and no decision, so there is nothing to audit — the audit table
records *decisions*, and reading a candidate list is not one. The city is already a
stored, audited fact; the reads do not add a second copy of it.

**Nothing is logged** (AD-13). The candidates carry a user's event names and a city's
events — that is the user's agenda and their location, and neither belongs in a log line.

---

## D15 — What this item does not do

- **It does not compose.** No ranking, no slotting, no scoring — that is
  `digest-composition-service`.
- **It does not schedule.** No job, no cron — that is `digest-scheduling`.
- **It does not read the Event Fit.** The digest's ranking may want the fit; the
  *personalization* app may not have it. That is a tension the composition service will
  have to resolve through a published interface; this item does not resolve it.
- **It does not expose an endpoint.** The candidates are read by a worker, not a user.

---

## The decision table

| # | Decision |
|---|---|
| D1 | A new `PublicEventCandidate`; `PublicEvent` is left alone |
| D2 | `CANDIDATE_POOL_SIZE = 60`, `MAX_CANDIDATE_POOL_SIZE = 200`, `CANDIDATE_OVERFETCH_FACTOR = 4`; a limit of zero returns nothing |
| D3 | `DIGEST_STALE_TTL_MULTIPLIER = 2`, bounded on `Event.last_seen_at`, inclusive at the boundary |
| D4 | City matching is `iexact` equality; an event with no city matches nothing; no centroid table |
| D5 | The Source Badge is resolved on the catalog side and carried as a string |
| D5a | The badge mapping lives in `source_badges`, a leaf that imports no Event Fit; the names are not re-exported from `preview_read` |
| D6 | Every gate is the shared constant, applied in SQL, inclusive at the boundary; `superseded_by` is *not* filtered separately (the database forbids that state); cancelled and postponed events are candidates; the confidences are `Decimal` |
| D7 | `list_public_candidates` in `catalog_read.py`, a new function rather than a widened one |
| D8 | A new `apps/personalization/services/digest_candidates.py` with three reads; the personal window is `RANKING_PERSONAL_EVENT_WINDOW`, inclusive at both ends |
| D8b | Saved events read their own snapshot; the catalog's facts come from one batched `get_public_events` lookup with no `now`; the saved pool is bounded at 60 and the 48-hour window does not apply to it |
| D8c | Conflict state comes from persisted `ConflictPair` rows, never computed at render |
| D9 | Candidates carry `conflict_ids`, not a boolean |
| D10 | `now` is explicit; the reads open no transaction |
| D11 | The alias separation is asserted by a test, on the table names |
| D12 | The Event Fit is not used, imported or re-exported; the coverage rule is not reused here |
| D13 | Plain frozen dataclasses; the Timeline's snapshots are not widened |
| D14 | No audit rows, no logs |
| D15 | No composition, no scheduling, no endpoint, no Event Fit |

---

## What the code review changed

The review found twelve things worth fixing, and six of them were changes to *this
document* rather than to the code — which is the point of writing the reasoning down
before the code. The design changed where the code proved the design wrong:

| Was | Now | Why |
|---|---|---|
| D6: filter on `status != superseded` **and** `superseded_by IS NULL` | D6: filter on the status alone | `event_superseded_consistent_ck` says a live event names no replacement, so the second filter could only ever be true in rows the first already admits |
| D2: the limit bounds the pool | D2: the limit bounds the pool **and** the SQL fetch, by an over-fetch factor | The staleness filter runs in Python, so without a `LIMIT` a mostly-stale catalog would hand every row over before the first candidate was found |
| D2: `max(1, ...)` | D2: a limit of zero returns nothing | "No candidates" must not silently become "one candidate" |
| D8b: one `get_public_event` per save | D8b: one batched `get_public_events` | Five saves would cost five round-trips to the catalog, times every user |
| D8: the 48-hour window applies to the personal *and* saved reads | D8b: it applies to the personal read only | The window is FR-5's Slot 1 *agenda* window; a save three weeks out is still a save three weeks out |
| D1: the confidences are carried as strings | D6: they are carried as `Decimal` | A string is exact but un-typable; the model's own type is `Decimal` |

The review also asked about three things the design had not answered at all, and they
are now stated rather than left implicit: that a **cancelled** event is a candidate (D6),
that `now` **must be timezone-aware** (D6), and that the badge mapping needed its own
module to keep the Event Fit out of `catalog_read`'s import graph (D5a).
